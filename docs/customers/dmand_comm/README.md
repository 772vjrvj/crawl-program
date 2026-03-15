
■ 고객 : 대기업사원
■ 요청 사이트 : 크몽
■ 크롤링 사이트 : https://comento.kr/job-wiki
■ 내용

# 리스트

전체 목록
https://gocho-back.com/v1/qnas?size=20&page=3&order=recent&q=&category=

자유
https://gocho-back.com/v1/qnas?size=20&page=2&order=recent&q=&category=FREE

취업·자격증
https://gocho-back.com/v1/qnas?size=20&page=3&order=recent&q=&category=EMPLOYMENT


상세보기
https://gocho-back.com/v1/qnas/18186

댓글
https://gocho-back.com/v1/qnas/18186/comments?size=6&qnaId=18186


■ worker 경로 "worker_class": "src.workers.main.api_comento_job_set_worker:ApiComentoJobSetWorker",


■ 개별 빌드
pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "DMAND_COMM" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\dmand_comm\version_info.txt" `
--distpath ".\dist" `
--hidden-import "src.workers.main.api_dmand_comm_set_worker" `
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
--name "DMAND_COMM" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\dmand_comm\version_info.txt" `
--distpath ".\dist" `
--hidden-import "src.workers.main.api_comento_job_set_worker" `
--hidden-import "src.workers.main.api_comento_qna_set_worker" `
--hidden-import "src.workers.main.api_dmand_comm_set_worker" `
--hidden-import "src.workers.main.api_naver_blog_contents_set_worker" `
--hidden-import "src.workers.main.api_457deep_set_worker" `
--hidden-import "src.workers.main.api_kmong_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl