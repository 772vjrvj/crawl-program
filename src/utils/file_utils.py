# /src/utils/file_utils.py
from __future__ import annotations  # === 신규 ===

import json
import os
import re
from typing import Any, Callable, Dict, List, Mapping, Optional
from urllib.parse import urlparse

import httpx

from src.utils.time_utils import get_current_yyyymmddhhmmss


LogFunc = Callable[[str], None]


class FileUtils:
    def __init__(self, log_func: Optional[LogFunc] = None, api_client: Optional[Any] = None):
        self.log_func: Optional[LogFunc] = log_func
        self.api_client: Optional[Any] = api_client  # === 신규 ===

        # === 신규 === httpx 클라이언트 재사용(선택)
        self._http: Optional[httpx.Client] = None

    # === 신규 === 로깅 통일
    def _log(self, msg: str) -> None:
        if self.log_func:
            try:
                self.log_func(msg)
            except Exception:
                pass

    # === 신규 === 필요 시만 생성/재사용
    def _get_http_client(self, timeout: float) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(
                follow_redirects=True,
                timeout=timeout,
                http2=True,
            )
        else:
            # timeout이 매 호출마다 다를 수 있어서 재생성할지/고정할지 선택인데
            # 여기선 단순히 기존 클라이언트를 재사용 (timeout은 request에 넘겨도 됨)
            pass
        return self._http

    # === 신규 === 종료 시 호출해주면 깔끔 (선택)
    def close(self) -> None:
        if self._http is not None:
            try:
                self._http.close()
            except Exception:
                pass
            self._http = None

    def create_folder(self, folder_name: str) -> str:
        folder_path = os.path.join(os.getcwd(), folder_name)

        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            self._log(f"📁 폴더 생성됨: {folder_path}")
        else:
            self._log(f"📁 폴더 이미 존재: {folder_path}")

        return folder_path

    def save_file(self, folder_path: str, filename: str, source: str) -> str:
        save_path = os.path.join(folder_path, filename)

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(source)
            self._log(f"💾 파일 저장 완료: {save_path}")
        except Exception as e:
            self._log(f"❌ 파일 저장 실패: {save_path} / 오류: {e}")
            raise

        return save_path

    def delete_file(self, file_path: str) -> str:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                self._log(f"🗑️ 파일 삭제됨: {file_path}")
            except Exception as e:
                self._log(f"❌ 파일 삭제 실패: {file_path} / 오류: {e}")
                raise
        else:
            self._log(f"⚠️ 삭제 대상 파일이 존재하지 않음: {file_path}")

        return file_path

    def get_timestamped_filepath(self, prefix: str, ext: str, label: str) -> str:
        filename = f"{prefix}_{get_current_yyyymmddhhmmss()}.{ext}"
        path = os.path.join(os.getcwd(), filename)
        self._log(f"{label} 파일 경로 생성됨: {path}")
        return path

    def get_csv_filename(self, prefix: str) -> str:
        return self.get_timestamped_filepath(prefix, "csv", "CSV")

    def get_excel_filename(self, prefix: str) -> str:
        return self.get_timestamped_filepath(prefix, "xlsx", "Excel")

    def read_numbers_from_file(self, file_path: str) -> List[int]:
        numbers: List[int] = []

        if not os.path.exists(file_path):
            self._log(f"❌ 파일이 존재하지 않습니다: {file_path}")
            return numbers

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s:
                        continue
                    try:
                        numbers.append(int(s))
                    except ValueError:
                        self._log(f"⚠️ 정수 변환 실패 (무시됨): '{s}'")
        except Exception as e:
            self._log(f"❌ 파일 읽기 실패: {file_path} / 오류: {e}")
            raise

        self._log(f"📄 숫자 {len(numbers)}개 읽음: {file_path}")
        return numbers

    def save_image(
            self,
            folder_path: str,
            filename: str,
            image_url: str,
            headers: Optional[Mapping[str, str]] = None,
            timeout: float = 30,
    ) -> Optional[str]:
        """
        image_url에서 바이너리 받아서 folder_path/filename 으로 저장
        실패하면 None 반환

        ✅ 개선:
        - Content-Type 로그 출력
        - 실제 Content-Type 기반 확장자 자동 교정(파일명 변경)
        - accept-encoding zstd 제거(디코딩 이슈 방지)
        - httpx Client 재사용
        """
        try:
            if not folder_path:
                return None
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)

            # headers None 방어 + zstd 제거(디코딩 이슈 방지)
            h: Dict[str, str] = {}
            if headers:
                for k, v in headers.items():
                    if v is None:
                        continue
                    h[str(k)] = str(v)

            ae = h.get("accept-encoding") or h.get("Accept-Encoding") or ""
            if "zstd" in ae:
                ae2 = ae.replace("zstd", "")
                ae2 = ae2.replace(",,", ",").strip(" ,")
                if ae2:
                    h["accept-encoding"] = ae2
                else:
                    h.pop("accept-encoding", None)
                    h.pop("Accept-Encoding", None)

            client = self._get_http_client(timeout=timeout)
            r = client.get(image_url, headers=h, timeout=timeout)

            self._log(f"[IMG] url={image_url} status={r.status_code} ctype={r.headers.get('Content-Type')}")

            if r.status_code != 200:
                self._log(f"❌ 이미지 HTTP {r.status_code}: {image_url}")
                return None

            content = r.content
            if not content:
                self._log(f"❌ 이미지 content 비었음: {image_url}")
                return None

            ctype = (r.headers.get("Content-Type") or "").lower()
            if "image/" not in ctype:
                head = content[:200]
                try:
                    head_text = head.decode("utf-8", errors="replace")
                except Exception:
                    head_text = str(head)
                self._log(f"❌ 이미지 아님 Content-Type={ctype}: {image_url} / head={head_text[:120]}")
                return None

            # Content-Type 기반 확장자 교정
            ext_map = {
                "image/png": "png",
                "image/jpeg": "jpg",
                "image/jpg": "jpg",
                "image/webp": "webp",
                "image/avif": "avif",
                "image/gif": "gif",
            }
            mime = ctype.split(";")[0].strip()
            real_ext = ext_map.get(mime)

            save_path = os.path.join(folder_path, filename)

            if real_ext:
                base, old_ext = os.path.splitext(filename)
                old_ext2 = (old_ext or "").lower().lstrip(".")
                if old_ext2 and old_ext2 != real_ext:
                    filename = f"{base}.{real_ext}"
                    save_path = os.path.join(folder_path, filename)
                elif not old_ext2:
                    # === 신규 === 확장자 없는 파일명도 보정
                    filename = f"{filename}.{real_ext}"
                    save_path = os.path.join(folder_path, filename)

            with open(save_path, "wb") as f:
                f.write(content)

            return save_path

        except httpx.RequestError as e:
            self._log(f"❌ 이미지 요청 실패: {image_url} / 오류: {str(e)}")
            return None
        except Exception as e:
            self._log(f"❌ 이미지 저장 실패: {os.path.join(folder_path, filename)} / 오류: {str(e)}")
            return None

    def read_json_array_from_resources(self, filename: str) -> List[Any]:
        """
        resources 폴더 안에서 지정한 JSON 파일을 읽어 배열(list)로 반환
        """
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        resources_dir = os.path.join(base_dir, "resources")
        file_path = os.path.join(resources_dir, filename)

        if not os.path.exists(file_path):
            self._log(f"❌ JSON 파일이 존재하지 않습니다: {file_path}")
            return []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                self._log(f"⚠️ JSON 배열 형식이 아님: {file_path}")
                return []
            self._log(f"📄 JSON 배열 {len(data)}개 읽음: {file_path}")
            return data
        except Exception as e:
            self._log(f"❌ JSON 읽기 실패: {file_path} / 오류: {e}")
            return []

    def safe_name(self, s: Any, max_len: int = 40) -> str:
        s2 = "" if s is None else str(s)
        s2 = s2.strip()
        s2 = re.sub(r'[\\/:*?"<>|]', "_", s2)
        s2 = re.sub(r"\s+", "_", s2)
        if max_len and len(s2) > max_len:
            s2 = s2[:max_len]
        return s2 or "noname"

    def guess_ext(self, url: str) -> str:
        path = urlparse(url).path.lower()
        if path.endswith(".png"):
            return "png"
        if path.endswith(".jpg") or path.endswith(".jpeg"):
            return "jpg"
        if path.endswith(".webp"):
            return "webp"
        if path.endswith(".gif"):
            return "gif"
        return "jpg"