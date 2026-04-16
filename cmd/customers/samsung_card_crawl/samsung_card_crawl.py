"""
삼성카드 크롤링 스크립트 v3

동작 원리:
1. Playwright → __NUXT__.data[0] 에서 wcms + bannerList 추출
2. WCMS JSON → 카드 기본정보 + 혜택 탭 URL
3. 혜택 탭 HTML → card_benefit.csv
4. 연회비/유의사항 HTML → card_notices.csv
5. bannerList → 이벤트 URL → card_events.csv

출력 파일:
    card_info.csv    → 카드 기본정보
    card_benefit.csv → 혜택 + 할인기준 (row_type으로 구분)
    card_notices.csv → 유의사항/이용안내/금융고지
    card_events.csv  → 이벤트/프로모션 (섹션별 1행)
"""

import asyncio, csv, re, os, json
import aiohttp
from datetime import datetime
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# ── 설정 ──────────────────────────────────────────────────────
CARD_LIST = [
    "AAP1731",
    "ABP1689",
    "ABP1384",
    "ABP1383",
    "AAP1483",
    "AAP1452",
]
BASE_URL     = "https://www.samsungcard.com/home/card/cardinfo/PGHPPCCCardCardinfoDetails001?code="
CDN_BASE     = "https://static11.samsungcard.com"
CARD_COMPANY = "삼성카드"

# ── CSV 컬럼 (CSV 파일 컬럼명과 통일) ─────────────────────────
INFO_FIELDS = [
    "card_id", "card_company", "card_name", "card_type",
    "payment_network", "is_overseas", "has_transit",
    "annual_fee_domestic", "annual_fee_domestic_premium",
    "annual_fee_overseas", "annual_fee_overseas_premium",
    "annual_fee_note",
    "base_spending_requirement", "extra_spending_requirement",
    "main_benefit", "image_url",
    "detail_page_url", "crawled_at",
]

BENEFIT_FIELDS = [
    "benefit_id",
    "card_id",
    "row_type",
    "benefit_group",
    "benefit_title",
    "benefit_summary",
    "category_id",
    "crawled_category",
    "payment_method",
    "region",
    "benefit_type",
    "benefit_value",
    "benefit_unit",
    "target_merchants",
    "excluded_merchants",
    "performance_condition",
    "max_limit",
    "raw_text",
    "crawled_at",
]

NOTICE_FIELDS = [
    "notice_id",
    "card_id",
    "category",
    "sub_category",
    "content",
    "crawled_at",
]

EVENT_FIELDS = [
    "card_id", "card_company", "card_name",
    "source_event_id", "event_title", "event_url",
    "event_start_date", "event_end_date",
    "benefit_type", "section", "content",
    "crawled_at",
]

# ── 업종 카테고리 매핑 (DB category 기준, 21개) ───────────────
# category_name: DB에 저장되는 최종 카테고리명
CATEGORY_MAP = [
    ("온라인쇼핑",            ["온라인쇼핑", "지마켓", "쿠팡", "11번가", "옥션", "인터파크"]),
    ("패션/뷰티",             ["패션", "뷰티", "올리브영", "무신사", "화장품"]),
    ("슈퍼마켓/생활잡화",     ["마트", "슈퍼마켓", "이마트", "홈플러스", "코스트코", "다이소"]),
    ("백화점/아울렛/면세점",  ["백화점", "아울렛", "면세점", "신세계", "갤러리아"]),
    ("대중교통/택시",          ["교통", "버스", "지하철", "택시", "대중교통", "기차", "KTX"]),
    ("자동차/주유",            ["주유", "자동차", "정비", "하이패스", "고속도로"]),
    ("반려동물",               ["반려동물", "펫", "동물병원"]),
    ("구독/스트리밍",          ["스트리밍", "넷플릭스", "웨이브", "티빙", "왓챠", "멜론", "FLO"]),
    ("레저/스포츠",            ["레저", "스포츠", "골프", "피트니스", "헬스", "경기관람"]),
    ("페이/간편결제",          ["간편결제", "삼성페이", "네이버페이", "카카오페이", "PAYCO", "온라인 간편결제"]),
    ("문화/엔터",              ["영화", "놀이공원", "공연", "CGV", "메가박스"]),
    # 생활비: 통신/보험/공과금/렌탈/자동납부 통합 (DB category 12번)
    ("생활비",                 ["이동통신", "통신", "SKT", "KT", "LG U+", "알뜰폰",
                                "보험", "생명보험",
                                "공과금", "전기요금", "가스요금", "국민연금", "건강보험",
                                "렌탈", "자동납부", "정기결제"]),
    ("편의점",                 ["편의점", "GS25", "CU", "세븐일레븐"]),
    ("커피제과/카페/베이커리", ["커피전문점", "카페", "스타벅스", "이디야", "커피빈", "투썸", "블루보틀", "뚜레쥬르", "파리바게뜨"]),
    ("배달",                   ["배달앱", "배달의민족", "요기요", "쿠팡이츠"]),
    ("외식",                   ["델리", "외식", "맥도날드", "버거킹", "써브웨이", "쉐이크쉑", "던킨", "배스킨"]),
    ("여행/숙박",              ["여행", "숙박", "호텔", "렌터카", "야놀자"]),
    ("항공",                   ["항공", "대한항공", "아시아나", "공항라운지", "마일리지"]),
    ("해외",                   ["해외", "해외 가맹점", "해외겸용", "직구"]),
    ("교육/육아",              ["교육", "학원", "서점", "육아", "학교납입금"]),
    ("의료",                   ["의료", "병원", "약국", "치과"]),
]

ON_OFF_MAP = {
    "커피제과/카페/베이커리": "Both", "배달": "Online", "외식": "Both",
    "대중교통/택시": "Offline", "생활비": "Online", "구독/스트리밍": "Online",
    "페이/간편결제": "Online", "해외": "Both", "온라인쇼핑": "Online",
    "편의점": "Offline", "자동차/주유": "Offline", "여행/숙박": "Both",
    "항공": "Both", "의료": "Both",
    "패션/뷰티": "Both", "슈퍼마켓/생활잡화": "Both",
    "백화점/아울렛/면세점": "Offline", "레저/스포츠": "Both",
    "문화/엔터": "Both", "교육/육아": "Both", "반려동물": "Both",
}

LOCATION_MAP = {k: "해외" if k == "해외" else "국내" for k in dict(ON_OFF_MAP)}

# ── benefit_summary 노이즈 필터 ───────────────────────────────
import re as _re_summary

_SUMMARY_NOISE = [
    r'청구금액|전신환매도율|브랜드사수수료|해외이용수수료|해외원화결제|DCC',
    r'^(기본|제휴|총)\s*연회비|^합계\s*[\d,]|^(본인|가족)\s.*(연회비|겸용|전용)',
    r'연회비는 카드 발급|연회비 반환|카드 중도 해지|재발급.*갱신',
    r'발급대상\s*:\s*만|후불교통 이용금액 청구방식',
    r'^무이자할부|^법인공용카드|^고용.산재보험',
    r'국세.지방세|전월 이용금액이란|전월 이용금액 산정',
    r'삼성카드의 다른.*(할인|혜택)|결제일할인금액은 다음 달',
    r'결제 취소건|포인트가 적립된 결제건이 취소',
    r'적립된 빅포인트는 보너스|빅포인트의 유효기간',
    r'2014년 4월|2014\.4\.30',
    r'삼성카드 가맹점 업종 분류|삼성카드는 아래 항목',
    r'이마트 에브리데이 상품공급점|해당 가맹점이 실제 등록한',
    r'이동통신의 경우.*알뜰폰|스트리밍은 간편결제건',
    r'삼성카드와 구매캐시백포인트',
    r'빅포인트 적립 제외 대상.*(법인|신규)',
    r'홈페이지.*(확인|바로가기)|바로가기\s*:\s*www\.',
    r'심의필 제\s*\d|금융상품 이용 전 상품설명서',
    r'국제 브랜드사별|삼성카드 선택 서비스는 국제',
    r'^지원(대상|금액|기간|범위|내용)\s*[:\:]',   # 콜론 앞 공백 포함 ("지원대상 :" 대응)
    r'^(이용|신청)방법\s*[①:]',
    r'^바우처 이용 시점|^국가바우처는 정부|^국가바우처 관련 자세',
    r'출산\(예정\)일.*전부터|기준 중위 소득.*임산부',  # 임산부 바우처 지원대상 설명문
    r'^알아두면 유용한 정보',
    r'^카드플레이트에 인증마크|^카드 플레이트에 위의 아이콘',
    r'^취향 저격|^주요 혜택 체크',
    r'^[①②③④⑤]\s(?!.*\d+\s*(%|원|포인트|마일))|^[QA]\.\s',  # 수치 없는 원문자 행만 제거
    r'^이 카드는.*할인이 적용된',
    r'^삼성 iD 카드 진짜|^뉴블루 디자인$|^모던 디자인$|^펑키 디자인$',
    r'에 반영됩니다[\.\s]*$|에서 확인 바랍니다[\.\s]*$|확인하시기 바랍니다$',
    r'이용 제한 가능\)$|에 청구됩니다$|신용상 불이익',
    r'^보너스클럽 이용|^일부 임대매장',
    r'^자세한 내용은|^삼성카드의 다른 혜택과 중복',
    r'^발급월\+[12]개월까지는',
    r'^해당 카드 이용 시 카드 혜택 외|^할인이 적용된 이용금액에 대해서는',
    r'^무이자할부 이용 시 할인 혜택|^트렌디숍.*오프라인 매장',
    r'^스타벅스의 경우 사이렌 오더|^정상적으로 삼성카드에 접수된',
    r'^실제 카드 이용일이 아닌|^옵션은 삼성카드 홈페이지',
    r'^변경 신청 다음 달 1일|^특별 적립은.*기본.*추가.*형태',
    r'^통합 월 적립한도는 \d|^전월 이용금액에 관계없이 제공$',
    r'^백화점 내 일부 임대매장|^예\s*:\s*[\d,]+원 결제 시',
    r'^해외형의 경우 해외 온라인|^해외형은 해외겸용카드에 한해',
    r'^선택한 옵션에 대해서만|^적립 혜택은 카드 승인일',
    r'^결제건당 삼성카드 접수금액|^결제금액을 1,000원으로 나눈',
    r'^적립된 마일리지의 사용방법|^자세한 내용은 항공사',
    r'^적립된 마일리지는 기존 스카이패스|^결제건 접수 후 마일리지 적립까지',
    r'(마일리지 적립\s*){2,}|(포인트 적립\s*){2,}|(할인\s*){3,}',  # "마일리지 적립 마일리지 적립" 등 중복 반복 문구
    r'^해외 이용 시 별도의 수수료|^해외겸용카드에 한해 제공',
    r'^캐시백금액은 매출전표|^캐시백 혜택 및 전월 이용금액 산정',
    r'^탈회 후 카드를 재발급|^아래의 경우.*발급월\+\d개월',
    r'^카드당 통합 일\s*\d회|^통합 일\s*\d회',
    r'^연 기준\s*:\s*1\.1~12\.31',
    r'^현장 결제.*공식 홈페이지|^예매 대행 사이트',
    r'^중국공상은행|^캐시백 제외 대상 중.*일부 가맹점',
    r'^삼성카드 앱을 통해 매월 옵션',
    r'^해외에서 카드 결제 시.*IC|^해외에서 카드 결제 시.*현지 통화',
    r'^본인 카드와 가족카드',
    r'^음식점\s*:\s*한식|^(스타벅스|G마켓|쿠팡|편의점|올리브영).*,',
    r'^(에버랜드|롯데월드|서울랜드|캐리비안|중흥골드)',
    r'^직전 3개월 월평균',
    r'^(백화점·프리미엄|할인점은 온라인|생활잡화는 오프라인|신선식품 배송은)',
    r'^(의료·산후조리원은|학원은 오프라인|온라인서점은|어린이집·유치원은)',
    r'^신세계백화점 할인쿠폰.*자세한 내용은',
    r'단말기에 카드 터치만으로|카드를 삽입하거나',
    r'^(포인트|캐시백|할인).*(국가바우처|어린이집|유치원|건강보험|국민연금)',
    r'^일반 가맹점$|^한도조건$|^실적조건$',
    r'^아멕스 PLATINUM 등급 서비스 안내장 다운로드$',
    r'^해외형 (업종|적립처|통합):|^국내형 (업종|적립처):',
    r'^주유 업종:|^커피 업종:|^편의점 업종:|^택시 업종:',
    r'^해외 : 해외 가맹점',
    r'^빅포인트 적립 제외 대상$',
    r'매출취소전표 접수월|접수일의 우리은행|승인일의 우리은행',
    r'대중교통.*이동통신.*자동납부 결제건',
    r'^3%/10% 할인 받은|^이 카드는 3%',
    r'커피전문점, 배달앱, 델리 영역 중 매달',
    r'버스, 지하철, 택시 이용건과 이동통신',
    r'온라인에서도, 해외에서도 월 최대',
    r'커피전문점·배달앱·델리 영역 중 월 이용금액이 가장',
    r'온라인 간편결제·해외 3%·1% 할인 혜택과 중복',
    r'^전월 이용금액 30만원 미만 시 또는 월 할인한도',
    # ── 추가 노이즈 패턴 ──────────────────────────────────────
    # 가맹점/업종 목록형 (업종명:설명 형태)
    r'^(음식점|주유|할인점|커피|편의점|택시|백화점|일반 가맹점)\s*[:\|]',
    r'^(의료|학원|학습지|온라인서점|어린이집|유치원|산후조리원)\s*[:\|]',
    r'^(국공립·사립|입시/보습|병·의원)',
    # 제외 대상 덩어리 텍스트
    r'국가바우처 이용건.*기프트/선불카드',
    r'기프트/선불카드.*구매 및 충전.*상품권',
    r'^빅포인트 적립 제외 대상',
    r'삼성카드와 구매캐시백포인트 제공 계약',
    r'페이백서비스 등의 이용금액',
    r'중국공상은행 삼성체크카드',
    r'해당 카드는 택시 이용 시에도 마일리지 적립',
    # 이용조건/제공조건 텍스트
    r'^30만원 이상 구간\d',
    r'구간\d:\s*\d',
    r'^전월 이용금액 30만원 이상 시 제공$',
    r'발급월\+\d개월까지는.*무실적',
    r'^삼성카드 신규 회원$',
    r'^직전 3개월 동안 무실적',
    # 카드이용TIP / 설명문
    r'라이프스타일에 따른 옵션 패키지|옵션 패키지 선택 시 업종별',
    r'^자세한 내용은.*옵션 패키지',
    r'삼성카드 앱을 통해 매월 옵션 패키지 변경',
    r'^변경 신청 다음 달 1일에 자동 반영$',
    r'^한도조건$|^실적조건$',
    r'^할인\s*:\s*|^적립\s*:\s*없음$',
    r'라이프스타일에 따른|취향 저격',
    r'^카드 플레이트에 위의 아이콘|컨택리스 아이콘이 있는 가맹점',
    r'카드를 삽입하거나 긁을 필요 없이',
    r'국내와 해외에서 어디서든 안전하고 편리하게',
    # 바우처 상세 내용
    r'^지원대상\s*:|^지원금액\s*:|^지원기간\s*:|^지원범위\s*:|^지원내용\s*:',
    r'^이용방법\s*:|^신청방법\s*:',
    r'^바우처 이용 시점|^국가바우처는 정부|^국가바우처 관련',
    # 포인트 계산 예시
    r'^예\s*:\s*[\d,]+원 결제 시',
    r'마일리지 적립\(기본.*추가.*\)',
    # 기타
    r'^매년 카드 최초 발급월 기준으로 이용금액이',
    r'^연간 이용금액은 본인이 발급받은',
    r'^캐시백은 결제한 다음 달|^캐시백 혜택 및',
]


def _is_benefit_summary_noise(text: str) -> bool:
    """benefit_summary에서 제거할 노이즈 텍스트 판별"""
    t = text.strip()
    for p in _SUMMARY_NOISE:
        if _re_summary.search(p, t):
            return True
    return False

# ── 대상점 줄글 필터 ──────────────────────────────────────────
# "가맹점/서비스명 + 수치(숫자%) + 혜택유형" 구조가 있어야 유효한 행으로 판단
_BENEFIT_VALUE_RE = re.compile(
    r"(\d+(\.\d+)?\s*(%|원|포인트|마일|배))"  # 숫자+단위 필수
)
_BENEFIT_TYPE_RE = re.compile(
    r"(할인|캐시백|적립|포인트|마일리지|면제|제공|무료|혜택|서비스)"
)
# 줄글 판별: 아래 패턴이 있으면 줄글로 간주
_PROSE_RE = re.compile(
    r"(의\s경우|경우에|해당하며|따라서|경우는|단,\s|단\s|주의|안내|참고|"
    r"이용\s*시\s*[가-힣]|결제\s*시\s*[가-힣]|적용\s*되[지며]|"
    r"산정\s*기준|이용금액이란|이용금액\s*산정|청구\s*기준|"
    r"제공\s*됩니다|적립\s*됩니다|할인\s*됩니다|"
    r"[가-힣]{2,}\s*(이|가|을|를|은|는|에서|으로|에)\s[가-힣])",
    re.IGNORECASE,
)

def _is_structured_benefit(text: str) -> bool:
    """
    '가맹점/서비스명 + 수치 + 혜택유형' 구조를 가진 유효한 혜택 텍스트인지 판별.
    - 수치(숫자+단위)가 없으면 False
    - 줄글 패턴이 감지되면 False
    - 수치 + 혜택유형이 모두 있으면 True
    """
    t = text.strip()
    if not t:
        return False
    # 줄글 패턴이 있으면 구조 텍스트가 아님
    if _PROSE_RE.search(t):
        return False
    # 수치가 있어야 함
    if not _BENEFIT_VALUE_RE.search(t):
        return False
    # 혜택유형 키워드가 있어야 함 (또는 % 자체가 할인 의미를 내포)
    if "%" in t:
        return True
    if _BENEFIT_TYPE_RE.search(t):
        return True
    return False

# ── 제외가맹점 노이즈 필터 ────────────────────────────────────
# 아래 항목은 이용 제외 조건(금융/정책/수수료)이지 가맹점명이 아니므로 제거
_EXCLUDED_NOISE_PATTERNS = [
    r'^법인공용카드',
    r'^무이자할부',
    r'^다이어트할부',
    r'삼성카드\s*할인이\s*적용된\s*일시불',
    r'^고용[./]?산재보험|고용.산재보험',
    r'^국세[./]?지방세|국세.지방세',
    r'^공과금',
    r'^대학\s*등록금',
    r'^대중교통',
    r'^택시',
    r'^고속버스',
    r'^고속도로\s*통행요금',
    r'^모바일\s*티머니',
    r'^선불카드\s*충전',
    r'^이마트\s*이클럽',
    r'^문자알림서비스',
    r'^스마트오토서비스',
    r'^기프트.선불카드',
    r'^상품권\s*구매',
    r'^단기카드대출|^장기카드대출|^카드론|^현금서비스',
    r'^연체료|^연회비',
    r'^할부수수료',
]
_re_excl = re.compile("|".join(_EXCLUDED_NOISE_PATTERNS), re.IGNORECASE)

def _is_excluded_noise(text: str) -> bool:
    """제외가맹점 항목에서 가맹점명이 아닌 노이즈 텍스트 판별"""
    return bool(_re_excl.search(text.strip()))

def _filter_excluded_merchants(texts: list) -> str:
    """
    제외 항목 리스트에서 노이즈(금융조건/정책)를 걸러내고
    실제 가맹점명만 ' / '로 연결해 반환
    """
    filtered = [t for t in texts if not _is_excluded_noise(t)]
    return " / ".join(filtered)

# ── target_merchants 전용 필터 ───────────────────────────────
_TM_NOISE_FULL = re.compile(
    r"기프트.선불카드|전자지급수단|상품권 구매|국가바우처 이용건|"
    r"고용.산재보험|국세.지방세|건강보험.국민연금|산재보험|장애인 고용|"
    r"이용금액.*제외|이용금액.*포함|이용금액.*결제|"
    r"삼성카드와 구매캐시백|빅포인트 적립 제외|페이백서비스|"
    r"중국공상은행|삼성체크카드.*CASHBACK|"
    r"교통.*이동통신.*스트리밍.*할인이.*적용되지|"
    r"휴대폰알림서비스|S\.InfoCare|스마트오토|이마트 이클럽|"
    r"부동산 임대|초·중·고등학교|학교납입금|대학 등록금|"
    r"의약품 결제건|유류 구매|대금결제",
    re.IGNORECASE,
)

def _filter_target_merchants(raw: str) -> str:
    """전체 raw가 금융조건/정책이면 빈 문자열, 아니면 그대로 반환."""
    if not raw:
        return raw
    if _TM_NOISE_FULL.search(raw):
        return ""
    parts = [p.strip() for p in raw.split(" / ") if p.strip()]
    clean_parts = [p for p in parts if not _is_excluded_noise(p) and not _TM_NOISE_FULL.search(p)]
    return " / ".join(clean_parts)

# ── benefit_summary 자동 생성 ────────────────────────────────
#
# 목표 포맷: "네이버플러스, 쿠팡 로켓와우 50% 할인"
#             "OTT 10% 할인"  /  "GS25, CU 5% 할인"
#
# 전략:
#   raw_text(혜택상세내용)에 이미 "가맹점명 N% 혜택유형" 구조가 있으면
#   그걸 정제해서 그대로 사용 (재조립 금지).
#   raw_text가 줄글이거나 구조가 없으면 필드(소제목·탭명·가맹점)로 조합.

# "N% 할인 / N원 캐시백 / N포인트 적립" 등 수치+혜택 패턴
_SB_VALUE_RE  = re.compile(r"\d+(\.\d+)?\s*(%|원|포인트|마일)")
# 줄글 판별: 이 패턴이 있으면 raw_text를 그대로 쓰지 않음
_SB_PROSE_RE  = re.compile(
    r"(의\s*경우|경우에|해당하며|따라서|적용\s*되[지며]|"
    r"이용\s*시\s*[가-힣]|결제\s*시\s*[가-힣]|"
    r"제공\s*됩니다|적립\s*됩니다|할인\s*됩니다|"
    r"산정\s*기준|이용금액이란|이용금액\s*산정|"
    r"[가-힣]{2,}\s*(이|가|을|를|은|는|에서|으로)\s[가-힣])"
)
# benefit_summary에 넣기엔 너무 긴 raw_text 길이 기준
_SB_MAX_LEN   = 60
# 메타성 소제목/탭명 (가맹점·카테고리명이 아닌 것)
_SB_META_NAMES = {
    "대상점", "서비스안내", "이용조건", "카드이용TIP",
    "할인 제외 대상", "유의사항", "", "KSP", "서비스 요약",
    "상세혜택", "주요혜택", "기본혜택", "추가혜택",
    "KSP", "카드이용TIP", "카드 디자인 소개",
    "컨택리스(비접촉) 결제 지원", "아멕스 PLATINUM 등급 서비스",
    "옵션 패키지 자세히 보기", "패키지 이용처", "바우처 서비스",
    "패키지1",  # 패키지1만 제외, 패키지2~6은 파싱 대상
}

# benefit_summary에서 완전 제거할 조건/제외/중복 안내성 문구
_SB_CONDITION_RE = re.compile(
    r"(할인\s*받은\s*이용금액\s*제외"        # "3%/10% 할인 받은 이용금액 제외!"
    r"|중복\s*적용"                           # "중복 적용 불가" / "중복 적용"
    r"|할인\s*혜택과\s*중복"                  # "온라인 간편결제·해외 3%·1% 할인 혜택과 중복"
    r"|전월\s*이용금액\s*\d+만원\s*미만\s*시" # "전월 이용금액 30만원 미만 시"
    r"|월\s*할인한도\s*초과\s*시"             # "월 할인한도 초과 시"
    r"|지원대상\s*[:\：]"                     # "지원대상 : 출산(예정)일 ..."
    r"|출산\(예정\)일.*전부터"                # 임산부 바우처 직접 문구
    r"|기준\s*중위\s*소득.*임산부"            # 임산부 조건
    r")"
)

def _summary_type_label(종류: str) -> str:
    """혜택종류 → 출력용 레이블. 서비스/연회비는 빈 문자열."""
    if not 종류: return ""
    if "캐시백" in 종류: return "캐시백"
    if "할인"   in 종류: return "할인"
    if "마일"   in 종류: return "마일리지 적립"
    if "포인트" in 종류 or "적립" in 종류: return "적립"
    return ""

def _build_benefit_summary(섹션분류: str, 소제목: str, 수치: str,
                            단위: str, 종류: str, 가맹점: str,
                            탭명: str, raw_text: str = "") -> str:
    """
    "가맹점/카테고리명 N% 혜택유형" 형태의 짧은 요약 생성.

    우선순위:
      1. raw_text가 짧고 구조적(수치 포함, 줄글 아님) → raw_text 그대로 반환
      2. raw_text가 줄글이거나 없음 → 필드 조합으로 생성
         a. 이름 = 소제목(메타 아닌 경우) > 탭명(메타 아닌 경우) > 가맹점 앞 2개
         b. 수치+단위 → "50%", "30원" 형태
         c. 혜택종류 → "할인", "캐시백", "적립", "마일리지 적립"
         조합: "{이름} {수치}{단위} {혜택유형}"
    """
    if 섹션분류 != "대상점":
        return ""

    # ── 0단계: raw_text 전처리 ────────────────────────────────
    raw = (raw_text or "").strip()

    # 원문자(①②③④⑤)가 앞에만 붙은 경우 → 원문자만 제거하고 본문 유지
    # ex) "① 많이 쓰는 영역 30% 자동 맞춤 할인" → "많이 쓰는 영역 30% 자동 맞춤 할인"
    raw = re.sub(r"^[①②③④⑤]\s+", "", raw)

    # 조건·제외·중복 안내성 텍스트 → benefit_summary로 부적합, 빈 문자열 반환
    if _SB_CONDITION_RE.search(raw):
        return ""

    # ── 1단계: raw_text 직접 사용 가능한지 확인 ──────────────
    if raw and len(raw) <= _SB_MAX_LEN \
            and _SB_VALUE_RE.search(raw) \
            and not _SB_PROSE_RE.search(raw):
        # 파이프 구분자가 있는 패키지 행은 쉼표로 정리
        if "|" in raw:
            return re.sub(r"\s*\|\s*", ", ", raw)[:120]
        return raw
    # 파이프 구분 패키지 행은 수치 없어도 raw_text 직접 사용
    if raw and "|" in raw and not _SB_PROSE_RE.search(raw):
        return re.sub(r"\s*\|\s*", ", ", raw)[:120]

    # ── 2단계: 필드 조합으로 생성 ────────────────────────────

    # 수치+단위 문자열 ("50%", "30원" …)
    value_str = ""
    v = (수치 or "").strip()
    u = (단위 or "").strip()
    if re.match(r"^\d+(\.\d+)?$", v):
        value_str = f"{v}{u}" if u else v

    # 혜택유형 레이블
    type_label = _summary_type_label(종류)

    # 이름 결정: 소제목 → 탭명 → 가맹점 앞 2개
    name = ""

    if 소제목 and 소제목 not in _SB_META_NAMES:
        name = 소제목
    if not name and 탭명 and 탭명 not in _SB_META_NAMES:
        name = 탭명
    if not name and 가맹점:
        gm = _filter_target_merchants(가맹점)
        if gm:
            pts = [p.strip() for p in re.split(r"[,/]", gm) if p.strip()]
            if pts:
                name = ", ".join(pts[:2]) + (" 등" if len(pts) > 2 else "")

    if not name and not value_str:
        return ""

    parts = [p for p in [name, value_str, type_label] if p]
    return " ".join(parts)[:80]

# ── 유틸 ──────────────────────────────────────────────────────
def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()

def extract_number(text):
    """만/천 단위 명시된 금액만 변환. 단위 없는 큰 숫자(날짜·코드)는 무시."""
    if not text: return ""
    total = sum(int(v) * (10000 if u == "만" else 1000)
                for v, u in re.findall(r"(\d+)(만|천)", text))
    if total: return str(total)
    # 단위 없이 순수 숫자만 있을 때: 6자리 이상이면 날짜/코드로 간주하고 무시
    m = re.search(r"[\d,]+", text)
    if not m: return ""
    raw = m.group(0).replace(",", "")
    if len(raw) >= 7:   # 1,000,000 이상 → 날짜/코드 위험, 무시
        return ""
    return raw

def fee_to_number(s):
    return extract_number(s) if s else ""

def get_category(소제목, 내용):
    text = 소제목 + " " + 내용
    for cat, kws in CATEGORY_MAP:
        if any(k in text for k in kws):
            return cat
    return ""

def parse_max_benefit(text):
    """한도 텍스트에서 숫자 추출. 단위 없는 이상한 큰 숫자 차단."""
    if not text or text in ("-", "없음"): return ""
    total = sum(int(v) * (10000 if u == "만" else 1000)
                for v, u in re.findall(r"(\d+)(만|천)", text))
    if total: return str(total)
    m = re.search(r"[\d,]+", text)
    if not m: return ""
    raw = m.group(0).replace(",", "")
    if len(raw) >= 10:   # 10자리 이상은 코드/날짜, 무시
        return ""
    return raw

def _validate_numeric(val: str, min_v: int = 1, max_v: int = 99_999_999) -> str:
    """숫자 문자열 범위 검증. 범위 밖이면 빈 문자열 반환 (날짜·코드 오인값 차단)."""
    if not val: return ""
    v = val.replace(",", "")
    if not v.isdigit(): return ""
    return v if min_v <= int(v) <= max_v else ""

def append_csv(path, fields, rows):
    exists = os.path.isfile(path)
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists: w.writeheader()
        w.writerows(rows)

# ── STEP 1: Playwright로 __NUXT__ 추출 ────────────────────────
async def get_nuxt_data(card_code: str) -> dict:
    target_url = BASE_URL + card_code
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="ko-KR",
        )
        page = await context.new_page()
        await page.route("**/*", lambda r: r.abort()
            if r.request.resource_type in ("image", "media", "font", "stylesheet")
            else r.continue_())

        print(f"[1/4] 페이지 접속: {target_url}")
        await page.goto(target_url, wait_until="domcontentloaded", timeout=30_000)

        try:
            await page.wait_for_function(
                """() => {
                    try {
                        const d = window.__NUXT__.data[0];
                        return d.wcms && d.wcms.pdList && d.wcms.pdList.length > 0;
                    } catch(e) { return false; }
                }""",
                timeout=15_000,
            )
        except Exception:
            await page.wait_for_timeout(5_000)

        data0 = await page.evaluate("() => window.__NUXT__.data[0]")

        sell_start_dt = await page.evaluate("""
            () => {
                const el = document.getElementById('sellStrtdt');
                return el ? el.textContent.trim() : '';
            }
        """)

        await browser.close()

    if not data0:
        raise RuntimeError("__NUXT__.data[0] 추출 실패")

    wcms = data0.get("wcms", {})
    banner_list = data0.get("bannerList", [])
    pd_list = wcms.get("pdList", [])
    card = next((c for c in pd_list if c.get("code") == card_code), None)
    if not card:
        raise RuntimeError(f"{card_code} 카드를 pdList에서 찾을 수 없음")

    print(f"[1/4] detailUrl: {card['detailUrl']}")
    유효_배너 = [b for b in banner_list if b.get("evtUrl")]
    print(f"[1/4] bannerList 총 {len(banner_list)}개 (이벤트URL 있는 것: {len(유효_배너)}개)")

    return {
        "detailUrl":     card["detailUrl"],
        "bannerList":    banner_list,
        "sell_start_dt": sell_start_dt,
    }

# ── 혜택 HTML 파싱 ────────────────────────────────────────────
def parse_benefit_html(html: str, tab_name: str) -> list:
    open_count  = len(re.findall(r'<div[\s>]', html, re.IGNORECASE))
    close_count = len(re.findall(r'</div>', html, re.IGNORECASE))
    if open_count > close_count:
        html += "</div>" * (open_count - close_count)

    soup = BeautifulSoup(html, "html.parser")
    rows = []

    h4 = soup.find("h4", class_="hide")
    benefit_title = clean(h4.get_text()) if h4 else tab_name

    def classify_benefit_type(title):
        t = title
        if any(k in t for k in ["마일리지", "Mile", "mile", "MILE"]): return "마일리지적립"
        if any(k in t for k in ["캐시백", "cashback", "CashBack"]):    return "캐시백"
        if any(k in t for k in ["포인트", "Point", "point", "적립"]):  return "포인트적립"
        if any(k in t for k in ["%", "할인"]):                         return "할인"
        return "서비스"
    혜택종류 = classify_benefit_type(benefit_title)

    def extract_rate(title):
        """혜택 수치·단위 추출. % > 마일리지 > 포인트 > 소액원 순으로 시도."""
        m = re.search(r"([\d]+(?:\.\d+)?)\s*%", title)
        if m:
            return m.group(1), "%"
        m = re.search(r"([\d,]+)\s*마일", title)
        if m:
            return m.group(1).replace(",", ""), "마일리지"
        m = re.search(r"([\d,]+)\s*포인트", title)
        if m:
            return m.group(1).replace(",", ""), "포인트"
        m = re.search(r"([\d,]+)\s*원(?!당)", title)
        if m:
            num = m.group(1).replace(",", "")
            if int(num) < 1000:
                return num, "원"
        return "", ""
    수치, 단위 = extract_rate(benefit_title)

    def parse_condition(txt):
        실적, 한도 = "", ""
        # ── 전월실적: "전월" + 숫자 + 단위 명시 필수, 1만~1천만 범위만 ──
        m_만   = re.search(r"전월.*?([0-9]{1,4})\s*만원", txt)
        m_실적 = re.search(r"전월.*?([1-9][0-9]{0,6})\s*원(?!\s*한도)", txt)
        if m_만:
            v = int(m_만.group(1)) * 10000
            if 10000 <= v <= 10_000_000:
                실적 = str(v)
        elif m_실적:
            v = int(m_실적.group(1).replace(",", ""))
            if 10000 <= v <= 10_000_000:
                실적 = str(v)
        # ── 최대한도: 문맥 키워드(한도/월최대/적립한도) 필수 ──
        def _safe_limit(raw):
            v = raw.replace(",", "")
            return v if v.isdigit() and 1 <= int(v) <= 99_999_999 else ""
        m_한도  = re.search(r"(?:한도|월\s*최대|적립한도)\s*[:\：]?\s*([0-9][0-9,]*)\s*원", txt)
        m_한도2 = re.search(r"([0-9][0-9,]+)\s*원\s*한도", txt)
        m_마일  = re.search(r"(?:한도|월\s*최대|적립한도)\s*[:\：]?\s*([0-9][0-9,]*)\s*마일", txt)
        m_마일2 = re.search(r"([0-9][0-9,]+)\s*마일(?:리지)?\s*한도", txt)
        m_pt    = re.search(r"(?:한도|월\s*최대|적립한도)\s*[:\：]?\s*([0-9][0-9,]*)\s*포인트", txt)
        m_pt2   = re.search(r"([0-9][0-9,]+)\s*포인트\s*한도", txt)
        if m_한도:    한도 = _safe_limit(m_한도.group(1))
        elif m_한도2: 한도 = _safe_limit(m_한도2.group(1))
        elif m_마일:  한도 = _safe_limit(m_마일.group(1))
        elif m_마일2: 한도 = _safe_limit(m_마일2.group(1))
        elif m_pt:    한도 = _safe_limit(m_pt.group(1))
        elif m_pt2:   한도 = _safe_limit(m_pt2.group(1))
        return 실적, 한도

    def get_li_texts(container):
        seen, texts = set(), []
        for li in container.find_all("li", recursive=False):
            direct = clean("".join(
                c.get_text() if hasattr(c, "get_text") else str(c)
                for c in li.children
                if getattr(c, "name", None) not in ("ul", "div", "table")
            ))
            sub_ul  = li.find("ul",  recursive=False)
            sub_div = li.find("div", recursive=False)
            if direct and len(direct) > 2 and direct not in seen:
                seen.add(direct); texts.append(direct)
            if sub_ul:
                for t in get_li_texts(sub_ul):
                    if t not in seen:
                        seen.add(t); texts.append(t)
            if sub_div:
                for table in sub_div.find_all("table"):
                    thead = table.find("thead")
                    col_hdrs = [clean(th.get_text()) for th in thead.find_all("th")] if thead else []
                    for tr in table.find_all("tr"):
                        cells = [clean(c.get_text()) for c in tr.find_all(["td","th"])]
                        cells_f = [c for c in cells if c and c not in col_hdrs]
                        row_txt = " | ".join(cells_f)
                        if row_txt and len(row_txt) > 2 and row_txt not in seen:
                            seen.add(row_txt); texts.append(row_txt)
        return texts

    def classify_h5(t):
        if any(k in t for k in ["서비스안내", "서비스 안내", "서비스내용", "서비스 내용"]): return "서비스안내"
        if any(k in t for k in ["대상점", "대상업종", "대상 가맹점", "대상 업종"]):         return "대상점"
        if any(k in t for k in ["유의사항", "공통 유의사항", "공통유의사항"]):              return "유의사항"
        if any(k in t for k in ["제외 대상", "제외대상", "적립 제외", "할인 제외",
                                  "캐시백 제외", "제외 가맹점"]):                            return "제외대상"
        if any(k in t for k in ["이용조건", "이용 조건", "이용방법", "이용 방법"]):         return "이용조건"
        if any(k in t for k in ["적립기준", "적립 기준", "할인기준", "할인 기준",
                                  "제공기준", "제공 기준", "전월", "할인율",
                                  "한도", "적립률", "구간"]):                               return "할인기준"
        return "카드이용TIP"

    _SUBTITLE_LABEL = {
        "카드이용TIP":    "카드이용TIP",
        "서비스안내":     "서비스안내",
        "대상점":         "대상점",
        "이용조건":       "이용조건",
        "할인기준":       "이용조건",
        "제외대상":       "할인 제외 대상",
        "유의사항":       "유의사항",
    }

    def normalize_subtitle(section_type, section_title):
        return _SUBTITLE_LABEL.get(section_type, section_title)

    def detect_table_type(table):
        thead = table.find("thead") or table
        headers = " ".join(clean(th.get_text()) for th in thead.find_all("th"))
        if any(k in headers for k in ["전월", "할인율", "한도", "적립률", "%",
                                       "구간", "연간", "이용금액"]):
            return "할인기준"
        return "대상점"

    전월실적 = ""
    월한도   = ""
    제외가맹점_tab = ""

    def make_row(섹션분류, 소제목, 요약, 상세,
                 종류="", 수치_val="", 단위_val="",
                 사용처="Both", 국내해외="국내", 카테고리="",
                 가맹점="", 제외="", 실적="", 한도="",
                 _section_type=""):
        normalized = normalize_subtitle(_section_type, 소제목) if _section_type else 소제목
        return {
            "혜택섹션분류": 섹션분류, "혜택제목": benefit_title,
            "혜택탭명":     tab_name, "혜택소제목": normalized,
            "혜택요약":     요약[:200], "혜택상세내용": 상세,
            "혜택종류":     종류, "혜택수치": 수치_val, "혜택단위": 단위_val,
            "사용처":       사용처, "국내해외": 국내해외, "소비카테고리": 카테고리,
            "적용가맹점":   가맹점, "제외가맹점": 제외,
            "최대한도":     한도, "전월실적_숫자": 실적,
        }

    def parse_table(table, section_title, section_type):
        nonlocal 전월실적, 월한도
        ttype = section_type
        if ttype not in ("대상점", "할인기준"):
            ttype = detect_table_type(table)
        elif ttype == "대상점" and detect_table_type(table) == "할인기준":
            ttype = "할인기준"

        thead = table.find("thead")
        col_headers = [clean(th.get_text()) for th in thead.find_all("th")] if thead else []
        tbody = table.find("tbody") or table

        if ttype == "대상점":
            for tr in tbody.find_all("tr"):
                tds = tr.find_all(["td", "th"])
                if len(tds) < 2: continue
                k = clean(tds[0].get_text())
                skip = set(col_headers) | {"영역","가맹점","구분","업종","대상",
                                           "할인 대상","적립처","서비스내용","대상점"}
                if not k or k in skip: continue
                inner_ul = tds[1].find("ul")
                if inner_ul:
                    v_parts = get_li_texts(inner_ul)
                    v = " / ".join(v_parts)
                else:
                    v = clean(tds[1].get_text())
                extra = " / ".join(clean(tds[i].get_text()) for i in range(2, len(tds)) if clean(tds[i].get_text()))
                if extra: v = (v + " / " + extra).strip(" /")
                if not v: continue
                cat = get_category(k, v)
                # 셀 값(v)에서 개별 수치/단위 추출, 없으면 탭 전역값 사용
                _rv, _ru = extract_rate(v) if v else ("", "")
                if not _rv:
                    _rv, _ru = 수치, 단위
                _종류 = 혜택종류
                if not _종류 or _종류 == "서비스":
                    if _ru == "%": _종류 = "할인"
                    elif _ru == "마일리지": _종류 = "마일리지적립"
                    elif _ru == "포인트": _종류 = "포인트적립"
                혜택명 = f"{k} {_rv}{_ru} {_종류}" if _rv else f"{k} {_종류}"
                원문 = f"{k}: {v}"
                rows.append(make_row(
                    "대상점", section_title, 혜택명, 원문,
                    종류=_종류, 수치_val=_rv, 단위_val=_ru,
                    사용처=ON_OFF_MAP.get(cat, "Both"),
                    국내해외=LOCATION_MAP.get(cat, "국내"),
                    카테고리=cat, 가맹점=v,
                    실적=전월실적, 한도=월한도,
                    _section_type="대상점",
                ))

        elif ttype == "할인기준":
            for tr in tbody.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                vals = [clean(c.get_text()) for c in cells]
                if not any(vals): continue
                row_label = vals[0]
                if row_label in col_headers: continue
                for i, val in enumerate(vals[1:], 1):
                    if not val: continue
                    col = col_headers[i] if i < len(col_headers) else f"구간{i}"
                    txt = f"{row_label} {col}: {val}".strip(" :")
                    s, h = parse_condition(col + " " + val)
                    if s and not 전월실적: 전월실적 = s
                    if h and not 월한도:   월한도 = h
                    # 수치·단위: val에서 직접 추출 (탭 전역값 fallback)
                    _v, _u = extract_rate(val)
                    if not _v:
                        _v, _u = extract_rate(row_label)
                    rows.append(make_row("할인기준", section_title, txt[:200], txt,
                                         수치_val=_v, 단위_val=_u,
                                         실적=전월실적, 한도=월한도,
                                         _section_type="할인기준"))

    def parse_ul(ul, section_title, section_type):
        nonlocal 전월실적, 월한도, 제외가맹점_tab
        texts = get_li_texts(ul)
        if not texts: return

        if section_type == "제외대상":
            제외가맹점_tab = _filter_excluded_merchants(texts)
            for r in rows:
                if r.get("혜택탭명") == tab_name and r.get("혜택섹션분류") == "대상점" \
                   and not r.get("제외가맹점"):
                    r["제외가맹점"] = 제외가맹점_tab
            for txt in texts:
                if not _is_excluded_noise(txt):
                    rows.append(make_row("혜택유의사항", section_title, txt[:200], txt,
                                          _section_type="제외대상"))

        elif section_type == "유의사항":
            for txt in texts:
                rows.append(make_row("혜택유의사항", section_title, txt, txt,
                                      _section_type="유의사항"))

        elif section_type == "이용조건":
            for txt in texts:
                s, h = parse_condition(txt)
                if s and not 전월실적: 전월실적 = s
                if h and not 월한도:   월한도 = h
                _v, _u = extract_rate(txt)
                rows.append(make_row("할인기준", section_title, txt[:200], txt,
                                      수치_val=_v, 단위_val=_u,
                                      실적=전월실적, 한도=월한도,
                                      _section_type="이용조건"))

        elif section_type == "할인기준":
            for txt in texts:
                s, h = parse_condition(txt)
                if s and not 전월실적: 전월실적 = s
                if h and not 월한도:   월한도 = h
                _v, _u = extract_rate(txt)
                rows.append(make_row("할인기준", section_title, txt[:200], txt,
                                      수치_val=_v, 단위_val=_u,
                                      실적=전월실적, 한도=월한도,
                                      _section_type="할인기준"))

        else:
            for txt in texts:
                if not _is_structured_benefit(txt):
                    continue
                cat = get_category(section_title, txt)
                _row_v, _row_u = extract_rate(txt)
                if not _row_v:
                    _row_v, _row_u = 수치, 단위
                _종류 = 혜택종류
                if not _종류 or _종류 == "서비스":
                    if _row_u == "%":         _종류 = "할인"
                    elif _row_u == "마일리지": _종류 = "마일리지적립"
                    elif _row_u in ("포인트",): _종류 = "포인트적립"
                # 가맹점명: 수치·단위·혜택종류 키워드 제거 후 앞부분만 추출
                _merchant = re.sub(
                    r"\s*[\d]+(?:\.\d+)?\s*(?:%|원|포인트|마일리지|마일)\s*(?:할인|적립|캐시백|마일리지적립)?",
                    "", txt
                ).strip(" ,/")
                rows.append(make_row(
                    "대상점", section_title, txt[:200], txt,
                    종류=_종류, 수치_val=_row_v, 단위_val=_row_u,
                    사용처=ON_OFF_MAP.get(cat, "Both"),
                    국내해외=LOCATION_MAP.get(cat, "국내"),
                    카테고리=cat, 가맹점=_merchant if _merchant else txt,
                    실적=전월실적, 한도=월한도,
                    _section_type=section_type,
                ))

    def parse_shoplist(container, section_title):
        for ul in container.find_all("ul", class_="shopList"):
            prev_h5 = ul.find_previous_sibling("h5")
            if not prev_h5:
                prev_h5 = ul.find_previous("h5")
            sub = clean(prev_h5.get_text()) if prev_h5 else section_title
            items = []
            for li in ul.find_all("li"):
                span = li.find("span", class_="name")
                img  = li.find("img")
                name = clean(span.get_text()) if span else \
                       (img.get("alt","").replace(" 로고","").strip() if img else "")
                if name: items.append(name)
            if items:
                txt = ", ".join(items)
                cat = get_category(sub, txt)
                rows.append(make_row(
                    "대상점", sub, txt[:200], txt,
                    종류=혜택종류, 수치_val=수치, 단위_val=단위,
                    사용처=ON_OFF_MAP.get(cat, "Both"),
                    국내해외=LOCATION_MAP.get(cat, "국내"),
                    카테고리=cat, 가맹점=txt,
                    실적=전월실적, 한도=월한도,
                    _section_type="대상점",
                ))

    def parse_p_tags(container, section_title):
        for p in container.find_all("p"):
            txt = clean(p.get_text())
            if txt and len(txt) > 5 and _is_structured_benefit(txt):
                rows.append(make_row("대상점", section_title, txt[:200], txt, 종류="서비스",
                                      _section_type="카드이용TIP"))

    def is_in_bnote(el):
        for parent in el.parents:
            if hasattr(parent, "get"):
                cls = " ".join(parent.get("class", []))
                if "b_note" in cls:
                    return True
        return False

    def process_elements(elements, section_title, section_type):
        for sib in elements:
            if not hasattr(sib, "find_all"): continue
            sib_class = " ".join(sib.get("class", []))

            if sib.find("ul", class_="shopList"):
                parse_shoplist(sib, section_title)
                continue

            if any(c in sib_class for c in ["list_btns", "btm_info"]):
                for a in sib.find_all(["a", "button"]):
                    txt = clean(a.get_text())
                    if txt and len(txt) > 3 and _is_structured_benefit(txt):
                        rows.append(make_row("대상점", section_title, txt[:200], txt, 종류="서비스",
                                              _section_type=section_type))
                continue

            if "b_note" in sib_class:
                def _has_bg_box(tag):
                    c = tag.get("class", [])
                    cls_str = " ".join(c) if isinstance(c, list) else (c or "")
                    return "bg_box" in cls_str

                for bg in sib.find_all("div"):
                    if not _has_bg_box(bg): continue
                    inner_h5   = bg.find("h5")
                    inner_sub  = clean(inner_h5.get_text()) if inner_h5 else "유의사항"
                    inner_type = classify_h5(inner_sub)
                    uls = bg.find_all("ul", recursive=False) or bg.find_all("ul")
                    for ul in uls:
                        parse_ul(ul, inner_sub, inner_type)
                for ul in sib.find_all("ul", recursive=False):
                    parse_ul(ul, section_title, "유의사항")
                continue

            for table in (sib.find_all("table") if sib.name != "table" else [sib]):
                if not table.find_parent("li"):
                    parse_table(table, section_title, section_type)

            if sib.name == "ul":
                parse_ul(sib, section_title, section_type)
            else:
                for ul in sib.find_all("ul"):
                    if not ul.find_parent(["li", "table"]) and not is_in_bnote(ul):
                        parse_ul(ul, section_title, section_type)
                        break
                direct_uls = sib.find_all("ul", recursive=False)
                for ul in direct_uls:
                    parse_ul(ul, section_title, section_type)

    # MAIN
    if not soup.find("h5") and not soup.find("h4", class_="hide"):
        card_design = soup.find("div", class_="cardDesign")
        if card_design:
            info_dl = card_design.find("div", class_="cardDesign_info")
            if info_dl:
                name = clean(info_dl.find("dt").get_text()) if info_dl.find("dt") else ""
                desc_txts = [clean(dd.get_text()) for dd in info_dl.find_all("dd") if clean(dd.get_text())]
                txt = (name + " " + " / ".join(desc_txts)).strip()
                if txt:
                    rows.append({
                        "혜택섹션분류": "대상점", "혜택제목": txt,
                        "혜택탭명": tab_name, "혜택소제목": "카드이용TIP",
                        "혜택요약": txt[:80], "혜택상세내용": txt,
                        "혜택종류": "서비스", "혜택수치": "", "혜택단위": "",
                        "사용처": "Both", "국내해외": "둘다", "소비카테고리": "",
                        "적용가맹점": "", "제외가맹점": "",
                        "최대한도": "", "전월실적_숫자": "",
                    })
            design_list = card_design.find("div", class_="cardDesign_list")
            if design_list:
                for li in design_list.find_all("li"):
                    dt = li.find("dt")
                    dd = li.find("dd")
                    if dt and dd:
                        d_name = clean(dt.get_text())
                        d_desc = clean(dd.get_text())
                        rows.append({
                            "혜택섹션분류": "대상점", "혜택제목": tab_name,
                            "혜택탭명": tab_name, "혜택소제목": "카드이용TIP",
                            "혜택요약": f"{d_name} 디자인"[:80],
                            "혜택상세내용": f"{d_name}: {d_desc}",
                            "혜택종류": "서비스", "혜택수치": "", "혜택단위": "",
                            "사용처": "Both", "국내해외": "둘다", "소비카테고리": "",
                            "적용가맹점": "", "제외가맹점": "",
                            "최대한도": "", "전월실적_숫자": "",
                        })
            return rows

        wcms_div = soup.find("div", class_=lambda c: c and "wcms-space" in " ".join(c) if c else False)
        if wcms_div:
            parse_p_tags(wcms_div, tab_name)
        else:
            parse_p_tags(soup, tab_name)
        return rows

    has_tit04 = bool(soup.find("h5", class_=lambda c: c and "tit04" in " ".join(c) if c else False))
    has_tit   = bool(soup.find("h5", class_="tit"))
    if has_tit and not has_tit04:
        parse_shoplist(soup, tab_name)
        return rows

    h5_list = soup.find_all("h5")
    processed_h5 = set()

    for h5 in h5_list:
        if id(h5) in processed_h5: continue
        if is_in_bnote(h5): continue

        section_title = clean(h5.get_text()) or tab_name
        section_type  = classify_h5(section_title)
        processed_h5.add(id(h5))

        sibs = []
        el = h5.next_sibling
        while el:
            if hasattr(el, "name") and el.name == "h5" and not is_in_bnote(el):
                break
            if hasattr(el, "name") and el.name:
                el_class = " ".join(el.get("class", []))
                if "b_note" in el_class:
                    process_elements([el], section_title, section_type)
                    break
                sibs.append(el)
            el = el.next_sibling

        process_elements(sibs, section_title, section_type)

    def _cls_str(tag):
        c = tag.get("class", [])
        return " ".join(c) if isinstance(c, list) else (c or "")

    for bn in soup.find_all("div"):
        if "b_note" not in _cls_str(bn): continue
        parent_lbn = bn.find_parent("div")
        if parent_lbn and "list_box_nt" in _cls_str(parent_lbn): continue
        process_elements([bn], tab_name, "유의사항")

    for r in rows:
        if r.get("혜택탭명") != tab_name:
            continue
        섹션 = r.get("혜택섹션분류", "")
        if 섹션 in ("대상점", "할인기준"):
            if not r.get("전월실적_숫자") and 전월실적:
                r["전월실적_숫자"] = 전월실적
            if not r.get("최대한도") and 월한도:
                r["최대한도"] = 월한도
        if 섹션 == "대상점" and not r.get("제외가맹점") and 제외가맹점_tab:
            r["제외가맹점"] = 제외가맹점_tab

    if not rows and not soup.find("h5"):
        for dl in soup.find_all("dl"):
            dt = dl.find("dt")
            dds = dl.find_all("dd")
            dd_txt = " ".join(clean(d.get_text()) for d in dds if clean(d.get_text()) and len(clean(d.get_text())) > 4)
            if dt and dd_txt:
                제목 = clean(dt.get_text())
                rows.append({
                    "혜택섹션분류": "대상점",
                    "혜택제목":    benefit_title,
                    "혜택탭명":    tab_name,
                    "혜택소제목":  "카드이용TIP",
                    "혜택요약":    f"{제목}: {dd_txt}"[:80],
                    "혜택상세내용": f"{제목}: {dd_txt}",
                    "혜택종류":    "서비스",
                    "혜택수치":    "", "혜택단위": "",
                    "사용처":      "Both", "국내해외": "국내",
                    "소비카테고리": "",
                    "적용가맹점":  "", "제외가맹점": "",
                    "최대한도":    "", "전월실적_숫자": "",
                })

    return rows


def parse_fee_html(html: str) -> tuple:
    soup = BeautifulSoup(html, "html.parser")
    summary = {
        "결제네트워크브랜드": "",
        "연회비_일반_국내": "", "연회비_일반_해외": "",
        "연회비_프리미엄_국내": "", "연회비_프리미엄_해외": "",
        "연회비_비고": "",
        "제휴연회비_국내": "", "제휴연회비_해외": "",
    }
    detail_rows = []
    brands = []

    for table in soup.find_all("table"):
        caption = clean(table.find("caption").get_text()) if table.find("caption") else ""
        is_가족 = "가족" in caption
        thead = table.find("thead")
        tbody = table.find("tbody")
        if not tbody:
            continue

        col_types = []
        if thead:
            for th in thead.find_all("th"):
                txt = clean(th.get_text())
                col_types.append(txt)
                for img in th.find_all("img"):
                    alt = img.get("alt", "")
                    for b in ["Mastercard", "VISA", "UnionPay", "Amex"]:
                        if b.lower() in alt.lower() and b not in brands:
                            brands.append(b)
                for b in ["Mastercard", "VISA", "UnionPay", "Amex"]:
                    if b.lower() in txt.lower() and b not in brands:
                        brands.append(b)
            if any("해외겸용" in c for c in col_types) and not brands:
                brands.append("Mastercard")

        for tr in tbody.find_all("tr"):
            th_tag = tr.find("th")
            tds    = tr.find_all("td")
            label  = clean(th_tag.get_text()) if th_tag else ""
            vals   = [fee_to_number(clean(td.get_text())) for td in tds]

            for i, val in enumerate(vals):
                if not val:
                    continue
                col_name = col_types[i+1] if i+1 < len(col_types) else f"열{i+1}"
                구분 = "가족" if is_가족 else "본인"
                detail_rows.append({
                    "혜택섹션분류": "혜택유의사항",
                    "혜택탭명": "연회비",
                    "혜택제목": "연회비",
                    "혜택요약": f"{구분} {col_name} {label}: {val}원",
                    "혜택소제목": f"{구분}_{col_name} {label}",
                    "혜택상세내용": f"{구분} {col_name} {label}: {val}원",
                    "혜택종류": "서비스",
                    "혜택수치": val, "혜택단위": "원",
                    "사용처": "", "국내해외": "", "소비카테고리": "",
                    "적용가맹점": "", "제외가맹점": "",
                    "최대한도": "", "전월실적_숫자": "",
                })

            if "총" in label and "연회비" in label or (label == "" and len(vals) >= 1 and not detail_rows):
                for i, val in enumerate(vals):
                    if not val:
                        continue
                    col_name = col_types[i+1] if i+1 < len(col_types) else ""
                    if not is_가족:
                        if "해외" in col_name or i == 0 and "국내" not in col_name:
                            summary["연회비_일반_해외"] = val
                        if "국내" in col_name or i == 1:
                            summary["연회비_일반_국내"] = val
                        if len(vals) == 1:
                            summary["연회비_일반_국내"] = val
                            summary["연회비_일반_해외"] = val
                    else:
                        if "해외" in col_name or i == 0:
                            summary["연회비_프리미엄_해외"] = val
                        if "국내" in col_name or i == 1:
                            summary["연회비_프리미엄_국내"] = val
                        if len(vals) == 1:
                            summary["연회비_프리미엄_국내"] = val
                            summary["연회비_프리미엄_해외"] = val

            elif "제휴" in label and "연회비" in label and not is_가족:
                for i, val in enumerate(vals):
                    if not val: continue
                    col_name = col_types[i+1] if i+1 < len(col_types) else ""
                    if "해외" in col_name or i == 0:
                        summary["제휴연회비_해외"] = val
                    if "국내" in col_name or i == 1:
                        summary["제휴연회비_국내"] = val
                    if len(vals) == 1:
                        summary["제휴연회비_국내"] = val
                        summary["제휴연회비_해외"] = val

    if brands:
        summary["결제네트워크브랜드"] = ", ".join(brands)

    if "후불교통" in soup.get_text():
        summary["연회비_비고"] = "후불교통 포함"

    seen = set()
    for h_tag in soup.find_all(["h4", "h5"]):
        if "유의사항" in clean(h_tag.get_text()):
            nxt = h_tag.find_next_sibling("ul")
            if not nxt:
                continue
            def walk_fee(ul):
                for li in ul.find_all("li", recursive=False):
                    cul = li.find("ul", recursive=False)
                    txt = clean("".join(
                        c.get_text() if hasattr(c, "get_text") else str(c)
                        for c in li.children if c.name != "ul"
                    ))
                    if txt and len(txt) > 8 and txt not in seen:
                        seen.add(txt)
                        detail_rows.append({
                            "혜택섹션분류": "혜택유의사항",
                            "혜택탭명": "연회비",
                            "혜택제목": "연회비",
                            "혜택요약": txt,
                            "혜택소제목": "연회비 유의사항",
                            "혜택상세내용": txt,
                            "혜택종류": "", "혜택수치": "", "혜택단위": "",
                            "사용처": "", "국내해외": "", "소비카테고리": "",
                            "적용가맹점": "", "제외가맹점": "",
                            "최대한도": "", "전월실적_숫자": "",
                        })
                    if cul:
                        walk_fee(cul)
            walk_fee(nxt)

    return summary, detail_rows


def parse_notice_html(notice_html: str, etc_html: str, add_service_html: str, fee_html: str) -> list:
    rows = []
    seen = set()

    def extract_ul(html_str, category, sub_category_default):
        soup = BeautifulSoup(html_str, "html.parser")

        def walk(ul, current_sub):
            for li in ul.find_all("li", recursive=False):
                cul = li.find("ul", recursive=False)
                if cul:
                    direct_txt = clean("".join(
                        c.get_text() if hasattr(c, "get_text") else str(c)
                        for c in li.children if c.name != "ul"
                    ))
                    full_txt = clean(li.get_text())
                    if direct_txt and len(direct_txt) > 4:
                        txt = full_txt
                        if txt and len(txt) > 8 and txt not in seen:
                            seen.add(txt)
                            rows.append({"category": category, "sub_category": current_sub, "content": txt})
                    else:
                        walk(cul, current_sub)
                else:
                    txt = clean(li.get_text())
                    if txt and len(txt) > 8 and txt not in seen:
                        seen.add(txt)
                        rows.append({"category": category, "sub_category": current_sub, "content": txt})

        current_sub = sub_category_default

        headings = soup.find_all(["h4", "h5"])
        if headings:
            for tag in soup.find_all(["h4", "h5", "ul"], recursive=True):
                if tag.name in ("h4", "h5"):
                    current_sub = clean(tag.get_text()) or sub_category_default
                elif tag.name == "ul":
                    if not tag.find_parent("ul"):
                        walk(tag, current_sub)
        else:
            for ul in soup.find_all("ul"):
                if not ul.find_parent("ul"):
                    walk(ul, current_sub)
            if not soup.find("ul"):
                for li in soup.find_all("li"):
                    txt = clean(li.get_text())
                    if txt and len(txt) > 8 and txt not in seen:
                        seen.add(txt)
                        rows.append({"category": category, "sub_category": current_sub, "content": txt})

    if notice_html:
        extract_ul(notice_html, "필수안내사항", "필수안내사항")

    if etc_html:
        extract_ul(etc_html, "기타안내사항", "기타안내사항")

    if add_service_html:
        soup = BeautifulSoup(add_service_html, "html.parser")
        current_sub = "부가서비스 변경 가능 사유"

        for tag in soup.find_all(["p", "ol", "ul", "li"]):
            if tag.name == "p":
                txt = clean(tag.get_text())
                if txt and len(txt) > 8 and txt not in seen:
                    if txt.startswith("*") or txt.startswith("카드사가"):
                        current_sub = "부가서비스 변경 가능 사유"
                    seen.add(txt)
                    rows.append({"category": "부가서비스안내", "sub_category": current_sub, "content": txt})

            elif tag.name in ("ol", "ul"):
                if tag.find_parent(["ol", "ul"]):
                    continue
                for li in tag.find_all("li", recursive=False):
                    txt = clean(li.get_text())
                    if txt and len(txt) > 8 and txt not in seen:
                        seen.add(txt)
                        rows.append({"category": "부가서비스안내", "sub_category": current_sub, "content": txt})

    return rows

# ── 이벤트 HTML 파싱 ──────────────────────────────────────────
def parse_event_html(html: str, banner: dict, card_name: str, card_code: str = "") -> list:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    crawled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    fmt = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) >= 8 else d
    evt_id    = banner.get("id", "")
    evt_title = clean(banner.get("evtTitle", ""))
    evt_url   = CDN_BASE + banner.get("evtUrl", "")
    s_date    = fmt(banner.get("sDate", "")[:8])
    e_date    = fmt(banner.get("eDate", "")[:8])

    def get_leaf(tag):
        res = []
        for li in tag.find_all("li", recursive=False):
            cul = li.find("ul", recursive=False)
            txt = clean("".join(
                c.get_text() if hasattr(c, "get_text") else str(c)
                for c in li.children if c.name != "ul"
            ))
            if txt and len(txt) > 4: res.append(txt)
            if cul: res += get_leaf(cul)
        return res

    def classify_evt_type(text):
        t = text.lower()
        if any(k in t for k in ["캐시백", "cashback"]):
            return "캐시백"
        if any(k in t for k in ["포인트", "point", "마일리지"]):
            return "포인트"
        if any(k in t for k in ["할인", "% 할인", "결제일할인"]):
            return "할인"
        if any(k in t for k in ["무료", "면제", "제공", "혜택"]):
            return "서비스"
        return "기타"

    benefit_type = classify_evt_type(evt_title)

    def add_row(section, content):
        if not content: return
        rows.append({
            "card_id":          card_code,
            "card_company":     CARD_COMPANY,
            "card_name":        card_name,
            "source_event_id":  evt_id,
            "event_title":      evt_title,
            "event_url":        evt_url,
            "event_start_date": s_date,
            "event_end_date":   e_date,
            "benefit_type":     benefit_type,
            "section":          section,
            "content":          content,
            "crawled_at":       crawled_at,
        })

    head_area = soup.find("div", class_="head_area")
    if head_area:
        span = head_area.find("span", class_="event_titie")
        if span:
            fc = span.find("span", class_="fc_blue")
            sub_txt = clean(fc.get_text()) if fc else ""
            if fc: fc.extract()
            main_txt = clean(span.get_text())
            if main_txt or sub_txt:
                evt_title = (main_txt + " " + sub_txt).strip()
        add_row("이벤트제목", evt_title)

    main_box = soup.find("div", class_=lambda c: c and "list_box_nt" in c and "bg_box" in c)
    if main_box:
        main_ul = main_box.find("ul", recursive=False)
        if main_ul:
            for li in main_ul.find_all("li", recursive=False):
                if li.find("div", class_=lambda c: c and "btn" in (c or "")): continue
                e_tit = li.find(class_="e_tit")
                section = clean(e_tit.get_text()) if e_tit else ""
                if e_tit: e_tit.extract()
                하위 = get_leaf(li)
                직접 = clean(li.get_text())
                content = " / ".join(하위) if 하위 else 직접
                add_row(section or "기타", content)

    for box in soup.find_all("div", class_="list_box_nt"):
        if "bg_box" in box.get("class", []): continue
        header = box.find(["p", "strong"])
        section = clean(header.get_text()) if header else "유의사항"
        ul = box.find("ul")
        if ul:
            texts = get_leaf(ul)
            if texts: add_row(section, " / ".join(texts))

    return rows

# ── 메인 ─────────────────────────────────────────────────────
async def crawl_one(card_code: str, session: aiohttp.ClientSession):
    """카드 1개 크롤링 → CSV append"""
    crawled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    target_url = BASE_URL + card_code

    # STEP 1: Playwright
    nuxt        = await get_nuxt_data(card_code)
    detail_url  = nuxt["detailUrl"]
    banner_list = nuxt["bannerList"]
    all_codes_in_banner = set()
    for b in banner_list:
        for c in b.get("code", "").split("|"):
            all_codes_in_banner.add(c.strip())

    if card_code not in all_codes_in_banner:
        my_banners = []
    else:
        my_banners = [
            b for b in banner_list
            if b.get("evtUrl") and card_code in [c.strip() for c in b.get("code", "").split("|")]
        ]

    # STEP 2: WCMS JSON
    print("[2/4] WCMS JSON 수신 중...")
    async with session.get(CDN_BASE + detail_url) as resp:
        wcms = await resp.json(content_type=None)

    from bs4 import BeautifulSoup as _BS
    raw_name  = wcms.get("cardTitle", card_code)
    card_name = clean(_BS(raw_name, "html.parser").get_text()) if "<" in raw_name else raw_name

    import re as _re
    type_match = _re.search(r'[(]?(신용|체크|하이브리드|직불)[)]?$', card_name.strip())
    if type_match:
        card_type = type_match.group(1)
        card_name = card_name[:type_match.start()].strip()
    elif "체크" in card_name or card_code.startswith("ABP"):
        card_type = "체크"
    elif "하이브리드" in card_name:
        card_type = "하이브리드"
    else:
        card_type = "신용"

    html_list = wcms.get("htmlList", {})
    bubbles   = wcms.get("bubble", [])
    print(f"  카드명: {card_name} ({card_type})  혜택탭: {len(bubbles)}개")

    # STEP 3: 혜택 탭 파싱
    print("[3/4] 혜택/연회비 HTML 수신 중...")
    benefit_rows_raw = []

    ksp_list_raw = wcms.get("ksp", [])
    for ksp in ksp_list_raw:
        title = ksp.get("title", "")
        if not title: continue
        benefit_rows_raw.append({
            "혜택섹션분류": "대상점",
            "혜택제목":    title,
            "혜택탭명":    "KSP",
            "혜택소제목":  "KSP",
            "혜택요약":    title,
            "혜택상세내용": title,
            "혜택종류":    "서비스",
            "혜택수치":    "", "혜택단위": "",
            "사용처":      "Both", "국내해외": "둘다",
            "소비카테고리": "",
            "적용가맹점":  "", "제외가맹점": "",
            "최대한도":    "", "전월실적_숫자": "",
        })

    for b in bubbles:
        svc_url = b.get("serviceUrl", "")
        if not svc_url:
            continue
        tab_name = b.get("tabName", b.get("title", ""))
        async with session.get(CDN_BASE + svc_url) as resp:
            html = await resp.text()
        rows = parse_benefit_html(html, tab_name)
        benefit_rows_raw += rows
        print(f"  [{tab_name}] {len(rows)}행")

    fee_url = html_list.get("feeUrl", "")
    fee_summary, fee_detail = {}, []
    fee_html = ""
    if fee_url:
        async with session.get(CDN_BASE + fee_url) as resp:
            fee_html = await resp.text()
        fee_summary, fee_detail = parse_fee_html(fee_html)
        benefit_rows_raw += fee_detail
        print(f"  연회비: 국내={fee_summary.get('연회비_일반_국내','')} 해외={fee_summary.get('연회비_일반_해외','')} 네트워크={fee_summary.get('결제네트워크브랜드','')}")

    # ── 대상점 행 중 줄글(설명문) 후처리 필터 ─────────────────
    # parse_table 등 다른 경로로 유입된 줄글도 여기서 제거
    before = len(benefit_rows_raw)
    benefit_rows_raw = [
        r for r in benefit_rows_raw
        if r.get("혜택섹션분류") != "대상점"
        or _is_structured_benefit(r.get("혜택상세내용", ""))
        or r.get("혜택탭명") == "KSP"  # KSP는 구조 무관하게 유지
    ]
    print(f"  줄글 필터: {before}행 → {len(benefit_rows_raw)}행 ({before - len(benefit_rows_raw)}행 제거)")

    # ── 탭별 실적/한도 cross-backfill ─────────────────────────
    # 같은 탭 내 할인기준 행에서 실적/한도를 모아 대상점 행에 채움
    from collections import defaultdict
    _tab_실적: dict = defaultdict(str)
    _tab_한도: dict = defaultdict(str)
    for r in benefit_rows_raw:
        tab = r.get("혜택탭명", "")
        if r.get("혜택섹션분류") == "할인기준":
            if r.get("전월실적_숫자") and not _tab_실적[tab]:
                _tab_실적[tab] = r["전월실적_숫자"]
            if r.get("최대한도") and not _tab_한도[tab]:
                _tab_한도[tab] = r["최대한도"]
    for r in benefit_rows_raw:
        tab = r.get("혜택탭명", "")
        if r.get("혜택섹션분류") == "대상점":
            if not r.get("전월실적_숫자") and _tab_실적.get(tab):
                r["전월실적_숫자"] = _tab_실적[tab]
            if not r.get("최대한도") and _tab_한도.get(tab):
                r["최대한도"] = _tab_한도[tab]

    notice_html = etc_html = add_service_html = ""
    if html_list.get("noticeUrl"):
        async with session.get(CDN_BASE + html_list["noticeUrl"]) as resp:
            notice_html = await resp.text()
        sell_dt = nuxt.get("sell_start_dt", "")
        if sell_dt and notice_html:
            notice_html = notice_html.replace(
                'id="sellStrtdt"></span>',
                f'id="sellStrtdt">{sell_dt}</span>'
            )
    if html_list.get("etcUrl"):
        async with session.get(CDN_BASE + html_list["etcUrl"]) as resp:
            etc_html = await resp.text()
    if html_list.get("addServiceUrl"):
        async with session.get(CDN_BASE + html_list["addServiceUrl"]) as resp:
            add_service_html = await resp.text()

    notice_rows = parse_notice_html(notice_html, etc_html, add_service_html, fee_html)

    # STEP 4: 이벤트
    print(f"[4/4] 이벤트 수신 중... ({len(my_banners)}개)")
    event_rows = []
    for banner in my_banners:
        evt_url_val = banner.get("evtUrl", "")
        if not evt_url_val:
            continue
        url = CDN_BASE + evt_url_val
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    evt_html = await resp.text()
                    rows = parse_event_html(evt_html, banner, card_name, card_code)
                    event_rows += rows
                    print(f"  → {len(rows)}행")
        except Exception as e:
            print(f"  이벤트 오류: {e}")

    # ── card_info.csv ─────────────────────────────────────────
    is_transit = "True" if "후불교통" in fee_summary.get("연회비_비고", "") else "False"

    비고_parts = []
    제휴_국내 = fee_summary.get("제휴연회비_국내", "")
    제휴_해외 = fee_summary.get("제휴연회비_해외", "")
    if 제휴_국내 and 제휴_해외 and 제휴_국내 == 제휴_해외:
        비고_parts.append(f"제휴연회비 {int(제휴_국내):,}원")
    elif 제휴_국내 or 제휴_해외:
        if 제휴_국내: 비고_parts.append(f"제휴연회비(국내) {int(제휴_국내):,}원")
        if 제휴_해외: 비고_parts.append(f"제휴연회비(해외) {int(제휴_해외):,}원")
    if is_transit == "True":
        비고_parts.append("후불교통 포함")
    annual_fee_note = " / ".join(비고_parts)

    img_info = wcms.get("imgInfo", {})
    image_url = CDN_BASE + img_info.get("pcImg1", "") if img_info.get("pcImg1") else ""

    payment_network = fee_summary.get("결제네트워크브랜드", "")
    is_overseas = "True" if any(b in payment_network for b in ["Mastercard", "VISA", "UnionPay", "Amex"]) else "False"

    benefit_list = wcms.get("benefit", [])
    print(f"  bubble: {len(bubbles)}개, benefit: {len(benefit_list)}개")

    seen_titles = []
    for r in benefit_rows_raw:
        if r.get("혜택탭명") == "KSP":
            continue
        t = r.get("혜택제목", "")
        if t and t not in seen_titles and t != r.get("혜택탭명", ""):
            seen_titles.append(t)
    main_benefit = " / ".join(seen_titles)

    if not main_benefit:
        ksp_list_fb = wcms.get("ksp", [])
        if ksp_list_fb:
            main_benefit = " / ".join(k.get("title", "") for k in ksp_list_fb if k.get("title"))
        elif bubbles:
            main_benefit = " / ".join(
                b.get("tabName", b.get("title", ""))
                for b in bubbles
                if b.get("tabName") or b.get("title")
            )
        else:
            main_benefit = " / ".join(
                (b if isinstance(b, str) else b.get("title", ""))
                for b in benefit_list
                if (b if isinstance(b, str) else b.get("title", ""))
            )

    실적_구간들 = sorted(set(
        int(r.get("전월실적_숫자"))
        for r in benefit_rows_raw
        if r.get("혜택섹션분류") == "할인기준"
        and r.get("전월실적_숫자")
        and str(r.get("전월실적_숫자")).isdigit()
    ))
    base_spending_requirement  = str(실적_구간들[0]) if len(실적_구간들) >= 1 else ""
    extra_spending_requirement = str(실적_구간들[1]) if len(실적_구간들) >= 2 else ""

    print(f"  main_benefit: {main_benefit[:50]}")
    append_csv("card_info.csv", INFO_FIELDS, [{
        "card_id":                     card_code,
        "card_company":                CARD_COMPANY,
        "card_name":                   card_name,
        "card_type":                   card_type,
        "payment_network":             payment_network,
        "is_overseas":                 is_overseas,
        "has_transit":                 is_transit,
        "annual_fee_domestic":         fee_summary.get("연회비_일반_국내", ""),
        "annual_fee_domestic_premium": fee_summary.get("연회비_프리미엄_국내", ""),
        "annual_fee_overseas":         fee_summary.get("연회비_일반_해외", ""),
        "annual_fee_overseas_premium": fee_summary.get("연회비_프리미엄_해외", ""),
        "annual_fee_note":             annual_fee_note,
        "base_spending_requirement":   base_spending_requirement,
        "extra_spending_requirement":  extra_spending_requirement,
        "main_benefit":                main_benefit,
        "image_url":                   image_url,
        "detail_page_url":             target_url,
        "crawled_at":                  crawled_at,
    }])
    print("[OK] card_info.csv")

    # ── card_benefit.csv ──────────────────────────────────────
    detail_out = []
    rid = 1
    for r in benefit_rows_raw:
        섹션 = r.get("혜택섹션분류", "")
        if 섹션 in ("주요혜택",):
            continue
        if 섹션 not in ("대상점", "할인기준", "혜택유의사항"):
            continue
        if r.get("혜택소제목", "") == "패키지1":  # 패키지1 행 제외, 패키지2~6은 파싱
            continue
        cat = r.get("소비카테고리", "")
        row_type = "유의사항" if 섹션 == "혜택유의사항" else "할인기준" if 섹션 == "할인기준" else "혜택"
        detail_out.append({
            "benefit_id":            rid,
            "card_id":               card_code,
            "row_type":              row_type,
            "benefit_group":         r.get("혜택탭명", ""),
            "benefit_title":         r.get("혜택소제목", ""),
            "benefit_summary":       (
                ""
                if row_type in ("유의사항", "할인기준")
                else _build_benefit_summary(
                    r.get("혜택섹션분류", ""),
                    r.get("혜택소제목", ""),
                    r.get("혜택수치", ""),
                    r.get("혜택단위", ""),
                    r.get("혜택종류", ""),
                    r.get("적용가맹점", ""),
                    r.get("혜택탭명", ""),
                    r.get("혜택상세내용", ""),   # raw_text 추가
                )
            ),
            "category_id":           "",
            "crawled_category":      cat if row_type == "혜택" else "",
            "payment_method":        ON_OFF_MAP.get(cat, "Both") if row_type == "혜택" else "",
            "region":                LOCATION_MAP.get(cat, "국내") if row_type == "혜택" else "",
            "benefit_type":          (
                r.get("혜택종류", "") if row_type != "유의사항" and r.get("혜택종류", "")
                else (
                    # 할인기준 행에서 혜택종류가 비어있으면 단위/수치로 추론
                    ("적립" if r.get("혜택단위", "") in ("마일리지", "포인트")
                     else "할인" if r.get("혜택단위", "") == "%"
                     else "")
                    if row_type == "할인기준"
                    else ""
                )
            ),
            "benefit_value":         r.get("혜택수치", "") if row_type != "유의사항" else "",
            "benefit_unit":          r.get("혜택단위", "") if row_type != "유의사항" else "",
            "target_merchants":      _filter_target_merchants(r.get("적용가맹점", "")) if row_type in ("혜택", "할인기준") else "",
            "excluded_merchants":    _filter_target_merchants(r.get("제외가맹점", "")) if row_type in ("혜택", "할인기준") else "",
            "performance_condition": _validate_numeric(r.get("전월실적_숫자", ""), min_v=10000, max_v=10_000_000) if row_type != "유의사항" else "",
            "max_limit":             _validate_numeric(r.get("최대한도", ""), min_v=1, max_v=99_999_999) if row_type != "유의사항" else "",
            "raw_text":              r.get("혜택상세내용", ""),
            "crawled_at":            crawled_at,
        })
        rid += 1
    append_csv("card_benefit.csv", BENEFIT_FIELDS, detail_out)
    print(f"[OK] card_benefit.csv ({len(detail_out)}행)")

    # ── card_notices.csv ──────────────────────────────────────
    notice_out = []
    nid = 1
    for r in notice_rows:
        notice_out.append({
            "notice_id":   nid,
            "card_id":     card_code,
            "category":    r["category"],
            "sub_category": r["sub_category"],
            "content":     r["content"],
            "crawled_at":  crawled_at,
        })
        nid += 1
    append_csv("card_notices.csv", NOTICE_FIELDS, notice_out)
    print(f"[OK] card_notices.csv ({len(notice_out)}행)")

    # ── card_events.csv ───────────────────────────────────────
    append_csv("card_events.csv", EVENT_FIELDS, event_rows)
    print(f"[OK] card_events.csv ({len(event_rows)}행)")

    print(f"\n{'='*50}")
    print(f" {CARD_COMPANY} |  {card_name} ({card_code})")
    print(f" 혜택: {len(detail_out)}행 | 유의사항: {len(notice_out)}행 | 이벤트: {len(event_rows)}행")
    print(f"{'='*50}")


async def main():
    print(f" 삼성카드 크롤링 시작 - 총 {len(CARD_LIST)}개 카드")
    print("="*60)

    async with aiohttp.ClientSession(headers={
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }) as session:
        for idx, card_code in enumerate(CARD_LIST, 1):
            print(f"\n[{idx}/{len(CARD_LIST)}] {card_code} 크롤링 중...")
            try:
                await crawl_one(card_code, session)
            except Exception as e:
                print(f"[ERR] {card_code} 오류: {e}")
                import traceback; traceback.print_exc()

    print("\n" + "="*60)
    print(f"[OK] 전체 크롤링 완료 - {len(CARD_LIST)}개 카드")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
