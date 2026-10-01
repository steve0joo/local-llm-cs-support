# cs-interest v07

성능 평가에서 v6보다 우세한 v7 파인튜닝 모델을 Ollama/API용으로 내보낸 결과입니다.

- 버전: `v07-20260930-1034-v07-09`
- 형식: `GGUF Q4_K_M`
- 원본 베이스: `Qwen/Qwen3-4B-Instruct-2507`
- 모델 등록명: `cs-interest`
- GGUF 파일: `cs-interest.gguf` (약 2.4GB, Git에서 제외)
- 무결성 정보: `export.json`

## 등록

```bash
cd backend
ollama create cs-interest -f models/interest/Modelfile
ollama list
```

`models/interest/VERSION`은 현재 등록 대상으로 선택한 학습 run을 가리킵니다.

## API 실행

Ollama를 먼저 실행한 뒤 FastAPI를 시작합니다.

```bash
ollama serve
cd backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

API 확인:

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"s1","customer_id":"C001","message":"이번 달 이자 납부일 알려줘"}'
```

API는 `app/agents/interest/agent.py`의 `MODEL = "cs-interest"`를 통해 Ollama 모델을 호출합니다. Ollama가 꺼져 있거나 모델 호출이 실패하면 에이전트의 검증된 fallback 문장을 사용합니다.

## GitHub에 올리는 파일

GGUF는 약 2.4GB라 저장소에 커밋하지 않습니다. 다음 파일만 커밋하면 다른 환경에서 모델을 재생성·검증할 수 있습니다.

- `models/interest/Modelfile`
- `models/interest/VERSION`
- `models/interest/export.json`
- `models/interest/README.md`
- `training/interest/export.md`
- v7 어댑터의 run 정보와 평가 결과는 로컬 산출물 정책에 따라 별도 보관합니다.

v7 어댑터 병합부터 GGUF 변환까지의 상세 절차는 `training/interest/export.md`에 있습니다.
