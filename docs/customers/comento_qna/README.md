
■ 고객 : 대기업사원
■ 요청 사이트 : 크몽
■ 크롤링 사이트 : https://comento.kr/job-wiki
■ 내용

직무소개 내요 크롤링
https://comento.kr/job-wiki

yohanflower1@gmail.com / kyh2050!

생산직, 기술직, 기능직, 고졸, 전문대졸

커뮤니티 부문 1. QNA 2. 직무소개

부문 추출 용도입니다!


■ worker 경로 "worker_class": "src.workers.main.api_comento_job_set_worker:ApiComentoJobSetWorker",


■ 개별 빌드
pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "COMENTO_JOB" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\comento_job\version_info.txt" `
--distpath ".\dist" `
--hidden-import "src.workers.main.api_comento_job_set_worker" `
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
--name "COMENTO_JOB" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\comento_job\version_info.txt" `
--distpath ".\dist" `
--hidden-import "src.workers.main.api_comento_job_set_worker" `
--hidden-import "src.workers.main.api_comento_qna_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl