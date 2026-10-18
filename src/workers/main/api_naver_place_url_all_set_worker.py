# src/workers/main/api_naver_place_url_all_set_worker.py
from __future__ import annotations

import json
import os
import random
import re
import requests
import shutil
import time
from typing import Any, Dict, List, Optional, Union, Set, Pattern
from urllib.parse import urlparse

import pandas as pd
from bs4 import BeautifulSoup

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiNaverPlaceUrlAllSetWorker(BaseApiWorker):

    LIMIT_IMAGE_SIZE: int = 1000

    # 네이버 플레이스 요청 제한 대응값
    PLACE_WAIT_MIN_SECONDS: float = 2.5
    PLACE_WAIT_MAX_SECONDS: float = 3.0
    PLACE_BATCH_SIZE: int = 100
    PLACE_BATCH_WAIT_SECONDS: float = 3 * 60
    PLACE_BATCH_WAIT_AFTER_429_SECONDS: float = 5 * 60
    PLACE_429_MAX_RETRIES: int = 3

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self.url_list: Optional[List[str]] = None
        self.columns: Optional[List[str]] = None
        self.csv_filename: Optional[str] = None
        self.keyword_list: Optional[List[str]] = None
        self.site_name: str = "네이버 플레이스 URL"
        self.total_cnt: int = 0
        self.total_pages: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None
        self.saved_ids: Set[str] = set()
        self.image_size: int = 1000
        self.zip: bool = True

        # === 신규 ===
        self.folder_path: str = ""
        self.out_dir: str = "output_naver_place_url"

        # 상세 HTML/이미지 GraphQL을 모두 같은 호출량으로 관리한다.
        self._place_request_count: int = 0
        self._next_place_rest_at: int = self.PLACE_BATCH_SIZE
        self._place_rest_seconds: float = self.PLACE_BATCH_WAIT_SECONDS
        self._http_429_detected: bool = False

    def _wait_crawl_delay(self, seconds: float, label: str = "") -> bool:
        """중지 요청을 즉시 반영할 수 있도록 짧게 나누어 대기한다."""
        if label:
            self.log_signal_func(label)

        end_time = time.monotonic() + seconds
        while self.running:
            remaining = end_time - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(0.2, remaining))
        return False

    def _increase_rest_after_429(self) -> None:
        """429가 한 번이라도 발생하면 이후 주기 휴식을 5분으로 늘린다."""
        if self._place_rest_seconds < self.PLACE_BATCH_WAIT_AFTER_429_SECONDS:
            self._place_rest_seconds = self.PLACE_BATCH_WAIT_AFTER_429_SECONDS
            self.log_signal_func(
                "⚠️ [휴식시간 변경] HTTP 429 발생으로 이후 플레이스 상세/이미지 요청 "
                f"{self.PLACE_BATCH_SIZE}회마다 {self._place_rest_seconds / 60:g}분 휴식합니다."
            )

    def _api_log_with_delay(self, message: str) -> None:
        """APIClient의 로그를 유지하면서 429 응답을 감지한다."""
        self.log_signal_func(message)
        text = str(message)
        if re.search(r"\b429\b", text) and ("HTTP" in text or "Too Many Requests" in text):
            self._http_429_detected = True
            self._increase_rest_after_429()

    def _wait_before_place_request(self, request_label: str) -> bool:
        """실제 네이버 요청 전 간격 및 100회 단위 휴식을 적용한다."""
        if self._place_request_count >= self._next_place_rest_at:
            self.log_signal_func(
                f"⏸️ [주기적 휴식] 플레이스 요청 {self._place_request_count}회 "
                f"완료. {self._place_rest_seconds / 60:g}분 대기합니다."
            )
            if not self._wait_crawl_delay(self._place_rest_seconds):
                return False
            self._next_place_rest_at += self.PLACE_BATCH_SIZE

        # 첫 요청은 바로 실행하고, 이후에는 요청 사이에 랜덤 간격을 둔다.
        if self._place_request_count > 0:
            seconds = random.uniform(self.PLACE_WAIT_MIN_SECONDS, self.PLACE_WAIT_MAX_SECONDS)
            if not self._wait_crawl_delay(seconds, f"⏳ [{request_label}] {seconds:.1f}초 대기"):
                return False
        return True

    def _call_place_api(self, request_label: str, request_func: Any) -> Any:
        """429이면 5분 뒤 같은 요청을 최대 3회 재시도한다."""
        for retry in range(self.PLACE_429_MAX_RETRIES + 1):
            if not self.running or not self._wait_before_place_request(request_label):
                return None

            self._http_429_detected = False
            self._place_request_count += 1
            result = request_func()

            # APIClient가 Response를 그대로 반환하는 구현도 함께 처리한다.
            if getattr(result, "status_code", None) == 429:
                self._http_429_detected = True

            if not self._http_429_detected:
                return result

            self._increase_rest_after_429()
            if retry >= self.PLACE_429_MAX_RETRIES:
                self.log_signal_func(
                    f"⛔ [{request_label}] HTTP 429 재시도 {self.PLACE_429_MAX_RETRIES}회 실패"
                )
                return None

            seconds = self.PLACE_BATCH_WAIT_AFTER_429_SECONDS
            self.log_signal_func(
                f"⏸️ [HTTP 429 휴식] {seconds / 60:g}분 대기 후 같은 요청 재시도 "
                f"({retry + 1}/{self.PLACE_429_MAX_RETRIES})"
            )
            if not self._wait_crawl_delay(seconds):
                return None

            # 429 대기 직후 같은 요청에서 주기 휴식이 중복되지 않게 한다.
            if self._place_request_count >= self._next_place_rest_at:
                self._next_place_rest_at += self.PLACE_BATCH_SIZE

        return None

    # 초기화
    def init(self) -> bool:
        self.data_set()
        self.driver_set()
        self.log_signal_func(f"선택 항목 : {self.columns}")
        self.log_signal_func(f"[DEBUG] folder_path = {self.folder_path}")
        self.log_signal_func(f"[DEBUG] out_dir = {self.out_dir}")
        return True

    # 프로그램 실행
    def main(self) -> bool:
        try:
            if not self.url_list:
                self.log_signal_func("⚠️ URL 목록이 비어있습니다.")
                return True

            if not self.columns:
                self.log_signal_func("⚠️ columns가 비어있습니다.")
                return True

            if not self.file_driver or not self.excel_driver:
                self.log_signal_func("⚠️ 드라이버가 초기화되지 않았습니다. (file_driver/excel_driver)")
                return True

            self.log_signal_func(f"크롤링 시작. 전체 {len(self.url_list)}개 URL")

            self.csv_filename = self.get_csv_filename()

            self.excel_driver.init_csv(
                filename=self.csv_filename,
                columns=self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )

            results: List[Dict[str, Any]] = []
            pattern: Pattern[str] = re.compile(r"/(\d+)(?=[/?#]|$)")

            for index, url in enumerate(self.url_list, start=1):
                if not self.running:
                    return True

                match = pattern.search(url)
                if match:
                    place_id = match.group(1)

                    place_info = self.fetch_place_info(place_id)
                    if not place_info:
                        self.log_signal_func(f"⚠️ ID {place_id}의 상세 정보를 가져오지 못했습니다.")
                        continue

                    self.log_signal_func(
                        f"진행 : {index} / {len(self.url_list)}, 아이디: {place_id}, 이름: {place_info['이름']}"
                    )
                    results.append(place_info)

                    pro_value: float = (index / len(self.url_list)) * 1000000
                    self.progress_signal.emit(self.before_pro_value, pro_value)
                    self.before_pro_value = pro_value

                    if index % 5 == 0:
                        self.excel_driver.append_to_csv(
                            filename=self.csv_filename,
                            data_list=results,
                            columns=self.columns,
                            folder_path=self.folder_path,
                            sub_dir=self.out_dir
                        )

            self.excel_driver.append_to_csv(
                filename=self.csv_filename,
                data_list=results,
                columns=self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )

            pro_value = 1000000.0
            self.progress_signal.emit(self.before_pro_value, pro_value)
            self.before_pro_value = pro_value

        except Exception as e:
            self.log_signal_func(f"크롤링 에러: {e}")

        return True

    # 데이터 세팅
    def data_set(self) -> None:
        value: Any = self.get_setting_value(self.setting, "image_size")

        try:
            num: int = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"image_size 값이 올바르지 않습니다: {value}")

        if not (1 <= num <= self.LIMIT_IMAGE_SIZE):
            raise ValueError(f"image_size는 1 ~ {self.LIMIT_IMAGE_SIZE} 사이여야 합니다 (현재 값: {num})")

        self.image_size = num
        self.zip = bool(self.get_setting_value(self.setting, "zip"))

        # === 신규 ===
        self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

        self.url_list = [
            str(row[k]).strip()
            for row in self.excel_data_list
            for k in row.keys()
            if k.lower() == "url" and row.get(k) and str(row[k]).strip()
        ]

    # 드라이버 세팅
    def driver_set(self) -> None:
        self.log_signal_func("드라이버 세팅 ========================================")

        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self._api_log_with_delay, verify=True)

    def safe_filename(self, name: str) -> str:
        name = re.sub(r'[\\/:*?"<>|]+', "_", str(name or "").strip())
        return (name or "output")[:120]

    def now_stamp(self) -> str:
        return time.strftime("%Y%m%d_%H%M%S")

    def get_csv_filename(self) -> str:
        return f"{self.safe_filename(self.site_name)}_{self.now_stamp()}.csv"

    def cleanup(self) -> None:
        try:
            if self.csv_filename and self.excel_driver:
                self.excel_driver.convert_csv_to_excel_and_delete(
                    csv_filename=self.csv_filename,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir
                )
                self.log_signal_func("✅ [엑셀 변환] 성공")
        except Exception as e:
            self.log_signal_func(f"[cleanup] 엑셀 변환 실패: {e}")

        try:
            if self.api_client:
                self.api_client.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] api_client.close 실패: {e}")

        try:
            if self.file_driver:
                self.file_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] file_driver.close 실패: {e}")

        try:
            if self.excel_driver:
                self.excel_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] excel_driver.close 실패: {e}")

    # 정지
    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        time.sleep(2.5)
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    # 마무리
    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()

    # 플레이스 목록
    def fetch_search_results(self, keyword: str, page: int) -> List[str]:
        url: str = "https://pcmap-api.place.naver.com/graphql"

        headers: Dict[str, str] = {
            "method": "POST",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko",
            "content-type": "application/json",
            "referer": "https://pcmap.place.naver.com",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        }

        payload: List[Dict[str, Any]] = [{
            "operationName": "getPlacesList",
            "variables": {
                "useReverseGeocode": True,
                "input": {
                    "query": keyword,
                    "start": (page - 1) * 100 + 1,
                    "display": 100,
                    "adult": True,
                    "spq": True,
                    "queryRank": "",
                    "x": "",
                    "y": "",
                    "clientX": "",
                    "clientY": "",
                    "deviceType": "pcmap",
                    "bounds": ""
                },
                "isNmap": True,
                "isBounds": True,
                "reverseGeocodingInput": {
                    "x": "",
                    "y": ""
                }
            },
            "query": "query getPlacesList($input: PlacesInput, $isNmap: Boolean!, $isBounds: Boolean!, $reverseGeocodingInput: ReverseGeocodingInput, $useReverseGeocode: Boolean = false) {  businesses: places(input: $input) {    total    items {      id      name      normalizedName      category      cid      detailCid {        c0        c1        c2        c3        __typename      }      categoryCodeList      dbType      distance      roadAddress      address      fullAddress      commonAddress      bookingUrl      phone      virtualPhone      businessHours      daysOff      imageUrl      imageCount      x      y      poiInfo {        polyline {          shapeKey {            id            name            version            __typename          }          boundary {            minX            minY            maxX            maxY            __typename          }          details {            totalDistance            arrivalAddress            departureAddress            __typename          }          __typename        }        polygon {          shapeKey {            id            name            version            __typename          }          boundary {            minX            minY            maxX            maxY            __typename          }          __typename        }        __typename      }      subwayId      markerId @include(if: $isNmap)      markerLabel @include(if: $isNmap) {        text        style        stylePreset        __typename      }      imageMarker @include(if: $isNmap) {        marker        markerSelected        __typename      }      oilPrice @include(if: $isNmap) {        gasoline        diesel        lpg        __typename      }      isPublicGas      isDelivery      isTableOrder      isPreOrder      isTakeOut      isCvsDelivery      isCvsDelivery      hasBooking      naverBookingCategory      bookingDisplayName      bookingBusinessId      bookingVisitId      bookingPickupId      baemin {        businessHours {          deliveryTime {            start            end            __typename          }          closeDate {            start            end            __typename          }          temporaryCloseDate {            start            end            __typename          }          __typename        }        __typename      }      yogiyo {        businessHours {          actualDeliveryTime {            start            end            __typename          }          bizHours {            start            end            __typename          }          __typename        }        __typename      }      isPollingStation      hasNPay      talktalkUrl      visitorReviewCount      visitorReviewScore      blogCafeReviewCount      bookingReviewCount      streetPanorama {        id        pan        tilt        lat        lon        __typename      }      naverBookingHubId      bookingHubUrl      bookingHubButtonName      newOpening      newBusinessHours {        status        description        dayOff        dayOffDescription        __typename      }      coupon {        total        promotions {          promotionSeq          couponSeq          conditionType          image {            url            __typename          }          title          description          type          couponUseType          __typename        }        __typename      }      mid      hasMobilePhoneNumber      hiking {        distance        startName        endName        __typename      }      __typename    }    optionsForMap @include(if: $isBounds) {      ...OptionsForMap      displayCorrectAnswer      correctAnswerPlaceId      __typename    }    searchGuide {      queryResults {        regions {          displayTitle          query          region {            rcode            __typename          }          __typename        }        isBusinessName        __typename      }      queryIndex      types      __typename    }    queryString    siteSort    __typename  }  reverseGeocodingAddr(input: $reverseGeocodingInput) @include(if: $useReverseGeocode) {    ...ReverseGeocodingAddr    __typename  }}fragment OptionsForMap on OptionsForMap {  maxZoom  minZoom  includeMyLocation  maxIncludePoiCount  center  spotId  keepMapBounds  __typename}fragment ReverseGeocodingAddr on ReverseGeocodingResult {  rcode  region  __typename}"
        }]

        try:
            if not self.api_client:
                self.log_signal_func("[에러] api_client가 초기화되지 않았습니다.")
                return []

            res: Any = self.api_client.post(url=url, headers=headers, json=payload)
            if not isinstance(res, list) or not res or not isinstance(res[0], dict):
                return []

            items: Any = res[0].get("data", {}).get("businesses", {}).get("items", [])
            if not isinstance(items, list):
                return []

            out: List[str] = []
            for item in items:
                if not self.running:
                    return out
                if isinstance(item, dict):
                    pid = item.get("id")
                    if pid:
                        out.append(str(pid))
            return out

        except Exception as e:
            self.log_signal_func(f"[에러] fetch_search_results 실패: {e}")
            return []

    # 숫자 체크
    def clean_number(self, value: Any) -> Union[str, float]:
        try:
            num: float = float(value)
            return "" if num == 0 else num
        except (ValueError, TypeError):
            return ""

    def build_payload(self, place_id: str, si: Optional[int] = None, lc: Optional[Union[int, str]] = None) -> List[Dict[str, Any]]:
        cursors: List[Dict[str, Any]] = [
            {"id": "biz"}, {"id": "clip"}, {"id": "cp0"},
            {"id": "aiView"}, {"id": "visitorReview"},
            {"id": "imgSas"}, {"id": "cp"}
        ]
        if si is not None:
            for c in cursors:
                if c.get("id") == "imgSas":
                    c["startIndex"] = si
                    if lc is not None:
                        c["lastCursor"] = str(lc)
                        c["hasNext"] = True
                    break

        return [{
            "operationName": "getPhotoViewerItems",
            "variables": {
                "input": {
                    "businessId": place_id,
                    "businessType": "place",
                    "cursors": cursors,
                    "excludeAuthorIds": [],
                    "excludeSection": [],
                    "excludeClipIds": [],
                    "dateRange": ""
                }
            },
            "query": "query getPhotoViewerItems($input: PhotoViewerInput) {\n  photoViewer(input: $input) {\n    cursors { id startIndex hasNext lastCursor __typename }\n    photos { viewId originalUrl originalDate width height title text desc link date photoType mediaType option { channelName dateString playCount likeCount __typename } to relation logId author { id nickname from imageUrl objectId url borderImageUrl __typename } votedKeywords { code iconUrl iconCode name __typename } visitCount originType isFollowing businessName rating externalLink { title url __typename } sourceTitle moment { channelId contentId momentId gdid blogRelation statAllowYn category docNo __typename } video { videoId videoUrl trailerUrl __typename } music { artists title __typename } clip { serviceType createdAt __typename } __typename }\n    __typename\n  }\n}"
        }]

    # 이미지 다운로드
    def fetch_place_image(self, place_id: str, name: str) -> List[str]:
        image_url_list: List[str] = []
        url: str = "https://api.place.naver.com/place/graphql"
        headers: Dict[str, str] = {
            "accept": "*/*",
            "accept-language": "ko",
            "content-type": "application/json",
            "referer": f"https://m.place.naver.com/place/{place_id}/photo",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        }

        parts_all: List[Dict[str, Any]] = []
        for si, lc in [(None, None), (40, "41"), (60, "61"), (80, "81"), (100, "101")]:
            if not self.running:
                return image_url_list

            if not self.api_client:
                self.log_signal_func("[에러] api_client가 초기화되지 않았습니다.")
                return image_url_list

            parts: Any = self._call_place_api(
                f"이미지 GraphQL Place ID {place_id} ({si or 0})",
                lambda: self.api_client.post(
                    url=url,
                    headers=headers,
                    json=self.build_payload(place_id, si, lc),
                ),
            )
            self.log_signal_func(f"이미지 다운로드 {place_id} {si} 호출")

            if isinstance(parts, list):
                parts_all.extend([p for p in parts if isinstance(p, dict)])

        photos: List[Dict[str, Any]] = []
        for part in parts_all:
            if not self.running:
                return image_url_list
            data = part.get("data")
            if not isinstance(data, dict):
                continue
            pv = data.get("photoViewer")
            if isinstance(pv, dict):
                ph = pv.get("photos", [])
                if isinstance(ph, list):
                    photos.extend([x for x in ph if isinstance(x, dict)])

        seen: Set[str] = set()
        for p in photos:
            if not self.running:
                return image_url_list
            u = p.get("originalUrl")
            if u and isinstance(u, str) and u not in seen:
                seen.add(u)
                image_url_list.append(u)

        # 저장 폴더
        safe_name: str = re.sub(r'[\\/:*?"<>|]+', "_", str(name))
        folder_name: str = f"{safe_name}({place_id})"

        # 엑셀 저장 폴더 기준으로 images 폴더 생성
        base_dir = self.excel_driver.resolve_output_dir(self.folder_path)
        image_root = os.path.join(base_dir, self.out_dir, "images")

        os.makedirs(image_root, exist_ok=True)

        folder: str = os.path.join(image_root, folder_name)
        os.makedirs(folder, exist_ok=True)

        limit_mb: int = int(getattr(self, "image_size", self.image_size))
        if limit_mb < 1 or limit_mb > self.LIMIT_IMAGE_SIZE:
            raise ValueError(f"image_size는 1 ~ {self.LIMIT_IMAGE_SIZE} 사이여야 합니다.")
        limit_bytes: int = limit_mb * 1024 * 1024

        ua: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        total: int = 0

        for idx, img_url in enumerate(image_url_list, 1):
            if not self.running:
                return image_url_list
            path: str = urlparse(img_url).path
            ext: str = os.path.splitext(path)[1].lower()
            if not ext or len(ext) > 5:
                ext = ".jpg"
            fname: str = f"{folder_name}_{idx}{ext}"
            fpath: str = os.path.join(folder, fname)

            with requests.get(img_url, stream=True, headers={"user-agent": ua}, timeout=20) as r:
                r.raise_for_status()

                cl_hdr = r.headers.get("Content-Length")
                content_len: Optional[int] = None
                if cl_hdr:
                    try:
                        content_len = int(cl_hdr)
                    except Exception:
                        content_len = None

                if content_len is not None and (total + content_len > limit_bytes):
                    break

                written: int = 0
                with open(fpath, "wb") as f:
                    for chunk in r.iter_content(8192):
                        if not chunk:
                            continue
                        if content_len is None and (total + written + len(chunk) > limit_bytes):
                            f.close()
                            try:
                                os.remove(fpath)
                            except Exception:
                                pass
                            written = 0
                            break
                        f.write(chunk)
                        written += len(chunk)

            total += written
            if total >= limit_bytes:
                break

        if self.zip:
            base = os.path.join(image_root, folder_name)
            try:
                zip_path = shutil.make_archive(base, "zip", root_dir=image_root, base_dir=folder_name)
                self.log_signal_func(f"압축 완료: {zip_path}")
            except Exception as e:
                self.log_signal_func(f"압축 실패: {e}")

        return image_url_list

    def _find_place_detail_key(self, root_query: Any, place_id: str) -> str:
        """네이버가 placeDetail input 필드를 바꿔도 현재 장소의 캐시 키를 찾는다."""
        if not isinstance(root_query, dict):
            return ""

        id_token = f'"id":"{place_id}"'
        for key in root_query.keys():
            if isinstance(key, str) and key.startswith("placeDetail(") and id_token in key:
                return key
        return ""

    # 상세조회
    def fetch_place_info(self, place_id: str) -> Optional[Dict[str, Any]]:
        url: str = f"https://m.place.naver.com/place/{place_id}"
        try:
            headers: Dict[str, str] = {
                "authority": "m.place.naver.com",
                "method": "GET",
                "scheme": "https",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "accept-encoding": "gzip, deflate",
                "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "priority": "u=0, i",
                "sec-ch-ua": '"Not/A)Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "referer": f"{url}",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
            }

            if not self.api_client:
                self.log_signal_func("[에러] api_client가 초기화되지 않았습니다.")
                return None

            response: Any = self._call_place_api(
                f"상세 HTML Place ID {place_id}",
                lambda: self.api_client.get(url=url, headers=headers),
            )
            if not response:
                self.log_signal_func(f"⚠️ Place ID {place_id} 응답 없음.")
                return None

            soup = BeautifulSoup(response, "html.parser")
            script_tag = soup.find("script", string=re.compile("window.__APOLLO_STATE__"))

            if not script_tag or not script_tag.string:
                self.log_signal_func(f"⚠️ Place ID {place_id}의 스크립트 태그 없음 또는 비어 있음.")
                return None

            script_text = script_tag.string
            marker = "window.__APOLLO_STATE__"
            marker_index = script_text.find(marker)
            if marker_index < 0:
                self.log_signal_func(f"⚠️ Place ID {place_id} APOLLO_STATE marker 없음.")
                return None

            equal_index = script_text.find("=", marker_index)
            json_start = script_text.find("{", equal_index)
            if equal_index < 0 or json_start < 0:
                self.log_signal_func(f"⚠️ Place ID {place_id}의 JSON 시작 위치를 찾지 못했습니다.")
                return None

            try:
                # 뒤에 붙는 자바스크립트 코드와 무관하게 JSON 객체 하나만 정확히 읽는다.
                data, _ = json.JSONDecoder().raw_decode(script_text[json_start:])
            except Exception as e:
                self.log_signal_func(f"⚠️ Place ID {place_id} JSON decode 실패: {e}")
                return None

            if not isinstance(data, dict):
                self.log_signal_func(f"⚠️ Place ID {place_id} data가 dict가 아님: {type(data)}")
                return None

            base: Any = data.get(f"PlaceDetailBase:{place_id}", {})
            if not isinstance(base, dict):
                base = {}

            name: str = str(base.get("name", "") or "")
            road: str = str(base.get("road", "") or "")
            address: str = str(base.get("address", "") or "")
            roadAddress: str = str(base.get("roadAddress", "") or "")
            category: str = str(base.get("category", "") or "")
            conveniences_raw: Any = base.get("conveniences", [])
            conveniences: List[str] = [str(x) for x in conveniences_raw] if isinstance(conveniences_raw, list) else []
            phone: str = str(base.get("phone", "") or "")
            virtualPhone: str = str(base.get("virtualPhone", "") or "")

            review_stats: Any = data.get(f"VisitorReviewStatsResult:{place_id}", {})
            if not isinstance(review_stats, dict):
                review_stats = {}

            review: Any = review_stats.get("review", {}) or {}
            analysis: Any = review_stats.get("analysis", {}) or {}
            if not isinstance(review, dict):
                review = {}
            if not isinstance(analysis, dict):
                analysis = {}

            visitorReviewsScore: Union[str, float] = self.clean_number(review.get("avgRating", ""))
            visitorReviewsTotal: Union[str, float] = self.clean_number(review.get("totalCount", ""))

            voted_keyword: Any = analysis.get("votedKeyword") or {}
            if not isinstance(voted_keyword, dict):
                voted_keyword = {}
            fsasReviewsTotal: Union[str, float] = self.clean_number(voted_keyword.get("userCount", ""))

            root_query: Any = data.get("ROOT_QUERY", {})
            if not isinstance(root_query, dict):
                root_query = {}

            place_detail_key = self._find_place_detail_key(root_query, place_id)
            if not place_detail_key:
                self.log_signal_func(f"⚠️ Place ID {place_id} placeDetail key를 찾지 못했습니다.")
                return None

            place_detail_obj: Any = root_query.get(place_detail_key, {})
            if not isinstance(place_detail_obj, dict):
                place_detail_obj = {}

            # source/format 인자가 바뀌어도 접두어 기준으로 현재 응답 값을 사용한다.
            business_hours: Any = []
            new_business_hours_json: Any = []
            for key, value in place_detail_obj.items():
                if not business_hours and isinstance(key, str) and key.startswith("businessHours"):
                    business_hours = value
                if not new_business_hours_json and isinstance(key, str) and key.startswith("newBusinessHours"):
                    new_business_hours_json = value
                if business_hours and new_business_hours_json:
                    break

            urls: List[str] = []
            shop_window: Any = place_detail_obj.get("shopWindow", {})
            if not isinstance(shop_window, dict):
                shop_window = {}

            homepages: Any = shop_window.get("homepages", "")
            if isinstance(homepages, dict):
                etc_list = homepages.get("etc", [])
                if isinstance(etc_list, list):
                    for item in etc_list:
                        if isinstance(item, dict):
                            urls.append(str(item.get("url", "") or ""))

                repr_data = homepages.get("repr")
                if isinstance(repr_data, dict):
                    repr_url = repr_data.get("url", "")
                    if repr_url:
                        urls.append(str(repr_url))

            category_list: List[str] = category.split(",") if category else ["", ""]
            main_category: str = category_list[0] if len(category_list) > 0 else ""
            sub_category: str = category_list[1] if len(category_list) > 1 else ""

            image_url_list: List[str] = self.fetch_place_image(place_id, name)

            result: Dict[str, Any] = {
                "아이디": place_id,
                "이름": name,
                "이미지": image_url_list,
                "주소(지번)": address,
                "주소(도로명)": roadAddress,
                "대분류": main_category,
                "소분류": sub_category,
                "별점": visitorReviewsScore,
                "방문자리뷰수": visitorReviewsTotal,
                "블로그리뷰수": fsasReviewsTotal,
                "이용시간1": self.format_new_business_hours(new_business_hours_json),
                "이용시간2": self.format_business_hours(business_hours),
                "카테고리": category,
                "URL": url,
                "지도": f"https://map.naver.com/p/entry/place/{place_id}",
                "편의시설": ", ".join(conveniences) if conveniences else "",
                "가상번호": virtualPhone,
                "전화번호": phone,
                "사이트": urls,
                "주소지정보": road,
            }

            return result

        except requests.exceptions.RequestException as e:
            self.log_signal_func(f"❌ 네트워크 에러: Place ID {place_id}: {e}")
        except Exception as e:
            self.log_signal_func(f"❌ 처리 중 에러: Place ID {place_id}: {e}")

        return None

    # 영업시간 함수1
    def format_business_hours(self, business_hours: Any) -> str:
        formatted_hours: List[str] = []
        try:
            if business_hours and isinstance(business_hours, list):
                for hour in business_hours:
                    if not isinstance(hour, dict):
                        continue
                    day = hour.get("day", "") or ""
                    start_time = hour.get("startTime", "") or ""
                    end_time = hour.get("endTime", "") or ""
                    if day and start_time and end_time:
                        formatted_hours.append(f"{day} {start_time} - {end_time}")
        except Exception as e:
            self.log_signal_func(f"Unexpected error: {e}")
            return ""
        return "\n".join(formatted_hours).strip() if formatted_hours else ""

    # 영업시간 함수2
    def format_new_business_hours(self, new_business_hours: Any) -> str:
        formatted_hours: List[str] = []
        try:
            if new_business_hours and isinstance(new_business_hours, list):
                for item in new_business_hours:
                    if not isinstance(item, dict):
                        continue

                    status_description = item.get("businessStatusDescription", {}) or {}
                    if not isinstance(status_description, dict):
                        status_description = {}

                    status = status_description.get("status", "") or ""
                    description = status_description.get("description", "") or ""

                    if status:
                        formatted_hours.append(status)
                    if description:
                        formatted_hours.append(description)

                    bh_list = item.get("businessHours", []) or []
                    if not isinstance(bh_list, list):
                        bh_list = []

                    for info in bh_list:
                        if not isinstance(info, dict):
                            continue

                        day = info.get("day", "") or ""
                        business_hours_obj = info.get("businessHours", {}) or {}
                        if not isinstance(business_hours_obj, dict):
                            business_hours_obj = {}

                        start_time = business_hours_obj.get("start", "") or ""
                        end_time = business_hours_obj.get("end", "") or ""

                        break_hours = info.get("breakHours", []) or []
                        if not isinstance(break_hours, list):
                            break_hours = []
                        break_times = [
                            f"{(bh.get('start', '') or '')} - {(bh.get('end', '') or '')}"
                            for bh in break_hours
                            if isinstance(bh, dict)
                        ]
                        break_times_str = (", ".join(break_times) + " 브레이크타임") if break_times else ""

                        last_order_times = info.get("lastOrderTimes", []) or []
                        if not isinstance(last_order_times, list):
                            last_order_times = []
                        last_order_times_str = (
                                ", ".join([
                                    f"{(lo.get('type', '') or '')}: {(lo.get('time', '') or '')}"
                                    for lo in last_order_times
                                    if isinstance(lo, dict)
                                ]) + " 라스트오더"
                        ) if last_order_times else ""

                        if day:
                            formatted_hours.append(day)
                        if start_time and end_time:
                            formatted_hours.append(f"{start_time} - {end_time}")
                        if break_times_str:
                            formatted_hours.append(break_times_str)
                        if last_order_times_str:
                            formatted_hours.append(last_order_times_str)

        except Exception as e:
            self.log_signal_func(f"영업시간 에러: {e}")
            return ""

        return "\n".join(formatted_hours).strip() if formatted_hours else ""
