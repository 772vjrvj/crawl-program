하얀토끼0102

2026-06-08

22만원

역지오코딩

1. 도로명주소 지번이 동일한거는 딱 1번만
2. 오늘 광고가 올라 왔더래도 과거에 광고를 진행중 : 2일 이상에 걸쳐 동일하게 나온거는 아에 저장X 이미 저장했다면 제거 ban 처리
3. 날짜는 매물 등록일 기준 : 시작 종료 사이에 있는 것만 나머지는 제거
4. 순서 : 매물명. 번지. 도로명. 매매가. 등록일자. 대지면적. 연면적. 건축면적...

_save_list_items_multi
이 함수가 핵심 로직




pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "naver_land_real_estate_detail_ad" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\naver_land_real_estate_detail_ad\version_info.txt" `
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
--add-data ".\resources\customers\naver_land_real_estate_detail_ad\filter_data.json;resources\customers\naver_land_real_estate_detail_ad" `
--add-data ".\resources\customers\naver_land_real_estate_detail_ad\region\korea_eup_myeon_dong.json;resources\customers\naver_land_real_estate_detail_ad\region" `
--add-data ".\resources\customers\naver_land_real_estate_detail_ad\js\list_hook.js;resources\customers\naver_land_real_estate_detail_ad\js" `
--add-data ".\resources\customers\naver_land_real_estate_detail_ad\js\browser_fetch_json.js;resources\customers\naver_land_real_estate_detail_ad\js" `
--add-data ".\resources\customers\naver_land_real_estate_detail_ad\js\click_sort_button.js;resources\customers\naver_land_real_estate_detail_ad\js" `
--add-data ".\resources\customers\naver_land_real_estate_detail_ad\js\click_article_button.js;resources\customers\naver_land_real_estate_detail_ad\js" `
--add-data ".\resources\customers\naver_place_loc_all\naver_loc_all_real.json;resources\customers\naver_place_loc_all" `
--add-data ".\resources\customers\naver_land_real_estate_detail_ad\db\schema_detail.sql;resources\customers\naver_land_real_estate_detail_ad\db" `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\icons\crawling.ico;resources\icons"