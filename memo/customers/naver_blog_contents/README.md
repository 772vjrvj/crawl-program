대기업사원
120,000원


기존에 이미까지 첨부되서 용량이 너무 많아서 힘듬
A열에 제목 / B열에 내용

3. 블로그 URL 넣고 조회
2. 카테고리 목록 나옴
3. 카테고리 시작 종료 page정해서 블로그 제목 내용 크롤링



https://m.blog.naver.com/factoryman_90
https://blog.naver.com/52kckkck



naverblog1/1234
navetblog2/1234



# 빌드
pyinstaller .\main.py `
--noconfirm `
--clean `
--console `
--windowed `
--name "CrawlProgram" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\naver_blog_contents\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_naver_blog_contents_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl