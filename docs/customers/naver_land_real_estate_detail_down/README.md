단정한사계759
25만
2026.03.25


pyinstaller .\main.py `
--noconfirm `
--clean `
--console `
--windowed `
--name "naver_land_real_estate_detail" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\naver_land_real_estate_detail\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_naver_land_real_estate_detail_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl