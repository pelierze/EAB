# 기여 안내

오류 제보, 기능 제안, 문서 개선과 코드 수정을 환영합니다. 사용 방법은 [README](README.md), 저장소 공통 규칙은 [AGENTS.md](AGENTS.md)를 먼저 확인해 주세요.

## 오류 제보와 기능 제안

[Issues](https://github.com/pelierze/EAB/issues)에서 같은 문제가 등록되어 있는지 확인해 주세요. 오류는 `오류 신고` 양식으로 작성하고 다음 내용을 포함해 주세요.

- 앱 버전과 실행 환경(STOVE PC 클라이언트 또는 앱플레이어·ADB)
- 사용한 기능, 재현 순서, 기대한 동작과 실제 동작
- 오류 발생 시 생성된 `logs/report`의 해당 보고서 폴더 전체 ZIP

보고서가 없다면 그 이유와 확보한 로그·화면을 첨부해 주세요. 첨부 전에 화면과 로그에 계정 정보 등 개인정보가 포함되어 있는지 확인해 주세요. 기능 제안은 해결하려는 불편과 원하는 사용 흐름을 설명하면 도움이 됩니다.

## 개발 환경 준비

Windows와 Python 3.12를 기준으로 개발 환경을 준비합니다. 아래 명령은 저장소 루트에서 PowerShell로 실행하세요. 외부 기여자는 저장소를 Fork한 뒤 자신의 Fork를 복제하고 작업 브랜치를 만들어 주세요.

```powershell
git clone https://github.com/<내-GitHub-ID>/SecretShopBot-E7.git
cd SecretShopBot-E7
git switch -c fix/short-description
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

ADB 연결이나 배포 빌드에 필요한 도구는 다음 명령으로 설치할 수 있습니다. STOVE 소스 실행에는 이 단계가 필요하지 않습니다.

```powershell
.\.venv\Scripts\python.exe setup_adb.py
```

앱 실행:

```powershell
.\.venv\Scripts\python.exe main.py
```

실행 시 관리자 권한 요청이 표시될 수 있습니다. 게임 연결과 해상도 설정은 [README](README.md#connect-the-game)를 따르세요.

## 코드와 이미지 수정

- `src/`: 앱 UI, 자동화 기능과 업데이트 처리
- `src/backend/`: 실행 환경별 연결·입력 처리
- `src/chaos/`: 자동 탐사 로직과 화면 배치 설정
- `images/`: 화면 인식용 이미지와 재현용 캡처
- `tests/`: `unittest` 기반 테스트
- `build_support/`, `EAB.spec`, `build_release.ps1`: 배포 파일 구성과 빌드
- `docs/`: 설계·검증 기록과 릴리즈 문서

변경은 한 가지 목적에 집중하고, 기존 코드의 형식과 명명 방식을 따라 주세요. 인식이나 입력 동작을 바꾸는 경우 재현 화면과 발생 조건을 설명하고, 가능한 경우 해당 오류를 재현하는 테스트를 함께 추가해 주세요. 새 이미지를 추가할 때는 용도와 촬영 조건을 설명하고, 배포 자산 수집 코드인 `build_support/release_assets.py`에서 필요한 파일이 포함되는지 확인해 주세요. 외부 코드·모델·이미지를 추가할 때는 출처와 라이선스도 기록해 주세요.

로그, 개인 설정, 가상 환경, 빌드 산출물은 커밋하지 않습니다. 기존 설정 저장 경로, 구버전 업데이트 호환성 또는 배포 파일 이름을 바꾸는 경우 사용자에게 미치는 영향과 이전 버전에서의 전환 방법을 설명해 주세요.

## 검증

수정한 기능과 관련된 테스트를 먼저 실행하세요. 예를 들어 업데이트 및 배포 변경은 다음과 같이 확인할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_app_updater.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_release*.py' -v
```

전체 테스트 실행 명령:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
git diff --check
```

일부 테스트에는 저장된 화면이나 Windows 환경이 필요합니다. 실패하면 실행 명령, 오류 내용과 누락된 파일·환경 조건을 PR에 적어 주세요. 실제 게임에서 확인한 동작과 저장 화면·모의 객체로 확인한 동작을 구분하고, 실행하지 않은 검증은 명시해 주세요.

배포 파일을 변경했다면 [DEPLOY.md](DEPLOY.md)에 따라 빌드와 패키지 구성을 확인하세요. PR을 제출하기 위해 GitHub Release를 게시할 필요는 없습니다.

## Pull Request 작성

기본 브랜치인 `main`을 대상으로 PR을 보내 주세요. 제목은 변경 목적이 드러나도록 작성하고, 본문에는 다음 내용을 포함해 주세요.

- 해결하는 문제와 관련 이슈(있는 경우)
- 변경 후 동작과 사용자에게 미치는 영향
- 실행한 검증 명령과 결과, 추가 확인이 필요한 부분
- UI·화면 인식 변경의 전후 화면 또는 재현 자료(해당하는 경우)

서로 다른 목적의 변경은 별도 커밋이나 PR로 나누어 주세요. 사용자용 릴리즈 노트는 체감 변화와 사용 방법 위주로 작성합니다. 테스트 결과·내부 구현·체크섬 안내는 릴리즈 본문 대신 PR이나 개발 문서에 기록합니다.

## 라이선스

제출하는 코드는 프로젝트의 [GPLv3 라이선스](LICENSE)에 따라 배포할 수 있어야 합니다. 제3자 자료에는 해당 자료의 라이선스와 권리 조건이 적용됩니다.
