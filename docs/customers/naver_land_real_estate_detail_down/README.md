■ 고객
크몽ID : 단정한사계759
가격 : 250,000
날짜 : 2026.03.25
특징 : 동일매물정렬, 날짜,


크몽ID : 특별한연예인1588
가격 : 20,000
날짜 : 2026.03.25
특징 : 


--add-data "원본경로;실행시경로"

pyinstaller .\main.py `
--noconfirm `
--clean `
--console `
--windowed `
--name "naver_land_real_estate_detail_down" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\naver_land_real_estate_detail_down\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_naver_land_real_estate_detail_down_set_worker" `
--hidden-import "src.workers.main.api_naver_land_real_estate_detail_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl `
--add-data ".\resources\customers\naver_land_real_estate_detail\filter_data.json;resources\customers\naver_land_real_estate_detail" `
--add-data ".\resources\customers\naver_land_real_estate_detail\region\korea_eup_myeon_dong.json;resources\customers\naver_land_real_estate_detail\region" `
--add-data ".\resources\customers\naver_land_real_estate_detail\js\list_hook.js;resources\customers\naver_land_real_estate_detail\js" `
--add-data ".\resources\customers\naver_land_real_estate_detail\js\browser_fetch_json.js;resources\customers\naver_land_real_estate_detail\js" `
--add-data ".\resources\customers\naver_land_real_estate_detail\js\click_sort_button.js;resources\customers\naver_land_real_estate_detail\js" `
--add-data ".\resources\customers\naver_land_real_estate_detail\js\click_article_button.js;resources\customers\naver_land_real_estate_detail\js" `
--add-data ".\resources\customers\naver_place_loc_all\naver_loc_all_real.json;resources\customers\naver_place_loc_all"
--add-data ".\resources\icons\crawling.ico;resources\icons\crawling.ico"