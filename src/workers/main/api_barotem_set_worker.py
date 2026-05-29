import json
import os
import re
import time
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List

from bs4 import BeautifulSoup

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.sqlite_utils import SqliteUtils
from src.workers.api_base_worker import BaseApiWorker
import urllib3
import random
import time

# HTTPS 인증서 검증 경고 숨기기
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ApiBarotemSetWorker(BaseApiWorker):

    def __init__(self, setting: Any = None) -> None:
        super().__init__()

        self.purchasePath_list = None
        self.accountType_list = None
        self.max = None
        self.min = None
        self.keyword = None
        self.current_cnt = None
        self.total_cnt = None
        self._stop_event = threading.Event()
        self.setting: Any = setting

        self.site_name: str = "바로템"
        self.worker_name: str = "barotem"

        self.running: bool = True
        self.before_pro_value: float = 0.0

        # UI 셋팅값
        self.detail_yn: bool = False
        self.auto_save_yn: bool = False

        # 상태값 / 드라이버
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.sqlite_driver: Optional[SqliteUtils] = None
        self.api_client: Optional[APIClient] = None

        self.init_flag: bool = False
        self._cleaned_up: bool = False

        self.folder_path: str = ""
        self.out_dir: str = "output"

        # DB 저장용 공통 상태
        self.hist_id = None
        self.job_id = None
        self.hist_status = "RUNNING"
        self.hist_error_message = None
        self.detail_table_name: str = "BAROTEM"
        self.detail_success_count: int = 0
        self.detail_fail_count: int = 0

        # config columns
        self.config_data: Dict[str, Any] = {}
        self.column_defs: List[Dict[str, Any]] = []
        self.db_columns: List[str] = []
        self.excel_columns: List[str] = []
        self.code_value_map: Dict[str, str] = {}
        self.game_list: List[dict] = [
            {
                "idx": "1",
                "name": "리니지M"
            },
            {
                "idx": "3931",
                "name": "리니지 클래식"
            },
            {
                "idx": "3839",
                "name": "아이온2"
            },
            {
                "idx": "3484",
                "name": "로드나인"
            },
            {
                "idx": "3683",
                "name": "컴투스프로야구V26"
            },
            {
                "idx": "4003",
                "name": "메이플스토리월드"
            },
            {
                "idx": "2573",
                "name": "리니지2M"
            },
            {
                "idx": "3227",
                "name": "나이트 크로우"
            },
            {
                "idx": "3792",
                "name": "뱀피르"
            },
            {
                "idx": "3967",
                "name": "SOL:enchant (솔인챈트)"
            },
            {
                "idx": "2958",
                "name": "오딘: 발할라 라이징"
            },
            {
                "idx": "3944",
                "name": "조선협객전 클래식"
            },
            {
                "idx": "2673",
                "name": "리그오브레전드(롤)"
            },
            {
                "idx": "3006",
                "name": "리니지W"
            },
            {
                "idx": "3999",
                "name": "임진왜란:조선의 반격"
            },
            {
                "idx": "3097",
                "name": "히트2"
            },
            {
                "idx": "3614",
                "name": "RF온라인 넥스트"
            },
            {
                "idx": "3084",
                "name": "피파온라인4(FC온라인)"
            },
            {
                "idx": "2784",
                "name": "아이온"
            },
            {
                "idx": "3875",
                "name": "메이플키우기"
            },
            {
                "idx": "3909",
                "name": "잠룡 : 무협 도트 RPG"
            },
            {
                "idx": "3215",
                "name": "프라시아 전기"
            },
            {
                "idx": "3714",
                "name": "세븐나이츠 리버스"
            },
            {
                "idx": "3982",
                "name": "라그나로크 오리진 클래식"
            },
            {
                "idx": "3159",
                "name": "배틀그라운드"
            },
            {
                "idx": "3429",
                "name": "명조: 워더링 웨이브"
            },
            {
                "idx": "3841",
                "name": "아키텍트 랜드 오브 엑자일"
            },
            {
                "idx": "3113",
                "name": "승리의 여신: 니케"
            },
            {
                "idx": "3486",
                "name": "운빨존많겜"
            },
            {
                "idx": "3149",
                "name": "발로란트"
            },
            {
                "idx": "3796",
                "name": "열혈강호:귀환"
            },
            {
                "idx": "3428",
                "name": "아스달연대기: 세 개의 세력"
            },
            {
                "idx": "3444",
                "name": "레이븐2"
            },
            {
                "idx": "4002",
                "name": "이환"
            },
            {
                "idx": "2922",
                "name": "디아블로 이모탈"
            },
            {
                "idx": "2817",
                "name": "미르4"
            },
            {
                "idx": "3617",
                "name": "DK모바일 리본"
            },
            {
                "idx": "3533",
                "name": "로한2"
            },
            {
                "idx": "3677",
                "name": "마비노기 모바일"
            },
            {
                "idx": "3721",
                "name": "카발RED(카발 레드)"
            },
            {
                "idx": "3220",
                "name": "포켓몬 GO"
            },
            {
                "idx": "3699",
                "name": "SD건담 지 제네레이션 이터널"
            },
            {
                "idx": "3815",
                "name": "R2오리진(알투오리진)"
            },
            {
                "idx": "3619",
                "name": "레전드 오브 이미르"
            },
            {
                "idx": "2520",
                "name": "V4"
            },
            {
                "idx": "4015",
                "name": "렐리온: NPC들의 생존기"
            },
            {
                "idx": "3595",
                "name": "Total Football (토탈풋볼)"
            },
            {
                "idx": "3616",
                "name": "라스트 Z: 서바이벌 슈터"
            },
            {
                "idx": "2456",
                "name": "에오스 레드"
            },
            {
                "idx": "3427",
                "name": "나 혼자만 레벨업:ARISE"
            },
            {
                "idx": "3295",
                "name": "MLB 9이닝스 라이벌"
            },
            {
                "idx": "3189",
                "name": "서든어택"
            },
            {
                "idx": "3639",
                "name": "헌터 키우기"
            },
            {
                "idx": "3240",
                "name": "제노니아 크로노브레이크"
            },
            {
                "idx": "2434",
                "name": "검은사막M"
            },
            {
                "idx": "3437",
                "name": "라살라스"
            },
            {
                "idx": "2987",
                "name": "거상"
            },
            {
                "idx": "2429",
                "name": "블소 레볼루션"
            },
            {
                "idx": "3214",
                "name": "아키에이지 워"
            },
            {
                "idx": "2413",
                "name": "리니지 리마스터"
            },
            {
                "idx": "3771",
                "name": "펭귄 대모험 : 꽁꽁 방어전"
            },
            {
                "idx": "3981",
                "name": "우와 모험단"
            },
            {
                "idx": "3243",
                "name": "아우터플레인"
            },
            {
                "idx": "3080",
                "name": "에픽세븐"
            },
            {
                "idx": "4004",
                "name": "왕좌의게임:킹스로드"
            },
            {
                "idx": "4017",
                "name": "넋나간 삼국지"
            },
            {
                "idx": "3219",
                "name": "리그 오브 레전드: 와일드 리프트"
            },
            {
                "idx": "3406",
                "name": "그라나도 에스파다M"
            },
            {
                "idx": "3054",
                "name": "던전앤파이터 모바일"
            },
            {
                "idx": "3368",
                "name": "뮤 모나크"
            },
            {
                "idx": "3076",
                "name": "메이플스토리M"
            },
            {
                "idx": "3352",
                "name": "브롤스타즈"
            },
            {
                "idx": "3966",
                "name": "창세기전 키우기"
            },
            {
                "idx": "3537",
                "name": "냥코대전쟁"
            },
            {
                "idx": "3544",
                "name": "트리 오브 세이비어: 네버랜드"
            },
            {
                "idx": "3549",
                "name": "천년어게인"
            },
            {
                "idx": "3853",
                "name": "몬길: STAR DIVE"
            },
            {
                "idx": "3961",
                "name": "스톤에이지 키우기"
            },
            {
                "idx": "3399",
                "name": "롬: 리멤버 오브 마제스티"
            },
            {
                "idx": "3459",
                "name": "오버워치2"
            },
            {
                "idx": "3105",
                "name": "프리스톤테일M"
            },
            {
                "idx": "3271",
                "name": "클래시 오브 클랜"
            },
            {
                "idx": "2973",
                "name": "로스트아크"
            },
            {
                "idx": "3328",
                "name": "콜 오브 드래곤즈"
            },
            {
                "idx": "3192",
                "name": "드래곤 베인(드래곤라자 오리진)"
            },
            {
                "idx": "3172",
                "name": "클래시 로얄"
            },
            {
                "idx": "3641",
                "name": "협동 타워 디펜스"
            },
            {
                "idx": "3071",
                "name": "디아블로2 레저렉션"
            },
            {
                "idx": "3804",
                "name": "더스타라이트"
            },
            {
                "idx": "3401",
                "name": "버섯커키우기"
            },
            {
                "idx": "3926",
                "name": "소울 헌터 키우기 : 방치형 RPG"
            },
            {
                "idx": "3984",
                "name": "영혼 인도자: 신의 이름으로"
            },
            {
                "idx": "3869",
                "name": "스트리트볼 올스타"
            },
            {
                "idx": "3848",
                "name": "카오스 제로 나이트메어"
            },
            {
                "idx": "3412",
                "name": "소울스트라이크"
            },
            {
                "idx": "3438",
                "name": "에오스 블랙"
            },
            {
                "idx": "3224",
                "name": "데블M"
            },
            {
                "idx": "3147",
                "name": "디아블로4"
            },
            {
                "idx": "3888",
                "name": "블리치: 소울 레조넌스"
            },
            {
                "idx": "3193",
                "name": "라그나로크X: Next Generation"
            },
            {
                "idx": "3992",
                "name": "실크로드 어게인"
            },
            {
                "idx": "3780",
                "name": "도원결의"
            },
            {
                "idx": "3124",
                "name": "천상비M"
            },
            {
                "idx": "3121",
                "name": "던전앤파이터"
            },
            {
                "idx": "3329",
                "name": "소드 오브 콘발라리아"
            },
            {
                "idx": "3962",
                "name": "DX: 각성자들"
            },
            {
                "idx": "3901",
                "name": "일곱 개의 대죄 오리진"
            },
            {
                "idx": "3969",
                "name": "린:크로니클"
            },
            {
                "idx": "3098",
                "name": "명일방주"
            },
            {
                "idx": "3949",
                "name": "히어로 모험단"
            },
            {
                "idx": "3393",
                "name": "모바일레전드"
            },
            {
                "idx": "3384",
                "name": "창세기전 모바일"
            },
            {
                "idx": "3234",
                "name": "붕괴: 스타레일"
            },
            {
                "idx": "3937",
                "name": "삼국지 왕전"
            },
            {
                "idx": "3803",
                "name": "변신 키우기"
            },
            {
                "idx": "2952",
                "name": "조선협객전M"
            },
            {
                "idx": "3518",
                "name": "뮤 모나크2"
            },
            {
                "idx": "3973",
                "name": "엘트릭스"
            },
            {
                "idx": "2867",
                "name": "메이플스토리"
            },
            {
                "idx": "3852",
                "name": "스타세이비어"
            },
            {
                "idx": "3265",
                "name": "아레스 : 라이즈 오브 가디언즈"
            },
            {
                "idx": "3125",
                "name": "스팀"
            },
            {
                "idx": "4008",
                "name": "레츠고 레전드"
            },
            {
                "idx": "3648",
                "name": "스위칭 히어로즈"
            },
            {
                "idx": "4006",
                "name": "딸깍 다이스"
            },
            {
                "idx": "3953",
                "name": "아너 오브 킹즈(왕자영요 글로벌)"
            },
            {
                "idx": "3859",
                "name": "스텔라 소라"
            },
            {
                "idx": "3925",
                "name": "코드아크"
            },
            {
                "idx": "3274",
                "name": "라스트 워:서바이벌"
            },
            {
                "idx": "3910",
                "name": "귀판오분전"
            },
            {
                "idx": "3743",
                "name": "다크 워 서바이벌"
            },
            {
                "idx": "2751",
                "name": "원신"
            },
            {
                "idx": "2525",
                "name": "바람의나라 : 연"
            },
            {
                "idx": "3112",
                "name": "트리오브세이비어M"
            },
            {
                "idx": "3968",
                "name": "크로스림:오디세이"
            },
            {
                "idx": "3980",
                "name": "2026프로야구GO"
            },
            {
                "idx": "3206",
                "name": "림버스컴퍼니"
            },
            {
                "idx": "3205",
                "name": "어나더던전"
            },
            {
                "idx": "3935",
                "name": "그놈은 드래곤"
            },
            {
                "idx": "3566",
                "name": "픽셀 법사 키우기"
            },
            {
                "idx": "3873",
                "name": "천상비K"
            },
            {
                "idx": "3814",
                "name": "슬레이어 키우기"
            },
            {
                "idx": "3854",
                "name": "건틀렛 : 방치형 액션 RPG"
            },
            {
                "idx": "3598",
                "name": "I9: 인페르노 나인"
            },
            {
                "idx": "3120",
                "name": "탕탕특공대"
            },
            {
                "idx": "4005",
                "name": "라스트 헌터 K: 서울"
            },
            {
                "idx": "3269",
                "name": "다크에덴M with SIA"
            },
            {
                "idx": "3763",
                "name": "섀도우버스 월즈 비욘드"
            },
            {
                "idx": "3997",
                "name": "마블 퓨처파이트"
            },
            {
                "idx": "3828",
                "name": "묵청대도: 바운티"
            },
            {
                "idx": "3109",
                "name": "토치라이트: 인피니트"
            },
            {
                "idx": "3688",
                "name": "카르나크"
            },
            {
                "idx": "3930",
                "name": "Legends Reborn: 마지막 전투"
            },
            {
                "idx": "2846",
                "name": "쿠키런:킹덤"
            },
            {
                "idx": "3695",
                "name": "소울이터 키우기"
            },
            {
                "idx": "3354",
                "name": "소울즈"
            },
            {
                "idx": "3333",
                "name": "달빛조각사: 다크게이머"
            },
            {
                "idx": "3943",
                "name": "세포특공대"
            },
            {
                "idx": "3527",
                "name": "블레이드&소울(블소 / 네오NEO)"
            },
            {
                "idx": "3945",
                "name": "미송자의 노래"
            },
            {
                "idx": "3668",
                "name": "레이싱 마스터"
            },
            {
                "idx": "3567",
                "name": "조선협객전2M"
            },
            {
                "idx": "3784",
                "name": "FC모바일"
            },
            {
                "idx": "3547",
                "name": "에이지 오브 엠파이어 모바일"
            },
            {
                "idx": "3374",
                "name": "리버스: 1999"
            },
            {
                "idx": "3143",
                "name": "마구마구 2023"
            },
            {
                "idx": "3867",
                "name": "와다다 던전런"
            },
            {
                "idx": "3610",
                "name": "나 혼자 만렙 삼국"
            },
            {
                "idx": "3554",
                "name": "주술회전 팬텀 퍼레이드"
            },
            {
                "idx": "2840",
                "name": "데카론M"
            },
            {
                "idx": "3782",
                "name": "악마단 돌겨억!"
            },
            {
                "idx": "2923",
                "name": "블레이드&소울2(블소2)"
            },
            {
                "idx": "3252",
                "name": "다크에덴"
            },
            {
                "idx": "3424",
                "name": "별이되어라2: 베다의 기사들"
            },
            {
                "idx": "3942",
                "name": "우르르 수비대"
            },
            {
                "idx": "3685",
                "name": "컴투스프로야구2026"
            },
            {
                "idx": "3505",
                "name": "미르2 : 깨어난 사북성"
            },
            {
                "idx": "3559",
                "name": "바람의나라 클래식"
            },
            {
                "idx": "3118",
                "name": "카트라이더 러쉬플러스"
            },
            {
                "idx": "3580",
                "name": "패스 오브 엑자일2 (POE2)"
            },
            {
                "idx": "3582",
                "name": "어비스: 데스티니"
            },
            {
                "idx": "3843",
                "name": "돼지 키우는 중입니다"
            },
            {
                "idx": "3645",
                "name": "라그나로크 : Back to Glory"
            },
            {
                "idx": "3987",
                "name": "퇴마 운빨 디펜스"
            },
            {
                "idx": "3083",
                "name": "우마무스메"
            },
            {
                "idx": "3983",
                "name": "판타스틱 베이스볼26"
            },
            {
                "idx": "3672",
                "name": "신궁키우기"
            },
            {
                "idx": "3476",
                "name": "냥냥시노비"
            },
            {
                "idx": "3964",
                "name": "삼국지 패업"
            },
            {
                "idx": "3739",
                "name": "원피스 바운티 러쉬"
            },
            {
                "idx": "3710",
                "name": "킹덤스토리"
            },
            {
                "idx": "3620",
                "name": "겟앰프드키우기"
            },
            {
                "idx": "3903",
                "name": "명일방주: 엔드필드"
            },
            {
                "idx": "3793",
                "name": "아키르: 콜 오브 에시르"
            },
            {
                "idx": "3550",
                "name": "귀혼M"
            },
            {
                "idx": "3950",
                "name": "바이오하자드 서바이벌 유닛"
            },
            {
                "idx": "3517",
                "name": "이스케이프 프롬 타르코프"
            },
            {
                "idx": "3825",
                "name": "드래곤 엠파이어"
            },
            {
                "idx": "3985",
                "name": "갓오브하이스쿨 체인지: 방치형 RPG"
            },
            {
                "idx": "3529",
                "name": "일곱 개의 대죄 키우기"
            },
            {
                "idx": "3573",
                "name": "화산파 키우기"
            },
            {
                "idx": "3908",
                "name": "전우치 키우기 : K 데몬 헌터"
            },
            {
                "idx": "3664",
                "name": "배틀그라운드 모바일"
            },
            {
                "idx": "3451",
                "name": "로블록스"
            },
            {
                "idx": "2891",
                "name": "원펀맨:최강의남자"
            },
            {
                "idx": "3952",
                "name": "심쿵삼국지"
            },
            {
                "idx": "3974",
                "name": "쿠키런: 오븐스매시"
            },
            {
                "idx": "3735",
                "name": "월드 오브 탱크"
            },
            {
                "idx": "3261",
                "name": "브라운더스트2"
            },
            {
                "idx": "3590",
                "name": "옛날바람(MSW)"
            },
            {
                "idx": "3886",
                "name": "유유백서: 격전"
            },
            {
                "idx": "3791",
                "name": "신월동행"
            },
            {
                "idx": "3128",
                "name": "에이펙스 레전드"
            },
            {
                "idx": "3534",
                "name": "탑 히어로즈"
            },
            {
                "idx": "3218",
                "name": "카이온M"
            },
            {
                "idx": "3577",
                "name": "궁수의전설2"
            },
            {
                "idx": "3331",
                "name": "세븐나이츠 키우기"
            },
            {
                "idx": "3846",
                "name": "아스텔리아M"
            },
            {
                "idx": "3383",
                "name": "씰M"
            },
            {
                "idx": "3326",
                "name": "리니지2레볼루션"
            },
            {
                "idx": "3185",
                "name": "랑그릿사"
            },
            {
                "idx": "2671",
                "name": "블루 아카이브"
            },
            {
                "idx": "3749",
                "name": "믹스마스터"
            },
            {
                "idx": "3568",
                "name": "소녀전선2: 망명"
            },
            {
                "idx": "3244",
                "name": "쓰론 앤 리버티(TL)"
            },
            {
                "idx": "3897",
                "name": "전지적 시점: 데몬 삼국"
            },
            {
                "idx": "3150",
                "name": "검은사막"
            },
            {
                "idx": "3920",
                "name": "어비스디아"
            },
            {
                "idx": "2454",
                "name": "킹덤 : 전쟁의불씨"
            },
            {
                "idx": "3720",
                "name": "문명: 연맹의 시대"
            },
            {
                "idx": "3380",
                "name": "리니지2"
            },
            {
                "idx": "3403",
                "name": "레이드 : 그림자의 전설"
            },
            {
                "idx": "3072",
                "name": "언디셈버"
            },
            {
                "idx": "3797",
                "name": "라이즈 신 키우기"
            },
            {
                "idx": "3504",
                "name": "더 라그나로크"
            },
            {
                "idx": "3366",
                "name": "트릭컬 리바이브"
            },
            {
                "idx": "2965",
                "name": "제2의 나라"
            },
            {
                "idx": "3239",
                "name": "알비온 온라인"
            },
            {
                "idx": "3449",
                "name": "젠레스 존 제로"
            },
            {
                "idx": "3940",
                "name": "파이널블레이드"
            },
            {
                "idx": "3658",
                "name": "패시브 마스터 키우기"
            },
            {
                "idx": "3902",
                "name": "던전슬래셔"
            },
            {
                "idx": "3456",
                "name": "일곱 개의 대죄: GRAND CROSS"
            },
            {
                "idx": "3669",
                "name": "삼국지:전란"
            },
            {
                "idx": "3847",
                "name": "냥냥기사단"
            },
            {
                "idx": "3073",
                "name": "달빛조각사"
            },
            {
                "idx": "3921",
                "name": "히어로 클래시"
            },
            {
                "idx": "3768",
                "name": "킹 오브 파이터 AFK"
            },
            {
                "idx": "3131",
                "name": "디지몬마스터즈"
            },
            {
                "idx": "3946",
                "name": "에르피스"
            },
            {
                "idx": "3795",
                "name": "킹샷: Kingshot"
            },
            {
                "idx": "3171",
                "name": "닌텐도"
            },
            {
                "idx": "3773",
                "name": "머머리 퀘스트"
            },
            {
                "idx": "3874",
                "name": "미르의 전설2:레드나이트"
            },
            {
                "idx": "3772",
                "name": "메카 어셈블:좀비 스웜"
            },
            {
                "idx": "3778",
                "name": "미르2:언데드"
            },
            {
                "idx": "3837",
                "name": "뮤: 포켓 나이츠"
            },
            {
                "idx": "3560",
                "name": "외계인은 배고파"
            },
            {
                "idx": "3745",
                "name": "드래곤소드"
            },
            {
                "idx": "3928",
                "name": "eFootball™"
            },
            {
                "idx": "3933",
                "name": "블러드 앤 소울"
            },
            {
                "idx": "3207",
                "name": "하이큐!! TOUCH THE DREAM"
            },
            {
                "idx": "3469",
                "name": "드래곤볼 Z 폭렬격전"
            },
            {
                "idx": "3161",
                "name": "마인크래프트"
            },
            {
                "idx": "3608",
                "name": "로스트 소드"
            },
            {
                "idx": "3604",
                "name": "발할라 서바이벌"
            },
            {
                "idx": "2734",
                "name": "R2M"
            },
            {
                "idx": "3307",
                "name": "마비노기 영웅전"
            },
            {
                "idx": "2781",
                "name": "세븐나이츠2"
            },
            {
                "idx": "3959",
                "name": "포켓마스터 : 각성"
            },
            {
                "idx": "3701",
                "name": "갓깨비 키우기"
            },
            {
                "idx": "3887",
                "name": "미드조선"
            },
            {
                "idx": "3975",
                "name": "붉은사막"
            },
            {
                "idx": "3079",
                "name": "루나 모바일"
            },
            {
                "idx": "3259",
                "name": "신의탑 : 새로운 세계"
            },
            {
                "idx": "3970",
                "name": "갓오브하이스쿨"
            },
            {
                "idx": "3545",
                "name": "저니 오브 모나크"
            },
            {
                "idx": "3898",
                "name": "스칼렛 판타지아"
            },
            {
                "idx": "3540",
                "name": "메틴 : 파멸의 서곡"
            },
            {
                "idx": "3965",
                "name": "새비지 서바이벌: 쥬라기 아일"
            },
            {
                "idx": "3947",
                "name": "헤븐헬즈"
            },
            {
                "idx": "3893",
                "name": "연운"
            },
            {
                "idx": "3204",
                "name": "로스트시티:제로"
            },
            {
                "idx": "3475",
                "name": "빵빵 좀비단"
            },
            {
                "idx": "3309",
                "name": "낚시의 신: 크루"
            },
            {
                "idx": "3766",
                "name": "다크에덴 키우기"
            },
            {
                "idx": "3225",
                "name": "바람의나라"
            },
            {
                "idx": "3233",
                "name": "어둠의전설"
            },
            {
                "idx": "3642",
                "name": "캣 히어로 : 방치형 RPG"
            },
            {
                "idx": "3293",
                "name": "이터널 리턴"
            },
            {
                "idx": "3551",
                "name": "포켓몬 카드 게임 Pocket"
            },
            {
                "idx": "3632",
                "name": "델타포스"
            },
            {
                "idx": "3310",
                "name": "포트리스 사가: AFK RPG"
            },
            {
                "idx": "3280",
                "name": "광전사 키우기"
            },
            {
                "idx": "3748",
                "name": "붉은보석"
            },
            {
                "idx": "3525",
                "name": "월드 오브 워크래프트(와우)"
            },
            {
                "idx": "3955",
                "name": "요괴잡이소대 X 대환장 MMORPG"
            },
            {
                "idx": "3747",
                "name": "라그나로크 온라인"
            },
            {
                "idx": "3458",
                "name": "페이트 그랜드 오더"
            },
            {
                "idx": "3557",
                "name": "초월자 키우기"
            },
            {
                "idx": "3638",
                "name": "질풍삼국"
            },
            {
                "idx": "3761",
                "name": "콩콩던전"
            },
            {
                "idx": "3684",
                "name": "컴투스프로야구 for 매니저 LIVE 2025"
            },
            {
                "idx": "3074",
                "name": "마법로 기사25길"
            },
            {
                "idx": "3849",
                "name": "정령킹 키우기"
            },
            {
                "idx": "3482",
                "name": "온라인 삼국지2"
            },
            {
                "idx": "3881",
                "name": "열혈강호 화룡전"
            },
            {
                "idx": "3521",
                "name": "AFK : 새로운 여정"
            },
            {
                "idx": "3503",
                "name": "퇴마검사 키우기"
            },
            {
                "idx": "3744",
                "name": "에테리아 리스타트"
            },
            {
                "idx": "3924",
                "name": "설레 삼국:미인계"
            },
            {
                "idx": "3746",
                "name": "드래곤볼 레전즈"
            },
            {
                "idx": "3899",
                "name": "쿠노이치 키우기"
            },
            {
                "idx": "3589",
                "name": "Grand Theft Auto V (GTA5)"
            },
            {
                "idx": "3936",
                "name": "다크디셈버"
            },
            {
                "idx": "3822",
                "name": "괴수 8호 THE GAME"
            },
            {
                "idx": "3410",
                "name": "까부리: 조선퇴마사 키우기"
            },
            {
                "idx": "3913",
                "name": "포지 마스터"
            },
            {
                "idx": "3628",
                "name": "애쉬앤베일"
            },
            {
                "idx": "3876",
                "name": "이블헌터 타이쿤"
            },
            {
                "idx": "3297",
                "name": "스노우 브레이크: 포비든 존"
            },
            {
                "idx": "3126",
                "name": "붕괴3rd"
            },
            {
                "idx": "3722",
                "name": "암살자 키우기"
            },
            {
                "idx": "3436",
                "name": "겟앰프드"
            },
            {
                "idx": "3499",
                "name": "스페셜포스"
            },
            {
                "idx": "3918",
                "name": "모범 놀이터： 타락자들"
            },
            {
                "idx": "3142",
                "name": "라이즈 오브 킹덤즈"
            },
            {
                "idx": "3719",
                "name": "실버 앤 블러드"
            },
            {
                "idx": "3904",
                "name": "블루 프로토콜: 스타 레조넌스"
            },
            {
                "idx": "3490",
                "name": "쿠키런: 모험의 탑"
            },
            {
                "idx": "3892",
                "name": "삼국지:리버스"
            },
            {
                "idx": "3838",
                "name": "미친 타워가 되었다"
            },
            {
                "idx": "3288",
                "name": "무제: 십대고수"
            },
            {
                "idx": "3254",
                "name": "마비노기"
            },
            {
                "idx": "3102",
                "name": "전생슬"
            },
            {
                "idx": "3548",
                "name": "히어로즈 키우기"
            },
            {
                "idx": "3870",
                "name": "레드문M"
            },
            {
                "idx": "3922",
                "name": "킹방치: 빵지의 제왕"
            },
            {
                "idx": "3816",
                "name": "천지겁"
            },
            {
                "idx": "3917",
                "name": "천만여신 : 가장 치명적인 AFK"
            },
            {
                "idx": "3579",
                "name": "그만 쫌 쳐들어와"
            },
            {
                "idx": "3184",
                "name": "달토끼 키우기"
            },
            {
                "idx": "3896",
                "name": "본 어게인: 해골히어로"
            },
            {
                "idx": "3851",
                "name": "듀엣 나이트 어비스"
            },
            {
                "idx": "3712",
                "name": "아드"
            },
            {
                "idx": "3790",
                "name": "랜드 오브 제일"
            },
            {
                "idx": "3916",
                "name": "린M:잊혀진 유산"
            },
            {
                "idx": "3890",
                "name": "판타테일"
            },
            {
                "idx": "3463",
                "name": "해리포터: 깨어난 마법"
            },
            {
                "idx": "3138",
                "name": "엘소드"
            },
            {
                "idx": "3725",
                "name": "MLB 클러치 히트 베이스볼 25"
            },
            {
                "idx": "3388",
                "name": "더블유: 크로스월드"
            },
            {
                "idx": "3277",
                "name": "랜덤 다이스"
            },
            {
                "idx": "3256",
                "name": "미르2: 왕의 귀환"
            },
            {
                "idx": "3389",
                "name": "아이모"
            },
            {
                "idx": "3198",
                "name": "에버소울"
            },
            {
                "idx": "3199",
                "name": "아바타라"
            },
            {
                "idx": "3398",
                "name": "땡땡 마법사"
            },
            {
                "idx": "3457",
                "name": "유희왕 마스터 듀얼"
            },
            {
                "idx": "3808",
                "name": "호라이즌 워커"
            },
            {
                "idx": "3809",
                "name": "스매시 레전드"
            },
            {
                "idx": "3894",
                "name": "팰리팰리"
            },
            {
                "idx": "3657",
                "name": "붉은 신화 : 나타"
            },
            {
                "idx": "3611",
                "name": "99강화 나무몽둥이 : 키우기"
            },
            {
                "idx": "3394",
                "name": "옥토패스 트래블러: 대륙의 패자"
            },
            {
                "idx": "3889",
                "name": "헤이즈 리버브"
            },
            {
                "idx": "3530",
                "name": "강호영웅"
            },
            {
                "idx": "3868",
                "name": "로스트아크 모바일"
            },
            {
                "idx": "3381",
                "name": "CoA: 아틀란의 크리스탈"
            },
            {
                "idx": "3777",
                "name": "엘피스 전기: 소울링"
            },
            {
                "idx": "3196",
                "name": "블레이드 키우기"
            },
            {
                "idx": "3247",
                "name": "WOS: 화이트 아웃 서바이벌"
            },
            {
                "idx": "3168",
                "name": "슬램덩크"
            },
            {
                "idx": "3818",
                "name": "뮤 온라인"
            },
            {
                "idx": "3600",
                "name": "서머너즈 워: 러쉬"
            },
            {
                "idx": "3689",
                "name": "쿠키런 for kakao"
            },
            {
                "idx": "3435",
                "name": "서머너즈 워: 천공의 아레나"
            },
            {
                "idx": "3644",
                "name": "스피릿 테일즈"
            },
            {
                "idx": "3676",
                "name": "픽미픽미 영웅"
            },
            {
                "idx": "3552",
                "name": "메카아라시"
            },
            {
                "idx": "3356",
                "name": "드래곤에어 : 침묵의 신"
            },
            {
                "idx": "3107",
                "name": "대항해시대 오리진"
            },
            {
                "idx": "3753",
                "name": "왔더벅: 미니 삼국"
            },
            {
                "idx": "3767",
                "name": "붉은도시"
            },
            {
                "idx": "3820",
                "name": "가디스오더"
            },
            {
                "idx": "3319",
                "name": "닥사RPG : 파밍용사키우기"
            },
            {
                "idx": "3775",
                "name": "에그몬 월드:저니"
            },
            {
                "idx": "3602",
                "name": "귀신과 함께"
            },
            {
                "idx": "3501",
                "name": "아르카나 블레이드 : 방치형 RPG"
            },
            {
                "idx": "3770",
                "name": "미니언100"
            },
            {
                "idx": "3840",
                "name": "아이러브커피 키우기"
            },
            {
                "idx": "3249",
                "name": "라테일"
            },
            {
                "idx": "3765",
                "name": "무한의 사신키우기 : 회귀한 사신"
            },
            {
                "idx": "3819",
                "name": "라그나로크 아이들 어드벤처 PLUS"
            },
            {
                "idx": "3211",
                "name": "마블스냅"
            },
            {
                "idx": "3698",
                "name": "묵혼온라인"
            },
            {
                "idx": "3117",
                "name": "카운터사이드"
            },
            {
                "idx": "3453",
                "name": "다크M"
            },
            {
                "idx": "3812",
                "name": "영웅줍줍 장비줍줍"
            },
            {
                "idx": "3798",
                "name": "페이트 워"
            },
            {
                "idx": "3541",
                "name": "고고머핀"
            },
            {
                "idx": "3654",
                "name": "다이너스티 레전드 2 : 무쌍전란"
            },
            {
                "idx": "3405",
                "name": "천마키우기"
            },
            {
                "idx": "3509",
                "name": "미르의 전설2: 기연"
            },
            {
                "idx": "3609",
                "name": "미르2: 뉴킹덤"
            },
            {
                "idx": "3583",
                "name": "로엠 짝퉁겜"
            },
            {
                "idx": "3599",
                "name": "레조넌스"
            },
            {
                "idx": "2425",
                "name": "A3: 스틸얼라이브"
            },
            {
                "idx": "3132",
                "name": "프린세스 커넥트"
            },
            {
                "idx": "3788",
                "name": "트라이워M"
            },
            {
                "idx": "3489",
                "name": "쿠로코의 농구"
            },
            {
                "idx": "3823",
                "name": "에타 크로니클"
            },
            {
                "idx": "3810",
                "name": "각성소녀: 욕망의 여정"
            },
            {
                "idx": "3667",
                "name": "운빨돌격대"
            },
            {
                "idx": "3647",
                "name": "비스트 로드: The New Land"
            },
            {
                "idx": "3461",
                "name": "킹갓캐슬"
            },
            {
                "idx": "3806",
                "name": "스톤에이지: 펫월드"
            },
            {
                "idx": "3556",
                "name": "카피바라 Go!"
            },
            {
                "idx": "3526",
                "name": "월드 오브 워크래프트 클래식(와우 클래식)"
            },
            {
                "idx": "3575",
                "name": "운명M"
            },
            {
                "idx": "3572",
                "name": "킹 아서: 레전드 라이즈"
            },
            {
                "idx": "3702",
                "name": "삼국지 올스타 : 방치형 RPG"
            },
            {
                "idx": "3750",
                "name": "유희왕 듀얼링크스"
            },
            {
                "idx": "3769",
                "name": "던전앤브레이커"
            },
            {
                "idx": "3727",
                "name": "모에라이: 운명의 계약"
            },
            {
                "idx": "3779",
                "name": "인생존망겜"
            },
            {
                "idx": "3409",
                "name": "신미르"
            },
            {
                "idx": "3100",
                "name": "퍼니싱:그레이 레이븐"
            },
            {
                "idx": "3561",
                "name": "바람의 드래군M"
            },
            {
                "idx": "3752",
                "name": "리버스 블루x리버스 엔드"
            },
            {
                "idx": "3317",
                "name": "데몬스쿼드 키우기 : 팀 방치형 RPG"
            },
            {
                "idx": "3522",
                "name": "영웅전설: 가가브 트릴로지"
            },
            {
                "idx": "3624",
                "name": "아크: 리버스"
            },
            {
                "idx": "3729",
                "name": "냄비뚜껑용병단"
            },
            {
                "idx": "3251",
                "name": "픽셀 히어로"
            },
            {
                "idx": "3679",
                "name": "엉망 특공대 - 8282회 뽑기 증정"
            },
            {
                "idx": "3601",
                "name": "비지 세이비어"
            },
            {
                "idx": "3191",
                "name": "프리스타일2"
            },
            {
                "idx": "3493",
                "name": "카드캡터 체리: 추억의 열쇠"
            },
            {
                "idx": "3092",
                "name": "아키에이지"
            },
            {
                "idx": "3382",
                "name": "라그나로크 비긴즈"
            },
            {
                "idx": "3740",
                "name": "퍼즐 오브 Z"
            },
            {
                "idx": "3755",
                "name": "패스 오브 라이징"
            },
            {
                "idx": "3562",
                "name": "삼국블레이드 키우기"
            },
            {
                "idx": "3625",
                "name": "특급주술대전 : 4인전"
            },
            {
                "idx": "3362",
                "name": "원피스 트레저 크루즈"
            },
            {
                "idx": "3158",
                "name": "아스가르드"
            },
            {
                "idx": "3656",
                "name": "성녀 키우기"
            },
            {
                "idx": "3506",
                "name": "미니히어로즈: Reborn"
            },
            {
                "idx": "3631",
                "name": "카르페디엠 온라인"
            },
            {
                "idx": "3700",
                "name": "앵커패닉"
            },
            {
                "idx": "3715",
                "name": "다키스트 데이즈"
            },
            {
                "idx": "3091",
                "name": "미르의전설3"
            },
            {
                "idx": "3390",
                "name": "미르2: 레드"
            },
            {
                "idx": "3697",
                "name": "던전헌터 6 : 각성"
            },
            {
                "idx": "3119",
                "name": "레오네: 레전드 오브 네버랜드"
            },
            {
                "idx": "3709",
                "name": "키워용: 도굴라이프"
            },
            {
                "idx": "3242",
                "name": "블랙클로버 모바일"
            },
            {
                "idx": "3692",
                "name": "타이니팜 리마스터"
            },
            {
                "idx": "3536",
                "name": "감자슉슈슉"
            },
            {
                "idx": "3439",
                "name": "페르소나5: 더 팬텀 X"
            },
            {
                "idx": "3441",
                "name": "노바삼국"
            },
            {
                "idx": "3099",
                "name": "가디언 테일즈"
            },
            {
                "idx": "3332",
                "name": "워크래프트 럼블"
            },
            {
                "idx": "3612",
                "name": "우가우가! 대모험"
            },
            {
                "idx": "2921",
                "name": "기적의검"
            },
            {
                "idx": "3085",
                "name": "뮤 오리진3"
            },
            {
                "idx": "3621",
                "name": "이세계 판타지 라이프"
            },
            {
                "idx": "3687",
                "name": "신화급 귀속 아이템을 손에 넣었다 : 방치형 RPG"
            },
            {
                "idx": "3422",
                "name": "서먼헌터 키우기"
            },
            {
                "idx": "3651",
                "name": "트리니티 가디언즈 : 혼돈의 탑"
            },
            {
                "idx": "3660",
                "name": "도쿄 구울: Awakening"
            },
            {
                "idx": "2920",
                "name": "삼국지 전략판"
            },
            {
                "idx": "3443",
                "name": "미르2:승자위왕"
            },
            {
                "idx": "3592",
                "name": "리메멘토 - 하얀 그림자"
            },
            {
                "idx": "3507",
                "name": "메탈슬러그: 각성"
            },
            {
                "idx": "3597",
                "name": "갓앤데몬"
            },
            {
                "idx": "3479",
                "name": "그랑사가 키우기: 나이츠x나이츠"
            },
            {
                "idx": "3442",
                "name": "버블파이터"
            },
            {
                "idx": "3413",
                "name": "소울웨폰 키우기"
            },
            {
                "idx": "3203",
                "name": "헤븐 번즈 레드"
            },
            {
                "idx": "3565",
                "name": "범: 낭만의 시대"
            },
            {
                "idx": "3340",
                "name": "블러드 헌터: 도깨비전"
            },
            {
                "idx": "3626",
                "name": "트라이브 나인 / TRIBE NINE"
            },
            {
                "idx": "3553",
                "name": "에이펙스 걸스"
            },
            {
                "idx": "3539",
                "name": "라그하임"
            },
            {
                "idx": "3488",
                "name": "삼국지 러쉬 Origins"
            },
            {
                "idx": "3596",
                "name": "워로드 온라인"
            },
            {
                "idx": "3603",
                "name": "오버로드: 나자릭의 왕"
            },
            {
                "idx": "3134",
                "name": "AFK아레나"
            },
            {
                "idx": "3358",
                "name": "몬스터헌터 나우"
            },
            {
                "idx": "3569",
                "name": "테일즈런너RPG"
            },
            {
                "idx": "3250",
                "name": "테일즈위버"
            },
            {
                "idx": "3468",
                "name": "워처 오브 렐름"
            },
            {
                "idx": "3570",
                "name": "별빛 여행자"
            },
            {
                "idx": "3447",
                "name": "로스트던전"
            },
            {
                "idx": "3474",
                "name": "라테일 플러스"
            },
            {
                "idx": "3253",
                "name": "에테르 게이저"
            },
            {
                "idx": "3248",
                "name": "둠스데이: 라스트 서바이버"
            },
            {
                "idx": "3532",
                "name": "조선 이변"
            },
            {
                "idx": "3262",
                "name": "삼국 올스타"
            },
            {
                "idx": "3494",
                "name": "우당탕탕 탐험대: 방치형 RPG"
            },
            {
                "idx": "3232",
                "name": "제5인격"
            },
            {
                "idx": "3320",
                "name": "개판오분전"
            },
            {
                "idx": "3502",
                "name": "퍼스트 디센던트"
            },
            {
                "idx": "3414",
                "name": "팰월드"
            },
            {
                "idx": "3266",
                "name": "아카디아M"
            },
            {
                "idx": "3543",
                "name": "나만없어 드래곤"
            },
            {
                "idx": "3090",
                "name": "미르의전설2"
            },
            {
                "idx": "3123",
                "name": "뉴럴 클라우드"
            },
            {
                "idx": "3122",
                "name": "라스트 클라우디아"
            },
            {
                "idx": "3483",
                "name": "에코칼립스: 진홍의 서약"
            },
            {
                "idx": "3434",
                "name": "리벤저:다크니스"
            },
            {
                "idx": "3538",
                "name": "멍멍삼국"
            },
            {
                "idx": "3535",
                "name": "이세계 삼국지"
            },
            {
                "idx": "3278",
                "name": "엘리멘탈 : 2DMMORPG"
            },
            {
                "idx": "3477",
                "name": "매니악M"
            },
            {
                "idx": "3426",
                "name": "스타시드: 아스니아 트리거"
            },
            {
                "idx": "3460",
                "name": "모두의 마블"
            },
            {
                "idx": "3467",
                "name": "하이큐!! FLY HIGH"
            },
            {
                "idx": "3432",
                "name": "제로나인"
            },
            {
                "idx": "3472",
                "name": "세라: 이터널스"
            },
            {
                "idx": "3160",
                "name": "리본: 사북성 결전"
            },
            {
                "idx": "3419",
                "name": "갓레이드"
            },
            {
                "idx": "3480",
                "name": "캣 판타지"
            },
            {
                "idx": "3308",
                "name": "카운터 스트라이크(카스)"
            },
            {
                "idx": "3455",
                "name": "크리스탈 나이츠"
            },
            {
                "idx": "3421",
                "name": "검방녀키우기"
            },
            {
                "idx": "3238",
                "name": "와일드헌트"
            },
            {
                "idx": "3416",
                "name": "삼켜라 드래곤"
            },
            {
                "idx": "3349",
                "name": "스트리트 파이터: 듀얼"
            },
            {
                "idx": "3082",
                "name": "신의탑M : 위대한 여정"
            },
            {
                "idx": "3397",
                "name": "지천"
            },
            {
                "idx": "3217",
                "name": "디스라이트"
            },
            {
                "idx": "3146",
                "name": "아르케랜드"
            },
            {
                "idx": "3089",
                "name": "천애명월도M"
            },
            {
                "idx": "3396",
                "name": "유령기사 키우기"
            },
            {
                "idx": "3369",
                "name": "카발 모바일 with SIA"
            },
            {
                "idx": "2839",
                "name": "그랑사가"
            },
            {
                "idx": "3291",
                "name": "퀸즈나이츠"
            },
            {
                "idx": "3375",
                "name": "도쿄 구울: Break the Chains"
            },
            {
                "idx": "3106",
                "name": "서머너즈 워: 크로니클"
            },
            {
                "idx": "3086",
                "name": "프로젝트 세카이"
            },
            {
                "idx": "3346",
                "name": "빛의 계승자: 이클립스"
            },
            {
                "idx": "3226",
                "name": "작혼"
            },
            {
                "idx": "2522",
                "name": "라그나로크 오리진"
            },
            {
                "idx": "3296",
                "name": "그랜드크로스: 에이지오브타이탄"
            },
            {
                "idx": "3344",
                "name": "십이지천2M"
            },
            {
                "idx": "3316",
                "name": "던만추 배틀 크로니클"
            },
            {
                "idx": "3306",
                "name": "울프 게임: 더 와일드 킹덤"
            },
            {
                "idx": "3201",
                "name": "카트라이더 드리프트"
            },
            {
                "idx": "3075",
                "name": "뮤 아크엔젤"
            },
            {
                "idx": "3194",
                "name": "카오스 포털: 저승사자"
            },
            {
                "idx": "3264",
                "name": "수삼국"
            },
            {
                "idx": "3221",
                "name": "소녀세계"
            },
            {
                "idx": "3272",
                "name": "무명 기사단"
            },
            {
                "idx": "3257",
                "name": "언던"
            },
            {
                "idx": "3110",
                "name": "DK Mobile: 제네시스"
            },
            {
                "idx": "2900",
                "name": "DK모바일 THE ORIGIN"
            },
            {
                "idx": "3145",
                "name": "히어로즈테일즈"
            },
            {
                "idx": "3103",
                "name": "타워 오브 판타지"
            },
            {
                "idx": "3104",
                "name": "블레스 이터널"
            },
            {
                "idx": "3041",
                "name": "심포니 오브 에픽"
            },
            {
                "idx": "3130",
                "name": "이터널트리"
            },
            {
                "idx": "3094",
                "name": "헌터W"
            },
            {
                "idx": "3101",
                "name": "미니어스"
            },
            {
                "idx": "3114",
                "name": "무기미도"
            },
            {
                "idx": "3115",
                "name": "메멘토 모리"
            },
            {
                "idx": "3137",
                "name": "월드플리퍼"
            },
            {
                "idx": "3139",
                "name": "나의 히어로 아카데미아"
            },
            {
                "idx": "3144",
                "name": "키메라랜드"
            },
            {
                "idx": "3152",
                "name": "SOS : 스테이트 오브 서바이벌"
            },
            {
                "idx": "3157",
                "name": "애니팡4"
            },
            {
                "idx": "3162",
                "name": "아바온라인"
            },
            {
                "idx": "3179",
                "name": "서머너즈 워 : 백년 전쟁"
            },
            {
                "idx": "3180",
                "name": "마법 소녀 키우기"
            },
            {
                "idx": "3183",
                "name": "클래시 오브 킹즈"
            },
            {
                "idx": "3190",
                "name": "엑자일"
            },
            {
                "idx": "3195",
                "name": "십이지천M 오리진"
            },
            {
                "idx": "3209",
                "name": "닌자 머스트 다이"
            },
            {
                "idx": "3222",
                "name": "삼국패황전"
            },
            {
                "idx": "3231",
                "name": "데미안 전기"
            },
            {
                "idx": "3236",
                "name": "워프레임"
            },
            {
                "idx": "3246",
                "name": "세비지M"
            },
            {
                "idx": "3255",
                "name": "오늘도 레벨업"
            },
            {
                "idx": "3260",
                "name": "원펀맨:영웅의 길"
            },
            {
                "idx": "3276",
                "name": "삼국지:무쌍전역"
            },
            {
                "idx": "3281",
                "name": "이세계 대장장이 키우기"
            },
            {
                "idx": "3287",
                "name": "리버스 히어로즈 : 혼돈삼국"
            },
            {
                "idx": "3290",
                "name": "파트롱2:컨트랙트"
            },
            {
                "idx": "3292",
                "name": "검풍"
            },
            {
                "idx": "3294",
                "name": "씰온라인"
            },
            {
                "idx": "3299",
                "name": "비질란테"
            },
            {
                "idx": "3300",
                "name": "별빛기사 키우기"
            },
            {
                "idx": "3301",
                "name": "산해 판타지"
            },
            {
                "idx": "3304",
                "name": "포켓몬 슬립"
            },
            {
                "idx": "3305",
                "name": "더프레이"
            },
            {
                "idx": "3311",
                "name": "미르2M : 더 드래곤 킨"
            },
            {
                "idx": "3312",
                "name": "이모탈 슬레이어 키우기"
            },
            {
                "idx": "3318",
                "name": "데스티니 메이든 CCG"
            },
            {
                "idx": "3324",
                "name": "말세의검녀"
            },
            {
                "idx": "3327",
                "name": "던랜드(dawnlands)"
            },
            {
                "idx": "3330",
                "name": "라그나로크V: 부활"
            },
            {
                "idx": "3345",
                "name": "브릭시티"
            },
            {
                "idx": "3347",
                "name": "썩쏘 또 키우기"
            },
            {
                "idx": "3348",
                "name": "칼리버리그"
            },
            {
                "idx": "3350",
                "name": "이카루스M: 길드워"
            },
            {
                "idx": "3351",
                "name": "칼리버 기사단"
            },
            {
                "idx": "3355",
                "name": "엑스토시움(EXTOCIUM)"
            },
            {
                "idx": "3357",
                "name": "다크앤다커"
            },
            {
                "idx": "3359",
                "name": "원더킹"
            },
            {
                "idx": "3373",
                "name": "종말의 발할라"
            },
            {
                "idx": "3378",
                "name": "아르미스"
            },
            {
                "idx": "3407",
                "name": "패스 오브 엑자일1 (POE1)"
            },
            {
                "idx": "3417",
                "name": "999위 용사"
            },
            {
                "idx": "3423",
                "name": "엑스 아스트리스"
            },
            {
                "idx": "3425",
                "name": "쿠키런: 마녀의 성"
            },
            {
                "idx": "3430",
                "name": "라스트 에포크"
            },
            {
                "idx": "3450",
                "name": "차칸게임"
            },
            {
                "idx": "3452",
                "name": "극락"
            },
            {
                "idx": "3462",
                "name": "뿌요뿌요!! 퀘스트"
            },
            {
                "idx": "3464",
                "name": "어나더 에덴"
            },
            {
                "idx": "3466",
                "name": "소드마스터 스토리"
            },
            {
                "idx": "3470",
                "name": "파티 히어로즈"
            },
            {
                "idx": "3471",
                "name": "히어로킹: 용사를 부탁해 RE:BOOT"
            },
            {
                "idx": "3473",
                "name": "혼(Horn)"
            },
            {
                "idx": "3481",
                "name": "레알팜"
            },
            {
                "idx": "3485",
                "name": "클래스"
            },
            {
                "idx": "3487",
                "name": "딜루전: 그림자 영웅단"
            },
            {
                "idx": "3492",
                "name": "샷온라인"
            },
            {
                "idx": "3497",
                "name": "수호자 키우기"
            },
            {
                "idx": "3498",
                "name": "뮈렌: 천년의 여정"
            },
            {
                "idx": "3510",
                "name": "가디언즈 디펜스 워"
            },
            {
                "idx": "3511",
                "name": "드림삼국"
            },
            {
                "idx": "3520",
                "name": "십이지천M The One"
            },
            {
                "idx": "3528",
                "name": "스톰게이트"
            },
            {
                "idx": "3531",
                "name": "DK온라인"
            },
            {
                "idx": "3542",
                "name": "블레이드M"
            },
            {
                "idx": "3558",
                "name": "매드메탈 월드"
            },
            {
                "idx": "3563",
                "name": "포켓히어로"
            },
            {
                "idx": "3571",
                "name": "슈퍼바이브"
            },
            {
                "idx": "3574",
                "name": "스트리노바"
            },
            {
                "idx": "3578",
                "name": "큐플레이"
            },
            {
                "idx": "3581",
                "name": "세라핌 사가: 날개소녀 키우기"
            },
            {
                "idx": "3584",
                "name": "로스트W: 폴른킹덤"
            },
            {
                "idx": "3585",
                "name": "월드 크러쉬:히어로 포스"
            },
            {
                "idx": "3586",
                "name": "인피니티 니키"
            },
            {
                "idx": "3587",
                "name": "머지머지 디펜스"
            },
            {
                "idx": "3588",
                "name": "마블 라이벌즈"
            },
            {
                "idx": "3591",
                "name": "엔에이지"
            },
            {
                "idx": "3593",
                "name": "픽셀 영웅전설 : 방치형 파티플RPG"
            },
            {
                "idx": "3594",
                "name": "미니디펜더스"
            },
            {
                "idx": "3606",
                "name": "유키:미니월드"
            },
            {
                "idx": "3607",
                "name": "블루 아이즈 : 길드 마스터"
            },
            {
                "idx": "3622",
                "name": "프리스타일1"
            },
            {
                "idx": "3623",
                "name": "십이지천M W"
            },
            {
                "idx": "3627",
                "name": "아레나 브레이크아웃"
            },
            {
                "idx": "3629",
                "name": "프리스톤테일"
            },
            {
                "idx": "3630",
                "name": "클래시 오브 스론 : 여정"
            },
            {
                "idx": "3633",
                "name": "전혼M"
            },
            {
                "idx": "3634",
                "name": "구룡쟁패"
            },
            {
                "idx": "3635",
                "name": "어리즌앤츠"
            },
            {
                "idx": "3636",
                "name": "나혼자만렙키우기"
            },
            {
                "idx": "3637",
                "name": "뉴 월드: 에테르눔"
            },
            {
                "idx": "3643",
                "name": "드래곤즈 토템"
            },
            {
                "idx": "3649",
                "name": "데몬 소서리스 키우기"
            },
            {
                "idx": "3655",
                "name": "와르르 공성대"
            },
            {
                "idx": "3659",
                "name": "나 혼자 네크로맨서"
            },
            {
                "idx": "3661",
                "name": "트리모 히어로즈"
            },
            {
                "idx": "3662",
                "name": "스컬디펜스"
            },
            {
                "idx": "3665",
                "name": "나이트 온라인"
            },
            {
                "idx": "3666",
                "name": "LUDUS"
            },
            {
                "idx": "3670",
                "name": "Kingshot"
            },
            {
                "idx": "3673",
                "name": "원스 휴먼"
            },
            {
                "idx": "3674",
                "name": "정복의 바다: 생존 서바이벌 해적 RPG"
            },
            {
                "idx": "3675",
                "name": "천상비"
            },
            {
                "idx": "3678",
                "name": "데빌 서머너 : 소환사 키우기"
            },
            {
                "idx": "3680",
                "name": "퍼스트 버서커: 카잔"
            },
            {
                "idx": "3682",
                "name": "아수라장"
            },
            {
                "idx": "3686",
                "name": "먼작귀 포켓"
            },
            {
                "idx": "3690",
                "name": "이브 온라인"
            },
            {
                "idx": "3691",
                "name": "던전 시스터즈 : 픽셀 방치형 RPG"
            },
            {
                "idx": "3693",
                "name": "마작일번가"
            },
            {
                "idx": "3694",
                "name": "열혈강호 온라인"
            },
            {
                "idx": "3696",
                "name": "로한 온라인"
            },
            {
                "idx": "3703",
                "name": "위드M"
            },
            {
                "idx": "3704",
                "name": "니다온라인"
            },
            {
                "idx": "3705",
                "name": "어쩌다 이세계 마을 생활"
            },
            {
                "idx": "3706",
                "name": "eFootball"
            },
            {
                "idx": "3707",
                "name": "언리미티드 파이터"
            },
            {
                "idx": "3708",
                "name": "엑시스 블레이드"
            },
            {
                "idx": "3711",
                "name": "원스 휴먼 모바일"
            },
            {
                "idx": "3713",
                "name": "Mistfall Hunter"
            },
            {
                "idx": "3716",
                "name": "포링 키우기: 방치형 RPG"
            },
            {
                "idx": "3717",
                "name": "슈빌 x 슬라임 300년"
            },
            {
                "idx": "3723",
                "name": "MLB 9이닝스 26"
            },
            {
                "idx": "3724",
                "name": "MLB 9이닝스 GM"
            },
            {
                "idx": "3726",
                "name": "일랜시아"
            },
            {
                "idx": "3728",
                "name": "카발온라인"
            },
            {
                "idx": "3730",
                "name": "오늘도 우라라 원시 헌팅 라이프"
            },
            {
                "idx": "3732",
                "name": "삼국장수 Go!"
            },
            {
                "idx": "3733",
                "name": "건쉽배틀 토탈워페어"
            },
            {
                "idx": "3734",
                "name": "라스트 포트리스"
            },
            {
                "idx": "3736",
                "name": "데블W"
            },
            {
                "idx": "3737",
                "name": "여소: 여신이 소녀가 되었다"
            },
            {
                "idx": "3738",
                "name": "시티레이서"
            },
            {
                "idx": "3741",
                "name": "발키리 히어로 키우기"
            },
            {
                "idx": "3742",
                "name": "루니아Z"
            },
            {
                "idx": "3751",
                "name": "삼국지RED"
            },
            {
                "idx": "3756",
                "name": "포트나이트"
            },
            {
                "idx": "3762",
                "name": "나혼자 클리어"
            },
            {
                "idx": "3764",
                "name": "우당탕탕 삼국지"
            },
            {
                "idx": "3774",
                "name": "사무라이 쇼다운 R"
            },
            {
                "idx": "3776",
                "name": "바이킹 라이즈"
            },
            {
                "idx": "3781",
                "name": "카오스 디펜스 머지?"
            },
            {
                "idx": "3783",
                "name": "블리치 브레이브 소울즈"
            },
            {
                "idx": "3785",
                "name": "마교회귀"
            },
            {
                "idx": "3786",
                "name": "윈드슬레이어"
            },
            {
                "idx": "3787",
                "name": "삼국지 오리진2: 적벽대전"
            },
            {
                "idx": "3789",
                "name": "파이널판타지14"
            },
            {
                "idx": "3799",
                "name": "군주 온라인"
            },
            {
                "idx": "3800",
                "name": "에버테일"
            },
            {
                "idx": "3801",
                "name": "캐리비안의 해적: 전쟁의 물결"
            },
            {
                "idx": "3802",
                "name": "데드 바이 데이라이트"
            },
            {
                "idx": "3805",
                "name": "롬: 골든 에이지"
            },
            {
                "idx": "3807",
                "name": "조조의 꿈: 디펜스의 서막"
            },
            {
                "idx": "3811",
                "name": "D3: 이모탈 드래곤즈"
            },
            {
                "idx": "3813",
                "name": "이세계 사가"
            },
            {
                "idx": "3817",
                "name": "R2"
            },
            {
                "idx": "3821",
                "name": "데스티니 라이징"
            },
            {
                "idx": "3824",
                "name": "소녀의 숲: 새로운 방치형 RPG"
            },
            {
                "idx": "3826",
                "name": "엠파이어 & 퍼즐"
            },
            {
                "idx": "3827",
                "name": "세븐: 글로리 로드"
            },
            {
                "idx": "3829",
                "name": "로스트소울"
            },
            {
                "idx": "3830",
                "name": "에이스크래프트"
            },
            {
                "idx": "3833",
                "name": "로드모바일 : 킹덤 워즈"
            },
            {
                "idx": "3834",
                "name": "고고스카이"
            },
            {
                "idx": "3835",
                "name": "벨라토르M:불멸의검"
            },
            {
                "idx": "3836",
                "name": "플랜티스와 좀비깡패"
            },
            {
                "idx": "3844",
                "name": "추억의 잡화점"
            },
            {
                "idx": "3855",
                "name": "응발로키우기"
            },
            {
                "idx": "3858",
                "name": "이터널 시티"
            },
            {
                "idx": "3860",
                "name": "프리프 유니버스"
            },
            {
                "idx": "3861",
                "name": "크레이지 아케이드"
            },
            {
                "idx": "3862",
                "name": "디지몬RPG"
            },
            {
                "idx": "3863",
                "name": "디지몬슈퍼럼블"
            },
            {
                "idx": "3864",
                "name": "클로저스"
            },
            {
                "idx": "3865",
                "name": "배틀필드6"
            },
            {
                "idx": "3866",
                "name": "워 썬더"
            },
            {
                "idx": "3872",
                "name": "뮤 블루"
            },
            {
                "idx": "3877",
                "name": "아야카시 라이즈"
            },
            {
                "idx": "3878",
                "name": "석기삼국: 타임리프 삼국지"
            },
            {
                "idx": "3879",
                "name": "C9 Global"
            },
            {
                "idx": "3880",
                "name": "역수한"
            },
            {
                "idx": "3882",
                "name": "개방공간: 오버필드"
            },
            {
                "idx": "3883",
                "name": "아크 레이더스"
            },
            {
                "idx": "3884",
                "name": "조조:관우를 돌려줘"
            },
            {
                "idx": "3885",
                "name": "디아블로3"
            },
            {
                "idx": "3891",
                "name": "드래곤네스트 클래식"
            },
            {
                "idx": "3895",
                "name": "십이지천M 글로벌"
            },
            {
                "idx": "3900",
                "name": "드래곤 플라이트2"
            },
            {
                "idx": "3905",
                "name": "부활얍카"
            },
            {
                "idx": "3906",
                "name": "포켓몬 마스터즈 EX"
            },
            {
                "idx": "3907",
                "name": "뱅드림(BanG Dream!)"
            },
            {
                "idx": "3911",
                "name": "검선귀환"
            },
            {
                "idx": "3912",
                "name": "드래곤빌리지 럼블"
            },
            {
                "idx": "3914",
                "name": "로맨싱 사가 Re; Universe"
            },
            {
                "idx": "3915",
                "name": "라스트 오리진"
            },
            {
                "idx": "3919",
                "name": "엘로아"
            },
            {
                "idx": "3927",
                "name": "Z9별"
            },
            {
                "idx": "3929",
                "name": "몬스터 스토리 : 전설의 시작"
            },
            {
                "idx": "3932",
                "name": "디바인: 신을 모시는 자"
            },
            {
                "idx": "3934",
                "name": "타일 서바이벌"
            },
            {
                "idx": "3938",
                "name": "이터널 에볼루션"
            },
            {
                "idx": "3939",
                "name": "로드판타지"
            },
            {
                "idx": "3941",
                "name": "세가 풋볼클럽 챔피언스2026"
            },
            {
                "idx": "3948",
                "name": "포트리스3 Blue"
            },
            {
                "idx": "3951",
                "name": "PUBG 블라인드 스팟"
            },
            {
                "idx": "3954",
                "name": "디오 온라인"
            },
            {
                "idx": "3956",
                "name": "한양온라인 조선무사키우기"
            },
            {
                "idx": "3957",
                "name": "매직 로스트 로드"
            },
            {
                "idx": "3958",
                "name": "카운터스트라이크 글로벌오펜시브"
            },
            {
                "idx": "3960",
                "name": "포켓 어드벤처: 드림"
            },
            {
                "idx": "3963",
                "name": "두근두근 타운"
            },
            {
                "idx": "3971",
                "name": "레인보우 식스 모바일"
            },
            {
                "idx": "3972",
                "name": "라스트 어사일럼: 페스트"
            },
            {
                "idx": "3976",
                "name": "스페셜포스 리마스터"
            },
            {
                "idx": "3977",
                "name": "대마인 스쿼드"
            },
            {
                "idx": "3978",
                "name": "낙원: LAST PARADISE"
            },
            {
                "idx": "3979",
                "name": "성좌 키우기"
            },
            {
                "idx": "3986",
                "name": "디시디아 듀엘름 파이널판타지"
            },
            {
                "idx": "3988",
                "name": "파운데이션 : 우주 전선"
            },
            {
                "idx": "3989",
                "name": "이터널 크로니클"
            },
            {
                "idx": "3990",
                "name": "여고생과 리셋중"
            },
            {
                "idx": "3991",
                "name": "슬러거"
            },
            {
                "idx": "3993",
                "name": "드래곤네스트 월드"
            },
            {
                "idx": "3994",
                "name": "픽셀 히어로즈 방치형 RPG"
            },
            {
                "idx": "3995",
                "name": "비스트 클래시"
            },
            {
                "idx": "3996",
                "name": "러시안피싱4"
            },
            {
                "idx": "4000",
                "name": "테일즈런너"
            },
            {
                "idx": "4001",
                "name": "카오스W"
            },
            {
                "idx": "4007",
                "name": "드로이얀 온라인"
            },
            {
                "idx": "4009",
                "name": "삼국지워"
            },
            {
                "idx": "4010",
                "name": "드래곤 퀘스트 스매시 그로우"
            },
            {
                "idx": "4011",
                "name": "다크슬레이어2"
            },
            {
                "idx": "4012",
                "name": "프리스타일 풋볼2"
            },
            {
                "idx": "4013",
                "name": "대항해시대 온라인"
            },
            {
                "idx": "4014",
                "name": "아주르 프로밀리아"
            },
            {
                "idx": "4016",
                "name": "문파존망겜"
            },
            {
                "idx": "4018",
                "name": "이터널시티3"
            },
            {
                "idx": "4019",
                "name": "별별히어로 : 영웅 다 있소"
            },
            {
                "idx": "4020",
                "name": "더 디비전 리서전스"
            },
            {
                "idx": "4021",
                "name": "인투더던전:리본"
            },
            {
                "idx": "4022",
                "name": "팰몬: 서바이벌"
            },
            {
                "idx": "4023",
                "name": "패왕의별M"
            },
            {
                "idx": "4024",
                "name": "드래곤빌리지3"
            },
            {
                "idx": "2445",
                "name": "그외 게임"
            }
        ]

    def init(self) -> bool:
        try:
            if self.init_flag:
                self.log_signal_func("이미 초기화 실행 완료")
                return True

            # 셋팅값 추출
            self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()
            self.auto_save_yn = bool(self.get_setting_value(self.setting, "auto_save_yn"))

            self.keyword = self.get_setting_value(self.setting, "keyword")

            # 숫자형 예외 처리 (빈 값일 경우 None 처리)
            min_val = self.get_setting_value(self.setting, "min")
            max_val = self.get_setting_value(self.setting, "max")
            self.min = int(min_val) if min_val else ""
            self.max = int(max_val) if max_val else ""

            sections = self.get_sections()

            for sec in sections:
                sec_id = sec.get("id")

                # 1. 계정 종류 섹션일 때
                if sec_id == 'accountType':
                    items = self.get_items(sec_id)
                    # checked가 True인 자식들 중에서 'value'만 쏙 뽑아서 리스트로 만들기
                    self.accountType_list = [
                        item.get('code') for item in items if item.get('checked')
                    ]

                # 2. 구매 경로 섹션일 때
                elif sec_id == 'purchasePath':
                    items = self.get_items(sec_id)
                    # checked가 True인 자식들 중에서 'value'만 쏙 뽑아서 리스트로 만들기
                    self.purchasePath_list = [
                        item.get('code') for item in items if item.get('checked')
                    ]

            self.log_signal_func(f"저장경로 : {self.folder_path}")
            self.log_signal_func(f"엑셀 자동 저장 여부 : {self.auto_save_yn}")
            self.log_signal_func(f"키워드 : {self.keyword}")
            self.log_signal_func(f"가격 시작 : {self.min} 만원")
            self.log_signal_func(f"가격 끝 : {self.max} 만원")

            self.log_signal_func(f"계정 종류 : {self.accountType_list}")
            self.log_signal_func(f"구매 경로 : {self.purchasePath_list}")
            
            # 컬럼세팅
            if not self.load_runtime_config_columns():
                return False

            self.driver_set()

            if not self.db_set():
                return False

            self.log_signal_func("✅ init 완료")
            self.init_flag = True
            return True

        except Exception as e:
            self.log_signal_func(f"❌ init 실패: {e}")
            return False

    def driver_set(self) -> None:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)

    def main(self) -> bool:
        try:
            self.log_signal_func("🚀 크롤링 시작")

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*; q=0.01",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "X-Requested-With": "XMLHttpRequest",
                "Connection": "keep-alive"
            }

            self.total_cnt = len(self.game_list)
            self.current_cnt = 0

            # 전체 아이템 진행도 로깅을 위한 누적 카운트
            total_items_saved = 0

            for game_idx_num, game in enumerate(self.game_list, start=1):
                if self._stop_event.is_set() or not self.running:
                    self.log_signal_func("⛔ 중지 감지 → 저장 후 종료")
                    break

                idx = game.get("idx")
                game_name_setting = game.get("name")

                self.log_signal_func(f"\n==================================================")
                self.log_signal_func(f">> [{game_idx_num}/{self.total_cnt}] [{game_name_setting}({idx})] 수집 시작")
                self.log_signal_func(f"==================================================")

                page = 1

                # 중복 ID 추적을 위한 Set (게임이 바뀔 때마다 초기화)
                seen_item_ids = set()

                while True:
                    if self._stop_event.is_set() or not self.running:
                        self.log_signal_func("⛔ 중지 감지 (페이징) → 종료")
                        return True

                    # 1. URL 및 파라미터 구성 (바로템 API 규격으로 변경)
                    url = f"https://www.barotem.com/product/productTable/{idx}"

                    params = {
                        "page": page,
                        "sell": "sell",
                        "display": "1",
                        "orderby": "1",
                        "total": "no"
                    }

                    # 리스트 파라미터는 콤마(,)로 연결
                    if self.accountType_list:
                        params["brand"] = ",".join(self.accountType_list)
                    if self.purchasePath_list:
                        params["buyloc"] = ",".join(self.purchasePath_list)

                    if self.min:
                        params["minpay"] = self.min
                    if self.max:
                        params["maxpay"] = self.max
                    if self.keyword:
                        params["search_word"] = self.keyword

                    try:
                        # 2. JSON 데이터 가져오기
                        response_text = self.api_client.get(url, headers=headers, params=params)

                        try:
                            json_data = json.loads(response_text)
                        except json.JSONDecodeError:
                            self.log_signal_func(f"[{game_name_setting} | P.{page}] 💥 JSON 파싱 실패 (응답 형태 확인 필요)")
                            break

                        rows = json_data.get('rows', [])

                        # 상품이 없으면 다음 게임으로 넘어가기 위해 루프 탈출
                        if not rows:
                            self.log_signal_func(f"  -> ⏹️ [종료] 더 이상 파싱할 상품 리스트가 없습니다. (Page: {page})")
                            break

                        self.log_signal_func(f"[{game_name_setting} | P.{page}] 파싱된 상품 수: {len(rows)}개")

                        new_item_found = False # 새 아이템 존재 여부

                        # 3. 데이터 추출 및 즉시 DB 저장
                        for item in rows:
                            if self._stop_event.is_set() or not self.running:
                                self.log_signal_func("⛔ 중지 감지 → 저장 후 종료")
                                break

                            item_id = str(item.get('number', '')).strip()

                            # 중복 아이템 거르기
                            if not item_id or item_id in seen_item_ids:
                                continue

                            seen_item_ids.add(item_id)
                            new_item_found = True

                            # [수정 1] 상태 체크: 'stat43'이면 거래완료 제외 처리
                            tr_class = item.get('trClass', '')
                            if tr_class == 'stat43':
                                continue  # 거래완료 상품은 스킵

                            trade_status = "판매중"
                            item_url = f"https://www.barotem.com/product/view/{item_id}"

                            # [수정 2] 요청하신 항목 매핑 추출
                            raw_price = str(item.get('acount_price', ''))
                            raw_trade_type = str(item.get('buyloc', ''))
                            raw_account_type = str(item.get('brand', ''))
                            title = str(item.get('product_name', ''))
                            job = str(item.get('title', ''))
                            server = str(item.get('server', ''))

                            # 코드 -> 한글 맵핑 딕셔너리
                            ACCOUNT_TYPE_MAP = {
                                "15961": "게임사",
                                "15962": "구글",
                                "15963": "페이스북",
                                "15965": "네이버",
                                "15966": "카카오",
                                "15967": "게스트",
                                "15968": "전화번호",
                                "15964": "기타"
                            }

                            TRADE_TYPE_MAP = {
                                "35781": "본인(1대)",
                                "35782": "바로템 구매",
                                "35783": "그외"
                            }

                            # 맵핑 적용 (매칭되는 값이 없으면 원래의 숫자를 그대로 출력)
                            account_type_str = ACCOUNT_TYPE_MAP.get(raw_account_type, raw_account_type)
                            trade_type = TRADE_TYPE_MAP.get(raw_trade_type, raw_trade_type)

                            # 가격 3자리 콤마 및 '원' 추가
                            try:
                                if raw_price:
                                    price_num = int(raw_price)
                                    price_formatted = f"{price_num:,}원"
                                else:
                                    price_formatted = ""
                            except ValueError:
                                # 숫자가 아닌 문자가 섞여 있어 int 변환 실패 시 기본 처리
                                price_formatted = f"{raw_price}원"

                            # DB Insert 용 Dictionary 생성
                            row_data = {
                                "게임명": game_name_setting,
                                "게시글 ID": item_id,
                                "계정종류": account_type_str,
                                "제목": title,
                                "서버": server,
                                "직업": job,
                                "거래유형": trade_type,
                                "가격": price_formatted,
                                "URL": item_url,
                                "거래상태": trade_status
                            }

                            # DB(및 엑셀용 메모리)에 저장
                            self.insert_detail_row(row_data)

                            total_items_saved += 1
                            self.log_signal_func(f"[{game_idx_num}/{self.total_cnt}] [{total_items_saved}] DB 저장: [{game_name_setting}] [{trade_status}] {title}")

                        if not new_item_found:
                            self.log_signal_func(f"  -> ⏹️ [종료] 새로운 상품이 없습니다 (중복만 존재). (Page: {page})")
                            break

                        page += 1
                        delay_time = random.uniform(1.2, 2.5)
                        time.sleep(delay_time)

                    except Exception as e:
                        self.log_signal_func(f"[{game_name_setting} | P.{page}] 💥 예외 오류 발생: {e}")
                        break

                self.current_cnt += 1
                pro_value = int((self.current_cnt / self.total_cnt) * 1000000) if self.total_cnt > 0 else 0
                self.progress_signal.emit(self.before_pro_value, pro_value)
                self.before_pro_value = pro_value
                time.sleep(random.uniform(0.3, 0.8))

            if self.hist_status == "RUNNING":
                if self.running:
                    self.finish_job("SUCCESS")
                else:
                    self.finish_job("STOP", "사용자 중단")

            self.log_signal_func("✅ main 종료 (수집 완료)")
            return True

        except Exception as e:
            self.log_signal_func(f"❌ 전체 실행 중 예외 발생: {e}")
            self.finish_job("FAIL", str(e))
            return False

    def get_sections(self) -> List[Dict[str, Any]]:
        return [r for r in (self.setting_detail or []) if r.get("row_type") == "section"]

    def get_items(self, parent_id: Any) -> List[Dict[str, Any]]:
        rows = self.setting_detail or []
        return [r for r in rows if r.get("row_type") == "item" and r.get("parent_id") == parent_id]

    # =========================================================
    # DB / Excel 공통 모듈 파트
    # =========================================================
    def db_set(self) -> bool:
        self.sqlite_driver = SqliteUtils(self.log_signal_func)
        db_path = self.get_runtime_db_path()

        if not self.sqlite_driver.connect(db_path):
            self.log_signal_func("❌ [DB] 연결 실패")
            return False

        schema_files = [
            os.path.join("resources", "customers", "common", "db", "schema_hist.sql"),
            os.path.join("resources", "customers", self.worker_name, "db", "schema_detail.sql"),
        ]

        if not self.sqlite_driver.execute_script_files(schema_files):
            self.log_signal_func("❌ [DB] 스키마 초기화 실패")
            return False

        if not self.insert_hist_start():
            return False

        return True

    def insert_hist_start(self) -> bool:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.job_id = time.strftime("%Y%m%d%H%M%S")

        query = """
                INSERT INTO worker_job_hist (
                    job_id, table_name, site_name, worker_name, user_id,
                    start_at, status, total_count, success_count, fail_count,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
        params = (
            self.job_id, self.detail_table_name, self.site_name, self.worker_name,
            getattr(self.user, "user_id", None) if self.user else None,
            now, "RUNNING", 0, 0, 0, now, now,
        )

        if not self.sqlite_driver.execute(query, params):
            return False

        row = self.sqlite_driver.fetchone("SELECT last_insert_rowid() AS hist_id")
        self.hist_id = row["hist_id"] if row else None
        return True

    def finish_job(self, status: str, error_message: Optional[str] = None) -> None:
        self.hist_status = status
        self.hist_error_message = error_message

    def update_hist_end(self, sqlite_driver: Optional[SqliteUtils] = None) -> bool:
        sqlite_driver = sqlite_driver or self.sqlite_driver
        if not sqlite_driver or not self.hist_id:
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        query = """
                UPDATE worker_job_hist
                SET end_at = ?, status = ?, total_count = ?, success_count = ?, fail_count = ?,
                    error_message = ?, updated_at = ?
                WHERE hist_id = ?
                """
        params = (
            now, self.hist_status, self.detail_success_count + self.detail_fail_count,
            self.detail_success_count, self.detail_fail_count, self.hist_error_message, now, self.hist_id,
        )
        return sqlite_driver.execute(query, params)

    def insert_detail_row(self, rs: Dict[str, Any]) -> bool:
        if not self.sqlite_driver or not self.db_columns:
            self.detail_fail_count += 1
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        db_rs = self.map_out_to_db(rs)

        base_columns = ["hist_id", "site_name", "worker_name", "table_name", "job_id", "user_id", "row_status"]
        all_columns = base_columns + self.db_columns + ["created_at", "updated_at"]
        placeholders = ", ".join(["?"] * len(all_columns))
        column_text = ",\n                    ".join(all_columns)

        query = f"INSERT INTO {self.detail_table_name} ({column_text}) VALUES ({placeholders})"
        params = (
            self.hist_id, self.site_name, self.worker_name, self.detail_table_name, self.job_id,
            getattr(self.user, "user_id", None) if self.user else None, "SUCCESS",
            *[db_rs.get(col, "") for col in self.db_columns], now, now,
        )

        ok = self.sqlite_driver.execute(query, params)
        if ok:
            self.detail_success_count += 1
        else:
            self.detail_fail_count += 1
        return ok

    def get_runtime_config_path(self) -> str:
        candidates = [
            os.path.join(self.get_resource_root(), "runtime", "customers", self.worker_name, "config.json"),
            os.path.join(self.get_project_root(), "runtime", "customers", self.worker_name, "config.json"),
        ]
        for path in candidates:
            if os.path.exists(path): return path
        return candidates[0]

    def load_runtime_config_columns(self) -> bool:
        config_path = self.get_runtime_config_path()
        if not os.path.exists(config_path): return False

        with open(config_path, "r", encoding="utf-8") as f:
            self.config_data = json.load(f)

        columns = self.config_data.get("columns") or []
        self.column_defs = [c for c in columns if str(c.get("code")).strip() and str(c.get("value")).strip()]
        self.db_columns = [str(c.get("code")).strip() for c in self.column_defs]
        self.excel_columns = [str(c.get("value")).strip() for c in self.column_defs if bool(c.get("checked", False))]
        self.code_value_map = {str(c.get("code")).strip(): str(c.get("value")).strip() for c in self.column_defs}
        self.columns = self.excel_columns
        return True

    def map_out_to_db(self, out: Dict[str, Any]) -> Dict[str, Any]:
        return {code: str(out.get(value) or "") for code, value in self.code_value_map.items()}

    def db_rows_to_kor_rows(self, row_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for row in row_list or []:
            out = {}
            for col in self.column_defs:
                if not bool(col.get("checked", False)): continue
                code, value = str(col.get("code")).strip(), str(col.get("value")).strip()
                out[value] = row.get(code, "")
            result.append(out)
        return result

    def export_detail_to_excel(self, sqlite_driver: Optional[SqliteUtils] = None) -> bool:
        sqlite_driver = sqlite_driver or self.sqlite_driver
        if not self.excel_driver or not sqlite_driver or not self.hist_id or not self.db_columns:
            return False

        select_text = ",\n                    ".join(self.db_columns)
        query = f"SELECT {select_text} FROM {self.detail_table_name} WHERE hist_id = ? ORDER BY detail_id"

        row_list = sqlite_driver.fetchall(query, (self.hist_id,))
        if not row_list:
            self.log_signal_func("⚠️ [엑셀] 저장할 detail 데이터가 없습니다.")
            return False

        excel_row_list = self.db_rows_to_kor_rows([dict(row) for row in row_list])
        excel_filename = f"{self.site_name}_{self.job_id}.xlsx"

        return self.excel_driver.save_db_rows_to_excel(
            excel_filename=excel_filename,
            row_list=excel_row_list,
            columns=self.columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir,
        )

    def finalize_db_and_excel(self) -> None:
        temp_sqlite_driver = None
        try:
            temp_sqlite_driver = SqliteUtils(self.log_signal_func)
            if temp_sqlite_driver.connect(self.get_runtime_db_path()):
                self.update_hist_end(temp_sqlite_driver)
                if self.auto_save_yn:
                    self.export_detail_to_excel(temp_sqlite_driver)
        except Exception as e:
            self.log_signal_func(f"[cleanup] finalize_db_and_excel 실패: {e}")
        finally:
            if temp_sqlite_driver: temp_sqlite_driver.close()

    # =========================================================
    # 종료 / 정리
    # =========================================================
    def cleanup(self) -> None:
        if self._cleaned_up:
            return

        try:
            if self.sqlite_driver and hasattr(self.sqlite_driver, "close"):
                self.sqlite_driver.close()
        except: pass
        finally:
            self.sqlite_driver = None

        self.finalize_db_and_excel()

        try:
            if self.file_driver: self.file_driver.close()
            if self.excel_driver: self.excel_driver.close()
            if self.api_client: self.api_client.close()
        except: pass

        self.file_driver, self.excel_driver, self.api_client = None, None, None
        self._cleaned_up = True

    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        self._stop_event.set()

        if self.hist_status == "RUNNING":
            self.finish_job("STOP", "사용자 중단")

        time.sleep(1)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()