$customerName = "naver_cafe_joonggonara_ad"

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
--add-data ".\resources\customers\$customerName\db\schema_detail.sql;resources\customers\$customerName\db" `
--add-data ".\resources\customers\common\db\schema_hist.sql;resources\customers\common\db" `
--add-data ".\resources\icons\crawling.ico;resources\icons"

if ($LASTEXITCODE -eq 0) {
    New-Item -ItemType Directory -Force `
        ".\dist\CrawlProgram\runtime\customers\common" | Out-Null

    New-Item -ItemType Directory -Force `
        ".\dist\CrawlProgram\runtime\customers\$customerName" | Out-Null

    Copy-Item ".\runtime\customers\common\*" `
        ".\dist\CrawlProgram\runtime\customers\common" `
        -Recurse -Force

    Copy-Item ".\runtime\customers\$customerName\*" `
        ".\dist\CrawlProgram\runtime\customers\$customerName" `
        -Recurse -Force

    Copy-Item ".\runtime\app.json" `
        ".\dist\CrawlProgram\runtime\app.json" `
        -Force

    Write-Host "Build and runtime copy completed." -ForegroundColor Green
}
else {
    Write-Host "Build failed. Runtime copy skipped." -ForegroundColor Red
}