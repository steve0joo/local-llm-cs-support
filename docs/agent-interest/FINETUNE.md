# QLoRA 파인튜닝: cs-interest 작업 방식과 계획

> 이자/연체 에이전트 모델(`cs-interest`)을 어떻게 학습·평가·배포하는지, 지금 어디까지 왔고 다음에 무엇을 하는지 한곳에 정리한 문서다.
> 세부 기준은 아래 문서에 있다: 데이터 형식·답변 기준 `TRAINING_DATA.md`, 데이터 구성·검수 `TRAINING_DATA_PLAN.md`, 평가 `EVALUATION.md`, 결과 `REPORT_v03.md`.

## 1. 무엇을 학습시키나

- **학습시키는 것:** 이자·연체 상담 말투와 안내 범위. 구체적으로는 슬롯(`{{interest_due}}` 등)으로 금액을 말하기, 이자 정보 줄에 있는 사실만 말하기, 모르는 것은 상담원에게 확인하도록 안내하기다.
- **학습시키지 않는 것:** 실제 금리·규정·상품명 같은 사실. 금액과 조회값은 코드가 mock API에서 가져와 슬롯으로 넘기고, 모델은 문장만 만든다(INT-001, INT-002).
- **안전장치:** 모델 답은 항상 출력 검증(`validate.is_valid`)을 거친다. 검증에 떨어지면 조회 사실만 담은 기본 문장으로 바뀐다. 학습 정답도 같은 검증을 통과해야 한다(INT-004).

## 2. 환경

| 항목 | 값 |
|---|---|
| 베이스 모델 | `unsloth/Qwen3-4B-Instruct-2507-unsloth-bnb-4bit` (4bit 체크포인트 = QLoRA 베이스) |
| 학습 장비 | RTX 4060 Laptop 8GB, WSL2 |
| 라이브러리 | Transformers + PEFT + TRL `SFTTrainer` (Unsloth 라이브러리는 쓰지 않음) |
| 가상환경 | `backend/training/interest/.venv` (학습 전용, 서비스 `.venv`와 분리) |
| 채팅 템플릿 | Qwen 공식 템플릿(`training/interest/chat_template.jinja`) |
| 실험 기록 | wandb (개인 개발용, 숫자만 기록. requirements에는 넣지 않음) |
| 변환·서빙 | llama.cpp로 GGUF 변환 → Ollama `cs-interest` (`training/interest/export.md`) |

- 공식 템플릿을 쓰는 이유: Unsloth 체크포인트의 템플릿은 학습할 때만 빈 `<think>` 블록을 넣는다(unslothai/unsloth#3383). 이 템플릿으로 학습한 v01은 답에 `<tool_call>` 같은 쓰레기 토큰을 냈다.

## 3. 작업 흐름

```
① 데이터 만들기 ─→ ② 학습 ─→ ③ 평가 ─→ ④ 약점 수집·수동 모범 답 ─→ ①로 돌아감
                                  │
                                  └─ 채택 → ⑤ GGUF 변환·Ollama 등록 → 서비스 연동
```

### ① 데이터 만들기 (`training/interest/`)

| 출처 | 만드는 도구 | 설명 |
|---|---|---|
| AI Hub 71926 이자/연체 QA | `prepare.py` | 원본 1,104건 중 금액·금리 수치·서류·개인정보 요구·약속·지어낸 채널 등 규칙에 걸리는 답을 모두 뺀다. 금액은 슬롯으로 바꾼다 |
| 합성 샘플 | `synth.py` | 사람이 검수한 템플릿에 가상 조회값을 넣어 400건. 외부 사실 없이 조회값과 안내 문구만 쓴다 |
| 수동 모범 답 | `manual_data.py`, `manual/` | 모델을 시험해서 틀린 답을 사람이 고친 것. 대출 종류만 바꿔 3배로 늘린다 |

- 모든 샘플은 서비스와 같은 입력 형식(`prompt.build_messages`)을 쓴다. 입력은 시스템 프롬프트, 질문, 이자 정보 줄, 사용할 수 있는 슬롯 줄 순서다.
- 합성·수동 샘플은 train에만 넣는다. val과 test는 AI Hub만 쓴다.
- 결과 폴더: `data/raw/NN_interest_finetune/` (gitignore). 폴더마다 `_manifest.json`에 구성과 만든 명령을 남기고, 폴더 하나만 학습에 쓴다.

### ② 학습 (`train.py`)

| 설정 | 값 | 이유 |
|---|---|---|
| LoRA | r 16 · alpha 32 · dropout 0.05, 모든 linear 층 | 기본 권장값 |
| 학습률·에폭 | 1e-4 · 2 epoch, cosine, warmup 5% | v01·v02(2e-4·3 epoch)는 과적합 경향이 있어 낮춤 |
| 배치 | 2 × 누적 8 = 유효 16 | 8GB VRAM 한도 |
| 최대 길이 | 1024 토큰 | 현재 데이터 최대 786토큰 |
| 손실 | 마지막 assistant 턴만(`completion_only_loss`) | 질문·조회 정보는 따라 쓰지 않게 |
| 종료 토큰 | `<|im_end|>` | 답 끝을 템플릿의 턴 종료와 맞춤 |
| 체크포인트 | 에폭마다 평가, eval_loss가 가장 낮은 것을 남김 | |

- **버전 관리:** 학습할 때마다 `training/interest/outputs/runs/vNN-<날짜시각>-<tag>/`를 새로 만들고 덮어쓰지 않는다. 폴더에는 데이터 해시, git 커밋, 설정, loss 요약을 남긴다. 전체 목록은 `runs/index.jsonl`에 있다.
- **학습 전 확인:** `--dry-run`으로 템플릿 적용 결과를 본다. 답 앞에 `<think>`가 없고, 답이 `<|im_end|>`로 끝나야 한다.

### ③ 평가 (`evaluate.py`, `probe.py`, `ask.py`)

| 평가 | 내용 | 기준 |
|---|---|---|
| 학습 안정성 | train/eval loss, grad_norm | eval loss가 오르지 않고 NaN이 없어야 함 |
| Golden Set 42문항 | 데모·평가 고객(C002~C007) 고정 질문, 학습에 없는 질문 | 규칙 준수율 = 검증 통과·금지 표현 없음·질문에 맞는 내용·상담 톤 **모두** 충족 |
| AI Hub test | 학습에 안 쓴 AI Hub 분할 | 기존 상담 능력 유지(회귀) |
| probe40 | 40문항 자동 채점, wandb에 숫자만 기록 | 버전 간 추세 |
| ask30 · weak30 · debit10 | 사람이 한 문항씩 읽고 판정하는 시트 | 자동 채점이 놓치는 결과 보장·규정 단정·지어낸 절차 찾기 |

- 베이스 모델과 같은 질문으로 비교한다(`--compare`). 결과는 `outputs/eval/`에 남긴다.
- **자동 채점만 믿지 않는다:** v03은 probe40 자동 채점이 100%였다. 그런데 사람이 읽어 보니 "입금하면 연체가 해소됩니다" 같은 결과 보장과 규정 단정이 나왔다. 사람 판정에서 나온 유형은 출력 검증(`validate.phrase_problems`)과 채점 기준에 패턴으로 추가한다.

### ④ 약점 수집 → 수동 모범 답

1. 새 질문 세트로 모델 답을 받는다(`ask.py --set …`).
2. 사람이 문제 답과 괜찮은 답을 나눈다(`manual/*_fix.md`, `*_ok.md`). 문제 답은 모범 답으로 고친다.
3. `manual_data.py`가 JSON(`manual/qNN.json`)으로 바꾼다. 검증을 하나라도 통과하지 못하면 저장하지 않는다.
4. 다음 데이터 폴더를 만들어 다시 학습한다.

LLM으로 데이터를 고쳐 쓰는 방식은 쓰지 않는다. 틀린 사실이 섞일 위험이 있어서, 모범 답은 사람이 쓰고 확인한다.

### ⑤ 변환·배포

어댑터를 16bit 베이스(`Qwen/Qwen3-4B-Instruct-2507`)에 병합한 뒤 llama.cpp로 GGUF를 만든다. 그다음 `ollama create cs-interest -f backend/models/interest/Modelfile`로 등록한다. Modelfile의 SYSTEM은 학습 때 쓴 시스템 프롬프트와 같은 문자열이어야 하고, `test_modelfile.py`가 이를 확인한다.

## 4. 지금까지 결과

| 버전 | 데이터 | 설정 | 결과 |
|---|---|---|---|
| v01 | AI Hub 218건 | Unsloth 템플릿, 2e-4·3ep | `<tool_call>` 쓰레기 토큰 발생. 템플릿 버그 |
| v02 | AI Hub 218건 | 공식 템플릿, 2e-4·3ep | 쓰레기 토큰 없어짐. 하지만 슬롯을 무시하고 금리를 지어냄(규칙 준수 21%) |
| **v03** | 04 폴더: AI Hub 110 + 합성 400 | 공식 템플릿, 1e-4·2ep, 13분 | Golden 규칙 준수 **64% → 86%**, 금지 표현 0%, 상담 톤 100%. 사람 판정 약 90%(probe40) |

v03에 남은 약점은 다섯 가지다: 결과 보장("해소됩니다"), 규정 단정("금리에 영향 없음"), 지어낸 절차·채널(앱, 고객센터, 계좌번호 입력), 행동 약속, 자동이체 연체 원인 단정.

## 5. 다음 계획

### v04 (데이터 준비 완료, 학습 전)

데이터는 `data/raw/06_interest_finetune`이다. train 664건(합성 400, 수동 207, AI Hub 57), val 8건, test 10건.

v03 대비 바뀐 점:
- 수동 모범 답 69문항 207건을 넣었다: v03 테스트 30, 약점 보강 30, 자동이체 10.
- 자동이체 계좌 잔액 비교를 넣었다. 코드가 잔액과 연체 금액(연체가 없으면 납부 예정 이자)을 비교해 결과 문장만 이자 정보 줄에 넣고, 잔액은 `{{debit_balance}}` 슬롯으로 넘긴다.
- 합성 템플릿을 21개로 늘렸다: 자동이체 연체 이유, 잔액 문의, 연체 영향 규정 질문.
- 출력 검증을 강화했다: 결과 보장·규정 단정·채널·절차·약속·반복. 이 때문에 AI Hub 샘플이 더 걸러졌다.

학습 전에 확인할 것:
- [ ] 새 합성 템플릿 3개와 q61~q70 모범 답 사람 검수
- [ ] C007 다음 납부일(2026-09-30)을 시연 날짜에 맞추고 06 폴더 재생성
- [ ] 학습 가상환경을 공통 버전(Python 3.11, trl 0.24, transformers 5.5, peft 0.19.1)에 맞출지 결정

실행과 평가:
```bash
cd backend
PY=training/interest/.venv/bin/python; D06=data/raw/06_interest_finetune
$PY -m training.interest.train --data-dir $D06 --dry-run
$PY -m training.interest.train --data-dir $D06 --tag 06
R=$(ls -d training/interest/outputs/runs/v*-06 | tail -1)
$PY -m training.interest.evaluate --name tuned-06 --data-dir $D06 --adapter $R/adapter
$PY -m training.interest.probe --name probe-v04 --adapter $R/adapter --wandb
$PY -m training.interest.ask --name v04 --set weak30 --adapter $R/adapter   # ask30·debit10도 같은 방식
```

채택 기준은 네 가지다:
- Golden 규칙 준수율이 v03(86%) 이상이다.
- 금지 표현이 0%다.
- weak30·debit10 사람 판정에서 문제 답이 v03보다 줄었다.
- eval loss가 오르지 않았다.

val과 test가 줄었으므로(17→8, 24→10) AI Hub test 수치는 v03과 바로 비교하지 않는다.

### v04 이후

| 순서 | 할 일 | 비고 |
|---|---|---|
| 1 | 채택한 모델을 GGUF로 변환하고 Ollama에 등록, 응답 시간 측정 | 목표 응답 시간은 공통 ADR 기준 |
| 2 | 블라인드 사람 평가(`evaluate.py --blind`) | 베이스·v03·v04를 섞어 판정 |
| 3 | 팀원C에게 TL(학습용) 데이터와 공통 분할(`split.json`) 받기 | 지금은 VL만 쓰고 있어 AI Hub 샘플이 적음 |
| 4 | AI Hub 샘플 사람 검수(`review.py`) | 현재는 자동 점검만 통과한 상태 |
| 5 | main 병합 뒤 잔액 조회를 잔액조회 영역 `get_accounts`로 교체 | `balance_source.py` 한 곳만 바뀜 |

## 6. 지키는 규칙

- AI Hub 원본·가공 데이터, 학습 결과(어댑터·GGUF)는 git에 커밋하지 않고 외부 서비스에 올리지 않는다. wandb에도 질문·답 원문 없이 숫자만 올린다.
- 수동 모범 답(`training/interest/manual/`)은 직접 쓴 데이터라 커밋할 수 있다.
- 학습 정답은 추론 검증을 통과해야 한다(INT-004). 검증을 바꾸면 데이터 폴더를 다시 만든다.
- 학습 결과는 덮어쓰지 않는다. 데이터 폴더와 run 폴더는 번호를 새로 붙인다.
- 새 기능은 테스트부터 쓴다(`backend/tests/interest/`).
