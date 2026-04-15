# 대화형 분기 생성 루프

`StoryEngine.run_turn()` 기준 처리 단계:

1. 현재 분기 기준으로 `BranchOptionGenerator`가 3개 선택지를 생성
2. 사용자가 선택한 옵션 인덱스를 입력
3. 선택된 옵션이 신규 분기면 `BranchNode` 생성
4. `PlotManager`가 현재 장면 수에 따라 막(`ActType`) 제안
5. `SceneCard` 생성 후 `SceneGenerator`로 본문/요약 작성
6. 프로젝트 상태 업데이트
   - `project.scenes` 저장
   - 분기별 장면 연결
   - 막별 장면 연결
   - 최근 장면 윈도우 갱신
   - 막 요약 갱신
   - 전역 사실집(`global_bible`) 기록

## 인터페이스 확장 포인트

- `SceneGenerator` 프로토콜 구현체를 교체해 OpenAI/로컬 모델 연결 가능
- `PlotManager`를 규칙+학습 혼합 방식으로 교체 가능
- 선택지 생성 시 결말 점수 기반 필터 추가 가능

