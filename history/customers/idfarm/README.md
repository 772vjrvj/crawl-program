캐리핑거

2026.06.11
사이트 css html 구조 바뀌어서 수정해줌


2026.05.27

가격 : 150000
부가세 : 15000


# 빌드

pyinstaller .\main.py `
--noconfirm `
--clean `
--console `
--windowed `
--name "CrawlProgram" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\idfarm\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_idfarm_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\customers\idfarm\db\schema_detail.sql;resources\customers\idfarm\db" `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl `
--add-data ".\resources\icons\crawling.ico;resources\icons"



--add-data ".\resources\customers\idfarm\db\schema_detail.sql;resources\customers\idfarm\db" `
--hidden-import "src.workers.main.api_idfarm_set_worker" `