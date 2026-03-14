# src/workers/main/api_dmand_comm_set_worker.py
import json
import os
import random
import re
import threading
import time
from typing import Any, Dict, List, Optional

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiDmandCommSetWorker(BaseApiWorker):

    CATEGORY_MAP = {
        "ALL": "전체",
        "FREE": "자유",
        "EMPLOYMENT": "취업·자격증",
    }

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self._stop_event = threading.Event()
        self.site_main_url = "https://www.dmand.co.kr/"
        self.driver = None
        self.selenium_driver = None
        self.columns: Optional[List[str]] = None
        self.csv_filename: Optional[str] = None
        self.site_name: str = "DMAND_COMM"
        self.total_cnt: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None
        self.folder_path: str = ""
        self.current_cookie_str: Optional[str] = None
        self.current_access_token: Optional[str] = None
        self.out_dir: str = "output_dmand_comm"

    # 초기화
    def init(self) -> bool:
        self.driver_set()
        self.log_signal_func(f"선택 항목 : {self.columns}")
        self.log_signal_func("✅ init 완료")
        return True

    # 프로그램 실행
    def main(self) -> bool:
        try:
            self.log_signal_func("main 시작")

            self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

            community = str(self.get_setting_value(self.setting, "community") or "").strip().upper()
            if not community:
                self.log_signal_func("❌ 커뮤니티 항목이 비어 있습니다.")
                return False

            if community not in ["ALL", "FREE", "EMPLOYMENT"]:
                self.log_signal_func(f"❌ 잘못된 community 값입니다: {community}")
                return False

            self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))

            self.excel_driver.init_csv(
                self.csv_filename,
                self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )

            self.driver.get(self.site_main_url)
            time.sleep(random.uniform(1.2, 2.0))
            self.driver_cookie_set()

            qna_list = self.fetch_all_list(community)
            if not qna_list:
                self.log_signal_func("⚠️ 수집된 질문 목록이 없습니다.")
                return False

            self.total_cnt = len(qna_list)
            self.current_cnt = 0

            rows_buffer: List[Dict[str, Any]] = []
            flush_size = 10

            for idx, qna in enumerate(qna_list, start=1):
                if self._stop_event.is_set():
                    break

                qna_id = qna.get("id")
                comment_list = self.fetch_all_comments(qna_id)
                rows = self.build_rows(qna, comment_list)

                if rows:
                    rows_buffer.extend(rows)

                if len(rows_buffer) >= flush_size:
                    self.flush_rows_buffer(rows_buffer)
                    rows_buffer = []

                self.current_cnt = idx
                self.log_signal_func(
                    f"✅ 질문 처리 완료 / {idx}/{self.total_cnt} / 번호={qna_id} / 댓글수={len(comment_list)} / 생성행수={len(rows)}"
                )

            if rows_buffer:
                self.flush_rows_buffer(rows_buffer)

            self.log_signal_func("✅ main 종료")
            return True

        except Exception as e:
            self.log_signal_func(f"크롤링 에러: {e}")
            return False

    def fetch_all_list(self, community: str) -> List[Dict[str, Any]]:
        category = "" if community == "ALL" else community
        all_items: List[Dict[str, Any]] = []
        page = 1
        total_pages = 0
        total_elements = 0

        while not self._stop_event.is_set():
            resp = self.fetch_list_page(page, category)
            page_result = resp.get("page_result") or {}
            items = resp.get("data") or []

            if page == 1:
                total_pages = int(page_result.get("total_pages") or 0)
                total_elements = int(page_result.get("total_elements") or 0)
                self.log_signal_func(
                    f"✅ 질문 목록 수집 시작 / community={community} / total_elements={total_elements} / total_pages={total_pages}"
                )

            if not items:
                self.log_signal_func(f"✅ 질문 목록 없음 / page={page} / 종료")
                break

            all_items.extend(items)

            self.log_signal_func(
                f"✅ 질문 목록 수집 완료 / community={community} / page={page} / page_count={len(items)} / 누적={len(all_items)}"
            )

            if total_pages and page >= total_pages:
                break

            page += 1
            time.sleep(random.uniform(0.4, 0.8))

        return all_items

    def fetch_list_page(self, page: int, category: str) -> Dict[str, Any]:
        url = "https://gocho-back.com/v1/qnas"

        params = {
            "size": 500,
            "page": page,
            "order": "recent",
            "q": "",
            "category": category,
        }

        resp = self.api_client.get(
            url,
            headers=self.build_api_headers(),
            params=params
        )
        return self.to_json(resp)

    def fetch_all_comments(self, qna_id: Any) -> List[Dict[str, Any]]:
        all_comments: List[Dict[str, Any]] = []
        page = 1
        total_pages = 0
        total_elements = 0

        while not self._stop_event.is_set():
            resp = self.fetch_comment_page(qna_id, page)
            page_result = resp.get("page_result") or {}
            items = resp.get("data") or []

            if page == 1:
                total_pages = int(page_result.get("total_pages") or 0)
                total_elements = int(page_result.get("total_elements") or 0)
                self.log_signal_func(
                    f"댓글 수집 시작 / 번호={qna_id} / total_elements={total_elements} / total_pages={total_pages}"
                )

            if not items:
                break

            all_comments.extend(items)

            if total_pages and page >= total_pages:
                break

            page += 1
            time.sleep(random.uniform(0.2, 0.5))

        return all_comments

    def fetch_comment_page(self, qna_id: Any, page: int) -> Dict[str, Any]:
        url = f"https://gocho-back.com/v1/qnas/{qna_id}/comments"

        params = {
            "size": 100,
            "page": page,
            "qnaId": qna_id,
        }

        resp = self.api_client.get(
            url,
            headers=self.build_api_headers(),
            params=params
        )
        return self.to_json(resp)

    def build_rows(self, qna: Dict[str, Any], comment_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        base_row = {
            "번호": str(qna.get("id") or ""),
            "카테고리": self.category_to_kr(qna.get("category")),
            "질문 제목": qna.get("title") or "",
            "질문 내용": qna.get("description") or "",
            "질문 등록일": qna.get("created_time") or "",
            "댓글 내용": "",
            "댓글 등록일": "",
            "대댓글 내용": "",
            "대댓글 등록일": "",
        }

        rows: List[Dict[str, Any]] = []

        if not comment_list:
            rows.append(self.sanitize_row_for_excel(base_row))
            return rows

        for comment in comment_list:
            comment_desc = comment.get("description") or ""
            comment_created_time = comment.get("created_time") or ""
            reply_arr = comment.get("reply_arr") or []

            if not reply_arr:
                row = dict(base_row)
                row["댓글 내용"] = comment_desc
                row["댓글 등록일"] = comment_created_time
                rows.append(self.sanitize_row_for_excel(row))
                continue

            for reply in reply_arr:
                row = dict(base_row)
                row["댓글 내용"] = comment_desc
                row["댓글 등록일"] = comment_created_time
                row["대댓글 내용"] = reply.get("description") or ""
                row["대댓글 등록일"] = reply.get("created_time") or ""
                rows.append(self.sanitize_row_for_excel(row))

        return rows

    def flush_rows_buffer(self, rows_buffer: List[Dict[str, Any]]) -> None:
        if not rows_buffer:
            return

        clean_rows = [self.sanitize_row_for_excel(row) for row in rows_buffer]
        save_count = len(clean_rows)

        self.excel_driver.append_to_csv(
            self.csv_filename,
            clean_rows,
            self.columns,
            folder_path=self.folder_path,
            sub_dir=self.out_dir
        )

        self.log_signal_func(f"✅ CSV 저장 완료 / 저장행수={save_count}")

    def sanitize_excel_value(self, value: Any) -> Any:
        if value is None:
            return ""

        if not isinstance(value, str):
            return value

        return re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", value).strip()

    def sanitize_row_for_excel(self, row: Dict[str, Any]) -> Dict[str, Any]:
        clean_row: Dict[str, Any] = {}
        for k, v in row.items():
            clean_row[k] = self.sanitize_excel_value(v)
        return clean_row

    def category_to_kr(self, category: Any) -> str:
        category_str = str(category or "").strip().upper()
        return self.CATEGORY_MAP.get(category_str, category_str)

    def build_api_headers(self) -> Dict[str, str]:
        headers = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "origin": "https://www.dmand.co.kr",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://www.dmand.co.kr/",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        }

        if self.current_cookie_str:
            headers["cookie"] = self.current_cookie_str

        if self.current_access_token:
            headers["x-access-token"] = self.current_access_token

        return headers

    def to_json(self, resp: Any) -> Dict[str, Any]:
        if isinstance(resp, dict):
            return resp

        if hasattr(resp, "json"):
            try:
                return resp.json()
            except Exception:
                pass

        if isinstance(resp, str):
            try:
                return json.loads(resp)
            except Exception:
                pass

        return {}

    def driver_cookie_set(self) -> None:
        cnt = 0
        cookie_parts: List[str] = []

        try:
            for c in self.driver.get_cookies():
                name = c.get("name")
                value = c.get("value")
                if name and value:
                    cookie_parts.append(f"{name}={value}")

                    if self.api_client:
                        self.api_client.cookie_set(name, value)

                    cnt += 1

            self.current_cookie_str = "; ".join(cookie_parts)

            try:
                self.current_access_token = str(
                    self.driver.execute_script("return window.localStorage.getItem('accessToken');") or ""
                ).strip()
            except Exception:
                self.current_access_token = ""

        except Exception as e:
            self.log_signal_func(f"⚠️ 쿠키 복사 중 예외: {e}")

        self.log_signal_func(
            f"✅ 쿠키 세팅 완료 (count={cnt}) / accessToken={'Y' if self.current_access_token else 'N'}"
        )

    def driver_set(self) -> None:
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)
        self.log_signal_func("✅ driver_set 완료")

        self.selenium_driver = SeleniumUtils(
            headless=False,
            debug=True,
            log_func=self.log_signal_func,
        )
        self.driver = self.selenium_driver.start_driver(1200)

    # 정리
    def cleanup(self) -> None:
        try:
            if self.csv_filename:
                self.log_signal_func(f"🧾 CSV -> 엑셀 변환 시작: {self.csv_filename}")
                self.excel_driver.convert_csv_to_excel_and_delete(
                    self.csv_filename,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir
                )
                self.log_signal_func("✅ [엑셀 변환] 성공")
        except Exception as e:
            self.log_signal_func(f"[cleanup] 엑셀 변환 실패: {e}")

        try:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
        finally:
            self.driver = None

        try:
            if self.selenium_driver:
                try:
                    self.selenium_driver.quit()
                except Exception:
                    pass
        finally:
            self.selenium_driver = None

        try:
            if self.file_driver:
                self.file_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] file_driver.close 실패: {e}")
        finally:
            self.file_driver = None

        try:
            if self.excel_driver:
                self.excel_driver.close()
        except Exception as e:
            self.log_signal_func(f"[cleanup] excel_driver.close 실패: {e}")
        finally:
            self.excel_driver = None

    def stop(self) -> None:
        self.log_signal_func("✅ stop 시작")
        self.running = False
        self._stop_event.set()
        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def destroy(self) -> None:
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("✅ destroy")
        time.sleep(2.5)
        self.progress_end_signal.emit()
