import json
import time
from typing import Any, Dict, List, Tuple

import requests


class ChildcareNurseryCrawler:
    BASE_URL = "https://www.childcare.go.kr"
    API_URL = "https://www.childcare.go.kr/icms/nursery/NurseryContentData.html"

    SIDO_LIST: List[Dict[str, str]] = [
        {"ARCODE": "11000", "ARNAME": "서울특별시"},
        {"ARCODE": "26000", "ARNAME": "부산광역시"},
        {"ARCODE": "27000", "ARNAME": "대구광역시"},
        {"ARCODE": "28000", "ARNAME": "인천광역시"},
        {"ARCODE": "29000", "ARNAME": "광주광역시"},
        {"ARCODE": "30000", "ARNAME": "대전광역시"},
        {"ARCODE": "31000", "ARNAME": "울산광역시"},
        {"ARCODE": "36000", "ARNAME": "세종특별자치시"},
        {"ARCODE": "41000", "ARNAME": "경기도"},
        {"ARCODE": "43000", "ARNAME": "충청북도"},
        {"ARCODE": "44000", "ARNAME": "충청남도"},
        {"ARCODE": "46000", "ARNAME": "전라남도"},
        {"ARCODE": "47000", "ARNAME": "경상북도"},
        {"ARCODE": "48000", "ARNAME": "경상남도"},
        {"ARCODE": "49000", "ARNAME": "제주특별자치도"},
        {"ARCODE": "51000", "ARNAME": "강원특별자치도"},
        {"ARCODE": "52000", "ARNAME": "전북특별자치도"},
    ]

    def __init__(self):
        pass

    def build_referer_url(self, ctprvn: str, ctprvn_name: str) -> str:
        return f"https://www.childcare.go.kr/?menuno=166&sido={ctprvn}&sidoText={requests.utils.quote(ctprvn_name)}"

    def create_session(self, referer_url: str) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9",
            "cache-control": "no-cache",
            "connection": "keep-alive",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": "https://www.childcare.go.kr",
            "pragma": "no-cache",
            "referer": referer_url,
            "sec-ch-ua": '"Chromium";v="145", "Not:A-Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "x-requested-with": "XMLHttpRequest",
        })
        return session

    def init_session(self, session: requests.Session, referer_url: str) -> None:
        res = session.get(referer_url, timeout=20)
        res.raise_for_status()

    def build_payload(self, page_num: int, ctprvn: str, ctprvn_name: str) -> Dict[str, Any]:
        return {
            "searchType": "list",
            "flag": "NSSlPLMAP",
            "offset": "0",
            "chCnt": "",
            "reqCnt": "",
            "menuno": "166",
            "pageNum": str(page_num),
            "pagingCnt": "0",
            "searchDetailCrtype": "",
            "searchDetailCrspec": "",
            "setSearchKeyword1": "",
            "setSearchKeyword2": "",
            "setSearchKeyword3": "",
            "setSearchKeyword4": "",
            "setSearchKeyword5": "",
            "setSearchKeyword6": "",
            "setSearchKeyword7": "",
            "setSearchKeyword8": "",
            "setSearchKeyword9": "",
            "crrepre_sort": "asc",
            "class_sum_num_sort": "",
            "crcapat_sort": "",
            "crchcnt_sort": "",
            "tchertcnt_sort": "",
            "ewcnt_sort": "",
            "spcedctchcnt_sort": "",
            "helthtchercnt_sort": "",
            "nrtrroom_cnt_sort": "",
            "plgrdco_cnt_sort": "",
            "searchPublic": "",
            "searchEvalute": "",
            "searchOpen": "",
            "sessionId": "",
            "ctprvn": ctprvn,
            "ctprvnName": ctprvn_name,
            "signgu": "",
            "signguName": "",
            "dong": "",
            "callType": "",
            "road": "",
            "cname": "",
        }

    def request_page(
            self,
            session: requests.Session,
            page_num: int,
            ctprvn: str,
            ctprvn_name: str,
    ) -> Dict[str, Any]:
        payload = self.build_payload(page_num, ctprvn, ctprvn_name)
        res = session.post(self.API_URL, data=payload, timeout=30)
        res.raise_for_status()
        return res.json()

    def crawl_region(
            self,
            ctprvn: str,
            ctprvn_name: str,
            sleep_sec: float = 0.3,
    ) -> List[Dict[str, Any]]:
        referer_url = self.build_referer_url(ctprvn, ctprvn_name)
        session = self.create_session(referer_url)
        self.init_session(session, referer_url)

        data_list: List[Dict[str, Any]] = []
        page_num = 1

        while True:
            print(f"[INFO] [{ctprvn} {ctprvn_name}] page={page_num} 요청 중...")
            data = self.request_page(session, page_num, ctprvn, ctprvn_name)

            result = str(data.get("result") or "").upper()
            if result != "SUCCESS":
                print(f"[WARN] [{ctprvn} {ctprvn_name}] 비정상 응답: page={page_num}, result={result}, msg={data.get('msg')}")
                break

            nursery_list = data.get("nurseryList") or []
            if not nursery_list:
                print(f"[INFO] [{ctprvn} {ctprvn_name}] page={page_num} 데이터 없음. 종료")
                break

            print(f"[INFO] [{ctprvn} {ctprvn_name}] page={page_num} 수집 건수: {len(nursery_list)}")
            data_list.extend(nursery_list)

            page_num += 1
            time.sleep(sleep_sec)

        return data_list

    def save_json(self, data_list: List[Dict[str, Any]], output_path: str) -> None:
        with open(output_path, "w", encoding="utf-8-sig") as f:
            json.dump({"data_list": data_list}, f, ensure_ascii=False, indent=2)
        print(f"[INFO] 저장 완료: {output_path}")

    def crawl_and_save_region(
            self,
            region: Dict[str, str],
            sleep_sec: float = 0.3,
    ) -> Tuple[str, int, str]:
        ctprvn = str(region.get("ARCODE") or "").strip()
        ctprvn_name = str(region.get("ARNAME") or "").strip()
        output_path = f"childcare_nursery_{ctprvn}.json"

        try:
            data_list = self.crawl_region(
                ctprvn=ctprvn,
                ctprvn_name=ctprvn_name,
                sleep_sec=sleep_sec,
            )
            self.save_json(data_list, output_path)
            return ctprvn, len(data_list), "SUCCESS"
        except Exception as e:
            print(f"[ERROR] [{ctprvn} {ctprvn_name}] 수집 실패: {e}")
            return ctprvn, 0, f"FAIL: {e}"


if __name__ == "__main__":
    crawler = ChildcareNurseryCrawler()

    regions: List[Dict[str, str]] = [
        {"ARCODE": "11000", "ARNAME": "서울특별시"},  # 이미 수집했으므로 주석 처리
        {"ARCODE": "26000", "ARNAME": "부산광역시"},
        {"ARCODE": "27000", "ARNAME": "대구광역시"},
        {"ARCODE": "28000", "ARNAME": "인천광역시"},
        {"ARCODE": "29000", "ARNAME": "광주광역시"},
        {"ARCODE": "30000", "ARNAME": "대전광역시"},
        {"ARCODE": "31000", "ARNAME": "울산광역시"},
        {"ARCODE": "36000", "ARNAME": "세종특별자치시"},
        {"ARCODE": "41000", "ARNAME": "경기도"},
        {"ARCODE": "43000", "ARNAME": "충청북도"},
        {"ARCODE": "44000", "ARNAME": "충청남도"},
        {"ARCODE": "46000", "ARNAME": "전라남도"},
        {"ARCODE": "47000", "ARNAME": "경상북도"},
        {"ARCODE": "48000", "ARNAME": "경상남도"},
        {"ARCODE": "49000", "ARNAME": "제주특별자치도"},
        {"ARCODE": "51000", "ARNAME": "강원특별자치도"},
        {"ARCODE": "52000", "ARNAME": "전북특별자치도"},
    ]

    sleep_sec = 0.3
    region_wait_sec = 2.0
    results: List[Tuple[str, int, str]] = []

    for region in regions:
        ctprvn = str(region.get("ARCODE") or "").strip()
        ctprvn_name = str(region.get("ARNAME") or "").strip()

        print("\n" + "=" * 80)
        print(f"[START] [{ctprvn} {ctprvn_name}] 수집 시작")
        print("=" * 80)

        result = crawler.crawl_and_save_region(region, sleep_sec=sleep_sec)
        results.append(result)

        print(f"[DONE] [{ctprvn} {ctprvn_name}] result={result}")
        print(f"[INFO] 다음 지역 전 {region_wait_sec}초 대기")
        time.sleep(region_wait_sec)

    print("\n================ 최종 결과 ================")
    for ctprvn, count, status in sorted(results, key=lambda x: x[0]):
        print(f"{ctprvn} | count={count} | status={status}")