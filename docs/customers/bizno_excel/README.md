한국전기공사협회 업체 리스트 (상호명,주소,대표자성명)약 2만개를 기준으로 bizno.net에서 업체 검색 후 
주소/대표자 비교하여 일치 업체의 팩스번호를 엑셀로 정리하는 자동화 프로그램 제작하거나 만들어 주는 일
참고로 비즈노 사이트는 자주검색하면 ip가 한동안 차단됩니다

비즈노 사이트에서 검색하면 상호명이 대한이엔지 대한e&g 이런식으로 조금 다르게 나올수도잇고 동일한 상호명이 있어서 
주소랑 대표자 성명 으로 비교하여 동일한 업체의 팩스번호를 추출해야 하고 비즈노 사이트에서 제가 자주검색했을때 ip가 한동안 차단됩니다


"worker_class": "src.workers.main.api_bizno_excel_set_worker:ApiBiznoExcelSetWorker",


■ 빌드
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