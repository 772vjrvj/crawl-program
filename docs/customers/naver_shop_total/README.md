

유일하게 service 로더가 있음

크롬 로그인 2개 되어 있으면 안됨



--console `


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