# 통합

pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "BAROTEM" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\barotem\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_barotem_set_worker" `
--hidden-import "src.workers.main.api_idfarm_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\customers\barotem\db\schema_detail.sql;resources\customers\barotem\db" `
--add-data ".\resources\customers\idfarm\db\schema_detail.sql;resources\customers\idfarm\db" `
--add-data ".\resources\icons\crawling.ico;resources\icons"




# 빌드

pyinstaller .\main.py `
--noconfirm `
--clean `
--windowed `
--name "BAROTEM" `
--icon ".\resources\icons\crawling.ico" `
--version-file ".\docs\customers\barotem\version_info.txt" `
--distpath ".\dist" `
--workpath ".\build" `
--hidden-import "src.workers.main.api_barotem_set_worker" `
--hidden-import "pandas" `
--hidden-import "openpyxl" `
--exclude-module tkinter `
--exclude-module _tkinter `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\customers\barotem\db\schema_detail.sql;resources\customers\barotem\db" `
--exclude-module tk `
--exclude-module Tcl `
--exclude-module tcl `
--add-data ".\resources\icons\crawling.ico;resources\icons"

