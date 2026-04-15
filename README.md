# NovelGenerator (Desktop-first Branching Novel Tool)

이 저장소는 데스크톱 중심의 분기형 장편 소설 창작툴 MVP 골격입니다.

## 포함된 구현 범위

- 도메인 모델: 프로젝트, 막, 분기노드, 장면카드, 상태 메모리, 결말 조건
- 생성 루프: 선택지 제시 → 선택 반영 → 장면 생성 → 요약/메모리 업데이트
- 정합성 계층: 사실 충돌 검사, 세계관 규칙 위반 검사, 분기 변경 영향 분석
- MVP 명세 문서: 기능 범위, 지표, 단계별 확장 전략

## 빠른 실행

### 1) 의존성 설치

```bash
python -m pip install -r requirements.txt
```

### 2) LM Studio 서버 실행

- LM Studio에서 모델을 로드한 뒤, **Local Server**(OpenAI compatible)를 켜세요.
- 기본 주소는 보통 `http://127.0.0.1:1234/v1` 입니다.
- 모델명은 LM Studio 서버 화면에 표시되는 값을 사용하세요.

### 3) 데스크톱 앱 실행

```bash
python src/app_desktop.py
```

### (선택) CLI 데모 실행

```bash
python src/main.py
```

## 폴더 구조

- `src/core/models.py`: 핵심 도메인 데이터 구조
- `src/core/generation_loop.py`: 대화형 분기 생성 엔진
- `src/core/consistency.py`: 모순 탐지 및 재생성 영향 분석
- `src/core/llm_adapter.py`: LLM 어댑터 인터페이스/모의 구현
- `docs/*.md`: 설계 명세(도메인, 루프, 정합성, MVP)

