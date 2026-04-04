■ 상세 지역 목록 데이터
    korea_eup_myeon_dong_list.py 
    korea_eup_myeon_dong.json: 위도 경도 지역번호가 있는 상세 데이터
    korea_eup_myeon_dong_simple.json : 지명만 있는 데이터


■ 진행순서
    
    1. 지역 목록 으로 URL 만들기
        화면에서는 지역 keyword들이 배열로 올 것이고 그거에 맞게 상세지역 데이터를 찾는다.
        korea_eup_myeon_dong.json를 사용한다.
        그걸로 URL을 만든다.
    
       
    2. 목록조회 : 메인
        https://fin.land.naver.com/front-api/v1/article/boundedArticles
        URL 로딩후 첫목록은 "매물 100개" 버튼을 눌러서 후킹을 해서 가져온다. (Fiddler로 network 잡아냄)
        후킹시 Post요청 데이터는 저장해놓는다. 응답에 articlePagingRequest 가 핵심이다. 
    
    3. 목록조회 : 첫 목록 다시 조회
        클릭해서 요청은 정렬방식이 없기 대문에 캐시한 post 요청 데이터에 정렬부분을 추가해서 1페이지 부터 마지막 페이지까지 요청한다.

    4. 상세조회
        https://fin.land.naver.com/front-api/v1/article/basicInfo









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