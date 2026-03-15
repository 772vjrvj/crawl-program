■ 고객 : 대기업사원
■ 요청 사이트 : 크몽

대기업사원
250,000

457deep1 / 1234
457deep2 / 1234


안녕하세요 추가로 크/몽에 서비스중인 것에 이미지+텍스트도 저장가능하게 가능할까요

예) 면접

검색했을때 나오는 전문가들의 서비스 관련 텍스트+이미지

각 저장


pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "KMONG" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\kmong\version_info.txt" `
--distpath ".\dist" `
--hidden-import "src.workers.main.api_kmong_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl