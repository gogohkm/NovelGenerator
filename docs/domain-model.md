# 도메인 모델 명세

## 핵심 엔티티

- `StoryProject`: 프로젝트 루트. 장르, 톤, 시점, 세계관 규칙, 막/분기/장면/결말/메모리 보유
- `BranchNode`: 사용자 선택으로 분기되는 노드. 부모-자식 관계와 합류 타깃 지원
- `SceneCard`: 생성 단위. 목표/갈등/결과/떡밥/요약/본문 포함
- `StoryStateMemory`: 계층형 메모리(전역 사실집, 막 요약, 최근 장면 윈도우, 캐릭터 상태)
- `EndingCondition`: 다중 결말 조건(필수 사실, 금지 사실, 긴장도 하한, 테마 힌트)

## 4막 구조

- `ActType.RISE`: 기
- `ActType.DEVELOPMENT`: 승
- `ActType.TURN`: 전
- `ActType.CONCLUSION`: 결

막은 장면 개수 기반으로 자동 추천되며, 추후 규칙 기반 엔진/모델 판단으로 대체 가능.

## 상태/사실 안정성

- `FactStability.IMMUTABLE`: 절대 변경 금지 (예: 세계 법칙)
- `FactStability.SEMI_MUTABLE`: 리라이트 시 조정 가능 (예: 사건 해석)
- `FactStability.MUTABLE`: 상황 전개에 따라 변경 가능 (예: 감정 상태)

