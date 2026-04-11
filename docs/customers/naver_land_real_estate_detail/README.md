■ 고객
    크몽ID : 단정한사계759
    가격 : 250,000
    날짜 : 2026.03.25
    특징 : 동일매물정렬, 해당 날짜에 있는 것만

■ 고객
    크몽ID : 느릿느릿크리스마스
    가격 : 100,000
    날짜 : 2026.04.11
    특징 : "파크골프" 전국 크롤링
    플레이스ID, 업종 분류(태그), 대표 키워드, 영업시간 및 휴무일, 대표자 성함, SNS 링크, 리뷰 수 및 평점, 개업일(또는 첫 리뷰 등록일), 시설 사진 URL 정보 등은 가능하면 필요해요


■ 상세 지역 목록 데이터
    korea_eup_myeon_dong_list.py 
    korea_eup_myeon_dong.json: 위도 경도 지역번호가 있는 상세 데이터
    korea_eup_myeon_dong_simple.json : 지명만 있는 데이터


■ 진행순서
    
    1. 지역 목록 으로 URL 만들기
        화면에서는 지역 keyword들이 배열로 올 것이고 그거에 맞게 상세지역 데이터를 찾는다.
        korea_eup_myeon_dong.json를 사용한다.
        그걸로 URL을 만든다.

    2. 화면에서 filter정보를 받아서 queryString을 만들어서
        https://fin.land.naver.com/map? 으로 화면을 열면 해당 filter가 적용된 화면이 나온다. 
        (zoom, filter, 등 모든 정보가 setting된 화면이 나온다.)

    3. 클릭 및 후킹은 js파일로 별도로 뺐다.

    4. 목록조회 : 메인
        https://fin.land.naver.com/front-api/v1/article/boundedArticles
        URL 로딩후 첫목록은 "매물 100개" 버튼을 눌러서 후킹을 해서 가져온다. (Fiddler로 network 잡아냄)
        후킹시 Post요청 데이터는 저장해놓는다. 응답에 articlePagingRequest 가 핵심이다.

    4. 상세조회
        https://fin.land.naver.com/front-api/v1/article/basicInfo

    5. 주소 key 를 가져오기위한 api 
        https://fin.land.naver.com/front-api/v1/article/key

    6. 주소를 가져오기 위한 api 주소key 필요
        https://fin.land.naver.com/front-api/v1/complex



■ 빌드후
    resources/customers/naver_land_real_estate_detail/filter_data.json
    resources/customers/naver_land_real_estate_detail/region/korea_eup_myeon_dong.json
    resources/customers/naver_land_real_estate_detail/js/list_hook.js
    resources/customers/naver_land_real_estate_detail/js/browser_fetch_json.js
    resources/customers/naver_land_real_estate_detail/js/click_sort_button.js
    resources/customers/naver_land_real_estate_detail/js/click_article_button.js
    resources/customers/naver_place_loc_all/naver_loc_all_real.json

    자료가 있어야함


■ 빌드

--add-data "원본경로;실행시경로"

pyinstaller .\main.py `
--noconfirm `
--clean `
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
--exclude-module tcl `
--add-data ".\resources\customers\naver_land_real_estate_detail\filter_data.json;resources\customers\naver_land_real_estate_detail" `
--add-data ".\resources\customers\naver_land_real_estate_detail\region\korea_eup_myeon_dong.json;resources\customers\naver_land_real_estate_detail\region" `
--add-data ".\resources\customers\naver_land_real_estate_detail\js\list_hook.js;resources\customers\naver_land_real_estate_detail\js" `
--add-data ".\resources\customers\naver_land_real_estate_detail\js\browser_fetch_json.js;resources\customers\naver_land_real_estate_detail\js" `
--add-data ".\resources\customers\naver_land_real_estate_detail\js\click_sort_button.js;resources\customers\naver_land_real_estate_detail\js" `
--add-data ".\resources\customers\naver_land_real_estate_detail\js\click_article_button.js;resources\customers\naver_land_real_estate_detail\js" `
--add-data ".\resources\customers\naver_place_loc_all\naver_loc_all_real.json;resources\customers\naver_place_loc_all" `
--add-data ".\resources\icons\crawling.ico;resources\icons\crawling.ico"