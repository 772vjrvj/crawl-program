# src/workers/main/api_naver_place_url_all_set_worker.py
import json
import os
import random
import re
import requests
import shutil
import time
from typing import Any, Dict, List, Optional, Union
from typing import Set, Pattern  
from urllib.parse import urlparse

import pandas as pd
from bs4 import BeautifulSoup

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.workers.api_base_worker import BaseApiWorker
from urllib.parse import quote

class ApiBiznoExcelSetWorker(BaseApiWorker):

    # 초기화
    def __init__(self) -> None:  
        super().__init__()

        self.driver = None
        self.selenium_driver = None
        self.url_list: Optional[List[str]] = None
        self.columns: Optional[List[str]] = None  
        self.csv_filename: Optional[str] = None  
        self.keyword_list: Optional[List[str]] = None  
        self.site_name: str = "BIZNO"
        self.total_cnt: int = 0  
        self.total_pages: int = 0  
        self.current_cnt: int = 0  
        self.before_pro_value: float = 0.0  
        self.file_driver: Optional[FileUtils] = None  
        self.excel_driver: Optional[ExcelUtils] = None  
        self.api_client: Optional[APIClient] = None
        self.saved_ids: Set[str] = set()  

    # 초기화
    def init(self) -> bool:  
        self.driver_set()
        self.log_signal_func(f"선택 항목 : {self.columns}")
        return True

    # 프로그램 실행
    def main(self) -> bool:  
        try:

            self.log_signal_func(f"크롤링 시작. 전체 수 {len(self.excel_data_list)}")
            self.csv_filename = self.file_driver.get_csv_filename(self.site_name)
            df = pd.DataFrame(columns=self.columns)
            df.to_csv(self.csv_filename, index=False, encoding="utf-8-sig")

            for index, item in enumerate(self.excel_data_list, start=1):
                if not self.running:
                    self.log_signal_func("크롤링이 중지되었습니다.")
                    break

                if index > 1:
                    break

                place_info = self.fetch_search_results(item['업체'])
                self.log_signal_func(f"place_info : {place_info}")

                for idx in place_info:
                    self.fetch_article_detail(idx)


        except Exception as e:
            self.log_signal_func(f"크롤링 에러: {e}")

        return True


    # 드라이버 세팅
    def driver_set(self) -> None:  
        self.log_signal_func("드라이버 세팅 ========================================")

        # 엑셀 객체 초기화
        self.excel_driver = ExcelUtils(self.log_signal_func)

        # 파일 객체 초기화
        self.file_driver = FileUtils(self.log_signal_func)

        # api
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)

        self.selenium_driver = SeleniumUtils(headless=False)
        self.selenium_driver.set_capture_options(enabled=True, block_images=False)

        self.driver = self.selenium_driver.start_driver(1200)



    def cleanup(self) -> None:
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
        if self.excel_driver and self.csv_filename:
            self.excel_driver.convert_csv_to_excel_and_delete(self.csv_filename)

        self.running = False
        self.cleanup()


    # 마무리
    def destroy(self) -> None:  
        if self.excel_driver and self.csv_filename:
            self.excel_driver.convert_csv_to_excel_and_delete(self.csv_filename)
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("=============== 크롤링 종료중...")
        self.cleanup()
        time.sleep(1)
        self.log_signal_func("=============== 크롤링 종료")
        self.progress_end_signal.emit()


    def fetch_search_results(self, keyword: str) -> list[str]:
        """
        bizno 검색 결과에서 article id 목록을 추출
        예: /article/2230853329 -> 2230853329
        """

        url = f"https://bizno.net/?area=&query={quote(keyword)}"

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "referer": "https://bizno.net/",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        }

        res = requests.get(url, headers=headers, timeout=20)
        res.raise_for_status()

        soup = BeautifulSoup(res.text, "html.parser")

        article_ids = []

        for a in soup.select('a[href^="/article/"]'):
            href = a.get("href", "")
            article_id = href.replace("/article/", "").strip()

            if article_id.isdigit():
                article_ids.append(article_id)

        # 중복 제거
        article_ids = list(dict.fromkeys(article_ids))

        return article_ids


    def fetch_article_detail(self, article_id: str):
        url = f"https://bizno.net/article/{article_id}"

        headers = {
            "authority": "bizno.net",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=0, i",
            "referer": "https://bizno.net/",
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

        html = requests.get(url, headers=headers, timeout=20).text
        soup = BeautifulSoup(html, "html.parser")

        table = soup.select_one("table.table_guide01")

        data = {}

        for tr in table.select("tr"):
            th = tr.find("th")
            td = tr.find("td")

            if not th or not td:
                continue

            key = th.get_text(strip=True)
            val = td.get_text("\n", strip=True)

            if key:
                data[key] = val

        return data
