■ 고객 : 갓승찬
■ 날짜 : 2026.03.30
■ 요청 사이트 : 크몽
■ 가격 : 180,000
■ 코드 : NAVER_SHOP_TOTAL
■ 크롤링 사이트 : https://msearch.shopping.naver.com
■ 내용

크몽 26.03.31 네이버 샵 크롤링 AI Whisper 추가됨 메크로

# 빌드후
/resources/customers/naver_shop_total
/bin/ffmpeg.exe

이거를 를 빌드후
_internal/resources/bin/ffmpeg.exe
넣어줘야함




유일하게 service 로더가 있음

크롬 로그인 2개 되어 있으면 안됨


pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "네이버 스토어" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\naver_shop_total\version_info.txt" `
--distpath ".\dist" `
--add-data "E:\git\crawl-program\venv\Lib\site-packages\whisper\assets;whisper\assets" `
--add-data ".\resources\customers\naver_shop_total\bin;resources\customers\naver_shop_total\bin" `
--hidden-import "src.workers.main.api_naver_shop_total_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--hidden-import "pyaudiowpatch" `
--hidden-import "whisper" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl