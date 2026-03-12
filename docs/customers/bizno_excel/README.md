
■ 고객 : 슬기로운별9504
■ 요청 사이트 : 크몽
■ 크롤링 사이트 : https://www.keca.or.kr/ecic/ad/ad0101.do?menuCd=6047
■ 내용
1. 전기공사 종합정보시스템 에서 [상호, 대표자, 소재지] 3개 항목을 크롤링한다.
2. 3개 항목을 엑셀로 뽑는다.
3. 그 엑셀을 BIZNO 프로그램에 넣고 상세정보를 크롤링해서 엑셀에 저장한다.

    ** BIZNO는 보안이 심해서 에러나 가면 외부 API를 호출한다.
    
    4개 사이트
    
    # 메인서버 1개
    # http://vjrvj.cafe24.com
    
    # 추가 서버 3게
    # http://404notfoundshop.shop
    # server3-api-key-2026
    # SERVER3
    
    # https://www.rapportcompany.co.kr
    # server4-api-key-2026
    # SERVER4
    
    # https://doublestock.co.kr
    # server2-api-key-2026
    # SERVER2
    
    메인서버에서 목록과 api-key를 내려주고 그거를 바탕으로 크롤링을 한다.
    
    # 추후 로컬 서버, proxy 서버를 추가할 예정이다.


■ 사용법

    ■ KECA
    1. BIZNO.exe 실행
    2. bizno1 / 1234 , bizno2 /1234 로 로그인
    3. 사이트에 KECA에 들어가서 시작
    4. 통합자료관 > 업체 현황에서   등록업체 지역선택: 후 검색 하거나 또는
      전체 검색이면 아무것도 안하고 > 확인 알림창에서 ok 클릭
    5. output_keca_ecic 에 엑셀 저장됨

    ■ BIZNO
    6. BIZNO 에 들어가서 "엑셀세팅" 버튼 클릭. KECA에서 받은 엑셀 드래그 앤 드랍
    7. "시작" 버튼 클릭
    8. output_bizno 에 저장됨

    특이사항 있으면 말씀해주세요.

    작업하실때는 한 1000~2000개 정도 나눠서 작업하시기를 추천드립니다.


■ worker 경로 "worker_class": "src.workers.main.api_keca_ecic_request_set_worker:ApiKecaEcicExcelSetWorker",


■ 개별 빌드
pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "BIZNO" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\bizno_excel\version_info.txt" `
--distpath ".\dist" `
--hidden-import "src.workers.main.api_bizno_excel_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl


■ 종합 빌드
pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "BIZNO" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\bizno_excel\version_info.txt" `
--distpath ".\dist" `
--hidden-import "src.workers.main.api_keca_ecic_request_set_worker" `
--hidden-import "src.workers.main.api_bizno_excel_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl