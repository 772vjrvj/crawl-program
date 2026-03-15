# src/workers/main/api_comento_qna_set_worker.py
import json
import os
import random
import re
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiComentoQnaSetWorker(BaseApiWorker):

    # 초기화
    def __init__(self) -> None:
        super().__init__()

        self._stop_event = threading.Event()
        self.site_login_url = "https://comento.kr/login"
        self.site_main_url = "https://comento.kr/job-questions"
        self.driver = None
        self.selenium_driver = None
        self.columns: Optional[List[str]] = None
        self.csv_filename: Optional[str] = None
        self.site_name: str = "COMENTO_QNA"
        self.total_cnt: int = 0
        self.current_cnt: int = 0
        self.before_pro_value: float = 0.0
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelUtils] = None
        self.api_client: Optional[APIClient] = None
        self.folder_path: str = ""
        self.current_cookie_str: Optional[str] = None
        self.out_dir: str = "output_comento_qna"

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

            keywords_str = str(self.get_setting_value(self.setting, "keyword") or "").strip()
            keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
            if not keywords:
                self.log_signal_func("❌ 키워드가 비어 있습니다.")
                return False

            self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))

            self.excel_driver.init_csv(
                self.csv_filename,
                self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )

            self.wait_for_user_confirmation()
            if self._stop_event.is_set():
                return False

            self.driver_cookie_set()

            all_items = self.fetch_all_list(keywords)
            if not all_items:
                self.log_signal_func("⚠️ 수집된 목록이 없습니다.")
                return False

            self.fetch_and_save_details(all_items)

            self.log_signal_func("✅ main 종료")
            return True

        except Exception as e:
            self.log_signal_func(f"크롤링 에러: {e}")
            return False

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value)).strip()

    def _build_search_api_headers(self, keyword: str) -> Dict[str, str]:
        headers = {
            "accept": "application/json",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": f"https://comento.kr/search/community/{quote(keyword)}?type=mentoring",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        }

        if self.current_cookie_str:
            headers["cookie"] = self.current_cookie_str

        return headers

    def _request_search_page(self, keyword: str, page: int) -> Dict[str, Any]:
        base_url = "https://comento.kr/api/v2/search/community"

        params = {
            "keyword": keyword,
            "limit": 500,
            "sort": "relevance",
            "page": page,
            "category": 0,
            "category_group_id": 0,
        }

        headers = self._build_search_api_headers(keyword)

        resp = self.api_client.get(
            base_url,
            headers=headers,
            params=params
        )

        return resp or {}

    def fetch_all_list(self, keywords: List[str]) -> List[Dict[str, Any]]:
        keyword_first_map: Dict[str, Dict[str, Any]] = {}
        keyword_page_map: Dict[str, int] = {}

        for keyword in keywords:
            if self._stop_event.is_set() or not self.running:
                break

            first_data = self._request_search_page(keyword, 1)
            keyword_first_map[keyword] = first_data

            list_obj = ((first_data.get("data") or {}).get("list") or {})
            last_page = int(list_obj.get("last_page") or 1)
            total = int((first_data.get("data") or {}).get("total") or 0)

            keyword_page_map[keyword] = last_page

            self.log_signal_func(f"✅ 키워드='{keyword}' / 전체 페이지={last_page} / 전체 건수={total}")
            time.sleep(random.uniform(0.5, 1.0))

        all_items: List[Dict[str, Any]] = []
        seen_keys = set()

        for keyword in keywords:
            if self._stop_event.is_set() or not self.running:
                self.log_signal_func("⏹️ fetch_all_list 중지")
                break

            last_page = keyword_page_map.get(keyword, 1)
            first_data = keyword_first_map.get(keyword) or {}

            for page in range(1, last_page + 1):
                if self._stop_event.is_set() or not self.running:
                    self.log_signal_func("⏹️ fetch_all_list 중지")
                    break

                data = first_data if page == 1 else self._request_search_page(keyword, page)
                list_obj = ((data.get("data") or {}).get("list") or {})
                items = list_obj.get("data") or []

                for idx, item in enumerate(items):
                    unique_key = str(item.get("no") or item.get("request_no") or f"{keyword}:{page}:{idx}")
                    if unique_key in seen_keys:
                        continue

                    seen_keys.add(unique_key)
                    self.current_cnt += 1

                    merged = dict(item)
                    merged["keyword"] = keyword
                    merged["search_page"] = page
                    all_items.append(merged)

                self.log_signal_func(f"✅ 목록 수집 중 / keyword={keyword} / page={page} / 누적={len(all_items)}")
                time.sleep(random.uniform(0.8, 1.0))

        self.total_cnt = len(all_items)
        self.log_signal_func(f"✅ 검색 API 수집 완료 / 총 {self.total_cnt}건")
        return all_items

    def _build_detail_url(self, item: Dict[str, Any]) -> str:
        company = str(item.get("company") or "").strip()
        job = str(item.get("job") or "").strip()
        search_o = str(item.get("search_o") or item.get("other_inf") or "").strip()
        request_no = str(item.get("request_no") or "").strip()

        slug_title = re.sub(r"\s+", "_", search_o).strip("_")
        slug = f"{slug_title}-{request_no}" if request_no else slug_title

        return (
            "https://comento.kr/job-questions/"
            f"{quote(company, safe='')}/"
            f"{quote(job, safe='')}/"
            f"{quote(slug, safe='')}"
        )

    def _build_detail_headers(self, item: Dict[str, Any]) -> Dict[str, str]:
        keyword = str(item.get("keyword") or "").strip()

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=0, i",
            "referer": f"https://comento.kr/search/community/{quote(keyword)}",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        }

        if self.current_cookie_str:
            headers["cookie"] = self.current_cookie_str

        return headers

    def _request_detail_page(self, item: Dict[str, Any]) -> str:
        url = self._build_detail_url(item)
        headers = self._build_detail_headers(item)

        resp = requests.get(url, headers=headers, timeout=(10, 30))
        resp.raise_for_status()
        return resp.text

    def _extract_next_f_payloads(self, text: str) -> List[str]:
        payloads: List[str] = []

        for m in re.finditer(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', text, re.S):
            raw = m.group(1)
            try:
                decoded = json.loads(f'"{raw}"')
                payloads.append(decoded)
            except Exception:
                continue

        return payloads

    def _extract_answers(self, text: str) -> List[Dict[str, Any]]:
        answers: List[Dict[str, Any]] = []

        for payload in self._extract_next_f_payloads(text):
            if '"pages":' not in payload or '"answers":' not in payload:
                continue

            m = re.match(r'^[^:]+:(\{.*\})$', payload, re.S)
            if not m:
                continue

            try:
                obj = json.loads(m.group(1))
            except Exception:
                continue

            pages = obj.get("pages") or []
            for page in pages:
                for answer in (page.get("answers") or []):
                    answers.append({
                        "no": answer.get("no", ""),
                        "createdAt": answer.get("createdAt", ""),
                        "content": answer.get("content", ""),
                    })

            if answers:
                break

        return answers

    def _parse_detail_page(self, text: str, item: Dict[str, Any]) -> Dict[str, Any]:
        soup = BeautifulSoup(text, "html.parser")

        title = ""
        canonical = ""
        question_no = ""
        route_company = ""
        route_job = ""
        route_slug = ""

        if soup.title:
            title = self._clean_text(soup.title.get_text())

        canonical_tag = soup.select_one('link[rel="canonical"]')
        if canonical_tag and canonical_tag.get("href"):
            canonical = canonical_tag.get("href", "").strip()

        if canonical:
            parts = [unquote(x) for x in urlparse(canonical).path.split("/") if x]
            if len(parts) >= 4:
                route_company = parts[1]
                route_job = parts[2]
                route_slug = parts[3]

            m = re.search(r"-(\d+)$", canonical)
            if m:
                question_no = m.group(1)

        article = soup.select_one('article[data-sentry-component="RequestQuestion"]')

        q_category = ""
        q_company = ""
        q_job = ""
        q_created_at = ""
        q_content = ""

        if article:
            info_tag = article.select_one("p.mb-14")
            if info_tag:
                info_text = self._clean_text(" ".join(info_tag.stripped_strings))
                m = re.match(r"(.+?)\s*·\s*(.+?)\s*/\s*(.+)", info_text)
                if m:
                    q_category = m.group(1).strip()
                    q_company = m.group(2).strip()
                    q_job = m.group(3).strip()

            content_tag = article.select_one('p[data-sentry-element="CaseDetailContent"]')
            if content_tag:
                q_content = content_tag.get_text("\n", strip=True)

            date_tags = article.select("p.text-body2.text-gray-400")
            if date_tags:
                q_created_at = self._clean_text(date_tags[-1].get_text())

        if not q_company:
            q_company = str(item.get("company") or "")
        if not q_job:
            q_job = str(item.get("job") or "")
        if not q_category:
            q_category = str(item.get("category") or "")
        if not q_created_at:
            q_created_at = str(item.get("time") or "")
        if not question_no:
            question_no = str(item.get("request_no") or "")

        answers = self._extract_answers(text)

        return {
            "route": {
                "company": route_company or str(item.get("company") or ""),
                "job": route_job or str(item.get("job") or ""),
                "slug": route_slug,
            },
            "meta": {
                "canonical": canonical or self._build_detail_url(item),
                "title": title or str(item.get("other_inf") or ""),
            },
            "question": {
                "questionNo": question_no,
                "createdAt": q_created_at,
                "content": q_content or str(item.get("question") or ""),
                "category": q_category,
                "company": q_company,
                "job": q_job,
            },
            "answers": answers,
        }

    def _detail_to_rows(self, detail: Dict[str, Any]) -> List[Dict[str, Any]]:
        question = detail.get("question") or {}
        meta = detail.get("meta") or {}
        route = detail.get("route") or {}
        answers = detail.get("answers") or []

        base_row = {
            "질문 번호": question.get("questionNo", ""),
            "질문 등록일": question.get("createdAt", ""),
            "질문 내용": question.get("content", ""),
            "카테고리": question.get("category", ""),
            "회사": question.get("company", ""),
            "URL": meta.get("canonical", ""),
            "질문 제목": meta.get("title", ""),
            "직무": route.get("job", question.get("job", "")),
        }

        if not answers:
            return [{
                **base_row,
                "응답 번호": "",
                "응답 등록일": "",
                "응답 내용": "",
            }]

        rows: List[Dict[str, Any]] = []
        for answer in answers:
            rows.append({
                **base_row,
                "응답 번호": answer.get("no", ""),
                "응답 등록일": answer.get("createdAt", ""),
                "응답 내용": answer.get("content", ""),
            })

        return rows

    def fetch_and_save_details(self, all_items: List[Dict[str, Any]]) -> None:
        total = len(all_items)
        rows_buffer: List[Dict[str, Any]] = []

        for idx, item in enumerate(all_items, start=1):
            if self._stop_event.is_set() or not self.running:
                self.log_signal_func("⏹️ 상세 수집 중지")
                break

            try:
                html = self._request_detail_page(item)
                detail = self._parse_detail_page(html, item)
                rows = self._detail_to_rows(detail)
                rows_buffer.extend(rows)
            except Exception as e:
                self.log_signal_func(f"⚠️ 상세 실패 / request_no={item.get('request_no')} / {e}")

                rows_buffer.append({
                    "질문 번호": item.get("request_no", ""),
                    "질문 등록일": item.get("time", ""),
                    "질문 내용": item.get("question", ""),
                    "카테고리": item.get("category", ""),
                    "회사": item.get("company", ""),
                    "URL": self._build_detail_url(item),
                    "질문 제목": item.get("other_inf", ""),
                    "직무": item.get("job", ""),
                    "응답 번호": "",
                    "응답 등록일": "",
                    "응답 내용": "",
                })

            if len(rows_buffer) >= 50:
                self.excel_driver.append_to_csv(
                    self.csv_filename,
                    rows_buffer,
                    self.columns,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir
                )
                rows_buffer.clear()

            pro_value = (idx / total) * 1000000
            self.progress_signal.emit(self.before_pro_value, pro_value)
            self.before_pro_value = pro_value

            self.log_signal_func(
                f"✅ 상세 수집 중 / {idx}/{total} / request_no={item.get('request_no')} / 누적 rows={len(rows_buffer)}"
            )
            time.sleep(random.uniform(0.5, 1))

        if rows_buffer:
            self.excel_driver.append_to_csv(
                self.csv_filename,
                rows_buffer,
                self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )

        self.log_signal_func("✅ 상세 수집 및 CSV 저장 완료")

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

        except Exception as e:
            self.log_signal_func(f"⚠️ 쿠키 복사 중 예외: {e}")

        self.log_signal_func(f"✅ 쿠키 세팅 완료 (count={cnt})")

    def wait_for_user_confirmation(self) -> None:
        self.driver.get(self.site_login_url)
        event = threading.Event()
        self.msg_signal_func("로그인 완료 후 OK를 눌러주세요", "info", event)

        while not event.wait(0.2):
            if self._stop_event.is_set():
                return

        if self._stop_event.is_set():
            return

        self.driver.get(self.site_main_url)
        self.log_signal_func("✅ 커뮤니티 검색 페이지 진입 완료")

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