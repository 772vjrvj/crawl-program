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
$AppJsonPath = Join-Path $SourceDataDir "app.json"


# ============================================================
# current.json에서 현재 프로그램과 버전 읽기
# ============================================================
if (-not (Test-Path $CurrentJsonPath)) {
    throw "current.json not found: $CurrentJsonPath"
}

$currentConfig = Get-Content `
    $CurrentJsonPath `
    -Raw `
    -Encoding UTF8 |
    ConvertFrom-Json

$ProgramId = $currentConfig.program_id
$CurrentVersion = $currentConfig.version

if ([string]::IsNullOrWhiteSpace($ProgramId)) {
    throw "program_id is empty in current.json"
}

if ([string]::IsNullOrWhiteSpace($CurrentVersion)) {
    throw "version is empty in current.json"
}

$CurrentVersionDirName = "v" + ($CurrentVersion -replace "\.", "_")

Write-Host ""
Write-Host "============================================================"
Write-Host "Launcher Build Information"
Write-Host "============================================================"
Write-Host "Program ID      : $ProgramId"
Write-Host "Current Version : $CurrentVersion"
Write-Host "Version Folder  : $CurrentVersionDirName"
Write-Host "Project Folder  : $ProjectDir"
Write-Host ""


# ============================================================
# 필수 파일 확인
# ============================================================
if (-not (Test-Path $LauncherSource)) {
    throw "Launcher source not found: $LauncherSource"
}

if (-not (Test-Path $VersionFile)) {
    throw "Version file not found: $VersionFile"
}

if (-not (Test-Path $IconFile)) {
    throw "Icon file not found: $IconFile"
}

if (-not (Test-Path $AppJsonPath)) {
    throw "app.json not found: $AppJsonPath"
}


# ============================================================
# 이전 런처 빌드 결과 제거
# ============================================================
if (Test-Path $LauncherDistDir) {
    Write-Host "Removing previous launcher build..."
    Write-Host $LauncherDistDir

    Remove-Item `
        $LauncherDistDir `
        -Recurse `
        -Force

    Write-Host "Previous launcher build removed."
    Write-Host ""
}


# ============================================================
# 런처 빌드
#
# --onefile 없음
# 폴더 방식(onedir)으로 빌드
# ============================================================
Set-Location $ProjectDir

Write-Host "============================================================"
Write-Host "Starting PyInstaller build"
Write-Host "============================================================"
Write-Host ""

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
    throw "PyInstaller build failed. Exit code: $LASTEXITCODE"
}

Write-Host ""
Write-Host "PyInstaller build completed."
Write-Host ""


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

Write-Host "Data folder created:"
Write-Host $LauncherDataDir
Write-Host ""

Write-Host "Versions folder created:"
Write-Host $LauncherVersionsDir
Write-Host ""


# ============================================================
# 런처 설정 파일 자동 복사
# ============================================================
Copy-Item `
    $AppJsonPath `
    (Join-Path $LauncherDataDir "app.json") `
    -Force

Copy-Item `
    $CurrentJsonPath `
    (Join-Path $LauncherDataDir "current.json") `
    -Force

Write-Host "Configuration files copied:"
Write-Host "app.json"
Write-Host "current.json"
Write-Host ""


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

Write-Host "Notice acknowledgment file created:"
Write-Host $NoticeAckPath
Write-Host ""


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

    Write-Host "============================================================"
    Write-Host "Current program copied"
    Write-Host "============================================================"
    Write-Host "Source:"
    Write-Host $ProgramDistDir
    Write-Host ""
    Write-Host "Target:"
    Write-Host $CurrentVersionTargetDir
    Write-Host ""
}
else {
    Write-Host ""
    Write-Warning "Program build folder not found:"
    Write-Warning $ProgramDistDir
    Write-Warning "The launcher build will continue without program files."
    Write-Host ""
}


# ============================================================
# 완료
# ============================================================
$LauncherExePath = Join-Path `
    $LauncherDistDir `
    "$LauncherName.exe"

Write-Host ""
Write-Host "============================================================"
Write-Host "Launcher build completed"
Write-Host "============================================================"
Write-Host "Output folder:"
Write-Host $LauncherDistDir
Write-Host ""
Write-Host "Executable:"
Write-Host $LauncherExePath
Write-Host ""