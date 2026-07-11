
■ 고객 : 슬기로운별9504
■ 요청 사이트 : 크몽
■ 크롤링 사이트 : https://www.keca.or.kr/ecic/ad/ad0101.do?menuCd=6047
■ 내용







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

