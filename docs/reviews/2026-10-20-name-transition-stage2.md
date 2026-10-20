# EAB 배포 이름 전환: 실행 파일과 ZIP

## 최종 범위

실행 파일은 `EAB.exe`, 업데이트 프로그램은 `EAB-Updater.exe`, 배포 ZIP은
`EAB-v<버전>.zip`으로 변경한다. 사용자 요청에 따라 오래된 업데이트 프로그램용
별도 ZIP은 제공하지 않는다. 자동 업데이트의 지원 기준은 호환성 준비 버전인
v1.5.15 이상이며, v1.5.14 이하 사용자는 EAB ZIP을 수동 설치한다.

GitHub 저장소는 `pelierze/SecretShopBot-E7`로 유지한다. 사용자 설정·프리셋·로그
저장 경로도 유지한다. 기존 이름·주소를 읽는 준비 코드까지 제거하는 작업은 아니다.

## 기존 바로가기

배포 루트에는 `EAB.exe`, `EAB-Updater.exe`, `SecretShopBot-E7.exe`, `_internal`이
들어간다. 기존 이름의 EXE는 전체 앱의 복사본이 아니라 `legacy_launcher.py`로 만든
연결 프로그램이다. 같은 폴더의 EAB.exe를 절대 경로로 실행하고 인자를 그대로
전달하며, 일반 실행에서는 연결 프로그램이 바로 종료된다. Python 런타임은
`_internal`을 공유하고 PyInstaller 환경은 새 프로세스로 초기화한다.

v1.5.15~v1.5.19의 업데이트 프로그램은 두 ZIP 형식을 지원하지만 기존 실행 파일을
먼저 실행한다. 이때 `--update-ready` 인자가 연결 프로그램으로 전달된다. 연결
프로그램이 즉시 종료되면 당시 시작 확인 코드가 실패하므로, 이 경우에는 EAB가
종료될 때까지 대기한다. Windows Job Object로 자신과 자식 프로세스를 묶어,
업데이트 프로그램이 복구를 위해 연결 프로그램을 종료하면 EAB도 함께 종료한다.
시작 확인 파일은 실제 EAB가 생성하며 연결 프로그램이 대신 생성하지 않는다.
동작의 근거는 [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)다.

연결 프로그램이 실행하는 EAB.exe가 없거나 실행이 실패하면 오류를 표시한다.
임의 경로나 다른 실행 파일을 대신 찾지 않는다. 최신 업데이트 프로그램은
EAB.exe를 우선하므로 연결 프로그램을 거치지 않는다.

## 빌드와 배포

`EAB.spec`에서 앱·업데이트 프로그램·연결 프로그램을 빌드한다.
`build_release.ps1`은 `build_support.release_packages`로 배포 파일을 검증한 뒤
EAB ZIP과 같은 이름의 SHA256 파일만 생성한다. 기존 릴리즈 파일을 덮어쓰지
않으며 ZIP 내부 최상위 폴더는 ZIP 파일 이름과 일치한다.

이번 소스의 버전은 v1.5.19로 유지하며 `release/name-transition-launcher-preview`에
로컬 검증용으로 빌드한다. 이전의 전체 실행 파일 복사 방식으로 만든
`release/name-transition-preview`는 폐기된 방식의 검증 산출물로 배포하면 안 된다.
실제 릴리즈 시 새 버전 번호를 정하고 ZIP과 체크섬 두 파일을 게시해야 한다.

## 검증 범위

관련 테스트는 단일 ZIP·체크섬·루트 파일 제한·인자 전달·일반 실행 즉시 반환·
자동 업데이트 실행 대기·실제 Windows Job Object의 자식 종료·설정 보존·
시작 실패 시 앱과 연결 프로그램 복구를 다룬다. 실제 배포 GUI의 수동 실행과
게임 연결은 별도 확인 사항이다.

관련 테스트 87개가 통과했다. 실제 PyInstaller 빌드에서 EAB ZIP과 체크섬
두 파일만 생성했다. `build/verify_frozen_launcher.py`에서 빌드된 연결 프로그램과
무해한 대체 앱을 사용해 일반 실행·인자 전달·업데이트 시작 확인·복구 시 자식
종료를 확인했다. Git 태그 v1.5.15·v1.5.19의 당시 릴리즈 선택 코드도 새 EAB
ZIP만 있는 자산 목록에서 올바른 파일을 선택했다.
