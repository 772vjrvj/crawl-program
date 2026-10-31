■ 고객
크몽ID : 지원마케팅
크몽ID : 190834
가격 : 220,000(부가세 포함)
날짜 : 2026.10.31
특징 : 


--add-data "원본경로;실행시경로"

개발/로그 확인용이면:
--console `

고객 배포용 GUI면:
--windowed `

pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "CrawlProgram" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\src\workers\main\api_naver_land_real_estate_ad_set_worker\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_naver_land_real_estate_ad_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl `
--add-data ".\resources\customers\naver_land_real_estate_ad\db\schema_detail.sql;resources\customers\naver_land_real_estate_ad\db" `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\icons\crawling.ico;resources\icons"