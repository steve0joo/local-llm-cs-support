# backend

FastAPI 게이트웨이 + 라우터 + 전문 에이전트 3개 + mock API, 학습 스크립트.

| 영역 | 담당 | 브랜치 | 문서 |
|------|------|--------|------|
| 라우터 + 게이트웨이 | 팀원C | `feat-router` | `docs/router/` |
| 잔액조회 에이전트 | 나 | `feat-agent-balance` | `docs/agent-balance/` |
| 대출문의 에이전트 | 팀원A | `feat-agent-loan` | `docs/agent-loan/` |
| 이자/연체 에이전트 | 팀원B | `feat-agent-interest` | `docs/agent-interest/` |

잔액조회 에이전트의 Mac 데이터 전처리·Hugging Face 베이스 모델 학습·Ollama 평가는 [`training/balance/MAC_TRAINING.md`](training/balance/MAC_TRAINING.md)를 따른다. 다른 영역의 Windows 학습 의존성과 분리되어 있다.
