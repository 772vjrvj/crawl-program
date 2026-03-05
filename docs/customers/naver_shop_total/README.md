
--windowed `
--console `


pyinstaller .\main.py `
--noconfirm `
--clean `
--console `
--name "네이버 스토어" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\naver_shop_total\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
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