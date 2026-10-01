# cs-interest v07 인수인계 패키지

머지 담당자에게 전달하는 v7 이자·연체 상담 모델 패키지입니다.
이 폴더에는 Git에 올리지 않은 실제 GGUF 모델 파일이 포함되어 있습니다.

## 포함 파일

- `cs-interest.gguf`: LoRA 병합 후 Q4_K_M 양자화한 실제 모델, 약 2.4GB
- `Modelfile`: Ollama 등록 설정
- `VERSION`: 학습 run 버전
- `README.md`: 모델 및 API 사용 설명
- `export.json`: 모델·데이터·평가 메타데이터
- `SHA256SUMS`: GGUF 무결성 확인용 해시

## 무결성 확인

```bash
sha256sum -c SHA256SUMS
```

정상 해시:

```text
d076edc09338420fcd3aae5383d83253020bb1a5314fa076227dd3b03c8cf319  cs-interest.gguf
```

## Ollama 등록

이 폴더 안에서 실행합니다.

```bash
ollama create cs-interest -f Modelfile
ollama list
```

`Modelfile`이 같은 폴더의 `cs-interest.gguf`를 읽으므로 두 파일은 반드시 같은 폴더에 둡니다.

## FastAPI 연결

프로젝트의 `backend` 폴더에서 Ollama와 API를 실행합니다.

```bash
ollama serve
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

API 확인:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"handoff-test","customer_id":"C002","message":"이번 달 이자 얼마예요?"}'
```

앱 코드는 `app/agents/interest/agent.py`의 `MODEL = "cs-interest"`로 Ollama 모델을 호출합니다.

## 모델 정보

- 버전: `v07-20260930-1034-v07-09`
- 베이스: `Qwen/Qwen3-4B-Instruct-2507`
- 학습 데이터: `data/raw/09_interest_finetune` 기반
- 양자화: `Q4_K_M`
- Golden rule: `94.12%`
- 일반 테스트 valid: `99.16%`
- 일반 테스트 슬롯 충족률: `100%`
- 금칙 표현 위반률: `0.84%`

## 주의사항

- 이 폴더의 GGUF는 GitHub에 올리지 않은 대용량 산출물입니다.
- AIHub 원본·전처리 데이터는 포함하지 않았습니다.
- 실제 개인정보를 입력하지 말고 C001~C003 목업 고객으로 확인합니다.
- `C002`는 정상 이자 데이터, `C003`은 연체 데이터, `C001`은 대출 없음 데이터입니다.
