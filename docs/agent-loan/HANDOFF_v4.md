# agent-loan v3→v4 인수인계 (2026-09-30 작성)

다른 컴퓨터(교육용)에서 이어받는 Claude Code가 "무엇이 바뀌었고, 어디까지 했고, 무엇이 남았는지" 파악하기 위한 문서다. 작업 브랜치는 `feat-agent-loan`이고 **v4 관련 변경은 대부분 아직 커밋되지 않았다**(아래 4절). 내용이 코드·테스트와 다르면 코드·테스트가 맞다.


## 0. 최신 상태 (2026-09-30 저녁, 이 절이 아래 절들보다 우선한다)

- **최종 모델은 v4로 확정했다**(`ADR.md` LN-009, `EVALUATION.md` 9-7절). 팀 공용틀 평가(Base, v1~v4, GPT-5 Mini Judge, 사람 평가)와 W&B 1단계 판정을 이 컴퓨터에서 끝냈다. 아래 3절의 "아직 안 한 것"과 3-1절의 공식 평가 준비는 **이미 끝난 일**이다.
- 이 컴퓨터의 Ollama `cs-loan`을 v4로 바꿨다(`ollama cp cs-loan-v4 cs-loan`). 서비스(`agent.py`)는 `cs-loan`을 부르므로 코드 수정 없이 v4로 답한다. 이전 `cs-loan`(v1)은 `cs-loan-test`로 남아 있다.
- **main에는 반영하지 않는다(사용자 결정).** 모든 변경은 `feat-agent-loan` 브랜치에만 있다.
- **모델 전달(팀원에게 따로)**: 가중치는 git에 넣지 않는다. 파일은 `~/models/cs-loan-v4-q4_k_m.gguf`(약 2.5GB, sha256 `5a4aa0f723c53ac06b3ec1ab0049b4cb470dc07a051cc053e421e9fba113583f`)이고 팀 내부 공유(USB, 팀 드라이브)로만 보낸다(팀 밖 제공 금지). 받은 사람은 파일을 확인(`sha256sum`)한 뒤 등록한다.
  ```bash
  cd local-llm-cs-support
  sed "s#^FROM .*#FROM /받은/절대경로/cs-loan-v4-q4_k_m.gguf#" backend/models/loan/Modelfile > /tmp/Modelfile.v4
  ollama create cs-loan -f /tmp/Modelfile.v4
  ```
- 평가 도구·기준·결과: `EVALUATION.md`(도구 `backend/training/loan/evaluate.py`, 테스트 `tests/loan/test_evaluate.py`). Judge는 `backend/.env`의 `OPENAI_API_KEY`(gitignore)가 있어야 하고 호출 전 확인을 받는다.
- **남은 일 없음**(평가 기준). 다음 후보(하지 않기로 함): v5 시드, 사람 평가 재실시. 알려진 한계(K06, D10, 문장이 딱딱함)는 `EVAL_CRITERIA_v4.md` 5절과 `EVALUATION.md` 9-7절에 있다.

## 1. 한 줄 요약

대출문의 에이전트 모델(Qwen3-4B-Instruct-2507 → QLoRA → GGUF Q4_K_M → Ollama)을 v1→v2→v3까지 만들고 사전 등록 기준으로 평가했더니 v3가 기준 미달이었다. 그 결함을 고치는 **v4 학습 데이터(시드)를 확정·해시 고정**했고, 야간 학습 스크립트와 평가 자료(문항·기준)를 준비했다. 학습은 사용자가 WSL에서 직접 돌린다(Claude는 명령만 안내, 로그 폴링 금지).

## 2. 지금까지 진행한 것

### 2-1. v3 평가 결과 (v4를 만든 이유)
- 기준은 `EVAL_CRITERIA_v3.md`(사전 등록). v3는 판정 기준 미달: 처리 요청·범위 밖·조건·수수료↔금리·손해/이득 유형에서 지어낸 사실(fabrication)이 8샘플 나왔다.
- 정상 질문(만기·원금·연장 여부) 통과율은 v3가 100%(320/320)였다. v4가 이보다 떨어지면 안 된다.
- 결함 유형: 거절 문형이 "~ㄹ 수 있"로 뒤집혀 처리 약속이 되는 문제, 연체·기한 초과에서 이자·법규를 지어냄, 조건 질문에서 연장 슬롯 누락, 수수료와 금리 혼동.

### 2-2. v4 시드 (핵심 변경)
- `backend/training/loan/manual_seed_v4.jsonl`: **451행, 최종 확정, 더 이상 수정 금지**. v3 시드에서 중복성 높은 거절을 정리하고 결함 유형 시드를 더했다(범위 밖, 처리 요청, 조건, 손해·이득, 수수료↔금리, 원금+상환액, 말투 변형 20, 마스킹 20, 멀티턴 20).
- 날짜 확인 시드: 틀린 날짜는 "아니요, 만기일은 X입니다"로 정정(`v4wrong` 6건), 맞는 날짜는 "네, 맞습니다. …"(`v4right` 4건). 맞는 날짜 6 : 틀린 날짜 8. `아니요,` 시작은 `v4wrong`에서만 허용.
- 생성 코드: `make_manual_seed.py --version v4`가 `seed_v4.py`를 불러 쓴다. 기본값(v3)은 기존 `manual_seed.jsonl`과 바이트 단위로 같게 재현된다(sha256 `5773891820c3…`, 테스트로 고정).
- 거절 문형: `prepare.py`에 `REFUSAL_TEMPLATES_V4`를 별도 상수로 추가(v3 상수는 해시로 고정). CLI `--refusal-version v3|v4`.
- 학습 데이터에서 "수 있/수 없/처리해 드", "확인해 드리겠", "조회되지 않아" 등 금지 문형은 0건이다.
- 학습 파라미터는 v3와 같다(lr 2e-4, 3 epoch, r16/alpha32/dropout 0.05, 배치 1×누적 16, seed 42). `train.py`에는 `--save-total-limit`(기본 2)만 추가했다.

### 2-3. 확정 해시 (3회차, 이전 회차 해시는 폐기)

| 파일 | 행 | sha256 |
|---|---|---|
| `backend/training/loan/manual_seed_v4.jsonl` | 451 | `3e586ec1bf98f89dce96ff3d51de60c049bcc9c111c2f3a8986241279316d448` |
| `backend/data/processed/loan_train_v4.jsonl` | 1,406 | `780c9ba5da7e106bb2564dba1f8bf73c53b8b50d22f1eadeaf7ae6c11a45e850` |
| `backend/data/processed/loan_val_v4.jsonl` | 199 | `5965cfdb6df0de646ea5adb3644065a39104dfb6134a123efa11669886f2a119` |

학습·검증 파일 생성 명령(AI Hub 원본 `data/raw`와 `split.json`이 로컬에 있어야 함):
```bash
cd backend
for w in train val; do .venv/bin/python -m training.loan.prepare --raw data/raw --split data/processed/split.json \
  --out data/processed/loan_${w}_v4.jsonl --which $w --manual training/loan/manual_seed_v4.jsonl --mode replace --refusal-version v4; done
```

### 2-4. 학습 스크립트와 wandb
- `backend/training/loan/night_v4.sh`: 위 해시가 다르면 학습하지 않고 종료 → 학습(`--report-to wandb --wandb-online`, wandb 프로젝트 `cs-loan`, 런 이름 `outputs_v4`) → 병합(bf16) → GGUF+Q4_K_M → `ollama create cs-loan-v4` → 스모크(`smoke_v4.py`). 단계 결과는 `outputs_v4/STATUS.txt`. 어댑터·체크포인트·로그는 지우지 않는다. `DRY=1`이면 점검만 한다.
- v3의 경로·이름(`outputs_v3/`, `cs-loan-v3`, `cs-loan-test`, `loan_*_v3.jsonl`)과 겹치지 않는다.
- 스모크 6문항은 최종 확인용 F01~F10과 유사도 0.75 이상이면 제외한다.

### 2-5. 평가 자료 (사전 등록, v4 응답을 보기 전에 확정)
- `docs/agent-loan/EVAL_CRITERIA_v4.md`: v4 판정 기준. **평가 뒤에 기준을 바꾸지 않는다**(바꾸면 사후 변경이라고 표시).
  - 정상 질문 64문항 × 5회(온도 0.3) = 320샘플: 통과율 100%, 사실 없이 상담원 안내만 한 응답 0건.
  - `golden_set_final_v4.jsonl` F01~F10(사용자 작성, 원문 수정 금지): 온도 0에서 9/10 이상. 온도 0.3 ×5는 안정성 보고(지어낸 사실은 별도 표시).
  - `golden_set_v4_compare.jsonl` K01~K20: 비교용 새 문항.
  - v3 결함별 개선 보고(판정 제외).
- 알려진 한계(이번에 고치지 않음, **v5는 하지 않기로 함**, 자세한 내용은 `EVAL_CRITERIA_v4.md` 5절):
  - 연장 불가 고객의 정상 답변 끝에 연장 언급이 없어도 "자세한 사항은 상담원에게 확인해 주세요."가 붙는다.
  - **D10**: "마지막 상환일이 며칠이에요?" 같은 낯선 날짜 표현을 거절한다(5회 중 4회). 사전 등록 기준 미달의 원인.
  - **K06**: 조건 + 해당 여부 질문에 연장 여부(`{{extendable_status}}`)를 빼먹고 거절문만 답한다(5/5).
  - 일본어·한자 혼입(v4 5샘플)은 검증기가 차단해 fallback으로 대체한다(모델 출력은 그대로).
- 채점 코드 정의는 `EVAL_CRITERIA_v3.md`, 문항은 `golden_set.jsonl`·`golden_set_v3.jsonl`·`golden_set_risk.jsonl`(커밋됨)에 있다.

### 2-6. 테스트
`cd backend && .venv/bin/python -m pytest tests/loan -q` → 1,209 통과(2026-09-30 기준, 일본어·한자 차단 테스트 12건 포함. 그 전에는 1,197). 새 테스트: `test_manual_seed_v4.py`(개수·금지 문형·겹침 0.75·v3 재현·v4 해시 고정·날짜 확인), `test_golden_set_final_v4.py`, `test_golden_set_v4_compare.py`, `test_train_args.py`.

## 3. 진행 상태와 남은 일

- **학습 완료(2026-09-30)**: val loss 0.1394 → 0.1080 → 0.1058(epoch 1~3), train_loss 0.2172, 학습 46분. STATUS 전 단계 OK, `cs-loan-v4` 등록, 스모크 통과. wandb 프로젝트 `cs-loan` 런 `outputs_v4`로 기록됨.
- **자체 평가 완료**: 결과와 해석은 `docs/agent-loan/EVAL_RESULT_v4.md`에 있다. 요약: 정상 질문 통과율 316/320(기준 100% **미달**, D10 한 문항의 과다 거절), final-v4는 온도 0에서 통과, v3의 뒤집힌 거절 문형(80→1건)·조건 슬롯 누락·수수료↔금리는 개선, 다만 v4에서 새로 일본어 혼입 5샘플과 K06형 조건 질문 실패가 나왔다. 전체 통과율은 v3와 비슷하다.
- ~~아직 안 한 것: 팀 공식 평가~~ → **완료(2026-09-30, 위 0절과 `EVALUATION.md`)**. Base GGUF는 `cs-loan-base`로 등록했고 Judge 키는 `backend/.env`를 쓴다.
- ~~사용자 결정 대기~~ → **결정 완료**: 검증기 비한글 차단(커밋됨), v5는 하지 않음, 공식 평가 후 v4 확정.
- 평가 코드는 `backend/training/loan/eval_v4_run.py`, `eval_v4_score.py`(커밋 대상, 데이터는 gitignored)다. 원문 응답(`backend/data/derived/eval_v4/`)은 이 컴퓨터에만 있다.
- 나중 후보: 검증기에 `확인해 드리겠` 패턴 추가(오탐 확인 뒤 별도 커밋), 연장 불가 꼬리 개선, `wandb_backfill.py`.

## 3-1. 교육용 컴퓨터에서 할 일 (순서대로) — 공식 평가(4~7)는 이 컴퓨터에서 이미 완료, 모델 등록 방법은 0절 참고

1. `git checkout feat-agent-loan && git pull origin feat-agent-loan`. 이 문서, `EVAL_CRITERIA_v3.md`, `EVAL_CRITERIA_v4.md`, `EVAL_RESULT_v4.md`를 읽는다. 내용이 코드·테스트와 다르면 코드·테스트가 맞다.
2. 환경 확인: `cd backend`, venv 준비, `.venv/bin/python -m pytest tests/loan -q`(1,194건 통과가 기준), Ollama 실행.
3. **모델 준비**(가중치는 git에 없다). 이 컴퓨터(집 WSL)에서 `backend/training/loan/outputs_v4/cs-loan-v4-q4_k_m.gguf`(약 2.5GB)와 `outputs_v3/cs-loan-v3-q4_k_m.gguf`를 USB나 드라이브로 옮긴 뒤 `models/loan/Modelfile`의 `FROM` 경로만 바꿔 `ollama create cs-loan-v4 -f <Modelfile>`(v3도 같은 방식)로 등록한다. 학습을 다시 하지 않는다. 학습을 재현해야 하면 AI Hub 원본(`data/raw`)과 `split.json`이 있어야 하고, 학습 데이터 해시가 2-3절 값과 같아야 한다.
4. **Base 모델 등록**(팀 공용틀 비교용): Base GGUF(Qwen3-4B-Instruct-2507 Q4_K_M)를 같은 Modelfile 설정으로 등록한다. v1(`cs-loan-test`)도 필요하면 옮긴다.
5. **팀 공식 평가** — `EVALUATION_공용틀.md`는 저장소에 없다(사용자가 채팅으로 준 문서). 사용자에게 파일을 받아 그 기준으로 진행한다. 요약: 규칙 준수율 80% 이상, Base 대비 회귀 5%p 이내, Judge(GPT-5 Mini, API 키 필요), 사람 블라인드 10문항. 비교 대상은 Base, v3, v4.
6. 자체 평가 결과(`EVAL_RESULT_v4.md`)를 공식 평가와 함께 해석한다. v4는 정상 질문 과다 거절 검사가 미달이고(D10), 일본어 혼입과 K06형 조건 질문 실패가 있다. 공식 평가 결과와 무관하게 이 사실을 숨기지 않는다.
7. 결과가 나오면 사용자와 다음 방향을 정한다: ① 검증기에 비한글 문자 차단 추가(모델 변경 없이 즉시 개선, 별도 커밋), ② v5 시드(D10형 날짜 표현 변형, 조건+해당 여부 질문 보강, 새 이름·새 해시, K 세트와 D10은 dev로 전환), ③ v3 유지 또는 v4 채택 결정.
8. 하지 말 것: 학습 실행(사용자가 직접), v4 시드·학습 데이터·사전 등록 기준 수정, F01~F10을 시드 설계에 사용, 사용자가 쓴 문항 수정, main·타 영역 수정, 가중치·AI Hub 데이터 커밋, 사용자 승인 없는 push.

## 4. git 상태와 주의

- 이 문서 작성 시점의 미커밋 목록이며, 아래 파일들은 사용자 승인으로 2026-09-30에 `feat-agent-loan`에 커밋·push했다(가중치·데이터·`wandb_backfill.py`·`outputs_*`·`manual_seed_old/v90`은 제외).
  - 수정: `make_manual_seed.py`, `prepare.py`, `train.py`, `tests/loan/test_prepare_replace.py`, `docs/agent-loan/ADR.md`(v3a→v3/v4 이름 정리)
  - 신규: `seed_v4.py`, `manual_seed_v4.jsonl`, `golden_set_final_v4.jsonl`, `golden_set_v4_compare.jsonl`, `night_v4.sh`, `smoke_v4.py`, 새 테스트 4개, `EVAL_CRITERIA_v4.md`, `EVAL_RESULT_v4.md`, `eval_v4_run.py`, `eval_v4_score.py`, 이 문서, `wandb_backfill.py`
- **`git add .` 금지.** `outputs_v2/`, `outputs_v3/`, `outputs_v4/`에는 모델 가중치(.gguf, .safetensors)가 있는데 `.gitignore`가 `outputs/`만 막고 있어 **git이 추적 대상으로 잡는다**. 가중치와 AI Hub 원본·가공 데이터(`backend/data/`)는 커밋하지 않는다(데이터 이용조건). 커밋은 파일명을 지정해서 한다. `backend/wandb/`, `manual_seed_old.jsonl`, `manual_seed_v90.jsonl`, `outputs_*.log`도 커밋 대상이 아니다.
- 다른 컴퓨터에서 `cs-loan-v4`를 쓰려면 `backend/training/loan/outputs_v4/cs-loan-v4-q4_k_m.gguf`를 직접 복사하고 `outputs_v4/Modelfile.v4`로 `ollama create cs-loan-v4 -f …`를 한다. 학습 데이터(`loan_train_v4.jsonl`)는 gitignored라서 그 컴퓨터에서 만들려면 AI Hub 원본이 필요하다.
- 규칙: push는 사용자가 한다, main과 다른 영역은 수정하지 않는다, 커밋은 사용자가 승인한 파일만, 커밋 범위(scope)는 `agent-loan`, F01~F10은 시드 설계와 스모크에 쓰지 않는다(겹침 검사만), 사용자가 쓴 문항 원문은 수정하지 않는다, 학습은 사용자가 직접 돌린다.
