# 네이버 중고나라 광고


1. 네이버 계정 순회하면서 13개씩 채팅에 광고 이미지 전송
2. 고객 중복 아이디 제거
3. 이미지 전화번호 그대로 있으면 안돼서 0.1.0으로 수정
4. 작업전에 계정은 본인인증, 보호 조치, 정지 등 해결 후 진행 필요
5. 실행경로에 user.csv가 있고 컬럼은 id pw 
6. 실행경로에 images 안에 joonggonara_ad.png 파일이 있어야함


# 고객
지원마케팅 / partner_id=190834
26.10.13 결제



# 계정

himred / tkdlek5%%
okimsnpartner@naver.com / rhkdzm23!
akn09 / kk7799%%
sku6562 / gkskenftpt12!
audvnarkrn123 / !rhkddn1004
aorehskfen / !rhkddn1004
leegamin2000 / !rhkddn1004



```powershell
pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "CrawlProgram" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\src\workers\main\api_naver_cafe_joonggonara_ad_set_worker\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_naver_cafe_joonggonara_ad_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl `
--add-data ".\resources\customers\naver_cafe_joonggonara_ad\db\schema_detail.sql;resources\customers\naver_cafe_joonggonara_ad\db" `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\icons\crawling.ico;resources\icons"
```