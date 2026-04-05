import json
import random
import time
import urllib3
from typing import Any, Dict, List, Optional

import requests


BASE_URL = "https://fin.land.naver.com/front-api/v1/legalDivision"
OUTPUT_FILE = "korea_eup_myeon_dong.json"
OUTPUT_SIMPLE_FILE = "korea_eup_myeon_dong_simple.json"

REQUEST_TIMEOUT = 20
RETRY_COUNT = 5

VERIFY_SSL = False

if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MIN_SLEEP = 2.5
MAX_SLEEP = 5.5

RETRY_MIN_SLEEP = 8.0
RETRY_MAX_SLEEP = 20.0

BACKOFF_429_MIN = 40.0
BACKOFF_429_MAX = 90.0

COOKIE_STRING = r'''NAC=sTKYB8Q0oCuv; NNB=EZJOVEYWNS7GS; ASID=dc5ec4bf0000019d0fd8bc0d0000001b; _fbp=fb.1.1774087357518.703983604281386815; SHOW_FIN_BADGE=Y; _ga=GA1.1.971879580.1774198458; _ga_E6ST2DMJ6E=GS2.1.s1774201536$o2$g0$t1774201536$j60$l0$h0; nhn.realestate.article.rlet_type_cd=A01; _fwb=239Zajng4FLPY6gVse0dIZw.1774285762042; landHomeFlashUseYn=Y; _ga_SPWZFHV5W9=GS2.1.s1774689327$o2$g0$t1774689329$j58$l0$h0; cto_bundle=S2Nb7F9sMTBEM05POXRxWkxoWHU0VUhBdHI2Q1pBQ3JFUGI4elJIZlFIJTJCNlZ3bUprSThJTnB4Y0F1M0xkeW10OUZFWGNOcEdBNGlvdUN1UUVRWVZyMGolMkZBMVFqQmpLaXBhVVg4eXBvSjVYdUV1U0Q4SEt4ZEFYM0JnUjRnazhQRmx3YTc; NACT=1; nhn.realestate.article.trade_type_cd=""; realestate.beta.lastclick.cortar=4180000000; PROP_TEST_KEY=1775301767519.25f1be85f8cf1973c6c6aa622d28c969be2f72fa360106e2dc3fae6faf74be19; PROP_TEST_ID=9044baf5db3f3094eda8eba1ed982de3c31574460b56e485a7acb0f84465b4ff; SRT30=1775308799; SRT5=1775308799; map_snb_collapsed=false; BUC=BK0wa0VhBNSiqU2DR1Gue98Y8x1Jxj3mjcB5N1sfuGo='''


def random_sleep(min_sec: float, max_sec: float) -> None:
    time.sleep(random.uniform(min_sec, max_sec))


def cookie_string_to_dict(cookie_string: str) -> Dict[str, str]:
    cookie_dict: Dict[str, str] = {}

    if not cookie_string:
        return cookie_dict

    for part in cookie_string.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue

        key, value = part.split("=", 1)
        cookie_dict[key.strip()] = value.strip()

    return cookie_dict


def build_session() -> requests.Session:
    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://fin.land.naver.com/map?center=126.90495201529836-37.5505791916911&realEstateTypes=A01-A04-B01&showOnlySelectedRegion=true&tradeTypes=A1-B1&zoom=9.975231075217891",
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Origin": "https://fin.land.naver.com",
    })

    cookie_dict = cookie_string_to_dict(COOKIE_STRING)
    if cookie_dict:
        session.cookies.update(cookie_dict)

    return session


def request_json(
        session: requests.Session,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        retry_count: int = RETRY_COUNT,
) -> Optional[Dict[str, Any]]:
    for attempt in range(1, retry_count + 1):
        try:
            random_sleep(MIN_SLEEP, MAX_SLEEP)

            response = session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
                verify=VERIFY_SSL,
            )

            if response.status_code == 429:
                print(f"[429] attempt={attempt} url={response.url}")
                if attempt < retry_count:
                    sleep_sec = random.uniform(BACKOFF_429_MIN, BACKOFF_429_MAX)
                    print(f"[429] {sleep_sec:.1f}초 대기 후 재시도")
                    time.sleep(sleep_sec)
                    continue
                return None

            if response.status_code != 200:
                print(f"[WARN] status={response.status_code} url={response.url}")
                if attempt < retry_count:
                    sleep_sec = random.uniform(RETRY_MIN_SLEEP, RETRY_MAX_SLEEP)
                    print(f"[WARN] {sleep_sec:.1f}초 대기 후 재시도")
                    time.sleep(sleep_sec)
                    continue
                return None

            return response.json()

        except Exception as e:
            print(f"[ERROR] attempt={attempt} url={url} params={params} error={e}")
            if attempt < retry_count:
                sleep_sec = random.uniform(RETRY_MIN_SLEEP, RETRY_MAX_SLEEP)
                print(f"[ERROR] {sleep_sec:.1f}초 대기 후 재시도")
                time.sleep(sleep_sec)
            else:
                return None

    return None


def get_info_list_by_level(session: requests.Session, region_level_type: str) -> List[Dict[str, Any]]:
    url = f"{BASE_URL}/infoListByLevel"
    params = {
        "regionLevelType": region_level_type
    }

    data = request_json(session, url, params=params)
    if not data:
        return []

    if not data.get("isSuccess"):
        print(f"[WARN] isSuccess false - regionLevelType={region_level_type}")
        return []

    result = data.get("result") or []
    if not isinstance(result, list):
        return []

    return result


def get_sub_info_list(
        session: requests.Session,
        legal_division_level_type: str,
        legal_division_number: str,
) -> List[Dict[str, Any]]:
    url = f"{BASE_URL}/subInfoList"
    params = {
        "legalDivisionLevelType": legal_division_level_type,
        "legalDivisionNumber": legal_division_number,
    }

    data = request_json(session, url, params=params)
    if not data:
        return []

    if not data.get("isSuccess"):
        print(
            f"[WARN] isSuccess false - legalDivisionLevelType={legal_division_level_type}, "
            f"legalDivisionNumber={legal_division_number}"
        )
        return []

    result = data.get("result") or []
    if not isinstance(result, list):
        return []

    return result


def is_valid_coordinate(eup_item: Dict[str, Any]) -> bool:
    coordinates = (eup_item.get("coordinates") or {})

    x = coordinates.get("xCoordinate")
    y = coordinates.get("yCoordinate")

    if x is None or y is None:
        return False

    try:
        x = float(x)
        y = float(y)
    except (TypeError, ValueError):
        return False

    if x == 0 or y == 0:
        return False

    return True


def collect_all_eup_myeon_dong() -> List[Dict[str, Any]]:
    session = build_session()
    final_list: List[Dict[str, Any]] = []

    print("[1] 시도(SI) 목록 조회 시작")
    si_list = get_info_list_by_level(session, "SI")
    print(f"[1] 시도(SI) 개수: {len(si_list)}")

    for si_index, si_item in enumerate(si_list, start=1):
        si_name = (si_item.get("legalDivisionName") or "").strip()
        si_number = (si_item.get("legalDivisionNumber") or "").strip()

        if not si_number:
            print(f"[SKIP] 시도 번호 없음: {si_item}")
            continue

        print(f"\n[2] 시도 시작 ({si_index}/{len(si_list)}) - {si_name} / {si_number}")

        gun_list = get_sub_info_list(session, "GUN", si_number)
        print(f"[2] 시군구(GUN) 개수: {len(gun_list)}")

        for gun_index, gun_item in enumerate(gun_list, start=1):
            gun_name = (gun_item.get("legalDivisionName") or "").strip()
            gun_number = (gun_item.get("legalDivisionNumber") or "").strip()

            if not gun_number:
                print(f"[SKIP] 시군구 번호 없음: {gun_item}")
                continue

            print(f"  [3] 시군구 시작 ({gun_index}/{len(gun_list)}) - {gun_name} / {gun_number}")

            eup_list = get_sub_info_list(session, "EUP", gun_number)
            print(f"  [3] 읍면동(EUP) 개수: {len(eup_list)}")

            for eup_index, eup_item in enumerate(eup_list, start=1):
                eup_name = (eup_item.get("legalDivisionName") or "").strip()

                if not is_valid_coordinate(eup_item):
                    print(
                        f"    [SKIP-COORD] {si_name} > {gun_name} > {eup_name} "
                        f"({eup_index}/{len(eup_list)}) | x/y 중 0 또는 없음"
                    )
                    continue

                row = {
                    "시도": si_name,
                    "시군구": gun_name,
                    "읍면동": eup_name,
                    "data": eup_item,
                }
                final_list.append(row)

                print(
                    f"    [SAVE] {si_name} > {gun_name} > {eup_name} "
                    f"({eup_index}/{len(eup_list)}) | 누적: {len(final_list)}"
                )

            time.sleep(random.uniform(1.5, 3.0))

        time.sleep(random.uniform(3.0, 6.0))

    return final_list


def build_simple_list(data: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    simple_list: List[Dict[str, str]] = []

    for item in data:
        simple_list.append({
            "시도": (item.get("시도") or "").strip(),
            "시군구": (item.get("시군구") or "").strip(),
            "읍면동": (item.get("읍면동") or "").strip(),
        })

    return simple_list


def save_json(data: List[Dict[str, Any]], output_file: str) -> None:
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    result = collect_all_eup_myeon_dong()

    save_json(result, OUTPUT_FILE)
    print(f"\n[완료] 상세 json 저장(좌표 0 제외): {len(result)}건 -> {OUTPUT_FILE}")

    simple_result = build_simple_list(result)
    save_json(simple_result, OUTPUT_SIMPLE_FILE)
    print(f"[완료] 심플 json 저장(좌표 0 제외): {len(simple_result)}건 -> {OUTPUT_SIMPLE_FILE}")


if __name__ == "__main__":
    main()