$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 이상이 필요합니다.' }
}
& '.venv\Scripts\python.exe' -m pip install -e '.[easyocr]'
if ($LASTEXITCODE -ne 0) { throw '설치가 완료되지 않았습니다.' }
& '.venv\Scripts\python.exe' -m worship_guide
