# Run only after closing the application. Code updates do not touch user data.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$branch = git branch --show-current
if ($branch -ne 'reboot-2026-10') { throw 'reboot-2026-10 체크아웃에서 실행하세요.' }
git pull --ff-only origin reboot-2026-10
if ($LASTEXITCODE -ne 0) { throw '로컬 변경 또는 원격 오류로 업데이트를 중단했습니다. 데이터는 유지됩니다.' }
& '.venv\Scripts\python.exe' -m pip install -e '.[easyocr]'
if ($LASTEXITCODE -ne 0) { throw '의존성 설치가 완료되지 않았습니다.' }
Write-Host '업데이트 완료. run_worship_guide.bat로 실행하세요. 사용자 DB는 실행 시 백업 후 migration됩니다.'
