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

class ApiIdfarmSetWorker(BaseApiWorker):

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

        self.site_name: str = "아아디팜"
        self.worker_name: str = "idfarm"

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
        self.detail_table_name: str = "IDFARM"
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
                "name": "리니지 리마스터"
            },
            {
                "idx": "2",
                "name": "리니지 M"
            },
            {
                "idx": "3",
                "name": "리니지 2M"
            },
            {
                "idx": "62",
                "name": "리니지W"
            },
            {
                "idx": "455",
                "name": "리니지 클래식"
            },
            {
                "idx": "30",
                "name": "로스트아크"
            },
            {
                "idx": "20",
                "name": "원신"
            },
            {
                "idx": "10",
                "name": "메이플스토리"
            },
            {
                "idx": "407",
                "name": "아이온2"
            },
            {
                "idx": "397",
                "name": "메이플스토리월드"
            },
            {
                "idx": "12",
                "name": "피파온라인4"
            },
            {
                "idx": "11",
                "name": "던전앤파이터"
            },
            {
                "idx": "98",
                "name": "승리의 여신: 니케"
            },
            {
                "idx": "134",
                "name": "리버스1999"
            },
            {
                "idx": "115",
                "name": "붕괴: 스타레일"
            },
            {
                "idx": "43",
                "name": "우마무스메"
            },
            {
                "idx": "65",
                "name": "블루아카이브"
            },
            {
                "idx": "124",
                "name": "에테르 게이저"
            },
            {
                "idx": "25",
                "name": "에픽세븐"
            },
            {
                "idx": "41",
                "name": "명일방주"
            },
            {
                "idx": "147",
                "name": "스타시드: 아스니아 트리거"
            },
            {
                "idx": "145",
                "name": "별이되어라2: 베다의 기사들"
            },
            {
                "idx": "148",
                "name": "나혼자만레벨업 : 어라이즈"
            },
            {
                "idx": "128",
                "name": "신의 탑: 새로운 세계"
            },
            {
                "idx": "120",
                "name": "블랙클로버 모바일"
            },
            {
                "idx": "85",
                "name": "검은사막 모바일"
            },
            {
                "idx": "5",
                "name": "검은사막"
            },
            {
                "idx": "109",
                "name": "헤븐 번즈 레드"
            },
            {
                "idx": "72",
                "name": "던전앤파이터M"
            },
            {
                "idx": "91",
                "name": "세븐나이츠 레볼루션"
            },
            {
                "idx": "49",
                "name": "백야극광"
            },
            {
                "idx": "102",
                "name": "무기미도"
            },
            {
                "idx": "104",
                "name": "뉴럴 클라우드"
            },
            {
                "idx": "42",
                "name": "붕괴3rd"
            },
            {
                "idx": "26",
                "name": "쿠키런킹덤"
            },
            {
                "idx": "46",
                "name": "에이펙스 레전드"
            },
            {
                "idx": "31",
                "name": "제2의 나라"
            },
            {
                "idx": "21",
                "name": "세븐나이츠2"
            },
            {
                "idx": "61",
                "name": "심포니 오브 에픽"
            },
            {
                "idx": "95",
                "name": "타워 오브 판타지"
            },
            {
                "idx": "100",
                "name": "아르케랜드"
            },
            {
                "idx": "33",
                "name": "오딘"
            },
            {
                "idx": "56",
                "name": "삼국지 전략판"
            },
            {
                "idx": "51",
                "name": "메이플스토리M"
            },
            {
                "idx": "93",
                "name": "히트2"
            },
            {
                "idx": "18",
                "name": "바람의나라 연"
            },
            {
                "idx": "78",
                "name": "천애명월도M"
            },
            {
                "idx": "36",
                "name": "거상"
            },
            {
                "idx": "50",
                "name": "퍼니싱 : 그레이 레이븐"
            },
            {
                "idx": "53",
                "name": "디아블로2:레저렉션"
            },
            {
                "idx": "103",
                "name": "디아블로 4"
            },
            {
                "idx": "77",
                "name": "디아블로 이모탈"
            },
            {
                "idx": "64",
                "name": "전생슬"
            },
            {
                "idx": "74",
                "name": "신의 탑M:위대한 여정"
            },
            {
                "idx": "81",
                "name": "이터널트리"
            },
            {
                "idx": "75",
                "name": "프로젝트 세카이"
            },
            {
                "idx": "35",
                "name": "가디언 테일즈"
            },
            {
                "idx": "29",
                "name": "아이온"
            },
            {
                "idx": "86",
                "name": "엘소드"
            },
            {
                "idx": "47",
                "name": "프린세스 커넥트!"
            },
            {
                "idx": "45",
                "name": "파이널기어"
            },
            {
                "idx": "24",
                "name": "그랑사가"
            },
            {
                "idx": "34",
                "name": "AFK아레나"
            },
            {
                "idx": "66",
                "name": "깨어난 마녀"
            },
            {
                "idx": "22",
                "name": "미르4"
            },
            {
                "idx": "32",
                "name": "원펀맨"
            },
            {
                "idx": "107",
                "name": "에버소울"
            },
            {
                "idx": "8",
                "name": "V4"
            },
            {
                "idx": "52",
                "name": "코노스바 모바일"
            },
            {
                "idx": "80",
                "name": "아터리 기어: 퓨전"
            },
            {
                "idx": "54",
                "name": "마블 퓨처 레볼루션"
            },
            {
                "idx": "60",
                "name": "미니어스"
            },
            {
                "idx": "79",
                "name": "미르M"
            },
            {
                "idx": "94",
                "name": "앨리스픽션"
            },
            {
                "idx": "58",
                "name": "월드 플리퍼"
            },
            {
                "idx": "83",
                "name": "백일몽화"
            },
            {
                "idx": "70",
                "name": "언디셈버"
            },
            {
                "idx": "71",
                "name": "트라하 인피니티"
            },
            {
                "idx": "40",
                "name": "리그오브레전드"
            },
            {
                "idx": "90",
                "name": "노아의 심장"
            },
            {
                "idx": "16",
                "name": "뮤 아크엔젤"
            },
            {
                "idx": "19",
                "name": "R2M"
            },
            {
                "idx": "13",
                "name": "DK모바일 THE ORIGIN"
            },
            {
                "idx": "17",
                "name": "라그나로크X:넥스트 제네레이션"
            },
            {
                "idx": "27",
                "name": "블레이드 & 소울 2"
            },
            {
                "idx": "38",
                "name": "기적의 검"
            },
            {
                "idx": "39",
                "name": "달빛조각사"
            },
            {
                "idx": "55",
                "name": "월드 오브 워크래프트"
            },
            {
                "idx": "57",
                "name": "나의 히어로 아카데미아"
            },
            {
                "idx": "59",
                "name": "카르마M"
            },
            {
                "idx": "4",
                "name": "블소 레볼루션"
            },
            {
                "idx": "63",
                "name": "제4구역"
            },
            {
                "idx": "69",
                "name": "미르의전설2"
            },
            {
                "idx": "73",
                "name": "에곤 : 인페르나 벨룸"
            },
            {
                "idx": "76",
                "name": "열혈강호W"
            },
            {
                "idx": "82",
                "name": "페어리테일:위대한여정"
            },
            {
                "idx": "84",
                "name": "라이즈 오브 킹덤즈"
            },
            {
                "idx": "87",
                "name": "마구마구 2025"
            },
            {
                "idx": "92",
                "name": "대항해시대 오리진"
            },
            {
                "idx": "14",
                "name": "A3"
            },
            {
                "idx": "96",
                "name": "프리스톤테일M"
            },
            {
                "idx": "97",
                "name": "히어로즈 테일즈"
            },
            {
                "idx": "99",
                "name": "토치라이트: 인피니트"
            },
            {
                "idx": "101",
                "name": "트리 오브 세이비어 M"
            },
            {
                "idx": "105",
                "name": "문명: Reign of Power"
            },
            {
                "idx": "106",
                "name": "루시다"
            },
            {
                "idx": "108",
                "name": "나이트 워커"
            },
            {
                "idx": "110",
                "name": "아바타라"
            },
            {
                "idx": "111",
                "name": "아키에이지 워"
            },
            {
                "idx": "112",
                "name": "프라시아 전기"
            },
            {
                "idx": "113",
                "name": "응: 인터루나"
            },
            {
                "idx": "116",
                "name": "나이트 크로우"
            },
            {
                "idx": "114",
                "name": "바람의나라"
            },
            {
                "idx": "117",
                "name": "제노니아"
            },
            {
                "idx": "118",
                "name": "코드기어스"
            },
            {
                "idx": "119",
                "name": "아우터플레인"
            },
            {
                "idx": "121",
                "name": "쓰론 앤 리버티TL"
            },
            {
                "idx": "122",
                "name": "클로저스RT: 뉴 오더"
            },
            {
                "idx": "123",
                "name": "마비노기"
            },
            {
                "idx": "125",
                "name": "아레스"
            },
            {
                "idx": "126",
                "name": "스노우 브레이크: 포비든 존"
            },
            {
                "idx": "127",
                "name": "이터널 리턴"
            },
            {
                "idx": "129",
                "name": "던만추 배틀 크로니클"
            },
            {
                "idx": "130",
                "name": "ASAP 아레나"
            },
            {
                "idx": "131",
                "name": "세븐나이츠 키우기"
            },
            {
                "idx": "132",
                "name": "블루프로토콜"
            },
            {
                "idx": "133",
                "name": "워헤이븐"
            },
            {
                "idx": "135",
                "name": "빌딩앤파이터"
            },
            {
                "idx": "137",
                "name": "도쿄 구울: Break the Chains"
            },
            {
                "idx": "138",
                "name": "콜오브카오스:어셈블"
            },
            {
                "idx": "139",
                "name": "씰M"
            },
            {
                "idx": "140",
                "name": "슈퍼걸스대전"
            },
            {
                "idx": "141",
                "name": "창세기전 모바일: 아수라 프로젝트"
            },
            {
                "idx": "142",
                "name": "팰월드: Palworld"
            },
            {
                "idx": "143",
                "name": "롬: 리멤버 오브 마제스티"
            },
            {
                "idx": "144",
                "name": "엑스 아스트리스"
            },
            {
                "idx": "146",
                "name": "쿠키런: 마녀의 성"
            },
            {
                "idx": "149",
                "name": "명조 : 워더링웨이브"
            },
            {
                "idx": "150",
                "name": "제로나인"
            },
            {
                "idx": "151",
                "name": "라살라스"
            },
            {
                "idx": "152",
                "name": "별의전쟁"
            },
            {
                "idx": "289",
                "name": "아스달연대기: 세 개의 세력"
            },
            {
                "idx": "290",
                "name": "레이븐2"
            },
            {
                "idx": "291",
                "name": "캣 판타지"
            },
            {
                "idx": "292",
                "name": "에코칼립스: 진홍의 서약"
            },
            {
                "idx": "293",
                "name": "로드나인"
            },
            {
                "idx": "294",
                "name": "패스 오브 엑자일"
            },
            {
                "idx": "296",
                "name": "젠레스 존 제로"
            },
            {
                "idx": "295",
                "name": "에오스 블랙"
            },
            {
                "idx": "297",
                "name": "쿠키런: 모험의 탑"
            },
            {
                "idx": "299",
                "name": "소드 오브 콘발라리아"
            },
            {
                "idx": "298",
                "name": "뮈렌: 천년의 여정"
            },
            {
                "idx": "301",
                "name": "AFK : 새로운 여정"
            },
            {
                "idx": "300",
                "name": "영웅전설: 가가브 트릴로지"
            },
            {
                "idx": "303",
                "name": "어비스메이트"
            },
            {
                "idx": "153",
                "name": "스팀"
            },
            {
                "idx": "154",
                "name": "에오스레드"
            },
            {
                "idx": "155",
                "name": "소울 커넥터"
            },
            {
                "idx": "156",
                "name": "S.O.S:스테이트오브서바이벌"
            },
            {
                "idx": "157",
                "name": "화이트멜로디"
            },
            {
                "idx": "158",
                "name": "서든어택"
            },
            {
                "idx": "159",
                "name": "일루전 커넥트"
            },
            {
                "idx": "160",
                "name": "마구마구2020"
            },
            {
                "idx": "161",
                "name": "닌자 머스트 다이"
            },
            {
                "idx": "162",
                "name": "카트라이더 러쉬플러스"
            },
            {
                "idx": "163",
                "name": "애니팡4"
            },
            {
                "idx": "164",
                "name": "드래곤라자 오리진"
            },
            {
                "idx": "165",
                "name": "배틀그라운드(배그)"
            },
            {
                "idx": "166",
                "name": "콜오브드래곤즈"
            },
            {
                "idx": "167",
                "name": "발로란트"
            },
            {
                "idx": "168",
                "name": "마인크래프트"
            },
            {
                "idx": "169",
                "name": "아바온라인"
            },
            {
                "idx": "170",
                "name": "천상비M"
            },
            {
                "idx": "171",
                "name": "디스라이트"
            },
            {
                "idx": "172",
                "name": "하이큐!!TOUCH THE DREAM"
            },
            {
                "idx": "173",
                "name": "뿌요뿌요!! 퀘스트공식"
            },
            {
                "idx": "174",
                "name": "삼국지난무"
            },
            {
                "idx": "175",
                "name": "마계전기"
            },
            {
                "idx": "176",
                "name": "라스트클라우디아"
            },
            {
                "idx": "177",
                "name": "슬램덩크"
            },
            {
                "idx": "178",
                "name": "서머너즈 워"
            },
            {
                "idx": "179",
                "name": "소녀세계"
            },
            {
                "idx": "180",
                "name": "마블스냅"
            },
            {
                "idx": "181",
                "name": "닌텐도"
            },
            {
                "idx": "182",
                "name": "클래시 로얄"
            },
            {
                "idx": "183",
                "name": "뮤 오리진"
            },
            {
                "idx": "184",
                "name": "해리포터: 깨어난 마법"
            },
            {
                "idx": "185",
                "name": "데스티니 차일드"
            },
            {
                "idx": "186",
                "name": "니어리인카네이션"
            },
            {
                "idx": "187",
                "name": "어나더에덴"
            },
            {
                "idx": "188",
                "name": "브라운더스트2"
            },
            {
                "idx": "189",
                "name": "서머너즈 워: 백년전쟁"
            },
            {
                "idx": "190",
                "name": "작혼"
            },
            {
                "idx": "191",
                "name": "천애명월도"
            },
            {
                "idx": "192",
                "name": "탁트오퍼스"
            },
            {
                "idx": "193",
                "name": "카운터사이드"
            },
            {
                "idx": "194",
                "name": "클래시 오브 킹즈"
            },
            {
                "idx": "195",
                "name": "달토끼 키우기"
            },
            {
                "idx": "196",
                "name": "탕탕특공대"
            },
            {
                "idx": "197",
                "name": "메멘토모리"
            },
            {
                "idx": "198",
                "name": "랑그릿사"
            },
            {
                "idx": "199",
                "name": "림버스컴퍼니"
            },
            {
                "idx": "200",
                "name": "킹갓캐슬"
            },
            {
                "idx": "201",
                "name": "카트라이더: 드리프트"
            },
            {
                "idx": "202",
                "name": "알투비트"
            },
            {
                "idx": "203",
                "name": "로스트시티제로"
            },
            {
                "idx": "204",
                "name": "프리스타일2"
            },
            {
                "idx": "205",
                "name": "디펜스더비"
            },
            {
                "idx": "206",
                "name": "데미안 전기"
            },
            {
                "idx": "207",
                "name": "어둠의전설"
            },
            {
                "idx": "208",
                "name": "소울타이드"
            },
            {
                "idx": "209",
                "name": "랜덤 다이스"
            },
            {
                "idx": "210",
                "name": "워프레임"
            },
            {
                "idx": "211",
                "name": "유그드라 리버스"
            },
            {
                "idx": "212",
                "name": "페이탈코드"
            },
            {
                "idx": "213",
                "name": "둠스데이: 라스트 서바이버"
            },
            {
                "idx": "214",
                "name": "WOS:화이트아웃서바이벌"
            },
            {
                "idx": "215",
                "name": "픽셀히어로"
            },
            {
                "idx": "216",
                "name": "무명 기사단"
            },
            {
                "idx": "217",
                "name": "클래시 오브 클랜"
            },
            {
                "idx": "218",
                "name": "다크에덴m"
            },
            {
                "idx": "219",
                "name": "이세계 가디스 스토리"
            },
            {
                "idx": "220",
                "name": "MLB 9이닝스 라이벌"
            },
            {
                "idx": "221",
                "name": "아카디아M"
            },
            {
                "idx": "222",
                "name": "카운터 스트라이크"
            },
            {
                "idx": "223",
                "name": "소녀 에볼루션"
            },
            {
                "idx": "224",
                "name": "마비노기 영웅전"
            },
            {
                "idx": "225",
                "name": "테일즈위버"
            },
            {
                "idx": "226",
                "name": "데몬스쿼드 키우기"
            },
            {
                "idx": "227",
                "name": "그랜드크로스: 에이지오브타이탄"
            },
            {
                "idx": "228",
                "name": "타이니테일즈"
            },
            {
                "idx": "229",
                "name": "컴투스프로야구V26"
            },
            {
                "idx": "230",
                "name": "소울즈"
            },
            {
                "idx": "231",
                "name": "라그나돌"
            },
            {
                "idx": "232",
                "name": "루나: 달빛 연대기"
            },
            {
                "idx": "233",
                "name": "언던(Undawn)"
            },
            {
                "idx": "234",
                "name": "원피스트레저크루즈"
            },
            {
                "idx": "235",
                "name": "빛의계승자:이클립스"
            },
            {
                "idx": "236",
                "name": "드래곤에어 : 침묵의 신"
            },
            {
                "idx": "237",
                "name": "트릭컬리바이브"
            },
            {
                "idx": "238",
                "name": "몬스터헌터 나우"
            },
            {
                "idx": "239",
                "name": "잡캐키우기온라인"
            },
            {
                "idx": "240",
                "name": "포트리스사가"
            },
            {
                "idx": "241",
                "name": "클라우드 트레일: 팀 벤처"
            },
            {
                "idx": "242",
                "name": "어둠의 실력자가 되고 싶어서"
            },
            {
                "idx": "243",
                "name": "뮤모나크"
            },
            {
                "idx": "244",
                "name": "진격의 거인 브레이브 오더"
            },
            {
                "idx": "245",
                "name": "진삼국무쌍M"
            },
            {
                "idx": "246",
                "name": "해양전설"
            },
            {
                "idx": "247",
                "name": "나이트코어킹덤"
            },
            {
                "idx": "248",
                "name": "옥토패스 트래블러 대륙의패자"
            },
            {
                "idx": "249",
                "name": "더블유w: 크로스 월드"
            },
            {
                "idx": "250",
                "name": "라그나로크 비긴즈"
            },
            {
                "idx": "251",
                "name": "유령기사 키우기"
            },
            {
                "idx": "252",
                "name": "버섯커키우기"
            },
            {
                "idx": "253",
                "name": "삼켜라 드래곤"
            },
            {
                "idx": "254",
                "name": "아도르: 수호의 여신"
            },
            {
                "idx": "255",
                "name": "콜오브듀티 워존 모바일"
            },
            {
                "idx": "256",
                "name": "크리티카:제로"
            },
            {
                "idx": "257",
                "name": "소울 스트라이크"
            },
            {
                "idx": "258",
                "name": "갓레이드"
            },
            {
                "idx": "259",
                "name": "999위용사"
            },
            {
                "idx": "260",
                "name": "그라나도에스파다m"
            },
            {
                "idx": "261",
                "name": "라스트에포크"
            },
            {
                "idx": "262",
                "name": "소드마스터 스토리"
            },
            {
                "idx": "263",
                "name": "브롤스타즈"
            },
            {
                "idx": "264",
                "name": "하이큐!!FLYHIGH"
            },
            {
                "idx": "265",
                "name": "워처오브렐름"
            },
            {
                "idx": "266",
                "name": "드래곤볼 돗칸배틀(폭렬격전)"
            },
            {
                "idx": "267",
                "name": "파티히어로"
            },
            {
                "idx": "268",
                "name": "스트리트 파이터: 듀"
            },
            {
                "idx": "269",
                "name": "히어로킹"
            },
            {
                "idx": "270",
                "name": "페르소나 5: 더 팬텀 X"
            },
            {
                "idx": "271",
                "name": "크리스탈나이츠"
            },
            {
                "idx": "272",
                "name": "라테일"
            },
            {
                "idx": "273",
                "name": "도사: 가디언즈"
            },
            {
                "idx": "274",
                "name": "그랑사가 키우기: 나이츠X나이츠"
            },
            {
                "idx": "275",
                "name": "스쿼드 버스터즈"
            },
            {
                "idx": "276",
                "name": "운빨존많겜"
            },
            {
                "idx": "277",
                "name": "블러드 위치"
            },
            {
                "idx": "278",
                "name": "MLB클러치히트베이스"
            },
            {
                "idx": "279",
                "name": "카드캡터 체리: 추억의 열쇠"
            },
            {
                "idx": "280",
                "name": "배틀크러쉬"
            },
            {
                "idx": "281",
                "name": "빵빵 좀비단"
            },
            {
                "idx": "282",
                "name": "퍼스트 디센던트"
            },
            {
                "idx": "283",
                "name": "미니히어로즈: Reborn"
            },
            {
                "idx": "284",
                "name": "쿠루쿠루 별가루 대모험"
            },
            {
                "idx": "285",
                "name": "메탈슬러그: 각성"
            },
            {
                "idx": "286",
                "name": "모두의마블"
            },
            {
                "idx": "287",
                "name": "일곱 개의 대죄 키우기"
            },
            {
                "idx": "288",
                "name": "미르의 전설2: 기연"
            },
            {
                "idx": "306",
                "name": "트리 오브 세이비어: 네버랜드"
            },
            {
                "idx": "307",
                "name": "더 라그나로크"
            },
            {
                "idx": "308",
                "name": "뮤 모나크2"
            },
            {
                "idx": "309",
                "name": "고고머핀!"
            },
            {
                "idx": "310",
                "name": "로한2"
            },
            {
                "idx": "312",
                "name": "에이지 오브 엠파이어 모바일"
            },
            {
                "idx": "311",
                "name": "인피니트 라그랑주"
            },
            {
                "idx": "313",
                "name": "저니 오브 모나크"
            },
            {
                "idx": "314",
                "name": "블레이드앤소울네오"
            },
            {
                "idx": "315",
                "name": "파이브스타즈 : 운명의 서사시"
            },
            {
                "idx": "316",
                "name": "히어로즈 키우기"
            },
            {
                "idx": "317",
                "name": "메카아라시"
            },
            {
                "idx": "318",
                "name": "포켓몬 카드게임 Pocket"
            },
            {
                "idx": "319",
                "name": "포켓몬GO"
            },
            {
                "idx": "320",
                "name": "주술회전 팬텀 퍼레이드"
            },
            {
                "idx": "321",
                "name": "바람의 드래군M"
            },
            {
                "idx": "322",
                "name": "바람의나라클래식"
            },
            {
                "idx": "323",
                "name": "소녀전선2: 망명"
            },
            {
                "idx": "324",
                "name": "귀혼M"
            },
            {
                "idx": "325",
                "name": "큐플레이 아카이브"
            },
            {
                "idx": "327",
                "name": "세라핌 사가: 날개소녀 키우기"
            },
            {
                "idx": "328",
                "name": "픽셀 법사 키우기"
            },
            {
                "idx": "326",
                "name": "테일즈런너RPG"
            },
            {
                "idx": "329",
                "name": "킹 아서: 레전드 라이즈"
            },
            {
                "idx": "330",
                "name": "인피니티 니키"
            },
            {
                "idx": "331",
                "name": "머지머지 디펜스"
            },
            {
                "idx": "332",
                "name": "패스 오브 엑자일 2"
            },
            {
                "idx": "333",
                "name": "밀리언아서:링"
            },
            {
                "idx": "334",
                "name": "리메멘토 - 하얀 그림자"
            },
            {
                "idx": "335",
                "name": "에이펙스 걸스"
            },
            {
                "idx": "337",
                "name": "로스트 소드"
            },
            {
                "idx": "336",
                "name": "99강화 나무몽둥이 : 키우기"
            },
            {
                "idx": "338",
                "name": "미르2: 뉴킹덤"
            },
            {
                "idx": "339",
                "name": "오버로드: 나자릭의 왕"
            },
            {
                "idx": "340",
                "name": "나혼자만렙삼국"
            },
            {
                "idx": "341",
                "name": "발할라 서바이벌"
            },
            {
                "idx": "345",
                "name": "겟앰프드키우기"
            },
            {
                "idx": "344",
                "name": "이세계 판타지 라이프"
            },
            {
                "idx": "343",
                "name": "레전드 오브 이미르"
            },
            {
                "idx": "342",
                "name": "레조넌스"
            },
            {
                "idx": "346",
                "name": "특급 주술대전 4인전"
            },
            {
                "idx": "347",
                "name": "페이트 그랜드 오더"
            },
            {
                "idx": "348",
                "name": "트라이브 나인"
            },
            {
                "idx": "349",
                "name": "카르페디엠"
            },
            {
                "idx": "350",
                "name": "RF온라인 넥스트"
            },
            {
                "idx": "351",
                "name": "옛날바람"
            },
            {
                "idx": "352",
                "name": "운빨돌격대"
            },
            {
                "idx": "353",
                "name": "마비노기모바일"
            },
            {
                "idx": "355",
                "name": "라그나로크 : Back To Glory"
            },
            {
                "idx": "354",
                "name": "앵커패닉"
            },
            {
                "idx": "356",
                "name": "DK모바일 리본"
            },
            {
                "idx": "357",
                "name": "SD건담G제네이터널"
            },
            {
                "idx": "358",
                "name": "유희왕 마스터듀얼"
            },
            {
                "idx": "359",
                "name": "엑시스 블레이드"
            },
            {
                "idx": "360",
                "name": "카르나크"
            },
            {
                "idx": "361",
                "name": "MLB 9이닝스 25"
            },
            {
                "idx": "362",
                "name": "세븐나이츠 리버스"
            },
            {
                "idx": "363",
                "name": "원피스 바운티러쉬"
            },
            {
                "idx": "364",
                "name": "드래곤볼 레전드"
            },
            {
                "idx": "365",
                "name": "아드"
            },
            {
                "idx": "366",
                "name": "CoA: 아틀란의 크리스탈"
            },
            {
                "idx": "367",
                "name": "서머너즈 워: 러쉬"
            },
            {
                "idx": "368",
                "name": "에테리아 리스타트"
            },
            {
                "idx": "369",
                "name": "믹스마스터"
            },
            {
                "idx": "370",
                "name": "포트나이트"
            },
            {
                "idx": "371",
                "name": "제5인격"
            },
            {
                "idx": "372",
                "name": "섀도우버스 월즈 비욘드"
            },
            {
                "idx": "373",
                "name": "모에라이: 운명의 계약"
            },
            {
                "idx": "374",
                "name": "문명: 연맹의 시대"
            },
            {
                "idx": "375",
                "name": "실버 앤 블러드"
            },
            {
                "idx": "376",
                "name": "사무라이 쇼다운 R"
            },
            {
                "idx": "377",
                "name": "리버스 블루×리버스 엔드"
            },
            {
                "idx": "378",
                "name": "에그몬 월드:저니"
            },
            {
                "idx": "379",
                "name": "미니언100"
            },
            {
                "idx": "380",
                "name": "파이널판타지14"
            },
            {
                "idx": "381",
                "name": "랜드 오브 제일"
            },
            {
                "idx": "382",
                "name": "신월동행"
            },
            {
                "idx": "383",
                "name": "다크에덴"
            },
            {
                "idx": "384",
                "name": "열혈강호:귀환"
            },
            {
                "idx": "385",
                "name": "엘피스 전기: 소울링"
            },
            {
                "idx": "386",
                "name": "천상비"
            },
            {
                "idx": "387",
                "name": "더 스타라이트"
            },
            {
                "idx": "388",
                "name": "뱀피르"
            },
            {
                "idx": "389",
                "name": "호라이즌 워커"
            },
            {
                "idx": "390",
                "name": "라그나로크 아이들 어드벤처PLUS"
            },
            {
                "idx": "391",
                "name": "월드오브워크래프트:클래식"
            },
            {
                "idx": "392",
                "name": "에타 크로니클"
            },
            {
                "idx": "393",
                "name": "괴수 8호 THE GAME"
            },
            {
                "idx": "394",
                "name": "킹오브파이터AFK"
            },
            {
                "idx": "395",
                "name": "원스휴먼"
            },
            {
                "idx": "396",
                "name": "가디스오더"
            },
            {
                "idx": "88",
                "name": "서머너즈 워: 크로니클"
            },
            {
                "idx": "398",
                "name": "뮤: 포켓 나이츠"
            },
            {
                "idx": "399",
                "name": "디지몬마스터즈"
            },
            {
                "idx": "400",
                "name": "디지몬RPG"
            },
            {
                "idx": "401",
                "name": "디지몬슈퍼럼블"
            },
            {
                "idx": "402",
                "name": "R2오리진"
            },
            {
                "idx": "403",
                "name": "로블록스"
            },
            {
                "idx": "404",
                "name": "프리프 유니버스"
            },
            {
                "idx": "405",
                "name": "듀엣 나이트 어비스"
            },
            {
                "idx": "406",
                "name": "아키텍트 랜드 오브 엑자일"
            },
            {
                "idx": "408",
                "name": "카오스 제로 나이트메어"
            },
            {
                "idx": "409",
                "name": "스타세이비어"
            },
            {
                "idx": "410",
                "name": "아스텔리아M"
            },
            {
                "idx": "411",
                "name": "크레이지아케이드"
            },
            {
                "idx": "412",
                "name": "FC모바일"
            },
            {
                "idx": "413",
                "name": "스텔라 소라"
            },
            {
                "idx": "414",
                "name": "아스가르드"
            },
            {
                "idx": "415",
                "name": "뮤"
            },
            {
                "idx": "416",
                "name": "뮤 BLUE"
            },
            {
                "idx": "417",
                "name": "천지겁"
            },
            {
                "idx": "418",
                "name": "겟앰프드"
            },
            {
                "idx": "419",
                "name": "미르의 전설2:레드나이트"
            },
            {
                "idx": "420",
                "name": "메이플키우기"
            },
            {
                "idx": "421",
                "name": "천상비K"
            },
            {
                "idx": "422",
                "name": "풋볼 매니저 26"
            },
            {
                "idx": "423",
                "name": "역수한"
            },
            {
                "idx": "424",
                "name": "레알팜"
            },
            {
                "idx": "425",
                "name": "유유백서: 격전"
            },
            {
                "idx": "426",
                "name": "개방공간: 오버필드"
            },
            {
                "idx": "427",
                "name": "레이싱마스터"
            },
            {
                "idx": "428",
                "name": "냥코대전쟁"
            },
            {
                "idx": "429",
                "name": "아크 레이더스"
            },
            {
                "idx": "430",
                "name": "블리치: 소울 레조넌스"
            },
            {
                "idx": "431",
                "name": "카발레드"
            },
            {
                "idx": "432",
                "name": "와다다 던전런"
            },
            {
                "idx": "433",
                "name": "라스트 Z: 서바이벌 슈터"
            },
            {
                "idx": "434",
                "name": "헤이즈 리버브"
            },
            {
                "idx": "435",
                "name": "모여봐요 동물의 숲"
            },
            {
                "idx": "436",
                "name": "부활얍카"
            },
            {
                "idx": "437",
                "name": "로스트아크M"
            },
            {
                "idx": "438",
                "name": "판타테일"
            },
            {
                "idx": "439",
                "name": "연운"
            },
            {
                "idx": "440",
                "name": "킹샷"
            },
            {
                "idx": "441",
                "name": "이스케이프 프롬 타르코프"
            },
            {
                "idx": "442",
                "name": "던전 슬래셔"
            },
            {
                "idx": "443",
                "name": "일곱 개의 대죄: Origin"
            },
            {
                "idx": "444",
                "name": "블루 프로토콜: 스타 레조넌스"
            },
            {
                "idx": "445",
                "name": "명일방주: 엔드필드"
            },
            {
                "idx": "446",
                "name": "드래곤네스트 클래식"
            },
            {
                "idx": "447",
                "name": "일곱개의대죄: GRAND CROSS"
            },
            {
                "idx": "448",
                "name": "로맨싱사가 리유니버스"
            },
            {
                "idx": "449",
                "name": "코드아크"
            },
            {
                "idx": "450",
                "name": "라스트 오리진"
            },
            {
                "idx": "451",
                "name": "잠룡:무협도트RPG"
            },
            {
                "idx": "452",
                "name": "붉은보석"
            },
            {
                "idx": "453",
                "name": "펭귄 대모험: 꽁꽁 방어전"
            },
            {
                "idx": "454",
                "name": "라스트 워: 서바이벌"
            },
            {
                "idx": "456",
                "name": "하이테일"
            },
            {
                "idx": "457",
                "name": "세가 풋볼 클럽 챔피언스 26"
            },
            {
                "idx": "458",
                "name": "하이가드"
            },
            {
                "idx": "459",
                "name": "린 크로니클"
            },
            {
                "idx": "460",
                "name": "다크디셈버"
            },
            {
                "idx": "461",
                "name": "그놈은드래곤"
            },
            {
                "idx": "462",
                "name": "드래곤소드"
            },
            {
                "idx": "463",
                "name": "실버팰리스"
            },
            {
                "idx": "464",
                "name": "컴투스프로야구2026"
            },
            {
                "idx": "465",
                "name": "귀판오분전"
            },
            {
                "idx": "466",
                "name": "협동타워디펜스"
            },
            {
                "idx": "467",
                "name": "미송자의 노래"
            },
            {
                "idx": "468",
                "name": "PUBG: 블라인드스팟"
            },
            {
                "idx": "469",
                "name": "온라인삼국지2"
            },
            {
                "idx": "470",
                "name": "헤븐헬즈"
            },
            {
                "idx": "471",
                "name": "에르피스"
            },
            {
                "idx": "472",
                "name": "바이오하자드 서바이벌 유닛"
            },
            {
                "idx": "473",
                "name": "러브앤딥스페이스"
            },
            {
                "idx": "474",
                "name": "이환"
            },
            {
                "idx": "475",
                "name": "어비스디아"
            },
            {
                "idx": "476",
                "name": "어나더던전"
            },
            {
                "idx": "477",
                "name": "조선협객전 클래식"
            },
            {
                "idx": "478",
                "name": "라그나로크 오리진 클래식"
            },
            {
                "idx": "479",
                "name": "페이트 트리거"
            },
            {
                "idx": "480",
                "name": "DX: 각성자들"
            },
            {
                "idx": "481",
                "name": "스톤에이지 키우기"
            },
            {
                "idx": "482",
                "name": "메카 르네상스"
            },
            {
                "idx": "483",
                "name": "두근두근타운"
            },
            {
                "idx": "484",
                "name": "SOL: enchant(솔인챈트)"
            },
            {
                "idx": "485",
                "name": "Total Football(토탈풋볼)26"
            },
            {
                "idx": "486",
                "name": "창세기전키우기"
            },
            {
                "idx": "487",
                "name": "쿠키런: 오븐스매시"
            },
            {
                "idx": "488",
                "name": "붉은사막"
            },
            {
                "idx": "489",
                "name": "스페셜포스 리마스터"
            },
            {
                "idx": "490",
                "name": "삼국지 왕전"
            },
            {
                "idx": "491",
                "name": "낙원: LAST PARADISE"
            },
            {
                "idx": "492",
                "name": "2026 프로야구GO!"
            },
            {
                "idx": "493",
                "name": "몬길: STAR DIVE"
            },
            {
                "idx": "494",
                "name": "MLB 퍼펙트 이닝 26"
            },
            {
                "idx": "495",
                "name": "컴투스프로야구for매니저"
            },
            {
                "idx": "496",
                "name": "임진왜란: 조선의 반격"
            },
            {
                "idx": "497",
                "name": "왕좌의 게임: 킹스로드"
            },
            {
                "idx": "498",
                "name": "아주르 프로밀리아"
            },
            {
                "idx": "499",
                "name": "드래곤빌리지3"
            },
            {
                "idx": "7",
                "name": "그외게임"
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
                        item.get('value') for item in items if item.get('checked')
                    ]

                # 2. 구매 경로 섹션일 때
                elif sec_id == 'purchasePath':
                    items = self.get_items(sec_id)
                    # checked가 True인 자식들 중에서 'value'만 쏙 뽑아서 리스트로 만들기
                    self.purchasePath_list = [
                        item.get('value') for item in items if item.get('checked')
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
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": "https://idfarm.co.kr/"
            }

            self.total_cnt = len(self.game_list)
            self.current_cnt = 0

            # 전체 아이템 진행도 로깅을 위한 누적 카운트
            total_items_saved = 0

            # 👇 [수정됨] enumerate를 사용해 현재 게임의 인덱스(game_idx_num)를 1부터 추적
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

                    # 1. URL 및 파라미터 구성
                    url = f"https://idfarm.co.kr/ItemMarket/character/{idx}"

                    params = {
                        "state": "all",
                        "sort": "new",
                        "search_action": "1",
                        "trx_type": "SELL",
                        "job[]": "전체",
                        "server[]": "전체",
                        "serverChannel[]": "전체",
                        "account_no": "전체",
                        "payment_history": "전체",
                        "account_multi_link": "전체",
                        "min_character_level": "",
                        "max_character_level": "",
                        "sellMethod": "전체",
                        "page": page
                    }

                    if self.accountType_list:
                        params["accountType[]"] = self.accountType_list
                    if self.purchasePath_list:
                        params["buyType[]"] = self.purchasePath_list
                    if self.min:
                        params["min"] = self.min
                    if self.max:
                        params["max"] = self.max
                    if self.keyword:
                        params["stx"] = self.keyword

                    try:
                        # 2. HTML 데이터 가져오기
                        response = self.api_client.get(url, headers=headers, params=params)

                        soup = BeautifulSoup(response, 'html.parser')

                        # "상품이 없습니다" 태그 확인
                        empty_tag = soup.find('p', class_='list-empty')
                        if empty_tag:
                            self.log_signal_func(f"  -> ⏹️ [종료] '상품이 없습니다' 태그 감지. (Page: {page})")
                            break

                        # 아이템 목록 파싱 (PC용 UI 기준)
                        items = soup.select('ul.market-item-row.trade_mode.desktop-item-list')

                        if not items:
                            self.log_signal_func(f"  -> ⏹️ [종료] 파싱할 상품 리스트가 없습니다. (Page: {page})")
                            break

                        self.log_signal_func(f"[{game_name_setting} | P.{page}] 파싱된 상품 수: {len(items)}개")

                        new_item_found = False # 새 아이템이 하나라도 있는지 체크

                        # 3. 데이터 추출 및 즉시 DB 저장
                        for item in items:
                            if self._stop_event.is_set() or not self.running:
                                self.log_signal_func("⛔ 중지 감지 → 저장 후 종료")
                                break

                            item_id = item.get('data-item-id', '')

                            # 중복 아이템(프리미엄 등) 거르기
                            if not item_id or item_id in seen_item_ids:
                                continue

                            seen_item_ids.add(item_id)
                            new_item_found = True

                            item_url = f"https://idfarm.co.kr/ItemMarket/gameItem/{item_id}"

                            # [수정 1] 거래 상태(판매중/거래완료) 추출 후 '거래완료(finish)'면 제외
                            item_classes = item.get('class', [])
                            if 'finish' in item_classes:
                                continue # 거래완료 상품은 스킵
                            trade_status = "판매중"

                            # 계정 종류 및 등급 배지 추출
                            account_types = []
                            logo_areas = item.select('.logo-area-wrap .logo-area')
                            for logo in logo_areas:
                                classes = logo.get('class', [])
                                for c in classes:
                                    if c != 'logo-area':
                                        account_types.append(c)

                            svg_elem = item.select_one('.logo-area i svg')
                            if svg_elem and svg_elem.get('aria-label'):
                                account_types.append(svg_elem.get('aria-label'))

                            # [수정 2] 선택한 계정 종류만 나오도록 필터링
                            if self.accountType_list:
                                extracted_str = " ".join(account_types).lower()
                                is_allowed = False

                                for sel in self.accountType_list:
                                    if sel == '게임사' and 'game-company' in extracted_str: is_allowed = True
                                    elif sel == '구글' and 'google' in extracted_str: is_allowed = True
                                    elif sel == '페이스북' and ('facebook' in extracted_str or 'face' in extracted_str): is_allowed = True
                                    elif sel == '전화번호' and 'phone' in extracted_str: is_allowed = True
                                    elif sel == '카카오' and 'kakao' in extracted_str: is_allowed = True
                                    elif sel == '네이버' and 'naver' in extracted_str: is_allowed = True
                                    elif sel == '기타' and 'etc' in extracted_str: is_allowed = True

                                # 사용자가 선택한 계정 조건에 하나도 부합하지 않으면 저장하지 않고 스킵
                                if not is_allowed:
                                    continue

                            account_type_str = ", ".join(account_types) if account_types else ""

                            # 제목
                            title_elem = item.select_one('.item-content-wrapper .one-line-trunc')
                            title = title_elem.get_text(strip=True) if title_elem else ""

                            # 메타정보
                            meta_info = item.select_one('.item-meta-info')
                            server, job, trade_type = "", "", ""
                            if meta_info:
                                game_servers = meta_info.select('.game-server')
                                if len(game_servers) >= 1:
                                    server = game_servers[0].get_text(strip=True)
                                if len(game_servers) >= 2:
                                    trade_type = game_servers[1].get_text(strip=True)

                                career_elem = meta_info.select_one('.career')
                                if career_elem:
                                    job = career_elem.get_text(strip=True)

                            # 가격
                            price_elem = item.select_one('.price-date-container .price--minimum.sale-price')
                            price = price_elem.get_text(strip=True).replace('\xa0', '') if price_elem else ""

                            # 게임명 (페이지의 h2 태그 우선, 없으면 설정값)
                            game_title_elem = soup.select_one('h2.content__title span')
                            actual_game_name = game_title_elem.get_text(strip=True) if game_title_elem else game_name_setting

                            # DB Insert 용 Dictionary 생성
                            row_data = {
                                "게임명": actual_game_name,
                                "게시글 ID": item_id,
                                "계정종류": account_type_str,
                                "제목": title,
                                "서버": server,
                                "직업": job,
                                "거래유형": trade_type,
                                "가격": price,
                                "URL": item_url,
                                "거래상태": trade_status
                            }

                            # DB(및 엑셀용 메모리)에 저장
                            self.insert_detail_row(row_data)

                            total_items_saved += 1
                            self.log_signal_func(f"[{game_idx_num}/{self.total_cnt}] [{total_items_saved}] DB 저장: [{actual_game_name}] [{trade_status}] {title}")

                        if not new_item_found:
                            self.log_signal_func(f"  -> ⏹️ [종료] 새로운 상품이 없습니다 (중복/프리미엄만 존재). (Page: {page})")
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