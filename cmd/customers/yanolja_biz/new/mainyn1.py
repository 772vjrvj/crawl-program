import requests
import json
import csv
import time

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


# ============================================================
# API
# ============================================================

API_URL = (
    "https://nol.yanolja.com"
    "/discovery/api/list/korea-accommodation/v2/list"
)

_print_lock = threading.Lock()


def safe_print(msg):
    with _print_lock:
        print(msg, flush=True)


# ============================================================
# 설정
# ============================================================

def create_options():
    return {
        # 날짜
        "checkInDate": "2026-10-14",
        "checkOutDate": "2026-10-15",

        "capacityAdults": 2,
        "childrenAges": [],

        "sort": "SORT_DEFAULT",

        # 안전장치
        "maxPages": 500,

        # 페이지별 요청 간격
        "sleepSec": 0.5,

        # 동시에 지역 몇 개 돌릴지
        # 기존 8 -> 4로 낮춤
        "maxWorkers": 4,

        # 로그 옵션
        "logIdsLimit": 0,
        "logIdsJoiner": ",",

        # 요청 실패 재시도
        "retryCount": 3,

        # 재시도 대기
        # 1차 2초 / 2차 4초 / 3차는 마지막
        "retrySleepSec": 2,
    }


# ============================================================
# 카테고리 / 지역
# ============================================================

def build_categories():
    return [
        # ----------------------------------------------------
        # 호텔 / 리조트
        # ----------------------------------------------------
        {
            "topCategory": "호텔/리조트",
            "pageName": "HOTEL",

            "regions": [
                {"name": "서울", "code": 900582},
                {"name": "부산", "code": 900583},
                {"name": "제주", "code": 900584},
                {"name": "경기", "code": 900585},
                {"name": "인천", "code": 900586},
                {"name": "강원", "code": 900587},
                {"name": "경상", "code": 900588},
                {"name": "전라", "code": 900589},
                {"name": "충청", "code": 900590},
            ],
        },

        # ----------------------------------------------------
        # 펜션 / 풀빌라
        # ----------------------------------------------------
        {
            "topCategory": "펜션/풀빌라",
            "pageName": "PENSION",

            "regions": [
                {"name": "가평", "code": 910252},
                {"name": "강원", "code": 900592},
                {"name": "경기", "code": 900591},
                {"name": "인천", "code": 900594},
                {"name": "충남", "code": 900595},
                {"name": "충북", "code": 900596},
                {"name": "경북", "code": 900598},
                {"name": "경남", "code": 910224},
                {"name": "전남", "code": 900599},
                {"name": "전북", "code": 900600},
                {"name": "제주", "code": 900593},
                {"name": "부산", "code": 900272},
                {"name": "울산", "code": 900575},
                {"name": "서울", "code": 900270},
            ],
        },
    ]


# ============================================================
# Header
# ============================================================

def build_headers(page_name, region_code):

    referer = (
        "https://nol.yanolja.com/discovery/list/"
        "PRODUCT_CATEGORY_KOREA_ACCOMMODATION/"
        f"{page_name}/{region_code}"
    )

    return {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://nol.yanolja.com",
        "referer": referer,
        "platform": "Web",

        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),

        "accept-language": (
            "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
        ),
    }


# ============================================================
# Filter
# ============================================================

def build_filter():
    return {
        "codeFilter": {
            "reservationTypeCodes": [],
            "starRatingCodes": [],
            "accommodationCategoryCodes": [],
            "amenitiesCodes": [],
            "accommodationLocationCodes": [],
            "maxRentHourCodes": [],
            "accommodationPromotionCodes": [],

            "leisureLocationCodes": [],
            "leisureCategoryCodes": [],
            "leisureBrandCodes": [],
            "leisurePromotionCodes": [],

            "entertainmentCategoryCodes": [],
            "entertainmentRegionCodes": [],
            "saleStatusCodes": [],
            "entertainmentPropertyCodes": [],

            "entertainmentTopingPaidMemberDiscount": False,

            "nolWorldDomesticStay": {
                "starRatingCodes": [],
                "facilityCodes": [],
            },
        },

        "rangeFilter": {
            "priceRange": {
                "from": 0,
                "to": 0,
            },

            "entertainmentShowDateRanges": [],
        },

        "productStatusFilter": {
            "availableOnly": False,
        },

        "quickFilters": [],

        "useDynamicFilter": False,

        "globalAccommodationCodeFilter": {
            "rateAmenityCodes": [],
            "propertyBadgeCodes": [],
            "propertyAmenityCodes": [],
        },
    }


# ============================================================
# Payload
# ============================================================

def build_payload(
        page,
        page_name,
        region_code,
        opt
):

    return {
        "localAccommodation": {
            "checkInDate": opt["checkInDate"],
            "checkOutDate": opt["checkOutDate"],
            "capacityAdults": opt["capacityAdults"],
            "childrenAges": opt["childrenAges"],
        },

        "filter": build_filter(),

        "pageName": page_name,

        "sort": opt["sort"],

        "region": region_code,

        "page": page,
    }


# ============================================================
# API 호출 + 재시도
# ============================================================

def post_search(
        session,
        headers,
        payload,
        opt,
        category,
        region
):
    retry_count = opt.get("retryCount", 3)
    retry_sleep = opt.get("retrySleepSec", 2)

    last_error = None

    for attempt in range(1, retry_count + 1):

        try:
            response = session.post(
                API_URL,
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.status_code == 200:
                return response.json()

            safe_print(
                "[HTTP ERROR]"
                + " | category={}".format(category["topCategory"])
                + " | region={}(#{})".format(
                    region["name"],
                    region["code"]
                )
                + " | page={}".format(payload.get("page"))
                + " | status={}".format(response.status_code)
                + " | attempt={}/{}".format(
                    attempt,
                    retry_count
                )
                + " | body={}".format(
                    response.text[:500]
                )
            )

            response.raise_for_status()

        except Exception as e:
            last_error = e

            safe_print(
                "[RETRY]"
                + " | category={}".format(category["topCategory"])
                + " | region={}(#{})".format(
                    region["name"],
                    region["code"]
                )
                + " | page={}".format(payload.get("page"))
                + " | attempt={}/{}".format(
                    attempt,
                    retry_count
                )
                + " | error={}".format(str(e))
            )

        if attempt < retry_count:

            wait_sec = retry_sleep * attempt

            safe_print(
                "[RETRY WAIT]"
                + " | category={}".format(category["topCategory"])
                + " | region={}(#{})".format(
                    region["name"],
                    region["code"]
                )
                + " | page={}".format(payload.get("page"))
                + " | sleep={}sec".format(wait_sec)
            )

            time.sleep(wait_sec)

    if last_error:
        raise last_error

    raise Exception("API 요청 실패")


# ============================================================
# 목록 파싱
# ============================================================

def parse_items(resp):

    rows = []

    for item in (
            resp.get("items") or []
    ):

        # 일반 숙소
        data = item.get(
            "productItem"
        )

        # 첫 페이지 광고 숙소
        if not data:
            data = item.get(
                "bannerTypeProductItem"
            )

        # sectionGroupHeader 등 제외
        if not data:
            continue


        pid = data.get(
            "id"
        )

        title = data.get(
            "title"
        )

        location_details = (
                data.get(
                    "locationDetails"
                )
                or []
        )


        if not pid:
            continue

        if not title:
            continue


        rows.append({
            "id": str(pid),

            "title": title,

            "locationDetails":
                location_details,
        })


    return rows


# ============================================================
# 로그
# ============================================================

def log_request_result(
        category,
        region,
        page,
        page_rows,
        region_total,
        total_pages,
        is_last,
        opt
):

    ids = [
        row["id"]
        for row in page_rows
    ]

    limit = opt.get(
        "logIdsLimit",
        0
    ) or 0

    joiner = opt.get(
        "logIdsJoiner",
        ","
    )


    if (
            limit > 0
            and len(ids) > limit
    ):

        shown = ids[:limit]

        ids_text = (
                joiner.join(shown)
                + joiner
                + "...(+{})".format(
            len(ids) - limit
        )
        )

    else:

        ids_text = joiner.join(
            ids
        )


    safe_print(
        "[REQ DONE]"
        + " | category={}".format(
            category["topCategory"]
        )
        + " | region={}(#{})".format(
            region["name"],
            region["code"]
        )
        + " | page={}/{}".format(
            page,
            total_pages
        )
        + " | received={}".format(
            len(page_rows)
        )
        + " | region_total={}".format(
            region_total
        )
        + " | isLast={}".format(
            is_last
        )
    )


    safe_print(
        "  ids: {}".format(
            ids_text
        )
    )


# ============================================================
# 지역 하나 전체 페이지 수집
# ============================================================

def fetch_region(
        session,
        category,
        region,
        opt
):

    page_name = (
        category["pageName"]
    )

    region_code = (
        region["code"]
    )

    headers = build_headers(
        page_name,
        region_code
    )

    page = 1

    collected = []

    seen_ids = set()


    while page <= opt["maxPages"]:

        payload = build_payload(
            page,
            page_name,
            region_code,
            opt,
        )


        try:

            resp = post_search(
                session,
                headers,
                payload,
                opt,
                category,
                region
            )


        except Exception as e:

            safe_print(
                "[ERROR]"
                + " | category={}".format(
                    category["topCategory"]
                )
                + " | region={}".format(
                    region["name"]
                )
                + " | page={}".format(
                    page
                )
                + " | error={}".format(
                    str(e)
                )
            )

            # 3번 재시도 후에도 실패하면
            # 해당 지역은 여기서 종료
            break


        # ====================================================
        # 숙소 파싱
        # ====================================================

        page_items = parse_items(
            resp
        )


        # ====================================================
        # paging
        # ====================================================

        paging = (
                resp.get("paging")
                or {}
        )


        current_page = (
            paging.get(
                "current",
                page
            )
        )


        total_pages = (
            paging.get(
                "total",
                page
            )
        )


        is_last = (
            paging.get(
                "isLast",
                False
            )
        )


        # ====================================================
        # 결과 저장
        # ====================================================

        new_count = 0


        for row in page_items:

            pid = row["id"]


            # 동일 지역 내 중복 제거
            if pid in seen_ids:
                continue


            seen_ids.add(
                pid
            )


            collected.append({
                "topCategory":
                    category[
                        "topCategory"
                    ],

                "pageName":
                    page_name,

                "regionCode":
                    str(
                        region_code
                    ),

                "regionName":
                    region[
                        "name"
                    ],

                "id":
                    pid,

                "title":
                    row[
                        "title"
                    ],

                "locationDetails_json":
                    json.dumps(
                        row[
                            "locationDetails"
                        ],
                        ensure_ascii=False
                    ),

                "detailUrl":
                    (
                            "https://nol.yanolja.com"
                            "/stay/domestic/"
                            + pid
                    ),
            })


            new_count += 1


        # ====================================================
        # 로그
        # ====================================================

        log_request_result(
            category,
            region,
            current_page,
            page_items,
            len(collected),
            total_pages,
            is_last,
            opt,
        )


        safe_print(
            "[PAGE SAVE]"
            + " | category={}".format(
                category["topCategory"]
            )
            + " | region={}".format(
                region["name"]
            )
            + " | page={}".format(
                current_page
            )
            + " | new={}".format(
                new_count
            )
        )


        # ====================================================
        # 종료 조건
        # ====================================================

        if is_last:

            safe_print(
                "[REGION LAST]"
                + " | category={}".format(
                    category["topCategory"]
                )
                + " | region={}".format(
                    region["name"]
                )
                + " | page={}".format(
                    current_page
                )
            )

            break


        if (
                current_page
                >= total_pages
        ):

            safe_print(
                "[REGION TOTAL END]"
                + " | category={}".format(
                    category["topCategory"]
                )
                + " | region={}".format(
                    region["name"]
                )
                + " | page={}/{}".format(
                    current_page,
                    total_pages
                )
            )

            break


        # paging이 이상할 경우 안전장치
        if not page_items:

            safe_print(
                "[EMPTY]"
                + " | category={}".format(
                    category["topCategory"]
                )
                + " | region={}".format(
                    region["name"]
                )
                + " | page={}".format(
                    current_page
                )
            )

            break


        # 다음 페이지
        page = (
                current_page + 1
        )


        # API 요청 간격
        time.sleep(
            opt["sleepSec"]
        )


    safe_print(
        "[REGION DONE]"
        + " | category={}".format(
            category["topCategory"]
        )
        + " | region={}".format(
            region["name"]
        )
        + " | total={}".format(
            len(collected)
        )
    )


    return collected


# ============================================================
# Thread
# ============================================================

def fetch_region_threadsafe(
        category,
        region,
        opt
):

    # 각 Thread별 Session
    # 로그인 세션이 아니라
    # HTTP 연결 재사용 목적
    with requests.Session() as session:

        return fetch_region(
            session,
            category,
            region,
            opt
        )


# ============================================================
# 전체 병렬 수집
# ============================================================

def scrape_all(
        categories,
        opt
):

    rows = []

    futures = []


    max_workers = (
            opt.get(
                "maxWorkers",
                4
            )
            or 4
    )


    with ThreadPoolExecutor(
            max_workers=max_workers
    ) as executor:


        for category in categories:

            for region in (
                    category["regions"]
            ):

                future = (
                    executor.submit(
                        fetch_region_threadsafe,
                        category,
                        region,
                        opt,
                    )
                )

                futures.append(
                    future
                )


        for future in as_completed(
                futures
        ):

            try:

                part = (
                    future.result()
                )


                if part:

                    rows.extend(
                        part
                    )


            except Exception as e:

                safe_print(
                    "[WORKER ERROR]"
                    + " | error={}".format(
                        str(e)
                    )
                )


    return rows


# ============================================================
# 전체 최종 중복 제거
# ============================================================
#
# 같은 숙소가 다른 지역/광고 영역 등에서
# 중복 등장할 가능성을 대비
#
# 여기서는
# topCategory + id
# 기준으로 중복 제거
#
# ============================================================

def remove_duplicate_rows(
        rows
):

    result = []

    seen = set()


    for row in rows:

        key = (
            row["topCategory"],
            row["id"]
        )


        if key in seen:
            continue


        seen.add(
            key
        )


        result.append(
            row
        )


    return result


# ============================================================
# CSV 저장
# ============================================================

def write_csv(
        rows,
        path
):

    if not rows:

        safe_print(
            "[WARN] 저장할 데이터가 없습니다."
        )

        return


    fields = [
        "topCategory",
        "pageName",
        "regionCode",
        "regionName",
        "id",
        "title",
        "locationDetails_json",
        "detailUrl",
    ]


    with open(
            path,
            "w",
            newline="",
            encoding="utf-8-sig"
    ) as f:

        writer = (
            csv.DictWriter(
                f,
                fieldnames=fields
            )
        )


        writer.writeheader()


        writer.writerows(
            rows
        )


    safe_print(
        "[CSV SAVED]"
        + " | path={}".format(
            path
        )
        + " | count={}".format(
            len(rows)
        )
    )


# ============================================================
# MAIN
# ============================================================

def main():

    categories = (
        build_categories()
    )


    options = (
        create_options()
    )


    safe_print(
        "=========================================="
    )

    safe_print(
        "야놀자 숙소 목록 수집 시작"
    )

    safe_print(
        "checkIn={} | checkOut={}".format(
            options[
                "checkInDate"
            ],
            options[
                "checkOutDate"
            ]
        )
    )

    safe_print(
        "maxWorkers={} | sleep={}sec".format(
            options[
                "maxWorkers"
            ],
            options[
                "sleepSec"
            ]
        )
    )

    safe_print(
        "retryCount={} | retrySleep={}sec".format(
            options[
                "retryCount"
            ],
            options[
                "retrySleepSec"
            ]
        )
    )

    safe_print(
        "=========================================="
    )


    # ========================================================
    # 수집
    # ========================================================

    rows = scrape_all(
        categories,
        options
    )


    safe_print(
        "[BEFORE DEDUP]"
        + " | count={}".format(
            len(rows)
        )
    )


    # ========================================================
    # 최종 중복 제거
    # ========================================================

    rows = (
        remove_duplicate_rows(
            rows
        )
    )


    safe_print(
        "[AFTER DEDUP]"
        + " | count={}".format(
            len(rows)
        )
    )


    # ========================================================
    # CSV
    # ========================================================

    output_file = (
        "yanolja_local_accommodation.csv"
    )


    write_csv(
        rows,
        output_file
    )


    safe_print(
        "=========================================="
    )

    safe_print(
        "전체 수집 완료"
    )

    safe_print(
        "총 {}건".format(
            len(rows)
        )
    )

    safe_print(
        "파일: {}".format(
            output_file
        )
    )

    safe_print(
        "=========================================="
    )


if __name__ == "__main__":
    main()