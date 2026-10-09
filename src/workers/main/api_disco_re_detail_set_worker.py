"""디스코 목록·상세 조회 → 체크한 컬럼만 공통 SQLite DB에 저장합니다."""

import json
import math
import time
from datetime import datetime
from urllib.parse import urlencode

from selenium.webdriver.support.ui import WebDriverWait

from src.utils.disco_filters import build_disco_form
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker
from src.repositories.worker_db_repository import WorkerDbRepository


LIST_LIMIT = 20
MAP_LEVEL = 3

# 디스코 화면에서 확인한 map_lv=3의 네 방향 거리를 기준으로 사용합니다.
# 실제 요청 범위는 config의 가로·세로 배율(기본 1.5)을 적용해 중간값으로 넓힙니다.
EARTH_RADIUS = 6378137.0
REFERENCE_MAP = {
    "swLat": 37.488512425802476, "swLng": 127.046812752172,
    "neLat": 37.49796186353175, "neLng": 127.06659383688581,
    "centerLat": 37.49323776305756, "centerLng": 127.05670253513213,
}

DEFAULT_FORM = [
    ("approvalYear", "null"),
    ("minPrice", "null"),
    ("maxPrice", "null"),
    ("minMonthly", "null"),
    ("maxMonthly", "null"),
    ("minDeposit", "null"),
    ("maxDeposit", "null"),
    ("minArea", "null"),
    ("maxArea", "null"),
    ("areaUnit", "pyeong"),
    ("selectedCategory", "null"),
    ("ownerVerifiedOnly", ""),
]


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

# 디스코 페이지가 지역 검색에 사용하는 카카오 geocoder를 그대로 호출합니다.


# 디스코 페이지 안에서 같은 출처 및 data.disco.re의 JSON을 조회합니다.



def _date_text(value):
    """YYYYMMDD를 YYYY-MM-DD로 바꿉니다."""
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return str(value or "") or None


def _price_text(value):
    """만원 단위 실거래가를 61억, 53억 7,900만원 형태로 표시합니다."""
    try:
        price = int(float(value))
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    billion, ten_thousand = divmod(price, 10000)
    if billion and ten_thousand:
        return f"{billion}억 {ten_thousand:,}만원"
    if billion:
        return f"{billion}억"
    return f"{ten_thousand:,}만원"


def _address_parts(address):
    """지번주소에서 시도, 시군구, 읍면동을 단순 분리합니다."""
    tokens = str(address or "").split()
    if not tokens:
        return None, None, None

    lot_index = next(
        (index for index, token in enumerate(tokens) if any(ch.isdigit() for ch in token)),
        len(tokens),
    )
    regions = tokens[:lot_index]
    sido = regions[0] if regions else None
    eup_myeon_dong = regions[-1] if len(regions) >= 2 else None
    sigungu = " ".join(regions[1:-1]) or None
    return sido, sigungu, eup_myeon_dong


def _planning_values(value):
    """토지이용계획 문장을 화면의 포함/저촉/접함 항목으로 분리합니다."""
    relations = {"포함": [], "저촉": [], "접함": []}
    for text in str(value or "").split(","):
        text = text.strip()
        for relation in relations:
            suffix = f"({relation})"
            if text.endswith(suffix):
                relations[relation].append(text[:-len(suffix)].strip())
                break
    return {
        relation: ", ".join(values) if values else None
        for relation, values in relations.items()
    }


def _korean_land_info(result):
    """land_by_pnu 응답을 실제 화면 명칭으로 변환합니다."""
    main_plan = _planning_values(result.get("land_use_planning_info_main"))
    etc_plan = _planning_values(result.get("land_use_planning_info_etc"))
    owner = result.get("owner_gbn")
    share = result.get("share")
    if owner not in (None, "") and share not in (None, ""):
        owner = f"{owner} (공유인수 {share})"

    return {
        "토지 정보_면적": result.get("area"),
        "토지 정보_지목": result.get("purpose"),
        "토지 정보_용도지역": result.get("p6"),
        "토지 정보_이용상황": result.get("p10"),
        "토지 정보_소유구분": owner,
        "토지 정보_소유권변동일자": _date_text(result.get("days")),
        "토지 정보_소유권변동원인": result.get("why"),
        "토지 정보_도로접면": result.get("p16"),
        "토지 정보_지형높이": result.get("p12"),
        "토지 정보_지형형상": result.get("p14"),
        "토지이용계획_국토의 계획 및 이용에 관한 법률_포함": main_plan["포함"],
        "토지이용계획_국토의 계획 및 이용에 관한 법률_저촉": main_plan["저촉"],
        "토지이용계획_국토의 계획 및 이용에 관한 법률_접함": main_plan["접함"],
        "토지이용계획_기타법률_포함": etc_plan["포함"],
        "토지이용계획_기타법률_저촉": etc_plan["저촉"],
        "토지이용계획_기타법률_접함": etc_plan["접함"],
    }


def _korean_land_history(rows):
    """화면의 토지 이동(변동) 사유 표와 동일한 키로 변환합니다."""
    return [
        {
            "일자": _date_text(row.get("move_date")),
            "사유": row.get("reason"),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def _korean_land_prices(rows):
    """개별공시지가 표를 기준년도/공시지가 배열과 현재 금액으로 만듭니다."""
    prices = []
    sortable = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            continue
        year, month, price = row[0], str(row[1]).zfill(2), row[2]
        prices.append({
            "기준년도": f"{year}.{month}",
            "공시지가(㎡)": price,
        })
        try:
            sortable.append((int(year), int(month), price))
        except (TypeError, ValueError):
            pass

    current_price = max(sortable, default=(None, None, None))[2]
    return {
        "개별공시지가": prices,
        "개별공시지가_공시지가(㎡)": current_price,
    }


def _korean_arch_info(result):
    """arch_by_pnu의 첫 표제부를 화면의 건물 정보 명칭으로 변환합니다."""
    rows = result.get("title_section") or result.get("overall_title_section") or []
    if not rows or not isinstance(rows[0], dict):
        return {}
    row = rows[0]
    return {
        "건물 정보_건물이름": row.get("a23"),
        "건물 정보_주용도": row.get("a36"),
        "건물 정보_기타용도": row.get("a37"),
        "건물 정보_주구조": row.get("a33"),
        "건물 정보_지붕구조": row.get("a39"),
        "건물 정보_높이": row.get("a43"),
        "건물 정보_지상/지하": f"{row.get('a44')}/{row.get('a45')}",
        "건물 정보_대지면적": row.get("a26"),
        "건물 정보_건축면적": row.get("a27"),
        "건물 정보_건축면적_건폐율": row.get("a28"),
        "건물 정보_연면적": row.get("a29"),
        "건물 정보_용적률산정연면적": row.get("a30"),
        "건물 정보_용적률산정연면적_용적률": row.get("a31"),
        "건물 정보_세대 수_세대": row.get("a41"),
        "건물 정보_세대 수_가구": row.get("a42"),
        "건물 정보_세대 수_호수": row.get("a67"),
        "건물 정보_외필지 수": row.get("a17"),
        "건물 정보_오수정화시설_형식": row.get("g23"),
        "건물 정보_오수정화시설_형식(기타)": row.get("g24"),
        "건물 정보_오수정화시설_용량(인용)": row.get("g26"),
        "건물 정보_오수정화시설_용량(루베)": row.get("g27"),
        "건물 정보_주차장_자주식_옥내_댓수": row.get("a55"),
        "건물 정보_주차장_자주식_옥내_면적": row.get("a56"),
        "건물 정보_주차장_자주식_옥외_댓수": row.get("a57"),
        "건물 정보_주차장_자주식_옥외_면적": row.get("a58"),
        "건물 정보_주차장_기계식_옥내_댓수": row.get("a51"),
        "건물 정보_주차장_기계식_옥내_면적": row.get("a52"),
        "건물 정보_주차장_기계식_옥외_댓수": row.get("a53"),
        "건물 정보_주차장_기계식_옥외_면적": row.get("a54"),
        "건물 정보_승강기_승용": row.get("a46"),
        "건물 정보_승강기_비상용": row.get("a47"),
        "건물 정보_일자정보_허가일": _date_text(row.get("a59")),
        "건물 정보_일자정보_착공일": _date_text(row.get("a60")),
        "건물 정보_일자정보_사용승인일": _date_text(row.get("a61")),
    }


def _korean_arch_floors(rows):
    """arch_floor_list 응답을 건축물현황의 한글 키 배열로 변환합니다."""
    return [
        {
            "건축물구분": row.get("d31"),
            "층": row.get("floor"),
            "주용도": row.get("d27"),
            "기타용도": row.get("d28"),
            "구조": row.get("d24"),
            "면적": row.get("d29"),
            "건물이름": row.get("d32"),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def _korean_businesses(rows):
    """상가업소정보를 화면 상세 팝업의 명칭으로 변환합니다."""
    businesses = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        location = ""
        if row.get("dong"):
            location += f"{row['dong']}동"
        if row.get("floor"):
            location += f" {row['floor']}층"
        if row.get("ho"):
            location += f" {row['ho']}호"
        businesses.append({
            "상호명": row.get("sbname"),
            "층호정보": location.strip() or "층호정보없음",
            "업종 대분류": row.get("sbclass1name"),
            "업종 중분류": row.get("sbclass2name"),
            "업종 소분류": row.get("sbclass3name"),
        })
    return businesses


def _korean_house_prices(rows):
    """개별주택공시가격을 화면 표와 현재 가격으로 변환합니다."""
    prices = []
    sortable = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            continue
        year, month, price = row[0], str(row[1]).zfill(2), row[2]
        prices.append({
            "기준년도": f"{year}.{month}",
            "공시가격": price,
        })
        try:
            sortable.append((int(year), int(month), price))
        except (TypeError, ValueError):
            pass
    return {
        "개별주택공시가격": prices,
        "개별주택공시가격_공시가격": max(
            sortable,
            default=(None, None, None),
        )[2],
    }


def _korean_exclusive_parts(rows):
    """전유부 표를 화면의 한글 키 배열로 변환합니다."""
    return [
        {
            "구분": row.get("e28"),
            "층": row.get("e31"),
            "면적": row.get("e38"),
            "건축물": row.get("e30"),
            "용도": row.get("e37"),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def _korean_apart_prices(rows):
    """공동주택공시가격을 화면 표와 현재 가격으로 변환합니다."""
    prices = []
    sortable = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            continue
        year, month, price = row[0], str(row[1]).zfill(2), row[2]
        prices.append({
            "기준년도": f"{year}.{month}",
            "공시가격": price,
        })
        try:
            sortable.append((int(year), int(month), price))
        except (TypeError, ValueError):
            pass

    current = max(sortable, default=(None, None, None))[2]
    first = rows[0] if rows and isinstance(rows[0], (list, tuple)) else []
    return {
        "공동주택공시가격": prices,
        "공동주택공시가격_공시가격": current,
        "공동주택공시가격_동": first[3] if len(first) > 3 else None,
        "공동주택공시가격_층": first[4] if len(first) > 4 else None,
        "공동주택공시가격_호": first[5] if len(first) > 5 else None,
        "공동주택공시가격_전용면적": first[6] if len(first) > 6 else None,
    }


def make_map_bounds(center_lat, center_lng, width_scale=1.0, height_scale=1.0):
    """중심 위·경도로 map_lv=4의 남서/북동 좌표를 계산합니다."""
    lat = float(center_lat)
    lng = float(center_lng)
    if not -85.0 < lat < 85.0 or not -180.0 <= lng <= 180.0:
        raise ValueError(f"잘못된 중심 좌표입니다: lat={lat}, lng={lng}")
    if not 0 < width_scale <= 3 or not 0 < height_scale <= 3:
        raise ValueError("지도 배율은 0보다 크고 3 이하여야 합니다.")

    def mercator_y(latitude):
        return EARTH_RADIUS * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))

    # 기준 화면의 중심이 사각형의 정확한 중앙이 아니므로 네 방향을 따로 보존합니다.
    left = EARTH_RADIUS * math.radians(REFERENCE_MAP["centerLng"] - REFERENCE_MAP["swLng"])
    right = EARTH_RADIUS * math.radians(REFERENCE_MAP["neLng"] - REFERENCE_MAP["centerLng"])
    down = mercator_y(REFERENCE_MAP["centerLat"]) - mercator_y(REFERENCE_MAP["swLat"])
    up = mercator_y(REFERENCE_MAP["neLat"]) - mercator_y(REFERENCE_MAP["centerLat"])

    center_x = EARTH_RADIUS * math.radians(lng)
    center_y = EARTH_RADIUS * math.log(
        math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)
    )

    def to_lat_lng(x, y):
        out_lat = math.degrees(2.0 * math.atan(math.exp(y / EARTH_RADIUS)) - math.pi / 2.0)
        out_lng = math.degrees(x / EARTH_RADIUS)
        return out_lat, out_lng

    sw_lat, sw_lng = to_lat_lng(
        center_x - left * width_scale,
        center_y - down * height_scale,
    )
    ne_lat, ne_lng = to_lat_lng(
        center_x + right * width_scale,
        center_y + up * height_scale,
    )
    return {
        "swLat": sw_lat,
        "swLng": sw_lng,
        "neLat": ne_lat,
        "neLng": ne_lng,
        "map_lv": MAP_LEVEL,
        "centerLat": lat,
        "centerLng": lng,
    }


class ApiDiscoReDetailSetWorker(BaseApiWorker):
    def __init__(self) -> None:
        super().__init__()
        self.worker_name = "disco_re_detail"
        self.driver = None
        self.selenium_driver = None
        self.file_driver = None
        self.browser_fetch_js = ""
        self.region_coordinates = {}
        self._stopping = False
        self.list_items = []
        self.detail_items = []
        self._seen_items = set()
        self._seen_pnus = set()
        self.column_defs = None
        self.selected_column_defs = []
        self.db_repository = None
        self.job_status = "RUNNING"
        self.job_error = None
        self.geocode_js = ""
        self.get_json_js = ""
        self.get_json_batch_js = ""
        self._json_prefetch_cache = {}
        self._batch_fallback_logged = False
        self.page_delay = 0.3
        self.region_delay = 2.0
        self.request_delay = 0.1
        self.detail_thread_count = 4
        self.map_width_scale = 1.2
        self.map_height_scale = 1.2
        self.excel_header_merge_yn = True
        self._row_errors = []
        self._current_stat = None
        self._cleaned_up = False
        self.folder_path = ""
        self.auto_save_yn = False
        self.detail_log_yn = True

    def set_columns(self, columns):
        self.column_defs = [
            dict(row) for row in (columns or [])
            if isinstance(row, dict) and row.get("code") and row.get("checked", True)
        ]
        self.columns = [row["value"] for row in self.column_defs]

    def _setting(self, config, code, default):
        values = {row.get("code"): row.get("value") for row in config.get("setting", [])}
        values.update({row.get("code"): row.get("value")
                       for row in (getattr(self, "setting", None) or [])})
        return values.get(code, default)

    @staticmethod
    def _bool(value):
        return str(value).strip().lower() in ("true", "1", "y", "yes", "on")

    def _pause(self, seconds):
        end = time.monotonic() + seconds
        while self.running and time.monotonic() < end:
            time.sleep(min(0.1, max(0, end - time.monotonic())))
        return self.running

    def db_set(self):
        config = self.read_runtime_customer_config(customer_name=self.worker_name)
        definitions = self.column_defs if self.column_defs is not None else [
            dict(row) for row in config.get("columns", [])
            if isinstance(row, dict) and row.get("code") and row.get("checked", True)
        ]
        self.selected_column_defs = definitions
        if not self.selected_column_defs:
            raise ValueError("출력항목을 하나 이상 선택해주세요.")
        for name, default in (("page_delay", 0.3), ("region_delay", 2), ("request_delay", 0.1),
                              ("map_width_scale", 1.2), ("map_height_scale", 1.2)):
            value = float(self._setting(config, name, default))
            if not math.isfinite(value) or value < 0 or value > (3 if "scale" in name else 60):
                raise ValueError(f"잘못된 설정값: {name}={value}")
            if "scale" in name and value == 0:
                raise ValueError("지도 배율은 0보다 커야 합니다.")
            setattr(self, name, value)
        try:
            self.detail_thread_count = int(
                str(self._setting(config, "detail_thread_count", 4)).strip()
            )
        except (TypeError, ValueError):
            raise ValueError("상세 동시 조회 수는 1~4 사이의 정수여야 합니다.")
        if not 1 <= self.detail_thread_count <= 4:
            raise ValueError("상세 동시 조회 수는 1~4 사이여야 합니다.")
        self.folder_path = str(self._setting(config, "folder_path", "") or "")
        self.auto_save_yn = self._bool(self._setting(config, "auto_save_yn", False))
        self.detail_log_yn = self._bool(self._setting(config, "detail_log_yn", True))
        self.excel_header_merge_yn = self._bool(
            self._setting(config, "excel_header_merge_yn", True)
        )
        stat_defs = []
        for tab in config.get("db_tabs", []):
            if isinstance(tab, dict) and tab.get("key") == "stat":
                stat_defs = [
                    dict(row) for row in tab.get("columns", [])
                    if isinstance(row, dict) and row.get("code")
                    and row.get("checked", True)
                ]
                break
        user = getattr(self, "user", None)
        self.db_repository = WorkerDbRepository(
            db_path=self.get_runtime_db_path(),
            site_name="disco_re",
            worker_name=self.worker_name,
            detail_table_name="DISCO_RE_DETAIL",
            column_defs=self.selected_column_defs,
            user_id=getattr(user, "user_id", user),
            log_func=self.log_signal_func,
            detail_log_fields=("pnu",),
            stat_table_name="DISCO_RE_STAT",
            stat_column_defs=stat_defs,
        )
        schema_files = [
            "resources/customers/common/db/schema_hist.sql",
            "resources/customers/disco_re_detail/db/schema_detail.sql",
            "resources/customers/disco_re_detail/db/schema_stat.sql",
        ]
        if not self.db_repository.initialize(schema_files, start_job=True):
            raise RuntimeError("공통 WorkerDbRepository 초기화 실패")
        self._ensure_search_keyword_column()
        self.log_signal_func("[디스코] 저장 컬럼: " + json.dumps(
            [c["value"] for c in self.selected_column_defs], ensure_ascii=False))
        self.log_signal_func(f"[디스코] DB 작업 시작: {self.db_repository.job_id}")

    def _ensure_search_keyword_column(self):
        """기존 SQLite DB에도 검색 키워드 컬럼을 한 번만 추가합니다."""
        rows = self.db_repository.sqlite.fetchall(
            'PRAGMA table_info("disco_re_detail")'
        )
        column_names = {
            str(row.get("name") or "")
            for row in (rows or [])
            if isinstance(row, dict)
        }
        if "search_keyword" in column_names:
            return
        if not self.db_repository.sqlite.execute(
            'ALTER TABLE "disco_re_detail" ADD COLUMN "search_keyword" TEXT'
        ):
            raise RuntimeError("기존 DB에 검색 키워드 컬럼을 추가하지 못했습니다.")
        self.log_signal_func("[디스코] 기존 DB에 검색 키워드 컬럼을 추가했습니다.")

    def init(self) -> bool:
        try:
            self.file_driver = FileUtils(self.log_signal_func)
            self.browser_fetch_js = self.file_driver.read_text_from_resources(
                "browser_fetch_json.js", "customers/disco_re_detail/js"
            )
            if not self.browser_fetch_js:
                raise FileNotFoundError("browser_fetch_json.js 파일을 찾을 수 없습니다.")
            self.geocode_js = self.file_driver.read_text_from_resources(
                "disco_geocode.js", "customers/disco_re_detail/js")
            self.get_json_js = self.file_driver.read_text_from_resources(
                "browser_get_json.js", "customers/disco_re_detail/js")
            self.get_json_batch_js = self.file_driver.read_text_from_resources(
                "browser_get_json_batch.js", "customers/disco_re_detail/js")
            if not self.geocode_js or not self.get_json_js or not self.get_json_batch_js:
                raise FileNotFoundError("디스코 주소검색/상세조회 JS 파일이 없습니다.")
            self.db_set()

            try:
                coordinate_rows = self.file_driver.read_json_array_from_resources(
                    "korea_eup_myeon_dong.json",
                    "customers/disco_re_detail/region",
                ) or []
            except Exception as error:
                coordinate_rows = []
                self.log_signal_func(
                    f"[디스코] 지역 좌표 파일을 읽지 못했습니다. "
                    f"화면 전달 좌표를 사용합니다: {error}"
                )
            for row in coordinate_rows:
                if not isinstance(row, dict):
                    continue
                key = self._region_key(row)
                if all(key):
                    self.region_coordinates[key] = row

            self.selenium_driver = SeleniumUtils(
                headless=False,
                debug=True,
                log_func=self.log_signal_func,
            )
            self.driver = self.selenium_driver.start_driver(
                timeout=1200,
                view_mode="browser",
                window_size=(1600, 1000),
            )
            if self.driver is None:
                raise RuntimeError("브라우저를 시작하지 못했습니다.")
            return True
        except Exception as error:
            self.job_status, self.job_error = "FAIL", str(error)
            self.log_signal_func(f"[디스코] 초기화 실패: {error}")
            self.cleanup()
            return False

    @staticmethod
    def _region_key(region):
        return tuple(
            str(region.get(name) or "").strip()
            for name in ("시도", "시군구", "읍면동")
        )

    @staticmethod
    def _read_coordinates(region):
        data = region.get("data") or {}
        coordinates = data.get("coordinates") or region.get("coordinates") or {}
        lng = (
            coordinates.get("xCoordinate")
            or coordinates.get("lng")
            or coordinates.get("longitude")
            or region.get("lng")
            or region.get("longitude")
            or region.get("경도")
        )
        lat = (
            coordinates.get("yCoordinate")
            or coordinates.get("lat")
            or coordinates.get("latitude")
            or region.get("lat")
            or region.get("latitude")
            or region.get("위도")
        )
        if lng in (None, "") or lat in (None, ""):
            return None
        return float(lat), float(lng)

    def _fallback_coordinates(self, region):
        coordinates = self._read_coordinates(region)
        if coordinates is None:
            source = self.region_coordinates.get(self._region_key(region))
            if source is None:
                address = " ".join(self._region_key(region))
                raise ValueError(f"지역 중심 좌표를 찾을 수 없습니다: {address}")
            coordinates = self._read_coordinates(source)
        if coordinates is None:
            address = " ".join(self._region_key(region))
            raise ValueError(f"지역 중심 좌표가 비어 있습니다: {address}")
        return coordinates

    def _disco_coordinates(self, region):
        address = " ".join(self._region_key(region))
        try:
            WebDriverWait(self.driver, 10).until(
                lambda driver: driver.execute_script(
                    "return !!(window.geocoder && "
                    "typeof window.geocoder.addressSearch === 'function');"
                )
            )
            self.driver.set_script_timeout(15)
            result = self.driver.execute_async_script(self.geocode_js, address) or {}
            if not result.get("ok"):
                raise RuntimeError(result.get("error") or "디스코 주소 검색 실패")

            lat = float(result["lat"])
            lng = float(result["lng"])
            if not -85.0 < lat < 85.0 or not -180.0 <= lng <= 180.0:
                raise ValueError(f"잘못된 검색 좌표: lat={lat}, lng={lng}")

            self.log_signal_func(
                f"[디스코] 주소 검색 좌표 사용: {address} / lat={lat}, lng={lng}"
            )
            return lat, lng
        except Exception as error:
            coordinates = self._fallback_coordinates(region)
            self.log_signal_func(
                f"[디스코] 주소 검색 실패, 예비 좌표 사용: {address} / "
                f"lat={coordinates[0]}, lng={coordinates[1]} / 사유={error}"
            )
            return coordinates

    def _map_for_region(self, region):
        return make_map_bounds(*self._disco_coordinates(region),
                               self.map_width_scale, self.map_height_scale)

    @staticmethod
    def _request_form(filters):
        form = build_disco_form(filters) if filters else DEFAULT_FORM.copy()
        if not any(key == "selectedCategory" for key, _ in form):
            form.append(("selectedCategory", "null"))
        return form

    def _fetch_page(self, base_form, map_values, offset):
        payload = base_form.copy()
        payload.extend((key, str(value)) for key, value in map_values.items())
        payload.extend([
            ("offset", str(offset)),
            ("limit", str(LIST_LIMIT)),
        ])

        self.driver.set_script_timeout(30)
        response = self.driver.execute_async_script(self.browser_fetch_js, payload) or {}
        if not response.get("ok"):
            self._request_error(response.get("error") or "목록 요청 실패")

        result = response.get("json")
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise ValueError("목록 응답에 data 배열이 없습니다.")
        if "has_next" not in result:
            raise ValueError("목록 응답에 has_next가 없습니다.")
        if any(not isinstance(row, dict) or not row.get("pnu") for row in result["data"]):
            raise ValueError("목록에 PNU가 없는 행이 있습니다.")
        return result

    def _fetch_json(self, url, response_name):
        response = self._json_prefetch_cache.pop(url, None)
        if response is None:
            if not self._pause(self.request_delay):
                raise InterruptedError("사용자 중단")
            self.driver.set_script_timeout(30)
            response = self.driver.execute_async_script(self.get_json_js, url) or {}
        if not response.get("ok"):
            self._request_error(response.get("error") or f"{response_name} 요청 실패")

        return response.get("json")

    def _prefetch_json(self, requests):
        """브라우저 세션 안에서 상세 GET 요청을 설정 개수만큼 동시에 처리합니다."""
        pending = [
            {"url": url, "name": name}
            for url, name in requests
            if url and url not in self._json_prefetch_cache
        ]
        if self.detail_thread_count <= 1 or len(pending) <= 1:
            return
        # 실제 Selenium 세션에서만 브라우저 병렬 요청을 사용합니다.
        if not getattr(self.driver, "session_id", None):
            return
        if not self._pause(self.request_delay):
            raise InterruptedError("사용자 중단")

        try:
            self.driver.set_script_timeout(120)
            response = self.driver.execute_async_script(
                self.get_json_batch_js,
                {"requests": pending, "concurrency": self.detail_thread_count},
            ) or {}
            results = response.get("results")
            if not response.get("ok") or not isinstance(results, list):
                raise RuntimeError(response.get("error") or "동시 상세 요청 실패")
            by_url = {
                str(row.get("url") or ""): row
                for row in results
                if isinstance(row, dict) and row.get("url")
            }
            if len(by_url) != len(pending):
                raise RuntimeError("동시 상세 요청 결과 수가 일치하지 않습니다.")
            self._json_prefetch_cache.update(by_url)
        except (PermissionError, InterruptedError):
            raise
        except Exception as error:
            # 일부 WebDriver 환경에서 배치 스크립트를 지원하지 않으면 기존 순차 조회로 복귀합니다.
            if not self._batch_fallback_logged:
                self.log_signal_func(
                    f"[디스코] 동시 상세 조회를 사용할 수 없어 순차 조회로 전환합니다: {error}"
                )
                self._batch_fallback_logged = True

    @staticmethod
    def _land_history_url(pnu, list_rows):
        url = f"https://data.disco.re/home/get_land_history/?pnu={pnu}"
        first_row = list_rows[0] if list_rows else {}
        lat = first_row.get("lat")
        lng = first_row.get("lng")
        if lat not in (None, "") and lng not in (None, ""):
            url += f"&lng={lng}&lat={lat}"
        return url

    def _core_detail_requests(self, pnu, list_rows):
        return [
            (f"https://data.disco.re/home/land_by_pnu/?pnu={pnu}", "토지정보"),
            (self._land_history_url(pnu, list_rows), "토지이동이력"),
            (f"https://data.disco.re/home/land_price/?pnu={pnu}", "개별공시지가"),
            (f"https://data.disco.re/home/arch_by_pnu/?pnu={pnu}", "건물정보"),
            (self._data_url("home/get_arch_business/", {"p": pnu}), "상가업소정보"),
            (self._data_url("home/house_price/", {"pnu": pnu}), "개별주택공시가격"),
        ]

    @staticmethod
    def _request_error(message):
        if any(code in str(message) for code in ("HTTP 401", "HTTP 403", "HTTP 429")):
            raise PermissionError(f"접근/요청 제한으로 수집을 중단합니다: {message}")
        raise RuntimeError(message)

    @staticmethod
    def _data_url(path, params):
        return f"https://data.disco.re/{path}?{urlencode(params)}"

    @staticmethod
    def _empty_unit_info():
        return {
            "호별정보_동": None,
            "호별정보_층": None,
            "호별정보_호": None,
            "호별정보_대지권 비율": None,
            "호별정보_전유부": [],
        }

    def _fetch_short_info(self, pnu):
        result = self._fetch_json(
            f"/common/short_info/?p={pnu}",
            "기본정보",
        )
        if not isinstance(result, dict):
            raise ValueError("기본정보 응답이 JSON 객체가 아닙니다.")
        return result

    def _fetch_land_info(self, pnu):
        result = self._fetch_json(
            f"https://data.disco.re/home/land_by_pnu/?pnu={pnu}",
            "토지정보",
        )
        if not isinstance(result, dict):
            raise ValueError("토지정보 응답이 JSON 객체가 아닙니다.")
        return result

    def _fetch_land_history(self, pnu, list_rows):
        result = self._fetch_json(
            self._land_history_url(pnu, list_rows), "토지이동이력"
        )
        if isinstance(result, dict):
            result = result.get("data")
        if not isinstance(result, list):
            raise ValueError("토지이동이력 응답이 JSON 배열이 아닙니다.")
        return result

    def _fetch_land_prices(self, pnu):
        result = self._fetch_json(
            f"https://data.disco.re/home/land_price/?pnu={pnu}",
            "개별공시지가",
        )
        if not isinstance(result, list):
            raise ValueError("개별공시지가 응답이 JSON 배열이 아닙니다.")
        return result

    def _fetch_arch_info(self, pnu):
        result = self._fetch_json(
            f"https://data.disco.re/home/arch_by_pnu/?pnu={pnu}",
            "건물정보",
        )
        if not isinstance(result, dict):
            raise ValueError("건물정보 응답이 JSON 객체가 아닙니다.")
        return result

    def _fetch_arch_floors(self, key):
        result = self._fetch_json(
            f"https://data.disco.re/home/arch_floor_list/?key={key}",
            "건축물현황",
        )
        if not isinstance(result, list):
            raise ValueError("건축물현황 응답이 JSON 배열이 아닙니다.")
        return result

    def _fetch_businesses(self, pnu):
        result = self._fetch_json(
            self._data_url("home/get_arch_business/", {"p": pnu}),
            "상가업소정보",
        )
        rows = result.get("data") if isinstance(result, dict) else None
        if not isinstance(rows, list):
            raise ValueError("상가업소정보 응답에 data 배열이 없습니다.")
        return rows

    def _fetch_house_prices(self, pnu):
        result = self._fetch_json(
            self._data_url("home/house_price/", {"pnu": pnu}),
            "개별주택공시가격",
        )
        if not isinstance(result, list):
            raise ValueError("개별주택공시가격 응답이 JSON 배열이 아닙니다.")
        return result

    def _fetch_first_unit_info(self, pnu):
        """디스코 화면과 같이 첫 동·층·호의 대지권과 전유부를 조회합니다."""
        dong_data = self._fetch_json(
            self._data_url("home/arch_ziphap_info_dong_2/", {"p": pnu}),
            "호별 동정보",
        )
        if not isinstance(dong_data, dict):
            raise ValueError("호별 동정보 응답이 JSON 객체가 아닙니다.")

        jeonyu_dongs = dong_data.get("jeonyu") or []
        daeji_dongs = dong_data.get("daeji") or []
        jeonyu_dong = jeonyu_dongs[0] if jeonyu_dongs else ""
        daeji_dong = daeji_dongs[0] if daeji_dongs else ""

        floor_data = self._fetch_json(
            self._data_url("home/arch_ziphap_info_floor_2/", {
                "p": pnu,
                "j_d": jeonyu_dong,
                "d_d": daeji_dong,
            }),
            "호별 층정보",
        )
        if not isinstance(floor_data, dict):
            raise ValueError("호별 층정보 응답이 JSON 객체가 아닙니다.")

        jeonyu_floors = floor_data.get("jeonyu") or []
        daeji_floors = floor_data.get("daeji") or []
        if not jeonyu_floors:
            return None
        floor_row = jeonyu_floors[0]
        floor_type = floor_row[0] if len(floor_row) > 0 else ""
        floor = floor_row[1] if len(floor_row) > 1 else ""
        daeji_floor = ""
        if daeji_floors:
            daeji_floor = (
                daeji_floors[0][0]
                if isinstance(daeji_floors[0], (list, tuple))
                else daeji_floors[0]
            )

        ho_data = self._fetch_json(
            self._data_url("home/arch_ziphap_info_ho_2/", {
                "p": pnu,
                "jd": jeonyu_dong,
                "dd": daeji_dong,
                "g": floor_type,
                "jf": floor,
                "df": daeji_floor,
            }),
            "호별 호정보",
        )
        if not isinstance(ho_data, dict):
            raise ValueError("호별 호정보 응답이 JSON 객체가 아닙니다.")
        ho_rows = ho_data.get("jeonyu") or []
        if not ho_rows:
            return None
        ho = ho_rows[0][0] if isinstance(ho_rows[0], (list, tuple)) else ho_rows[0]

        parts_result = self._fetch_json(
            self._data_url("home/arch_exclusive_share_list_2/", {
                "p": pnu,
                "d": str(jeonyu_dong).replace("동", ""),
                "t": floor_type,
                "f": floor,
                "h": ho,
            }),
            "전유부",
        )
        parts = parts_result.get("parts") if isinstance(parts_result, dict) else None
        if not isinstance(parts, list):
            raise ValueError("전유부 응답에 parts 배열이 없습니다.")

        rights_result = self._fetch_json(
            self._data_url("home/land_rights_registration/", {
                "p": pnu,
                "d": str(jeonyu_dong).replace("동", ""),
                "f": floor,
                "h": ho,
            }),
            "대지권 비율",
        )
        rights = (
            rights_result.get("land_rights_registration")
            if isinstance(rights_result, dict)
            else None
        )
        rights_text = None
        if isinstance(rights, str) and "/" in rights:
            numerator, denominator = rights.split("/", 1)
            rights_text = f"{denominator}분의 {numerator}"

        return {
            "호별정보_동": jeonyu_dong,
            "호별정보_층": floor,
            "호별정보_호": ho,
            "호별정보_대지권 비율": rights_text,
            "호별정보_전유부": _korean_exclusive_parts(parts),
        }

    def _fetch_first_apart_prices(self, pnu):
        """디스코 화면과 같이 첫 동·층·호의 공동주택공시가격을 조회합니다."""
        dongs = self._fetch_json(
            self._data_url("home/apart_price_info_dong/", {"p": pnu}),
            "공동주택 동정보",
        )
        if not isinstance(dongs, list) or not dongs:
            return []
        dong = dongs[0]

        floors = self._fetch_json(
            self._data_url("home/apart_price_info_floor/", {"p": pnu, "d": dong}),
            "공동주택 층정보",
        )
        if not isinstance(floors, list) or not floors:
            return []
        floor = floors[0][0] if isinstance(floors[0], (list, tuple)) else floors[0]

        hos = self._fetch_json(
            self._data_url("home/apart_price_info_ho/", {
                "p": pnu,
                "d": dong,
                "f": floor,
            }),
            "공동주택 호정보",
        )
        if not isinstance(hos, list) or not hos:
            return []
        ho = hos[0][0] if isinstance(hos[0], (list, tuple)) else hos[0]

        prices = self._fetch_json(
            self._data_url("apart_price/", {
                "p": pnu,
                "d": dong,
                "f": floor,
                "h": ho,
            }),
            "공동주택공시가격",
        )
        if not isinstance(prices, list):
            raise ValueError("공동주택공시가격 응답이 JSON 배열이 아닙니다.")
        return prices

    @staticmethod
    def _korean_short_info(pnu, result):
        """short_info 응답을 화면/최종 표의 부모_자식 키로 변환합니다."""
        address = result.get("address")
        sido, sigungu, eup_myeon_dong = _address_parts(address)
        completed_date = _date_text(result.get("const_year"))
        recent_deal_date = _date_text(result.get("realp_date"))
        recent_price = result.get("price")

        return {
            "PNU": str(pnu),
            "기본_시도": sido,
            "기본_시군구": sigungu,
            "기본_읍면동": eup_myeon_dong,
            "기본_주소(지번)": address,
            "기본_주소(도로명)": result.get("road_address"),
            "기본_준공": completed_date,
            "실거래가_등록된 매물수": result.get("count"),
            "실거래가_최근실거래가": _price_text(recent_price),
            "실거래가_최근실거래가 일자": recent_deal_date,
            "토지 정보_면적": result.get("land_area"),
            "토지 정보_지목": result.get("purpose"),
            "토지 정보_용도지역": result.get("use_district"),
            "토지 정보_소유구분": result.get("owner_gbn"),
            "건물 정보_건물이름": result.get("name"),
            "건물 정보_대지면적": result.get("land_area"),
            "건물 정보_연면적": result.get("floor_area"),
            "건물 정보_지상/지하": (
                f"{result.get('ground_floor')}/{result.get('basement_floor')}"
                if result.get("ground_floor") is not None
                and result.get("basement_floor") is not None
                else None
            ),
            "건물 정보_세대 수_가구": result.get("family"),
            "건물 정보_세대 수_호수": result.get("ho"),
        }

    def _collect_short_infos(self, progress_start=0, progress_end=1000000):
        rows_by_pnu = {}
        missing_pnu = 0
        skipped_pnus = set()
        for row in self.list_items:
            pnu = str(row.get("pnu") or "").strip()
            if pnu in self._seen_pnus:
                continue
            if not pnu:
                missing_pnu += 1
                continue
            # 목록에는 필지 PNU(19자리)가 아닌 법정동/지역코드(10자리)가
            # 포함될 수 있습니다. 상세조회 대상이 아니므로 실패가 아닌 SKIP 처리합니다.
            if len(pnu) != 19 or not pnu.isdigit():
                skipped_pnus.add(pnu)
                self._seen_pnus.add(pnu)
                continue
            rows_by_pnu.setdefault(pnu, []).append(row)

        total = len(rows_by_pnu)
        self.log_signal_func(
            f"[디스코] 상세 요약 조회 시작: 대상 PNU {total}건"
            + (f", SKIP {len(skipped_pnus)}건" if skipped_pnus else "")
            + (f", PNU 없는 목록 {missing_pnu}건" if missing_pnu else "")
        )
        for pnu in sorted(skipped_pnus):
            self.log_signal_func(
                f"[디스코] 상세 SKIP (상세 대상이 아닌 지역코드): {pnu}"
            )

        success = 0
        progress_value = int(progress_start)

        def update_detail_progress(done):
            nonlocal progress_value
            if total <= 0:
                target = int(progress_end)
            else:
                ratio = min(1.0, max(0.0, done / total))
                target = int(progress_start + (progress_end - progress_start) * ratio)
            self.progress_signal.emit(progress_value, target)
            progress_value = target

        if total == 0:
            update_detail_progress(0)

        for index, (pnu, list_rows) in enumerate(rows_by_pnu.items(), 1):
            if not self.running:
                break

            # 기본정보를 먼저 만들고, 뒤에서 조회한 토지 상세정보로 같은 컬럼을 덮어씁니다.
            self._row_errors = []
            started_at = now_text()
            item = self._korean_short_info(pnu, {})
            item["검색 키워드"] = next(
                (
                    str(row.get("_search_keyword") or "").strip()
                    for row in list_rows
                    if str(row.get("_search_keyword") or "").strip()
                ),
                None,
            )
            fetched = 0
            short_info = {}

            try:
                short_info = self._fetch_short_info(pnu)
                item.update(self._korean_short_info(pnu, short_info))
                fetched += 1
            except Exception as error:
                if isinstance(error, PermissionError):
                    raise
                self._row_errors.append(str(error))
                self._seen_pnus.add(pnu)
                self.log_signal_func(
                    f"[디스코] 기본정보 실패 (PNU={pnu}): {error} / DB 저장하지 않음"
                )
                # 기본정보가 없으면 주소/PNU 검증이 되지 않은 행이므로
                # 나머지 상세 API도 호출하지 않고 완전히 제외합니다.
                update_detail_progress(index)
                continue

            self._prefetch_json(self._core_detail_requests(pnu, list_rows))

            try:
                land_info = self._fetch_land_info(pnu)
                item.update(_korean_land_info(land_info))
                fetched += 1
            except Exception as error:
                if isinstance(error, PermissionError):
                    raise
                self._row_errors.append(str(error))
                self.log_signal_func(f"[디스코] 토지정보 실패 (PNU={pnu}): {error}")

            try:
                history_rows = self._fetch_land_history(pnu, list_rows)
                histories = _korean_land_history(history_rows)
                item["토지 이동(변동) 사유"] = histories
                fetched += 1
            except Exception as error:
                if isinstance(error, PermissionError):
                    raise
                self._row_errors.append(str(error))
                item["토지 이동(변동) 사유"] = []
                self.log_signal_func(f"[디스코] 토지이동이력 실패 (PNU={pnu}): {error}")

            try:
                price_rows = self._fetch_land_prices(pnu)
                item.update(_korean_land_prices(price_rows))
                fetched += 1
            except Exception as error:
                if isinstance(error, PermissionError):
                    raise
                self._row_errors.append(str(error))
                item["개별공시지가"] = []
                item["개별공시지가_공시지가(㎡)"] = None
                self.log_signal_func(f"[디스코] 개별공시지가 실패 (PNU={pnu}): {error}")

            try:
                arch_info = self._fetch_arch_info(pnu)
                item.update(_korean_arch_info(arch_info))
                floor_items = []
                arch_rows = (
                    arch_info.get("title_section")
                    or arch_info.get("overall_title_section")
                    or []
                )
                seen_arch_keys = set()
                for arch_row in arch_rows:
                    if not isinstance(arch_row, dict):
                        continue
                    arch_key = str(arch_row.get("a1") or "").strip()
                    if not arch_key or arch_key in seen_arch_keys:
                        continue
                    seen_arch_keys.add(arch_key)
                self._prefetch_json([
                    (f"https://data.disco.re/home/arch_floor_list/?key={key}", "건축물현황")
                    for key in seen_arch_keys
                ])
                for arch_key in seen_arch_keys:
                    try:
                        floor_rows = self._fetch_arch_floors(arch_key)
                        floor_items.extend(_korean_arch_floors(floor_rows))
                    except Exception as error:
                        if isinstance(error, PermissionError):
                            raise
                        self._row_errors.append(str(error))
                        self.log_signal_func(
                            f"[디스코] 건축물현황 실패 "
                            f"(PNU={pnu}, key={arch_key}): {error}"
                        )
                item["건물 정보_건축물현황"] = floor_items
                fetched += 1
            except Exception as error:
                if isinstance(error, PermissionError):
                    raise
                self._row_errors.append(str(error))
                item["건물 정보_건축물현황"] = []
                self.log_signal_func(f"[디스코] 건물정보 실패 (PNU={pnu}): {error}")

            try:
                business_rows = self._fetch_businesses(pnu)
                item["상가업소정보"] = _korean_businesses(business_rows)
                fetched += 1
            except Exception as error:
                if isinstance(error, PermissionError):
                    raise
                self._row_errors.append(str(error))
                item["상가업소정보"] = []
                self.log_signal_func(f"[디스코] 상가업소정보 실패 (PNU={pnu}): {error}")

            try:
                house_price_rows = self._fetch_house_prices(pnu)
                item.update(_korean_house_prices(house_price_rows))
                fetched += 1
            except Exception as error:
                if isinstance(error, PermissionError):
                    raise
                self._row_errors.append(str(error))
                item["개별주택공시가격"] = []
                item["개별주택공시가격_공시가격"] = None
                self.log_signal_func(
                    f"[디스코] 개별주택공시가격 실패 (PNU={pnu}): {error}"
                )

            is_ziphap = str(short_info.get("ziphap") or "").strip() == "1"
            if is_ziphap:
                try:
                    unit_info = self._fetch_first_unit_info(pnu)
                    item.update(unit_info or self._empty_unit_info())
                    fetched += 1
                except Exception as error:
                    if isinstance(error, PermissionError):
                        raise
                    self._row_errors.append(str(error))
                    item.update(self._empty_unit_info())
                    self.log_signal_func(f"[디스코] 호별정보 실패 (PNU={pnu}): {error}")

                try:
                    apart_price_rows = self._fetch_first_apart_prices(pnu)
                    item.update(_korean_apart_prices(apart_price_rows))
                    fetched += 1
                except Exception as error:
                    if isinstance(error, PermissionError):
                        raise
                    self._row_errors.append(str(error))
                    item.update(_korean_apart_prices([]))
                    self.log_signal_func(
                        f"[디스코] 공동주택공시가격 실패 (PNU={pnu}): {error}"
                    )
            else:
                item.update(self._empty_unit_info())
                item.update(_korean_apart_prices([]))

            if not self.running:
                break
            row_status = "SUCCESS" if fetched and not self._row_errors else ("PARTIAL" if fetched else "FAIL")
            db_item = {
                column["code"]: item.get(column["value"])
                for column in self.selected_column_defs
            }
            stored = self.db_repository.insert_detail(
                db_item,
                row_status=row_status,
                row_error_message="; ".join(self._row_errors) or None,
                row_start_at=started_at,
                row_end_at=now_text(),
            )
            if not stored:
                self._row_errors.append("detail DB 저장 실패")
                self.job_error = "detail DB 저장 실패"
            self._seen_pnus.add(pnu)
            selected_item = {c["value"]: item.get(c["value"]) for c in self.selected_column_defs}
            self.detail_items.append(selected_item)
            if row_status == "SUCCESS":
                success += 1
            if self.detail_log_yn:
                self.log_signal_func("[디스코] 상세: " + json.dumps(selected_item, ensure_ascii=False))
            self.log_signal_func(f"[디스코] DB 저장 {index}/{total} / PNU={pnu} / {row_status}")
            update_detail_progress(index)

        self.log_signal_func(
            f"[디스코] 상세 요약 조회 완료: 성공 {success}/{total}건"
        )
        return success, total

    def _collect_region(self, region, filters):
        address = " ".join(self._region_key(region))
        map_values = self._map_for_region(region)
        base_form = self._request_form(filters)
        self.log_signal_func(
            f"[디스코] {address} 지도 좌표: "
            + json.dumps(map_values, ensure_ascii=False)
        )

        offset = 0
        region_count = 0
        region_keys = set()
        self._current_stat = {"bounds": map_values, "total": None, "count": 0}
        previous_page_keys = None
        while self.running:
            result = self._fetch_page(base_form, map_values, offset)
            rows = result["data"]
            page_keys = [
                str(row.get("suid") or row.get("uuid") or row.get("refer_uuid")
                    or row.get("u") or json.dumps(row, sort_keys=True))
                for row in rows
            ]
            if previous_page_keys == page_keys and rows:
                raise RuntimeError("같은 목록 페이지가 반복되어 중단했습니다.")
            previous_page_keys = page_keys
            if result.get("total_count") is not None:
                self._current_stat["total"] = int(result["total_count"])

            self.log_signal_func(
                f"[디스코] {address} / offset={offset}, 조회={len(rows)}건, "
                f"total_count={result.get('total_count')}, "
                f"has_next={result.get('has_next')}"
            )
            for key, row in zip(page_keys, rows):
                region_keys.add(key)
                self._current_stat["count"] = len(region_keys)
                if key in self._seen_items:
                    continue
                self._seen_items.add(key)
                detail_row = dict(row)
                detail_row["_search_keyword"] = address
                self.list_items.append(detail_row)
                region_count += 1

            has_next = result.get("has_next") is True or str(result.get("has_next")).lower() == "true"
            if not rows and has_next:
                raise RuntimeError("has_next=true인데 목록이 비어 있습니다.")
            if not has_next:
                break
            offset += LIST_LIMIT
            if not self._pause(self.page_delay):
                break

        return region_count

    def _jobs(self):
        favorites = self.setting_region_filter_favorite or []
        checked = [
            favorite for favorite in favorites
            if isinstance(favorite, dict) and favorite.get("checked")
        ]
        if checked:
            return checked
        return [{
            "regions": self.region or [],
            "filters": self.setting_detail_all_style or [],
        }]

    def main(self) -> bool:
        tasks = [
            (region, job.get("filters") or [])
            for job in self._jobs()
            for region in (job.get("regions") or [])
        ]
        if not tasks:
            self.log_signal_func("[디스코] 전체세팅에서 지역을 하나 이상 선택해주세요.")
            self.job_status, self.job_error = "FAIL", "선택 지역 없음"
            self.cleanup()
            return False

        completed = 0
        processed_tasks = 0
        try:
            self.driver.get("https://www.disco.re/")
            WebDriverWait(self.driver, 20).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )

            for index, (region, filters) in enumerate(tasks, 1):
                if not self.running:
                    break
                address = " ".join(self._region_key(region))
                region_start = int((index - 1) / len(tasks) * 1000000)
                detail_start = int((index - 0.9) / len(tasks) * 1000000)
                region_end = int(index / len(tasks) * 1000000)
                self.log_signal_func(f"[디스코] 지역 {index}/{len(tasks)}: {address}")
                self._current_stat = {"bounds": {}, "total": None, "count": 0}
                region_status, region_error = "SUCCESS", None
                try:
                    count = self._collect_region(region, filters)
                    completed += 1
                    self.log_signal_func(
                        f"[디스코] 지역 완료 {count}건 / 전체 누적 {len(self.list_items)}건"
                    )
                except Exception as error:
                    if isinstance(error, PermissionError):
                        raise
                    region_status, region_error = "FAIL", str(error)
                    self.log_signal_func(f"[디스코] 지역 실패 ({address}): {error}")
                stat = self._current_stat
                # 각 지역이 끝날 때 저장하므로 다음 지역 실패에도 이전 결과는 보존됩니다.
                self.progress_signal.emit(region_start, detail_start)
                detail_success, detail_total = self._collect_short_infos(
                    detail_start, region_end
                )
                if not self.running:
                    region_status, region_error = "STOP", "사용자 중단"

                # 디스코의 total_count는 화면 마커/그룹 수가 섞여 실제 상세 대상과
                # 일치하지 않습니다. 통계는 중복 및 SKIP을 제거한 유효 PNU 기준입니다.
                stat_matched = (
                    region_status == "SUCCESS"
                    and detail_success == detail_total
                )
                self.db_repository.insert_stat({
                    "task_index": index,
                    "city": region.get("시도"),
                    "division": region.get("시군구"),
                    "sector": region.get("읍면동"),
                    "totalCount": detail_total,
                    "crawledCount": detail_success,
                    "trueFalse": "T" if stat_matched else "F",
                    "status": region_status,
                    "error_message": region_error,
                    "map_bounds": json.dumps(stat["bounds"], ensure_ascii=False),
                })
                self.log_signal_func(
                    f"[디스코] 지역 통계: 전체={detail_total}, "
                    f"수집={detail_success}, 일치={'T' if stat_matched else 'F'} "
                    f"(중복·SKIP 제외)"
                )
                processed_tasks = index
                if index < len(tasks) and not self._pause(self.region_delay):
                    break

            self.log_signal_func(
                f"[디스코] 목록 수집 완료: {completed}/{len(tasks)} 지역, "
                f"중복 제외 {len(self.list_items)}건"
            )
            if not self.running:
                self.job_status, self.job_error = "STOP", "사용자 중단"
            elif completed != len(tasks) or self.db_repository.fail_count:
                self.job_status, self.job_error = "FAIL", "일부 지역 또는 상세 조회 실패(행/지역 오류 확인)"
            else:
                self.job_status = "SUCCESS"
            if self.running and processed_tasks == len(tasks):
                self.progress_signal.emit(1000000, 1000000)
            return self.job_status == "SUCCESS"
        except Exception as error:
            self.job_status = "FAIL" if self.running else "STOP"
            self.job_error = str(error)
            self.log_signal_func(f"[디스코] 작업 종료: {self.job_error}")
            return False
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        if self._cleaned_up:
            return
        self._cleaned_up = True
        if self.db_repository is not None:
            try:
                if self.job_status == "RUNNING":
                    self.job_status = "FAIL" if self.running else "STOP"
                    self.job_error = self.job_error or "작업 미완료"
                self.db_repository.set_job_result(self.job_status, self.job_error)
                self.db_repository.finish_job()
                if self.auto_save_yn:
                    from src.utils.excel_utils import ExcelUtils

                    labels, rows = self.db_repository.get_excel_data()
                    if rows:
                        header_groups = [
                            [part.strip() for part in str(label or "").split("_") if part.strip()]
                            or [str(label or "")]
                            for label in labels
                        ]
                        excel = ExcelUtils(self.log_signal_func)
                        saved = excel.save_db_rows_to_excel(
                            excel_filename=f"disco_re_{self.db_repository.job_id}.xlsx",
                            row_list=rows,
                            columns=labels,
                            folder_path=self.folder_path,
                            sub_dir="output",
                            header_groups=header_groups,
                            merge_headers=self.excel_header_merge_yn,
                        )
                        if not saved:
                            self.log_signal_func("[디스코] 엑셀 저장 실패. DB 데이터는 유지됩니다.")
            except Exception as error:
                self.log_signal_func(f"[디스코] 작업 마감/엑셀 저장 실패: {error}")
            finally:
                self.db_repository.close()
        driver, self.driver = self.driver, None
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

        if self.file_driver is not None:
            try:
                self.file_driver.close()
            except Exception:
                pass
            self.file_driver = None

    def stop(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        self.running = False
        # UI 스레드에서 SQLite 연결을 닫지 않습니다. main의 finally에서 마감합니다.

    def destroy(self) -> None:
        self.cleanup()
        self.progress_end_signal.emit()
