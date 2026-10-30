from __future__ import annotations

import random
import csv
import os
import time
from typing import Optional

from PIL import Image

from src.utils.excel_hybrid_utils import ExcelHybridUtils
from src.utils.file_utils import FileUtils
from src.utils.selenium_utils import SeleniumUtils
from src.utils.sqlite_utils import SqliteUtils
from src.workers.api_base_worker import BaseApiWorker

from datetime import datetime
from urllib.parse import urlparse


from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    NoSuchWindowException,
    StaleElementReferenceException,
)
from selenium.webdriver.remote.webdriver import WebDriver

class ApiNaverCafeJoonggonaraAdSetWorker(BaseApiWorker):

    def __init__(self) -> None:
        super().__init__()

        # =====================================================
        # 작업 기본 정보
        # =====================================================
        self.site_name: str = "네이버 카페 중고나라"
        self.worker_name: str = "naver_cafe_joonggonara_ad"
        self.detail_table_name: str = "NAVER_CAFE_JOONGGONARA_AD"

        self.hist_id: Optional[int] = None
        self.job_id: Optional[str] = None

        self.hist_status: str = "RUNNING"
        self.hist_error_message: Optional[str] = None

        self.detail_success_count: int = 0
        self.detail_fail_count: int = 0

        # 사용자 중지 중복 실행 방지
        self._stopping: bool = False

        self.user_index = 0

        # =====================================================
        # 설정값
        # =====================================================
        self.folder_path: str = ""
        self.image_path: str = ""
        self.start_page = None
        self.remove_duplicate_yn = None
        self.user_list: list[dict[str, str]] = []

        # 엑셀 저장 시 사용할 하위 폴더
        self.out_dir: str = "output"

        # =====================================================
        # 드라이버
        # =====================================================
        self.driver = None
        self.selenium_driver: Optional[SeleniumUtils] = None
        self.file_driver: Optional[FileUtils] = None
        self.excel_driver: Optional[ExcelHybridUtils] = None
        self.sqlite_driver: Optional[SqliteUtils] = None

        # 진행률
        self.before_pro_value: float = 0.0

        # 현재 사용 중인 계정
        self.now_user: Optional[dict[str, str]] = None

        # 추후 발송 건수 관리
        self.push_cnt: int = 0


    # =========================================================
    # 초기화
    # =========================================================
    def init(self) -> bool:
        try:
            self.log_signal_func("✅ 초기화 시작")

            # 기존 워커와 동일하게 엑셀 / 파일 유틸 초기화
            self.excel_driver = ExcelHybridUtils(self.log_signal_func)
            self.file_driver = FileUtils(self.log_signal_func)

            # DB 연결 / 스키마 초기화 / 작업 시작 이력 등록
            if not self.db_set():
                return False

            # 설정값 조회 및 로그 출력
            self.load_settings()

            # 실행 경로의 user.csv에서 계정 목록 조회
            self.load_user_list()

            # 셀레니움 및 브라우저 실행
            self.driver_set()

            # BaseApiWorker.set_columns()에서 선택된 컬럼을 받는다.
            self.log_signal_func(f"선택 항목 : {self.columns}")

            self.log_signal_func("✅ init 완료")
            return True

        except Exception as e:
            self.finish_job("FAIL", str(e))
            self.log_signal_func(f"❌ 초기화 에러: {e}")

            # 작업 시작 이력이 등록된 후 오류가 발생했다면
            # 현재 스레드의 DB 연결로 실패 상태를 저장한다.
            if self.hist_id and self.sqlite_driver:
                try:
                    self.update_hist_end(self.sqlite_driver)
                except Exception as update_error:
                    self.log_signal_func(
                        f"❌ [DB] 초기화 실패 이력 저장 오류: {update_error}"
                    )

            return False

        finally:
            # 초기화용 연결은 생성한 작업 스레드에서 닫는다.
            # main()에서 데이터를 저장할 때 다시 연결한다.
            self.close_init_db()

    def load_settings(self) -> None:
        """
        설정 JSON에서 값을 가져와 로그에 출력한다.
        """

        # 저장 폴더
        self.folder_path = str(
            self.get_setting_value(self.setting, "folder_path") or ""
        ).strip()

        # 이미지 폴더
        image_folder = str(
            self.get_setting_value(self.setting, "image_path") or ""
        ).strip()

        # 선택한 폴더가 없다면 실행 경로의 images 폴더 사용
        if not image_folder:
            image_folder = os.path.join(
                self.get_project_root(),
                "images",
            )

        # 선택한 폴더 안의 고정 이미지 파일 사용
        self.image_path = os.path.abspath(
            os.path.join(image_folder, "joonggonara_ad.png")
        )

        # 조회 시작 페이지
        self.start_page = self.get_setting_value(
            self.setting,
            "start_page",
        )

        # 중복 제거 여부
        self.remove_duplicate_yn = self.get_setting_value(
            self.setting,
            "remove_duplicate_yn",
        )

        self.log_signal_func("========== 설정값 ==========")
        self.log_signal_func(f"저장 폴더 : {self.folder_path}")
        self.log_signal_func(f"이미지 폴더 : {image_folder}")
        self.log_signal_func(f"이미지 파일 경로 : {self.image_path}")
        self.log_signal_func(f"조회 시작 페이지 : {self.start_page}")
        self.log_signal_func(f"중복 제거 여부 : {self.remove_duplicate_yn}")
        self.log_signal_func("============================")

        # 이미지 파일 확인
        self.log_image_info()

    def load_user_list(self) -> None:
        """실행 경로의 user.csv에서 id, pw 컬럼을 읽는다."""
        csv_path = os.path.join(self.get_project_root(), "user.csv")
        self.log_signal_func(f"[유저] CSV 경로 : {csv_path}")

        if not os.path.isfile(csv_path):
            raise FileNotFoundError(f"유저 파일이 없습니다: {csv_path}")

        users = []
        try:
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                if not reader.fieldnames or not {"id", "pw"}.issubset(reader.fieldnames):
                    raise ValueError("user.csv에 id, pw 컬럼이 필요합니다.")

                for row in reader:
                    user_id = (row.get("id") or "").strip()
                    password = row.get("pw") or ""
                    if not user_id and not password.strip():
                        continue
                    if not user_id or not password.strip():
                        raise ValueError(f"user.csv {reader.line_num}행에 id 또는 pw가 없습니다.")
                    users.append({"id": user_id, "pw": password})
        except UnicodeDecodeError as e:
            raise ValueError("user.csv를 UTF-8 형식으로 저장해 주세요.") from e

        if not users:
            raise ValueError("user.csv에 등록된 유저가 없습니다.")

        self.user_list = users
        self.log_signal_func(f"✅ [유저] CSV 로드 완료 : {len(self.user_list)}명")
        for index, user in enumerate(self.user_list, start=1):
            self.log_signal_func(f"[유저] {index}번 id : {user['id']} / pw : {user['pw']}")

    def log_image_info(self) -> None:
        """
        이미지 파일을 열어 기본 정보를 출력한다.
        """
        self.log_signal_func("========== 이미지 정보 ==========")
        self.log_signal_func(f"파일 경로 : {self.image_path}")

        if not os.path.isfile(self.image_path):
            self.log_signal_func("❌ 이미지 파일이 없습니다.")
            self.log_signal_func("=================================")
            return

        try:
            file_size = os.path.getsize(self.image_path)

            with Image.open(self.image_path) as image:
                # 실제 이미지 데이터까지 읽어서 확인
                image.load()

                self.log_signal_func(
                    f"파일명 : {os.path.basename(self.image_path)}"
                )
                self.log_signal_func(f"이미지 형식 : {image.format}")
                self.log_signal_func(
                    f"이미지 크기 : {image.width} x {image.height}"
                )
                self.log_signal_func(f"색상 모드 : {image.mode}")
                self.log_signal_func(
                    f"파일 크기 : {file_size:,} bytes "
                    f"({file_size / 1024:.2f} KB)"
                )

            self.log_signal_func("✅ 이미지 파일 읽기 완료")

        except Exception as e:
            self.log_signal_func(f"❌ 이미지 파일 읽기 실패: {e}")

        finally:
            self.log_signal_func("=================================")

    # =========================================================
    # 드라이버 설정
    # =========================================================
    def driver_set(self) -> None:
        """
        기존 워커와 동일한 방식으로 드라이버를 초기화한다.
        """
        if not self.excel_driver:
            self.excel_driver = ExcelHybridUtils(
                self.log_signal_func
            )

        if not self.file_driver:
            self.file_driver = FileUtils(
                self.log_signal_func
            )

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

        if not self.driver:
            raise RuntimeError("셀레니움 브라우저 실행 실패")

        self.log_signal_func("✅ 엑셀 / 파일 / 셀레니움 드라이버 설정 완료")

    # =========================================================
    # DB 초기화
    # =========================================================
    def db_set(self) -> bool:
        self.sqlite_driver = SqliteUtils(self.log_signal_func)

        db_path = self.get_runtime_db_path()

        self.log_signal_func(
            f"[DB] 실제 경로 = {os.path.abspath(db_path)}"
        )

        if not self.sqlite_driver.connect(db_path):
            self.log_signal_func("❌ [DB] 연결 실패")
            return False

        schema_files = [
            os.path.join(
                "resources",
                "customers",
                "common",
                "db",
                "schema_hist.sql",
            ),
            os.path.join(
                "resources",
                "customers",
                self.worker_name,
                "db",
                "schema_detail.sql",
            ),
        ]

        if not self.sqlite_driver.execute_script_files(schema_files):
            self.log_signal_func("❌ [DB] 스키마 초기화 실패")
            return False

        self.log_signal_func("✅ [DB] 스키마 초기화 완료")

        # 작업 시작 이력 등록
        if not self.insert_hist_start():
            return False

        return True

    def insert_hist_start(self) -> bool:
        """
        WORKER_JOB_HIST에 작업 시작 이력을 등록한다.
        """
        if not self.sqlite_driver:
            self.log_signal_func("❌ [DB] sqlite_driver 없음")
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.job_id = time.strftime("%Y%m%d%H%M%S")

        query = """
                INSERT INTO worker_job_hist (
                    job_id,
                    table_name,
                    site_name,
                    worker_name,
                    user_id,
                    start_at,
                    status,
                    total_count,
                    success_count,
                    fail_count,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) \
                """

        params = (
            self.job_id,
            self.detail_table_name,
            self.site_name,
            self.worker_name,
            str(self.user).strip() if self.user else None,
            now,
            "RUNNING",
            0,
            0,
            0,
            now,
            now,
        )

        if not self.sqlite_driver.execute(query, params):
            self.log_signal_func("❌ [DB] hist 시작 row 저장 실패")
            return False

        row = self.sqlite_driver.fetchone(
            "SELECT last_insert_rowid() AS hist_id"
        )

        self.hist_id = row["hist_id"] if row else None

        if not self.hist_id:
            self.log_signal_func("❌ [DB] 생성된 hist_id 조회 실패")
            return False

        self.log_signal_func(
            f"✅ [DB] hist 시작 row 저장 완료 | "
            f"hist_id={self.hist_id} | job_id={self.job_id}"
        )

        return True

    def close_init_db(self) -> None:
        """
        초기화에 사용한 DB 연결을 작업 스레드에서 닫는다.
        """
        if not self.sqlite_driver:
            return

        try:
            self.sqlite_driver.close()

        except Exception as e:
            self.log_signal_func(
                f"❌ [DB] 초기화 연결 해제 실패: {e}"
            )

        finally:
            self.sqlite_driver = None

    # =========================================================
    # 상세 데이터 저장
    # =========================================================
    def insert_detail_row(self,sqlite_driver: SqliteUtils,row: dict,) -> bool:
        """
        상세 데이터 1건을 저장한다.

        row에는 DB 컬럼명과 동일한 키를 사용한다.
        """
        now = time.strftime("%Y-%m-%d %H:%M:%S")

        query = f"""
            INSERT INTO {self.detail_table_name} (
                hist_id,
                site_name,
                worker_name,
                table_name,
                job_id,
                user_id,
                articleId,
                menuName,
                subject,
                boardType,
                nickName,
                memberKey,
                writeDateTimestamp,
                writeDate,
                successYn,
                errorMessage,
                created_at,
                updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?
            )
        """

        params = (
            self.hist_id,
            self.site_name,
            self.worker_name,
            self.detail_table_name,
            self.job_id,
            str(self.user).strip() if self.user else None,

            row.get("articleId"),
            row.get("menuName"),
            row.get("subject"),
            row.get("boardType"),
            row.get("nickName"),
            row.get("memberKey"),
            row.get("writeDateTimestamp"),
            row.get("writeDate"),
            row.get("successYn"),
            row.get("errorMessage"),

            now,
            now,
        )

        if not sqlite_driver.execute(query, params):
            self.detail_fail_count += 1

            self.log_signal_func(
                f"❌ [DB] detail 저장 실패 | "
                f"hist_id={self.hist_id} | "
                f"articleId={row.get('articleId')}"
            )
            return False

        self.detail_success_count += 1

        self.log_signal_func(
            f"✅ [DB] detail 저장 완료 | "
            f"hist_id={self.hist_id} | "
            f"articleId={row.get('articleId')}"
        )

        return True

    def is_member_already_processed(self, member_key: str) -> bool:
        """전체 작업 이력에서 전송 버튼을 클릭한 회원인지 확인한다."""
        sqlite_driver = SqliteUtils(self.log_signal_func)
        try:
            if not sqlite_driver.connect(self.get_runtime_db_path()):
                raise RuntimeError("중복 확인용 DB 연결 실패")
            # 오류와 조회 결과 없음을 구별하기 위해 예외를 그대로 전달한다.
            row = sqlite_driver.conn.execute(
                f"SELECT 1 FROM {self.detail_table_name} "
                "WHERE memberKey = ? AND successYn = ? LIMIT 1",
                (member_key, "Y"),
            ).fetchone()
            return row is not None
        finally:
            sqlite_driver.close()

    def save_processed_article(self, article: dict) -> None:
        """전송 버튼 클릭 결과를 상세 테이블에 저장한다."""
        sqlite_driver = SqliteUtils(self.log_signal_func)
        try:
            if not sqlite_driver.connect(self.get_runtime_db_path()):
                raise RuntimeError("상세 저장용 DB 연결 실패")
            if not self.insert_detail_row(sqlite_driver, article):
                raise RuntimeError(
                    "전송 버튼 클릭 후 DB 저장 실패: 중복 전송 방지를 위해 작업을 중단합니다."
                )
        finally:
            sqlite_driver.close()

    # =========================================================
    # 작업 이력 마감
    # =========================================================
    def finish_job(self,status: str,error_message: Optional[str] = None,) -> None:
        self.hist_status = status
        self.hist_error_message = error_message

    def update_hist_end(self,sqlite_driver: Optional[SqliteUtils] = None,) -> bool:
        """
        작업 종료 상태를 WORKER_JOB_HIST에 저장한다.
        """
        sqlite_driver = sqlite_driver or self.sqlite_driver

        if not sqlite_driver:
            self.log_signal_func("❌ [DB] 종료 처리용 연결 없음")
            return False

        if not self.hist_id:
            self.log_signal_func(
                "⚠️ [DB] hist_id 없음 - 종료 update 생략"
            )
            return False

        now = time.strftime("%Y-%m-%d %H:%M:%S")

        query = """
                UPDATE worker_job_hist
                SET
                    end_at = ?,
                    status = ?,
                    total_count = ?,
                    success_count = ?,
                    fail_count = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE hist_id = ? \
                """

        params = (
            now,
            self.hist_status,
            self.detail_success_count + self.detail_fail_count,
            self.detail_success_count,
            self.detail_fail_count,
            self.hist_error_message,
            now,
            self.hist_id,
        )

        if not sqlite_driver.execute(query, params):
            self.log_signal_func(
                f"❌ [DB] hist 종료 row 수정 실패 | "
                f"hist_id={self.hist_id}"
            )
            return False

        self.log_signal_func(
            f"✅ [DB] hist 종료 row 수정 완료 | "
            f"hist_id={self.hist_id} | status={self.hist_status}"
        )

        return True

    def finalize_db(self) -> None:
        """
        종료 시 별도 DB 연결을 만들어 작업 이력을 마감한다.
        """
        if not self.hist_id:
            return

        temp_sqlite_driver = None

        try:
            temp_sqlite_driver = SqliteUtils(
                self.log_signal_func
            )

            db_path = self.get_runtime_db_path()

            if not temp_sqlite_driver.connect(db_path):
                self.log_signal_func(
                    "❌ [DB] 최종 마감용 연결 실패"
                )
                return

            if self.update_hist_end(temp_sqlite_driver):
                self.log_signal_func(
                    "✅ [DB] hist 최종 업데이트 완료"
                )
            else:
                self.log_signal_func(
                    "❌ [DB] hist 최종 업데이트 실패"
                )

        except Exception as e:
            self.log_signal_func(
                f"❌ [DB] 최종 마감 실패: {e}"
            )

        finally:
            if temp_sqlite_driver:
                try:
                    temp_sqlite_driver.close()

                except Exception as e:
                    self.log_signal_func(
                        f"❌ [DB] 마감용 연결 해제 실패: {e}"
                    )

    # =========================================================
    # 메인 작업
    # =========================================================
    def main(self) -> bool:
        self.log_signal_func("✅ main 시작")

        try:
            # 첫 번째 계정부터 시작
            self.user_index = 0
            self.now_user = self.user_list[self.user_index]

            # 이번 실행에서 전송 버튼을 클릭한 총 횟수
            self.push_cnt = 0

            # 1. 네이버 로그인
            if not self.naver_login(
                    self.now_user["id"],
                    self.now_user["pw"],
            ):
                if not self.running:
                    self.finish_job("STOP", "사용자 중단")
                else:
                    self.finish_job("FAIL", "네이버 로그인 실패")

                return False

            # 2. 카페 목록 API 응답 후킹 설정
            self.setup_article_list_hook()

            # 3. 설정한 시작 페이지부터 조회
            page = int(self.start_page or 1)

            if page < 1:
                raise ValueError("조회 시작 페이지는 1 이상이어야 합니다.")

            while self.running:
                article_rows = self.get_article_list(page)

                if not self.running:
                    break

                # 더 이상 게시글이 없으면 종료
                if not article_rows:
                    self.log_signal_func(
                        f"ℹ️ [목록] {page}페이지에 게시글이 없어 종료합니다."
                    )
                    break

                # 4. 게시글을 순회하며 로그 출력
                for article in article_rows:
                    if not self.running:
                        break

                    self.log_signal_func(
                        f"📌 [게시글] "
                        f"페이지={page} | "
                        f"ID={article['articleId']} | "
                        f"제목={article['subject']} | "
                        f"닉네임={article['nickName']}"
                    )

                    # 중복 제거 설정이 켜진 경우, 처리한 회원은 건너뛴다.
                    member_key = str(article.get("memberKey") or "").strip()
                    if self.remove_duplicate_yn:
                        if not member_key:
                            self.log_signal_func(
                                f"⚠️ [중복 확인] memberKey 없음 - 건너뜀 | articleId={article['articleId']}"
                            )
                            continue
                        if self.is_member_already_processed(member_key):
                            self.log_signal_func(
                                f"ℹ️ [중복 확인] 이미 처리한 회원 | articleId={article['articleId']}"
                            )
                            continue

                    # 게시글 상세 이동 → 채팅방 → 이미지 전송 버튼 클릭
                    if self.open_article_chat(article):
                        # Y는 실제 수신 확인이 아니라 전송 버튼 클릭을 뜻한다.
                        article["successYn"] = "Y"
                        article["errorMessage"] = ""
                        article["memberKey"] = member_key or None
                        self.save_processed_article(article)

                        # 전송 버튼 클릭 횟수 증가
                        self.push_cnt += 1

                        self.log_signal_func(
                            f"✅ [채팅] 전송 버튼 클릭 완료 | "
                            f"articleId={article['articleId']} | "
                            f"누적={self.push_cnt}건"
                        )

                        # 전송 버튼 클릭 13건마다 다음 계정으로 변경
                        if self.push_cnt % 13 == 0:

                            # 마지막 계정 다음에는 첫 번째 계정으로 돌아간다.
                            self.user_index = (self.user_index + 1) % len(self.user_list)
                            self.now_user = self.user_list[self.user_index]

                            self.log_signal_func(
                                f"🔄 [계정 변경] 다음 계정 로그인 시작 | "
                                f"아이디={self.now_user['id']}"
                            )

                            # 다음 계정으로 로그인
                            if not self.naver_login(
                                    self.now_user["id"],
                                    self.now_user["pw"],
                            ):
                                if not self.running:
                                    self.finish_job("STOP", "사용자 중단")
                                else:
                                    self.finish_job("FAIL", "다음 계정 로그인 실패")

                                return False

                            self.log_signal_func(
                                f"✅ [계정 변경] 로그인 완료 | "
                                f"아이디={self.now_user['id']}"
                            )
                    else:
                        self.log_signal_func(
                            f"⚠️ [채팅] 처리 실패 | "
                            f"articleId={article['articleId']}"
                        )

                # 페이지 작업 도중 중지된 경우 바로 종료
                if not self.running:
                    break

                # 다음 페이지로 넘어가기 전 3초 휴식
                self.log_signal_func(
                    f"⏳ [목록] {page}페이지 처리 완료 - 3초 휴식"
                )

                if not self.sleep_s(3):
                    break

                page += 1

            if not self.running:
                self.finish_job("STOP", "사용자 중단")
                return False

            self.finish_job("SUCCESS")
            self.log_signal_func("✅ main 종료")
            return True

        except Exception as e:
            self.finish_job("FAIL", str(e))
            self.log_signal_func(f"❌ main 오류: {e}")
            return False

    def naver_login(self, user_id: str, password: str) -> bool:
        """
        네이버에 로그인한다.

        추가 인증 화면이 나오면 사용자가 직접 인증할 수 있도록
        최대 3분 동안 로그인 완료를 기다린다.
        """

        try:
            self.log_signal_func(f"🔐 [로그인] 시작 : {user_id}")

            self.driver.get(
                "https://nid.naver.com/nidlogin.login"
                "?mode=form&url=https://www.naver.com/"
            )

            wait = WebDriverWait(self.driver, 20)

            id_input = wait.until(
                EC.presence_of_element_located((By.ID, "id"))
            )
            pw_input = wait.until(
                EC.presence_of_element_located((By.ID, "pw"))
            )

            # 기존에 사용하던 방식과 동일하게 input/change 이벤트 발생
            self._set_login_input(id_input, user_id)
            self._set_login_input(pw_input, password)


            # 실제 화면에 표시된 로그인 버튼을 찾는다.
            def find_login_button(driver):
                selectors = (
                    "#loginBtn_column",
                    "#loginBtn_row",
                    r"#log\.login",
                    "button[type='submit']",
                )

                for selector in selectors:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)

                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            return element

                return False

            login_button = wait.until(find_login_button)

            self.log_signal_func("🔐 [로그인] 버튼 클릭")
            login_button.click()
            self.log_signal_func("🔐 [로그인] 버튼 클릭 완료")

            # 로그인 버튼 클릭 후 화면이 바뀔 시간을 준다.
            if not self.sleep_s(2):
                self.log_signal_func("ℹ️ [로그인] 사용자 중단")
                return False

            # 기기 등록 버튼 중복 클릭 방지
            device_registered = False


            def wait_for_login(driver):
                nonlocal device_registered

                if not self.running:
                    return True

                # 새로운 기기 등록 화면이 표시된 경우
                if not device_registered:
                    buttons = driver.find_elements(By.ID, "new.save")

                    for button in buttons:
                        if button.is_displayed() and button.is_enabled():
                            self.log_signal_func(
                                "📱 [로그인] 새로운 기기 등록 화면 확인"
                            )

                            button.click()
                            device_registered = True

                            self.log_signal_func(
                                "✅ [로그인] 기기 등록 버튼 클릭"
                            )

                            # 기기 등록 후 화면 이동 대기
                            self.sleep_s(2)
                            break

                return self._is_naver_login_completed()


            self.log_signal_func(
                "🔐 [로그인] 완료 대기 중 "
                "(추가 인증이 나오면 브라우저에서 직접 완료해 주세요.)"
            )

            try:
                WebDriverWait(
                    self.driver,
                    180,
                    poll_frequency=0.5,
                ).until(wait_for_login)

            except TimeoutException:
                self.log_signal_func(
                    "❌ [로그인] 제한시간 안에 완료되지 않았습니다. "
                    "아이디, 비밀번호 또는 인증 화면을 확인해 주세요."
                )
                return False

            if not self.running:
                self.log_signal_func("ℹ️ [로그인] 사용자 중단")
                return False

            self.log_signal_func(f"✅ [로그인] 완료 : {user_id}")
            return True


        except Exception as e:
            self.log_signal_func(f"❌ [로그인] 오류: {e}")
            return False


    def _set_login_input(self, element, value: str) -> None:
        """
        로그인 입력란에 값을 넣고 입력 이벤트를 발생시킨다.
        """
        self.driver.execute_script(
            """
            const element = arguments[0];
            const value = arguments[1];
    
            const setter = Object.getOwnPropertyDescriptor(
                HTMLInputElement.prototype,
                "value"
            ).set;
    
            element.focus();
            setter.call(element, value);
            element.dispatchEvent(new Event("input", { bubbles: true }));
            element.dispatchEvent(new Event("change", { bubbles: true }));
            """,
            element,
            value,
        )


    def _is_naver_login_completed(self) -> bool:
        """
        네이버 로그인 페이지를 벗어나
        네이버 서비스 화면으로 이동했는지 확인한다.
        """
        parsed_url = urlparse(self.driver.current_url)

        host = (parsed_url.hostname or "").lower()
        path = parsed_url.path.lower()

        is_naver = host == "naver.com" or host.endswith(".naver.com")

        # 로그인 화면이나 네이버 인증 도메인에 있으면 계속 대기
        if not is_naver or host == "nid.naver.com":
            return False

        if "nidlogin.login" in path:
            return False

        return True



    def setup_article_list_hook(self) -> None:
        """
        페이지가 열릴 때 게시글 목록 API 응답을 수집하도록
        fetch / XMLHttpRequest 후킹을 등록한다.
        """
        hook_js = r"""
            (() => {
                const targetPath =
                    "/cafe-web/cafe-boardlist-api/v1/cafes/10050146/menus/0/articles";
    
                window.__articleListResponses = [];
    
                function saveResponse(url, data) {
                    try {
                        const requestUrl = new URL(url, location.href);
    
                        if (!requestUrl.pathname.includes(targetPath)) {
                            return;
                        }
    
                        window.__articleListResponses.push({
                            page: requestUrl.searchParams.get("page") || "1",
                            data: data
                        });
                    } catch (error) {
                        // 목록 API와 관련 없는 응답은 무시
                    }
                }
    
                // fetch 응답 후킹
                const originalFetch = window.fetch;
    
                window.fetch = async function (...args) {
                    const response = await originalFetch.apply(this, args);
    
                    try {
                        const request = args[0];
                        const url = typeof request === "string"
                            ? request
                            : request.url;
    
                        if (url && url.includes(targetPath)) {
                            response.clone().json()
                                .then(data => saveResponse(url, data))
                                .catch(() => {});
                        }
                    } catch (error) {
                        // 원래 응답에는 영향을 주지 않는다.
                    }
    
                    return response;
                };
    
                // XMLHttpRequest 응답 후킹
                const originalOpen = XMLHttpRequest.prototype.open;
                const originalSend = XMLHttpRequest.prototype.send;
    
                XMLHttpRequest.prototype.open = function (method, url, ...rest) {
                    this.__articleListUrl = String(url);
                    return originalOpen.call(this, method, url, ...rest);
                };
    
                XMLHttpRequest.prototype.send = function (...args) {
                    this.addEventListener("load", function () {
                        try {
                            const url = this.__articleListUrl || "";
    
                            if (!url.includes(targetPath)) {
                                return;
                            }
    
                            const data = this.responseType === "json"
                                ? this.response
                                : JSON.parse(this.responseText);
    
                            saveResponse(url, data);
                        } catch (error) {
                            // JSON이 아닌 응답은 무시
                        }
                    });
    
                    return originalSend.apply(this, args);
                };
            })();
        """

        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": hook_js},
        )

        self.log_signal_func("✅ [목록] 네트워크 후킹 설정 완료")


    def get_article_list(self, page: int) -> list[dict]:
        """
        카페 목록 페이지로 이동하고,
        해당 페이지의 API 응답을 받아 게시글 배열로 변환한다.
        """
        page_url = (
            "https://cafe.naver.com/f-e/cafes/10050146/menus/0"
            f"?page={page}"
        )

        self.log_signal_func(f"📄 [목록] {page}페이지 이동")
        self.driver.get(page_url)

        def find_response(driver):
            # 중지 요청이 있으면 대기를 종료한다.
            if not self.running:
                return {"stopped": True}

            return driver.execute_script(
                """
                const page = String(arguments[0]);
                const responses = window.__articleListResponses || [];
    
                return responses.find(item => item.page === page) || null;
                """,
                page,
            )

        try:
            response = WebDriverWait(
                self.driver,
                30,
                poll_frequency=0.5,
            ).until(find_response)

        except TimeoutException:
            raise RuntimeError(
                f"{page}페이지 목록 API 응답을 받지 못했습니다."
            )

        if response.get("stopped"):
            return []

        data = response.get("data") or {}

        if not isinstance(data, dict):
            raise RuntimeError(f"{page}페이지 응답 형식이 올바르지 않습니다.")

        result = data.get("result")

        if not isinstance(result, dict) or not isinstance(
                result.get("articleList"), list
        ):
            raise RuntimeError(
                f"{page}페이지 응답에 articleList가 없습니다."
            )

        article_list = result["articleList"]
        rows = []

        for article in article_list:
            if not isinstance(article, dict):
                continue

            # 게시글 항목만 처리
            if article.get("type") != "ARTICLE":
                continue

            item = article.get("item") or {}

            if not isinstance(item, dict):
                continue

            writer_info = item.get("writerInfo") or {}

            if not isinstance(writer_info, dict):
                writer_info = {}

            timestamp = item.get("writeDateTimestamp")
            write_date = ""

            if timestamp is not None:
                try:
                    # 응답의 타임스탬프는 밀리초 단위
                    write_date = datetime.fromtimestamp(
                        int(timestamp) / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError, OSError, OverflowError):
                    self.log_signal_func(
                        f"⚠️ [목록] 작성일 변환 실패 | "
                        f"articleId={item.get('articleId')}"
                    )

            # 기존 DB 컬럼명과 동일하게 구성
            rows.append({
                "articleId": item.get("articleId"),
                "menuName": item.get("menuName"),
                "subject": item.get("subject"),
                "boardType": item.get("boardType"),
                "nickName": writer_info.get("nickName"),
                "memberKey": writer_info.get("memberKey"),
                "writeDateTimestamp": timestamp,
                "writeDate": write_date,

                # 상세 처리 후 설정할 값
                "successYn": None,
                "errorMessage": None,
            })

        self.log_signal_func(
            f"✅ [목록] {page}페이지 | 게시글 {len(rows)}건"
        )

        return rows


    def click_button(self, element) -> None:
        """
        버튼이 잘 보이도록 이동한 뒤 클릭한다.
        """
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            element,
        )

        if not self.sleep_s(1):
            return

        element.click()


    def _find_chat_button(self, driver):
        """게시글 본문과 cafe_main iframe에서 채팅하기 링크를 찾는다."""
        driver.switch_to.default_content()
        frames = driver.find_elements(By.ID, "cafe_main")
        for frame in [None, *frames]:
            driver.switch_to.default_content()
            if frame is not None:
                driver.switch_to.frame(frame)
            for button in driver.find_elements(By.ID, "more-button"):
                if button.is_displayed() and button.is_enabled() and "채팅하기" in button.text:
                    return button
        driver.switch_to.default_content()
        return False

    def open_article_chat(self, article: dict) -> bool:
        """첨부된 테스트 코드의 상세 및 최초 연동 흐름을 그대로 사용한다."""
        article_id = article.get("articleId")
        if not article_id:
            self.log_signal_func("⚠️ [상세] 게시글 ID가 없습니다.")
            return False
        driver = self.driver
        article_url = f"https://cafe.naver.com/f-e/cafes/10050146/articles/{article_id}"
        article_handle = driver.current_window_handle
        original_handles = set(driver.window_handles)
        MIN_ACTION_DELAY_SEC = 0.5
        MAX_ACTION_DELAY_SEC = 0.8
        CHAT_LOADING_DELAY_SEC = 1.5
        # 테스트 코드의 print 로그를 워커 로그에 표시한다.
        print = self.log_signal_func

        def human_delay() -> None:
            time.sleep(random.uniform(MIN_ACTION_DELAY_SEC, MAX_ACTION_DELAY_SEC))

        def wait_document_ready(driver: WebDriver, timeout: int = 20) -> None:
            WebDriverWait(driver, timeout).until(
                lambda current_driver: current_driver.execute_script(
                    "return document.readyState"
                )
                                       in ("interactive", "complete")
            )

        def click_joongna_naver_login_if_needed(driver: WebDriver) -> bool:
            """중고나라 최초 연동 화면이면 '네이버로 시작하기'를 클릭한다."""
            selector = (
                By.XPATH,
                "//button[.//span[normalize-space()='네이버로 시작하기']]",
            )
            wait_seconds = 20 if "/signin" in driver.current_url.lower() else 5

            try:
                login_button = WebDriverWait(driver, wait_seconds).until(
                    EC.element_to_be_clickable(selector)
                )
            except TimeoutException:
                return False

            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});",
                login_button,
            )
            human_delay()

            before_url = driver.current_url
            try:
                login_button.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", login_button)

            print("[중고나라 로그인] 네이버로 시작하기를 클릭했습니다.")

            try:
                WebDriverWait(driver, 30).until(
                    lambda current_driver: current_driver.current_url != before_url
                                           or bool(
                        current_driver.find_elements(
                            By.CSS_SELECTOR,
                            "textarea[name='message']",
                        )
                    )
                )
            except TimeoutException:
                print("[중고나라 로그인] 인증 화면 전환을 확인하지 못했습니다.")

            time.sleep(CHAT_LOADING_DELAY_SEC)
            return True

        def open_chat_page(driver: WebDriver, article_url: str) -> tuple[str, str | None]:
            driver.switch_to.default_content()
            driver.get(article_url)
            wait_document_ready(driver)
            human_delay()

            # 구형 네이버 카페 게시글 주소는 실제 본문을 iframe#cafe_main 안에
            # 렌더링한다. iframe이 있는 경우 본문 프레임으로 전환하고,
            # 신형 /f-e 페이지처럼 iframe이 없으면 최상위 문서를 그대로 사용한다.
            try:
                WebDriverWait(driver, 3).until(
                    EC.frame_to_be_available_and_switch_to_it((By.ID, "cafe_main"))
                )
                wait_document_ready(driver, timeout=15)
                print("[게시글] cafe_main iframe으로 전환했습니다.")
            except TimeoutException:
                driver.switch_to.default_content()
                print("[게시글] iframe이 없어 현재 문서에서 채팅 버튼을 찾습니다.")

            try:
                chat_button = WebDriverWait(driver, 4).until(
                    EC.presence_of_element_located((By.ID, "more-button"))
                )
            except TimeoutException:
                return "", None

            chat_url = (chat_button.get_attribute("href") or "").strip()
            if not chat_url:
                return "", None

            article_handle = driver.current_window_handle
            handles_before = set(driver.window_handles)

            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});",
                chat_button,
            )
            human_delay()

            try:
                chat_button.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", chat_button)

            try:
                WebDriverWait(driver, 10).until(
                    lambda current_driver: len(current_driver.window_handles)
                                           > len(handles_before)
                )
            except TimeoutException:
                # target=_blank 클릭이 막힌 환경에서는 같은 세션의 새 탭을 직접 연다.
                driver.execute_script("window.open(arguments[0], '_blank');", chat_url)
                WebDriverWait(driver, 10).until(
                    lambda current_driver: len(current_driver.window_handles)
                                           > len(handles_before)
                )

            new_handles = [
                handle for handle in driver.window_handles if handle not in handles_before
            ]
            if new_handles:
                driver.switch_to.window(new_handles[-1])

            # tracking.joongna.com 리다이렉트 후 표시되는 상품 상세 화면에서는
            # 하단의 '채팅하기' 버튼을 한 번 더 눌러야 실제 채팅방으로 이동한다.
            time.sleep(CHAT_LOADING_DELAY_SEC)
            wait_document_ready(driver)

            product_chat_button = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "button[aria-label='채팅하기']")
                )
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});",
                product_chat_button,
            )
            human_delay()

            try:
                product_chat_button.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", product_chat_button)

            print("[상품 상세] 채팅하기 버튼을 클릭했습니다.")
            time.sleep(CHAT_LOADING_DELAY_SEC)
            wait_document_ready(driver)

            first_login_completed = click_joongna_naver_login_if_needed(driver)

            # 최초 인증 때는 callbackUrl의 상품 상세로 다시 돌아온다.
            # 이 경우 상품 상세의 채팅하기 버튼을 한 번 더 눌러야 채팅방이 열린다.
            if first_login_completed:
                try:
                    product_chat_button = WebDriverWait(driver, 60).until(
                        EC.element_to_be_clickable(
                            (By.CSS_SELECTOR, "button[aria-label='채팅하기']")
                        )
                    )
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});",
                        product_chat_button,
                    )
                    human_delay()

                    try:
                        product_chat_button.click()
                    except ElementClickInterceptedException:
                        driver.execute_script(
                            "arguments[0].click();",
                            product_chat_button,
                        )

                    print("[최초 인증 완료] 채팅하기 버튼을 다시 클릭했습니다.")
                    time.sleep(CHAT_LOADING_DELAY_SEC)
                    wait_document_ready(driver)

                except TimeoutException:
                    # 인증 후 바로 채팅방으로 이동한 경우에는 textarea가 이미 보인다.
                    if not driver.find_elements(
                            By.CSS_SELECTOR,
                            "textarea[name='message']",
                    ):
                        raise

            return chat_url, article_handle

        try:
            chat_url, _ = open_chat_page(driver, article_url)

            if not chat_url:
                self.log_signal_func(
                    f"ℹ️ [게시글] 채팅하기 버튼 없음 | "
                    f"articleId={article_id}"
                )
                return False

            self.log_signal_func(
                f"✅ [채팅] 화면 이동 완료 | articleId={article_id}"
            )

            # 채팅 탭이 닫히기 전에 이미지 첨부 및 전송
            result = self.send_chat_image()

            if result == "stopped":
                self.log_signal_func("ℹ️ [채팅] 사용자 중단")
                return False

            self.log_signal_func(
                f"✅ [채팅] 이미지 전송 버튼 클릭 완료 | "
                f"articleId={article_id}"
            )

            return True


        except TimeoutException:
            self.log_signal_func(f"⚠️ [상세] 화면 또는 버튼 대기 시간 초과 | articleId={article_id}")
            return False
        except Exception as e:
            self.log_signal_func(f"❌ [상세] 처리 오류 | articleId={article_id} | {e}")
            return False
        finally:
            try:
                for handle in list(driver.window_handles):
                    if handle not in original_handles:
                        driver.switch_to.window(handle)
                        driver.close()
                if article_handle in driver.window_handles:
                    driver.switch_to.window(article_handle)
                    driver.switch_to.default_content()
            except Exception as e:
                self.log_signal_func(f"⚠️ [상세] 탭 정리 실패: {e}")


    def send_chat_image(self) -> str:
        """
        현재 채팅방에 설정된 이미지를 첨부하고 전송 버튼을 클릭한다.

        반환값:
            "clicked": 전송 버튼 클릭 완료
            "stopped": 사용자 중단
        """
        driver = self.driver

        # 채팅 입력창이 표시될 때까지 대기
        textarea = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (
                    By.CSS_SELECTOR,
                    "textarea[name='message']"
                    "[placeholder='메시지를 입력해 주세요.']",
                )
            )
        )

        textarea.click()

        if not self.sleep_s(1):
            return "stopped"

        textarea.clear()

        # 이미지 파일 첨부
        file_input = driver.find_element(
            By.CSS_SELECTOR,
            "form input[type='file']",
        )

        file_input.send_keys(self.image_path)

        self.log_signal_func(
            f"✅ [채팅] 이미지 첨부: {os.path.basename(self.image_path)}"
        )

        if not self.sleep_s(1):
            return "stopped"

        # 기존 테스트 코드와 동일한 전송 버튼
        submit_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (
                    By.CSS_SELECTOR,
                    "textarea[name='message'] ~ button[type='submit']",
                )
            )
        )

        if not self.sleep_s(1):
            return "stopped"

        submit_button.click()

        self.log_signal_func("✅ [채팅] 이미지 전송 버튼 클릭")

        return "clicked"


    # =========================================================
    # 종료 및 정리
    # =========================================================
    def cleanup(self) -> None:
        """
        기존 워커와 동일하게 각 드라이버를 정리하고
        별도 DB 연결로 작업 이력을 마감한다.
        """

        try:
            if self.driver:
                self.driver.quit()
        except Exception as e:
            self.log_signal_func(
                f"[cleanup] driver.quit 실패: {e}"
            )
        finally:
            self.driver = None

        try:
            if self.selenium_driver:
                self.selenium_driver.quit()
        except Exception as e:
            self.log_signal_func(
                f"[cleanup] selenium_driver.quit 실패: {e}"
            )
        finally:
            self.selenium_driver = None

        try:
            if self.file_driver:
                self.file_driver.close()
        except Exception as e:
            self.log_signal_func(
                f"[cleanup] file_driver.close 실패: {e}"
            )
        finally:
            self.file_driver = None

        # 기존 워커처럼 별도 연결로 작업 이력 마감
        self.finalize_db()

        try:
            if self.excel_driver:
                self.excel_driver.close()
        except Exception as e:
            self.log_signal_func(
                f"[cleanup] excel_driver.close 실패: {e}"
            )
        finally:
            self.excel_driver = None

    def stop(self) -> None:
        # 기존 워커와 동일하게 중복 호출 방지
        if self._stopping:
            return

        self._stopping = True

        self.log_signal_func("✅ stop 시작")
        self.running = False

        if self.hist_status == "RUNNING":
            self.finish_job("STOP", "사용자 중단")

        self.cleanup()
        self.log_signal_func("✅ stop 완료")

    def destroy(self) -> None:
        self.progress_signal.emit(
            self.before_pro_value,
            1000000,
        )

        self.log_signal_func("✅ destroy")
        self.progress_end_signal.emit()


