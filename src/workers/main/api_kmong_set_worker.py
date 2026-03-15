import os
import json
import time
import random

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlencode

from src.utils.api_utils import APIClient
from src.utils.excel_utils import ExcelUtils
from src.utils.file_utils import FileUtils
from src.workers.api_base_worker import BaseApiWorker


class ApiKmongSetLoadWorker(BaseApiWorker):
    def __init__(self):
        super().__init__()

        self.running = True
        self.init_flag = False

        self.current_cnt = 0
        self.total_cnt = 0
        self.before_pro_value = 0.0
        self.site_name = "kmong"

        self.result_list = []
        self.csv_filename = None

        self.excel_driver = None
        self.file_driver = None
        self.api_client = None

        self.folder_path = ""
        self.out_dir = "output_kmong"

    def init(self):
        try:
            if self.init_flag:
                self.log_signal_func("이미 초기화 실행 완료")
                return True

            self.driver_set()
            self.init_flag = True
            self.log_signal_func("✅ init 완료")
            return True

        except Exception as e:
            self.log_signal_func(f"❌ init 실패: {e}")
            return False

    def stop(self):
        self.running = False
        self.log_signal_func("⛔ 중지 요청됨")

    def destroy(self):
        self.progress_signal.emit(self.before_pro_value, 1000000)
        self.log_signal_func("크롤링 종료중...")
        time.sleep(1)
        self.log_signal_func("크롤링 종료")
        self.progress_end_signal.emit()

    def driver_set(self):
        self.excel_driver = ExcelUtils(self.log_signal_func)
        self.file_driver = FileUtils(self.log_signal_func)
        self.api_client = APIClient(use_cache=False, log_func=self.log_signal_func)
        self.log_signal_func("✅ driver_set 완료")

    def main(self):
        try:
            self.log_signal_func("크롤링 시작합니다.")

            self.running = True
            self.current_cnt = 0
            self.total_cnt = 0
            self.before_pro_value = 0.0
            self.result_list = []

            self.folder_path = str(self.get_setting_value(self.setting, "folder_path") or "").strip()

            self.csv_filename = os.path.basename(self.file_driver.get_csv_filename(self.site_name))
            self.excel_driver.init_csv(
                self.csv_filename,
                self.columns,
                folder_path=self.folder_path,
                sub_dir=self.out_dir
            )
            self.log_signal_func(f"CSV 생성: {self.csv_filename}")

            self.get_list()

            if not self.running:
                self.log_signal_func("⛔ 중지됨: 목록 수집 후 종료")
                return True

            self.fetch_details()

            self.log_signal_func("✅ main 종료")
            return True

        except Exception as e:
            self.log_signal_func(f"❌ main 오류: {e}")
            return False

        finally:
            self.cleanup()

    # =========================
    # 목록 수집
    # =========================
    def get_list(self):
        keyword = self.get_setting_value(self.setting, "keyword")
        base_url = "https://api.kmong.com/gig-app/gig/v1/gigs/search"

        headers = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://kmong.com",
            "pragma": "no-cache",
            "referer": "https://kmong.com/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        }

        last_page = 1
        self.total_cnt = 0
        page = 1

        while True:
            if not self.running:
                self.log_signal_func("⛔ 중지됨: 목록 수집을 종료합니다.")
                break

            params = {
                "keyword": keyword,
                "isPrime": "false",
                "isFastReaction": "false",
                "isCompany": "false",
                "isNowContactable": "false",
                "hasPortfolios": "false",
                "page": page,
                "perPage": 100,
                "sortType": "SCORE",
                "service": "web",
                "q": keyword,
                "rootCategoryId": "null",
                "subCategoryId": "null",
                "thirdCategoryId": "null"
            }

            url = base_url + "?" + urlencode(params, doseq=True)
            data = self.api_client.get(url, headers=headers) or {}

            if page == 1:
                last_page = data.get("lastPage", 1)
                self.total_cnt = data.get("totalItemCount", 0)
                self.log_signal_func(f"📄 목록 수집 시작 (총 {self.total_cnt}건 / {last_page}페이지)")

            gigs = data.get("gigs") or []

            for g in gigs:
                obj = {
                    "아이디": g.get("gigId", ""),
                    "제목": g.get("title", ""),
                    "판매자": (g.get("seller") or {}).get("nickname", ""),
                    "평점": (g.get("review") or {}).get("reviewAverage", ""),
                    "댓글수": (g.get("review") or {}).get("reviewCount", ""),
                }
                self.result_list.append(obj)

            current_count = len(self.result_list)
            percent = 0
            if self.total_cnt:
                percent = int((current_count / self.total_cnt) * 100)

            self.log_signal_func(
                f"📄 목록 수집중... {current_count}/{self.total_cnt}건 ({percent}%)  |  {page}/{last_page}페이지"
            )

            if page >= last_page:
                break

            page += 1
            time.sleep(random.uniform(1, 3))

        self.log_signal_func(f"✅ 목록 수집 완료 ({len(self.result_list)}건)")

    # =========================
    # 상세 수집
    # =========================
    def fetch_details(self):
        content_root = self._ensure_output_dir("kmong_content")
        image_root = self._ensure_output_dir("kmong_image")

        headers_detail = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        }

        headers_img = {
            "accept": "*/*",
            "referer": "https://kmong.com/",
            "user-agent": headers_detail["user-agent"],
        }

        total = len(self.result_list)
        self.current_cnt = 0

        for item in self.result_list:
            if not self.running:
                self.log_signal_func("⛔ 중지됨: 상세 수집을 종료합니다.")
                break

            self.current_cnt += 1

            gig_id = item.get("아이디")
            nickname = item.get("판매자") or ""
            nick_safe = self.file_driver.safe_name(nickname)

            seq = str(self.current_cnt).zfill(7)
            folder_name = f"{seq}_{gig_id}_{nick_safe}"

            content_dir = os.path.join(content_root, folder_name)
            image_dir = os.path.join(image_root, folder_name)

            if not os.path.exists(content_dir):
                os.makedirs(content_dir)
            if not os.path.exists(image_dir):
                os.makedirs(image_dir)

            detail_url = f"https://kmong.com/gig/{gig_id}"

            self.log_signal_func(f"🔎 상세 수집중... {self.current_cnt}/{total}  |  id={gig_id}")

            try:
                html_text = self.api_client.get(detail_url, headers=headers_detail)
                if isinstance(html_text, (bytes, bytearray)):
                    html_text = html_text.decode("utf-8", errors="replace")

                saved = self._parse_and_save_detail(
                    html_text=html_text,
                    content_dir=content_dir,
                    image_dir=image_dir,
                    headers_img=headers_img,
                    base_url=detail_url
                )

                item["URL"] = detail_url
                item["등록일"] = saved.get("createdAt") or ""
                item["상세페이지 JSON 경로"] = saved.get("contentJsonPath") or ""
                item["상세페이지 HTML 경로"] = saved.get("contentHtmlPath") or ""
                item["이미지 경로"] = saved.get("imagePath") or ""
                item["이미지"] = saved.get("image") or "[]"

                self.excel_driver.append_to_csv(
                    self.csv_filename,
                    [item],
                    self.columns,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir
                )

            except Exception as e:
                self.log_signal_func(f"❌ 상세 실패 id={gig_id} / {str(e)}")

            base_total = self.total_cnt if self.total_cnt > 0 else (total if total > 0 else 1)
            pro_value = (self.current_cnt / float(base_total)) * 1000000
            self.progress_signal.emit(self.before_pro_value, pro_value)
            self.before_pro_value = pro_value

            time.sleep(random.uniform(1, 3))

        self.log_signal_func("✅ 상세 수집 완료")

    def _parse_and_save_detail(self, html_text, content_dir, image_dir, headers_img, base_url):
        soup = BeautifulSoup(html_text, "html.parser")

        json_path = ""
        created_at = ""

        next_tag = soup.find("script", id="__NEXT_DATA__")
        if next_tag:
            raw = next_tag.string or next_tag.get_text() or ""
            try:
                data = json.loads(raw)
                created_at = (
                    data.get("props", {})
                    .get("pageProps", {})
                    .get("gig", {})
                    .get("createdAt", "")
                )
                json_text = json.dumps(data, ensure_ascii=False, indent=2)
            except Exception:
                json_text = raw

            json_path = self.file_driver.save_file(content_dir, "__NEXT_DATA__.json", json_text)

        main_tag = soup.find("main")
        merged_html = ""

        if main_tag:
            ids = ["9", "83", "84", "10", "11"]
            for did in ids:
                div = main_tag.find("div", id=did)
                if div:
                    merged_html += str(div)

        html_doc = (
            "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "</head><body>"
            f"{merged_html}"
            "</body></html>"
        )

        html_doc, image_files = self._download_and_rewrite_images(
            html_doc, content_dir, image_dir, headers_img, base_url
        )

        html_path = self.file_driver.save_file(content_dir, "content.html", html_doc)

        return {
            "createdAt": created_at,
            "contentJsonPath": json_path,
            "contentHtmlPath": html_path,
            "imagePath": image_dir,
            "image": json.dumps(image_files, ensure_ascii=False)
        }

    def _download_and_rewrite_images(self, html_doc, content_dir, image_dir, headers_img, base_url):
        soup = BeautifulSoup(html_doc, "html.parser")
        imgs = soup.find_all("img")

        image_files = []

        idx = 0
        for img in imgs:
            src = img.get("src") or ""
            if not src:
                continue
            if src.startswith("data:"):
                continue

            full_url = urljoin(base_url, src)

            idx += 1
            ext = self.file_driver.guess_ext(full_url)
            filename = f"img_{str(idx).zfill(4)}.{ext}"

            saved_path = self.file_driver.save_image(
                folder_path=image_dir,
                filename=filename,
                image_url=full_url,
                headers=headers_img
            )

            if saved_path:
                rel = os.path.relpath(saved_path, content_dir).replace("\\", "/")
                img["src"] = rel
                image_files.append(filename)

        return str(soup), image_files

    def _ensure_output_dir(self, dir_name):
        base_dir = self.folder_path.strip() if self.folder_path else os.getcwd()
        out_dir = os.path.join(base_dir, dir_name)
        os.makedirs(out_dir, exist_ok=True)
        return out_dir

    def cleanup(self):
        try:
            if self.csv_filename and self.excel_driver:
                self.log_signal_func(f"🧾 CSV -> 엑셀 변환 시작: {self.csv_filename}")
                self.excel_driver.convert_csv_to_excel_and_delete(
                    self.csv_filename,
                    folder_path=self.folder_path,
                    sub_dir=self.out_dir
                )
                self.log_signal_func("✅ 엑셀 변환 완료")
                self.csv_filename = None
        except Exception as e:
            self.log_signal_func(f"[cleanup] 엑셀 변환 실패: {e}")

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

        self.api_client = None