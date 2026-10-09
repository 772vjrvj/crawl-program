■ 고객
    크몽ID : 만인의오리너구리8071
    가격 : 220,000
    날짜 : 2026.10.05
    특징 : 네이버랑 같이 사용 하길 원하심.


■ 진행순서
    




■ 빌드

--add-data "원본경로;실행시경로"


pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "CrawlProgram" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\src\workers\main\api_disco_re_detail_set_worker\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_disco_re_detail_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl `
--add-data ".\resources\customers\disco_re_detail\js\browser_get_json.js;resources\customers\disco_re_detail\js" `
--add-data ".\resources\customers\disco_re_detail\js\disco_geocode.js;resources\customers\disco_re_detail\js" `
--add-data ".\resources\customers\disco_re_detail\js\list_hook.js;resources\customers\disco_re_detail\js" `
--add-data ".\resources\customers\disco_re_detail\js\browser_fetch_json.js;resources\customers\disco_re_detail\js" `
--add-data ".\resources\customers\disco_re_detail\region\korea_eup_myeon_dong.json;resources\customers\disco_re_detail\region" `
--add-data ".\resources\customers\disco_re_detail\db\schema_detail.sql;resources\customers\disco_re_detail\db" `
--add-data ".\resources\customers\disco_re_detail\db\schema_stat.sql;resources\customers\disco_re_detail\db" `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\icons\crawling.ico;resources\icons"