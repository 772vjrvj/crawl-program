$ErrorActionPreference = "Stop"

# ============================================================
# 기본 경로
# ============================================================
$ProjectDir = $PSScriptRoot
$LauncherName = "GB7Launcher"

$LauncherSource = Join-Path $ProjectDir "launcher\launcher_main.py"
$VersionFile = Join-Path $ProjectDir "docs\launcher\version_info.txt"
$IconFile = Join-Path $ProjectDir "resources\icons\crawling.ico"

$DistDir = Join-Path $ProjectDir "dist"
$BuildDir = Join-Path $ProjectDir "build"

$LauncherDistDir = Join-Path $DistDir $LauncherName
$LauncherDataDir = Join-Path $LauncherDistDir "data"
$LauncherVersionsDir = Join-Path $LauncherDistDir "versions"

$SourceDataDir = Join-Path $ProjectDir "launcher\data"
$CurrentJsonPath = Join-Path $SourceDataDir "current.json"


# ============================================================
# current.json에서 현재 프로그램과 버전 읽기
# ============================================================
if (-not (Test-Path $CurrentJsonPath)) {
    throw "current.json을 찾을 수 없습니다: $CurrentJsonPath"
}

$currentConfig = Get-Content $CurrentJsonPath -Raw -Encoding UTF8 |
    ConvertFrom-Json

$ProgramId = $currentConfig.program_id
$CurrentVersion = $currentConfig.version
$CurrentVersionDirName = "v" + ($CurrentVersion -replace "\.", "_")

Write-Host ""
Write-Host "프로그램 ID : $ProgramId"
Write-Host "현재 버전   : $CurrentVersion"
Write-Host "버전 폴더   : $CurrentVersionDirName"
Write-Host ""


# ============================================================
# 이전 런처 빌드 결과 제거
# ============================================================
if (Test-Path $LauncherDistDir) {
    Remove-Item $LauncherDistDir -Recurse -Force
}


# ============================================================
# 런처 빌드
#
# --onefile 없음
# 폴더 방식(onedir)으로 빌드
# ============================================================
Set-Location $ProjectDir

python -m PyInstaller `
    $LauncherSource `
    --noconfirm `
    --clean `
    --windowed `
    --name $LauncherName `
    --icon $IconFile `
    --version-file $VersionFile `
    --distpath $DistDir `
    --workpath $BuildDir `
    --paths $ProjectDir `
    --exclude-module tkinter `
    --exclude-module _tkinter `
    --exclude-module tk `
    --exclude-module Tcl `
    --exclude-module tcl `
    --add-data "$ProjectDir\launcher\img;img"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 런처 빌드에 실패했습니다."
}


# ============================================================
# EXE 옆에 data, versions 폴더 자동 생성
# ============================================================
New-Item `
    -ItemType Directory `
    -Force `
    -Path $LauncherDataDir |
    Out-Null

New-Item `
    -ItemType Directory `
    -Force `
    -Path $LauncherVersionsDir |
    Out-Null


# ============================================================
# 런처 설정 파일 자동 복사
# ============================================================
Copy-Item `
    (Join-Path $SourceDataDir "app.json") `
    (Join-Path $LauncherDataDir "app.json") `
    -Force

Copy-Item `
    (Join-Path $SourceDataDir "current.json") `
    (Join-Path $LauncherDataDir "current.json") `
    -Force


# ============================================================
# 공지 숨김 기록은 빈 JSON으로 생성
# UTF-8 BOM 없이 저장
# ============================================================
$NoticeAckPath = Join-Path $LauncherDataDir "notice_ack.json"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

[System.IO.File]::WriteAllText(
    $NoticeAckPath,
    "{}",
    $Utf8NoBom
)


# ============================================================
# 현재 프로그램 빌드 결과 자동 복사
#
# 기본 프로그램 빌드 위치:
# dist\NAVER_BAND_MEMBER
#
# current.json의 program_id와 빌드 폴더명이 다르면
# 아래 $ProgramDistDir만 실제 폴더명으로 수정한다.
# ============================================================
$ProgramDistDir = Join-Path $DistDir $ProgramId

if (Test-Path $ProgramDistDir) {

    $CurrentVersionTargetDir = Join-Path `
        $LauncherVersionsDir `
        $CurrentVersionDirName

    New-Item `
        -ItemType Directory `
        -Force `
        -Path $CurrentVersionTargetDir |
        Out-Null

    Copy-Item `
        "$ProgramDistDir\*" `
        $CurrentVersionTargetDir `
        -Recurse `
        -Force

    Write-Host "현재 프로그램 복사 완료"
    Write-Host "$ProgramDistDir"
    Write-Host "-> $CurrentVersionTargetDir"
}
else {
    Write-Host ""
    Write-Warning "현재 프로그램 빌드 폴더를 찾지 못했습니다."
    Write-Warning "$ProgramDistDir"
    Write-Warning "versions 폴더만 생성하고 런처 빌드를 계속합니다."
}


# ============================================================
# 완료
# ============================================================
Write-Host ""
Write-Host "============================================================"
Write-Host "런처 빌드 완료"
Write-Host "============================================================"
Write-Host "결과 폴더:"
Write-Host $LauncherDistDir
Write-Host ""
Write-Host "실행 파일:"
Write-Host (Join-Path $LauncherDistDir "$LauncherName.exe")
Write-Host ""