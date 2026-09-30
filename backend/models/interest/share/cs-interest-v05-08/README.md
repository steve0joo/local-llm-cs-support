# cs-interest v05-08

이 폴더는 이자·연체 상담 에이전트 모델을 Ollama에서 실행하기 위한 공유 파일입니다.

## 포함 파일

- `cs-interest.gguf`: LoRA 병합 후 `Q4_K_M`으로 양자화한 실제 추론 모델입니다.
- `Modelfile`: Ollama 모델 생성 설정입니다. 모델 파일과 같은 폴더에 두어야 합니다.
- `VERSION`: 사용한 학습 run 버전(`v05-08`)을 기록한 파일입니다.
- `export.md`: GGUF 변환 및 Ollama 등록 절차의 상세 안내입니다.

## 실행 방법

1. 네 파일을 같은 폴더에 둡니다.
2. 해당 폴더에서 다음 명령을 실행합니다.

```bash
ollama create cs-interest -f Modelfile
```

3. 등록을 확인합니다.

```bash
ollama list
```

이 모델은 이자·연체 문의 응답용이며, 실제 금액은 애플리케이션의 mock/API 조회값과 슬롯 치환을 통해 전달하는 구조입니다.
