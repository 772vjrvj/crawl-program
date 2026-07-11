MD값을 못찾아서
js를 분석해서 찾음

코딩
https://www.band.us/band/91333382/post
91333382

772vjrvj
Ksh#8818510

https://www.band.us/band/4877094/post
4877094

https://www.band.us/band/61514880/post
61514880

mybiz153
payplay00153!!



# 빌드
pyinstaller .\main.py `
--noconfirm `
--clean `
--console `
--windowed `
--name "CrawlProgram" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\naver_band_member\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_naver_band_member_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl