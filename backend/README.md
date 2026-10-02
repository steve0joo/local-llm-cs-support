# backend

FastAPI 게이트웨이 + 라우터 + 전문 에이전트 3개 + mock API, 학습 스크립트.

| 영역 | 담당 | 브랜치 | 문서 |
|------|------|--------|------|
| 라우터 + 게이트웨이 | 팀원C | `feat-router` | `docs/router/` |
| 잔액조회 에이전트 | 나 | `feat-agent-balance` | `docs/agent-balance/` |
| 대출문의 에이전트 | 팀원A | `feat-agent-loan` | `docs/agent-loan/` |
| 이자/연체 에이전트 | 팀원B | `feat-agent-interest` | `docs/agent-interest/` |

잔액조회 에이전트의 Mac 데이터 전처리·Hugging Face 베이스 모델 학습·Ollama 평가는 [`training/balance/MAC_TRAINING.md`](training/balance/MAC_TRAINING.md)를 따른다. 다른 영역의 Windows 학습 의존성과 분리되어 있다.

## 구동 절차

모델이 아직 없어도 서버는 뜬다. 라우터는 Ollama 호출이 실패하면 키워드 규칙으로 분류하고(`docs/router/ADR.md` RT-002), 에이전트의 모델 호출이 실패하면 게이트웨이가 "지금은 답변을 드릴 수 없습니다. 상담원 연결을 도와드릴까요?"로 답한다.

```bash
# 1. 런타임 venv (최초 1회)
uv venv backend/.venv --python 3.11
uv pip install --python backend/.venv/bin/python -r backend/requirements.txt

# 2. 모델 (구현 후)
ollama serve                                                   
ollama create cs-router   -f backend/models/router/Modelfile
ollama create cs-balance  -f backend/models/balance/Modelfile
ollama create cs-loan     -f backend/models/loan/Modelfile
ollama create cs-interest -f backend/models/interest/Modelfile

# 3. API 서버 → http://localhost:8000/docs 에서 /api/chat을 바로 눌러 볼 수 있다
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

# 4. 챗봇 UI → http://localhost:3000
cd frontend && npm run dev
```

Ollama 주소가 localhost:11434가 아니면 `OLLAMA_URL=http://<host>:11434`를 앞에 붙여 서버를 띄운다.

### 동작 확인

```bash
curl -s -X POST localhost:8000/api/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"s1","customer_id":"C001","message":"제 계좌 110-1234-5678 잔액 알려줘"}'
# → {"type":"answer","agent":"balance", ...}

grep -c "110-1234-5678" backend/logs/model_inputs.jsonl     # 0 이어야 한다 — 모델 입력에 원본이 없다 (인수 기준 5)
```

`backend/logs/model_inputs.jsonl`은 모든 모델 호출의 입력이 한 줄씩 쌓이는 파일이다. 인수 전에 지우고 시나리오를 돌린 뒤 PM이 연다.

## 에이전트 담당이 할 일

1. `git merge main` 뒤 분할 파일을 한 번 만든다. gitignore 대상이라 기기마다 생성한다.
   ```bash
   cd backend
   python -m training.common.split      # data/processed/split.json
   ```
2. `app/agents/<영역>/__init__.py`의 스텁을 자기 구현으로 덮어쓴다.  
게이트웨이가 import하는 이름은 `agent`와 `mock_router` 둘뿐이므로 이 두 이름은 유지(계약 3).

3. 모델을 만들면 `backend/models/<영역>/Modelfile`을 커밋하고(.gguf는 커밋 금지) `ollama create cs-<영역>`으로 등록한다. 서버 코드는 모델 이름만 알기 때문에 고칠 곳이 없다.
4. 학습 전처리는 `app.masking.mask()`와 `data/processed/split.json`을 쓴다.  
추론 입력과 학습 입력의 마스킹 토큰이 같아야 한다(계약 4, ADR-008).

## 테스트

```bash
cd backend && .venv/bin/python -m pytest              # 전체
cd backend && .venv/bin/python -m pytest tests/<폴더>  # gateway · masking · llm · router · balance · loan · interest
```
