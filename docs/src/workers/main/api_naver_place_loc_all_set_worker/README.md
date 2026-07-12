키워드와 지역 선택해서 네이버 플레이스 정보를 엑셀로 추출해주는 프로그램


pyinstaller .\main.py `
--noconfirm `
--clean `
--console `
--windowed `
--name "네이버 플레이스" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\naver_place_url_all\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_naver_place_loc_all_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl `
--add-data ".\resources\customers\naver_place_loc_all\naver_loc_all_real.json;resources\customers\naver_place_loc_all" `
--add-data ".\resources\customers\naver_place_loc_all\db\schema_detail.sql;resources\customers\naver_place_loc_all\db" `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\icons\crawling.ico;resources\icons"