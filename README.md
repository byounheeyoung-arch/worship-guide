# Worship Guide

하나의 Desktop 앱에서 악보 PDF/이미지 → OCR 후보 → 사람 검수 → Song / Arrangement / Score Variant → 검색 → 악보집 / 세트리스트 → PDF를 연결합니다.

현재 개발 기준은 `reboot-2026-10`과 Draft PR #2입니다. 원본 v2.0.2를 복구한 뒤 통합한 프로젝트이며, 이전 버전별 폴더나 ZIP을 새로 만들지 않습니다. 먼저 [작업 인수인계](docs/WORK_HANDOFF.md)를 읽으세요.

## 실행

Python 3.11 이상과 Tk가 필요합니다. 처음 한 번 체크아웃과 설치를 하고 이후 같은 체크아웃을 업데이트합니다.

```bash
git clone --branch reboot-2026-10 https://github.com/byounheeyoung-arch/worship-guide.git
cd worship-guide
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[easyocr,dev]"
wg-app
```

Windows에서는 설치 후 `run_worship_guide.bat`를 클릭합니다. `run_editor.bat`, `run_worship_guide_v2.bat`, 기존 `wg-editor` / `wg-studio` 명령도 같은 앱으로 연결됩니다. `scripts/setup.ps1`은 초기 환경 설치용, `scripts/update.ps1`은 앱 종료 후 같은 브랜치를 업데이트하는 용도입니다. 업데이트 과정에서 사용자 DB를 삭제하지 않습니다.

EasyOCR는 첫 사용 시 한국어/영어 모델을 다운로드하고 이후 캐시를 재사용합니다. 기본은 CPU입니다. Linux에서 CPU PyTorch를 사용할 때는 PyTorch 공식 CPU 배포판을 먼저 설치하면 불필요한 CUDA 패키지 설치를 피할 수 있습니다. 선택적으로 Tesseract 5 + `kor`, `eng` 언어 데이터도 지원합니다. `WG_TESSERACT`로 실행 파일을, `WG_TESSDATA_DIR`로 언어 데이터 폴더를 지정할 수 있습니다.

## 데이터 보존

- Windows: `%LOCALAPPDATA%\WorshipGuide`
- macOS: `~/Library/Application Support/WorshipGuide`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/WorshipGuide`
- 사용자 지정: `WG_DATA_DIR` 또는 `wg-app --db <기존 DB 경로>`

DB, 원본 복사본, 페이지 캐시, 출력 파일은 코드 폴더와 분리합니다. 동일 PDF의 다른 파일명은 SHA-256으로 같은 원본을 식별하고, 서로 다른 PDF의 같은 페이지 번호는 구분합니다. 원본을 다른 곳으로 이동해도 관리되는 복사본에서 PDF를 출력합니다.

처음 실행할 때 기존 체크아웃의 `data/wgdb.sqlite3`가 하나면 복사하여 가져옵니다. 원래 DB와 폴더는 그대로 둡니다. 기존 DB가 여러 개면 임의로 하나를 선택하지 않고 명시적인 `--db` 선택을 요구합니다. 두 복구 DB 형식 및 혼합 형식을 지원하며, migration 전에 SQLite backup으로 일관된 `.bak`를 만듭니다. 실패 시 migration 전체를 rollback합니다. 지원 버전보다 새로운 DB는 변경하지 않습니다.

## 사용 흐름

1. PDF 또는 악보 이미지를 선택하고 처음에는 1~20페이지를 분석합니다.
2. 검수센터에서 원본 악보, OCR 원문, 추천 제목, Key 후보를 비교합니다. 제목 / Key / 편곡을 사람이 승인합니다. 미확인 Key는 빈칸으로 유지합니다.
3. 같은 곡의 다른 조성은 같은 Song 아래 별도 Score Variant로 저장합니다. 동명곡은 기존 곡을 명시적으로 선택하거나 새 곡으로 등록할 수 있습니다.
4. `곡 · 검색 · 악보집`에서 메타데이터를 편집하고, 주제·분위기·Key·성경·예배 흐름·난이도·사용자 태그·작사/작곡을 동시에 검색합니다. 필드 간 AND, 같은 필드의 쉼표 값은 OR입니다. 최대 난이도 검색에서는 미확인 난이도를 제외합니다.
5. Collection에 실제 Score Variant를 선택하고 순서·섹션·메모를 저장합니다. 저장한 조건으로 추가 후보를 다시 조회할 수 있으며, 새 후보는 선택 목록을 자동 변경하지 않습니다.
6. `simple` PDF는 선택한 원본 악보 페이지만 병합합니다. `guide`는 한글 표지·링크 목차·섹션·곡 메타데이터와 원본 악보를 포함합니다. 세트리스트는 날짜·예배·성경·선택 악보·전환 메모와 PDF 팩을 지원합니다.
7. 실제로 검수한 연속 20페이지에 복수 조성, OCR 오류 수정, 미확인 Key가 포함되면 `검수한 20페이지 E2E 검증`을 실행합니다. 별도 DB 복사본에서 재시작·수정 기억·후보 재분석·악보집 선택·PDF 렌더 순서·한글 목차를 검증합니다. 모두 통과한 원본에만 20페이지 초과 분석을 허용합니다.

분석은 페이지마다 저장됩니다. 중단 / 재시작 후 완료된 페이지를 재사용합니다. 미검수 상태에서 엔진을 바꾸면 이전 OCR 관측을 보존하면서 새 후보를 만들고, 이미 승인한 악보는 재분석으로 덮어쓰지 않습니다. 입력칸의 좌우 방향키는 글자 커서를 이동하고 Ctrl+좌우는 페이지를 이동합니다.

## 기준 자료

Google Drive의 Worship Guide 폴더에 있는 `worship-guide-v2.0.2`, `pdf24_merged.pdf`, `WGDB Master 구글시트`가 기준 자료입니다. 기존 원본과 시트는 수정하지 않습니다. 마스터 스냅샷 JSON은 9개 탭의 원문을 로컬 DB에 보존하며, 기존 WGID / 사용자 메타데이터를 덮어쓰지 않습니다. 시트에 기재된 사용 가능 Key를 근거로 실제 악보 파일을 만들어내지 않습니다. 원본 악보와 개인 메타데이터는 공개 저장소에 커밋하지 않습니다.

## 진단 / 검증

```bash
python -m pytest -q
wg --db /path/to/wgdb.sqlite3 doctor
wg --db /path/to/wgdb.sqlite3 import-master /path/to/wgdb_master.json
wg --db /path/to/wgdb.sqlite3 import /path/to/scores.pdf --start 1 --end 20
wg --db /path/to/wgdb.sqlite3 verify-20 1
wg --db /path/to/wgdb.sqlite3 export 1 /path/to/book.pdf --mode guide
```

`verify-20`의 인자는 해당 DB의 원본 ID입니다. 위 명령을 버그마다 반복할 필요는 없습니다. 일상 사용은 Desktop 버튼으로 가능합니다.

자동 테스트는 migration / rollback / 재시작 / 사람 수정 / 원본 식별 / 중단·재개 / 다중조건 검색 / Collection / PDF 순서 / 한글 / 실제 Tk 위젯을 다룹니다. 합성 OCR 어댑터를 사용한 재현 가능한 테스트와 실제 552페이지 원본의 20페이지 OCR 검증은 구분하여 기록합니다. Tk 테스트는 화면 또는 Xvfb가 필요합니다.

현재 검증 결과와 남은 문제는 [진행 보고서](docs/PROGRESS_2026-10-06.md)에 기록합니다. Windows 배포 패키지와 이후 웹/모바일 단계는 이 Desktop 기반 위에서 이어갑니다.
