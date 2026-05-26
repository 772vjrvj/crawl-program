노란베프2758

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
--version-file ".\docs\customers\kakao_talkdeal_rank\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_kakao_talkdeal_rank_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\customers\kakao_talkdeal_rank\db\schema_detail.sql;resources\customers\kakao_talkdeal_rank\db" `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl `
--add-data ".\resources\icons\crawling.ico;resources\icons"