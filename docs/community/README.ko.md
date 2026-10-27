# 레딧 소개글 초안과 첨부 이미지

게시용 영어 초안: [reddit-introduction.en.md](reddit-introduction.en.md)

프로젝트 소개, 기능 요약, 게임에서 열어 두어야 하는 시작 화면, 연결 방법, 현재 언어 지원 범위, 피드백 안내를 담았습니다. 현재 공개 문서와 개발 상태를 기준으로 작성했으며, 게시하거나 릴리즈를 변경하지는 않았습니다.

## 첨부 이미지와 영문 캡션

레딧 편집기에서 이미지를 직접 업로드하고 해당 기능 설명 아래에 배치하세요. 로컬 Markdown의 상대 이미지 경로는 레딧에 붙여 넣는 것만으로 업로드되지 않습니다. 갤러리로 게시한다면 아래 순서로 첨부하고 본문에 번호를 유지하면 됩니다.

| 순서 | 이미지 | 붙여 넣을 영문 캡션 |
| --- | --- | --- |
| 1 | [비밀상점](images/01-secret-shop.png) | Secret Shop: leave the item list open, then start Secret Shop in EAB. Korean screenshot; English game screens are also supported. |
| 2 | [펭귄 구매 목록](images/02-penguins.png) | Penguins: open Forest of Souls → Growth Altar and leave this list visible. EAB handles the Penguin Nest purchase popup. |
| 3 | [탐사 시작](images/03-exploration-start.png) | Dimensional Exploration: choose your difficulty and leave Start Exploration visible. English exploration is supported in v1.7.0 and later. |
| 4 | [탐사 진행 중 지도](images/04-exploration-map.png) | Already exploring? You can also start from the node map. English exploration is supported in v1.7.0 and later. |

이미지는 기존 인게임 원본을 그대로 복사했습니다. 앱 UI나 가상의 화면을 제작한 것이 아닙니다. 표시된 재화 보유량과 상품 구성은 촬영 당시의 예시입니다.

## 초안의 핵심 내용

- EAB는 비밀상점 갱신·책갈피/신비 구매, 스티그마 펭귄 구매, 차원 탐사를 돕는 Windows용 오픈소스 도구입니다.
- STOVE PC 클라이언트 또는 ADB로 연결한 앱플레이어를 사용하며, 배포 ZIP은 Python 별도 설치가 필요 없습니다.
- 비밀상점은 상품 목록 화면, 펭귄은 성장의 제단 구매 목록 화면에서 실행합니다. 탐사는 난이도를 정한 시작 화면 또는 진행 중인 노드 지도에서 실행합니다.
- 자연 갱신 모드도 상품 구매 재화는 소모하며, 펭귄 사이클 수는 펭귄 마릿수가 아닌 구매 반복 횟수입니다.
- 탐사 이벤트는 선택지 내용을 이해해 최적 선택을 하는 기능이 아니므로 불리한 결과가 나올 수 있습니다.
- 계정 안전을 보장하는 표현이나 전 기능 영어 지원 완료라는 표현은 사용하지 않았습니다.

## 게시 직전 반영할 항목

영어 초안과 캡션은 v1.7.0의 영어 탐사 지원을 기준으로 갱신했습니다. 게시 시 다운로드 링크와 릴리즈 버전이 일치하는지 확인하세요.

게시할 서브레딧이 지정되지 않아 특정 게시판 규칙에 맞는지 확인하지 않았습니다. 게시 위치를 정한 뒤 자동화 도구 소개와 자기 프로젝트 홍보 관련 규칙에 맞춰 게시 형식·플레어를 정하세요.

이 파일은 작성자용 안내입니다. 레딧에는 영어 초안 본문과 필요한 이미지만 사용하면 됩니다.
