# UI 디자인 가이드

## 디자인 원칙
1. **랜딩은 장면이 주인공이다.** 시각적 정체성은 디오라마 영상·이미지(매트 클레이, 아이소메트릭, 크림 배경, 주황 캐릭터)에서 나온다. 상단바·점 내비·카피 같은 UI 크롬은 조용하게 둔다.
2. **챗 패널은 같은 세계의 일부처럼 보이되, 읽기가 먼저다.** 크림·잉크 색과 알약형 버튼으로 랜딩에 맞추고, 금액과 선택지가 가장 잘 보이게 한다.
3. **다음에 누를 것이 한눈에 보여야 한다.** 상단바 CTA, 예시 칩, 선택지 버튼, 상담원 안내가 그 역할을 한다.
4. **카피는 짧고 구체적으로.** eyebrow 한 줄 + 제목 한 줄 + 본문 한두 문장 + 태그 0~3개. 검증되지 않은 수치는 쓰지 않는다.

## AI 슬롭 안티패턴 — 하지 마라
| 금지 사항 | 이유 |
|-----------|------|
| backdrop-filter: blur() | glass morphism은 AI 템플릿의 가장 흔한 징후 |
| gradient-text (배경 그라데이션 텍스트) | AI가 만든 SaaS 랜딩의 1번 특징 |
| "Powered by AI" 배지 | 기능이 아니라 장식. 사용자에게 가치 없음 |
| box-shadow 글로우 애니메이션 | 네온 글로우 = AI 슬롭 |
| 보라/인디고 브랜드 색상 | "AI = 보라색" 클리셰 |
| 모든 카드에 동일한 rounded-2xl | 균일한 둥근 모서리는 템플릿 느낌 |
| 배경 gradient orb (blur-3xl 원형) | 모든 AI 랜딩 페이지에 있는 장식 |

> 알려진 예외: 엔진 기본 CSS(`scrub-engine.js`)의 상단 nav·점 내비 라벨에 `backdrop-filter: blur()`가 있고, 배경에 은은한 그라데이션이 있다. 엔진 원본이라 그대로 둔다(FE-008). `src/`에서는 쓰지 않는다.

## 색상 (라이트 테마 고정)
토큰은 `globals.css`의 `@theme`에 한 번만 정의한다(`--color-<토큰>` → Tailwind `bg-<토큰>`·`text-<토큰>`). 엔진 변수(`--sw-*`)도 같은 토큰을 가리킨다.

| 토큰 | 값 | 용도 |
|------|------|------|
| `cream` | `#FCF1E6` | 페이지·챗 섹션 배경, 엔진 `--sw-bg`. 장면 이미지 배경과 맞춘 값 |
| `surface` | `#FFFBF6` | 챗 패널 |
| `bubble` | `#F3E6D8` | 봇 말풍선, 입력 중 표시 |
| `ink` | `#2A2118` | 주 텍스트, 고객 말풍선, 전송 버튼, 엔진 `--sw-ink` |
| `ink-soft` | `#7A6A5C` | 보조 텍스트(안내 문구·라벨·섹션 본문), 엔진 `--sw-ink-soft` |
| `accent-orange` | `#E07B2E` | 01 장면 accent, 엔진 기본 `--sw-accent`, 예시 칩 틴트 |
| `accent-blue` | `#3A6FD0` | 02·04 장면 accent, 챗 포인트(선택지 버튼·포커스 테두리·섹션 eyebrow) |
| `accent-yellow` | `#E5A527` | 03 장면 accent |
| 오류 | `text-red-700` (`#b91c1c`) | 오류 말풍선 글자. 테스트가 이 클래스를 확인한다 |

- 대비: `ink-soft`는 `cream` 위에서 약 4.7:1, `accent-blue`는 `surface` 위에서 약 4.7:1이다. 작은 글자에 쓸 수 있는 하한이다.
- `accent-orange`·`accent-yellow`는 챗에서 글자색으로 쓰지 않는다. 배경 틴트와 테두리에만 쓴다.
- teal·stone 등 이전 팔레트는 쓰지 않는다.

## 컴포넌트

### 랜딩 (엔진)
엔진이 만드는 컴포넌트를 그대로 쓰고 새로 만들지 않는다. 버튼·카피·상단바·점 내비는 `.sw-*` 기본 스타일이다.
- 섹션 카피: 번호(01 / 04) → eyebrow(accent) → 제목 → 본문 → 태그 → (마지막만) CTA. 데스크톱은 좌측 중앙 최대 460px, 860px 이하는 하단 고정.
- `globals.css`의 레이어 밖 CSS로 덮어쓰는 것은 이것뿐이다(`docs/frontend/ARCHITECTURE.md` "CSS 레이어").
  - `:root, .sw-root`에 `--sw-bg`(cream), `--sw-ink`(ink), `--sw-ink-soft`(ink-soft), `--sw-accent`(accent-orange), `--sw-font-display`·`--sw-font-body`(Pretendard 스택)
  - `.sw-copy__title, .sw-copy__body { word-break: keep-all; }`
  - `@media (min-width: 861px) { .sw-scene__video, .sw-scene__still { object-fit: contain; } }` — 데스크톱에서 장면을 자르지 않고 전체를 보여준다. 배경색이 같아 여백이 묻힌다.

### 챗 섹션 (`#chat`)
```
section: relative z-[45] min-h-dvh bg-cream pt-24 pb-10 px-[clamp(18px,5vw,64px)]
         (z-[45]: 엔진 장면·카피·점 내비를 덮고 상단바 아래. pt-24: 배경 없는 상단바 높이만큼 여백)
lg 이상: 2열 — 왼쪽 카피(세로 가운데), 오른쪽 챗 패널(최대 40rem). lg 미만: 1열(카피 위, 패널 아래)
카피: eyebrow "직접 체험" text-accent-blue text-[0.8rem] font-bold tracking-[.16em]
      → h2 제목 text-ink font-bold text-[clamp(2rem,4.4vw,3.5rem)] leading-tight
      → 본문 text-ink-soft, 둘 다 word-break: keep-all
패널: flex flex-col bg-surface border border-ink/12 rounded-[20px] overflow-hidden
      높이 h-[min(44rem,calc(100dvh_-_8rem))] — 대화 목록만 스크롤
```
- 페이지의 `h1`은 `sr-only` "Local LLM — 은행 상담 AI" 하나다. 엔진 카피와 챗 섹션 제목은 `h2`다.

### 챗 패널 상단
```
flex items-center justify-between gap-2 border-b border-ink/10 px-4 py-3
왼쪽: 데모 고객 선택 / 오른쪽: "새 대화" 버튼
```

### 데모 고객 선택
```
라벨 "데모 고객" text-sm text-ink-soft
select: rounded-full border border-ink/20 bg-white px-3 py-1.5 text-sm text-ink focus:border-accent-blue focus:outline-none disabled:opacity-40
항목 텍스트: C001 · C002 · C003
```

### "새 대화" 버튼 (엔진 ghost 버튼과 같은 모양)
```
rounded-full border-[1.5px] border-ink/25 px-3.5 py-1.5 text-sm font-medium text-ink hover:bg-ink/5 disabled:opacity-40
```

### 말풍선
```
공통: w-fit max-w-[80%] px-4 py-3 text-sm leading-relaxed whitespace-pre-line animate-fade-in
봇:   rounded-[18px] rounded-bl-md bg-bubble text-ink
고객: rounded-[18px] rounded-br-md bg-ink text-white ml-auto
오류: 봇과 같고 글자색만 text-red-700
```
- 치환된 슬롯 조각은 `font-semibold tabular-nums`다. 여러 줄 슬롯 값(예: 거래내역)도 같다.
- 선택지 버튼은 그 봇 말풍선 바로 아래에 둔다.

### 선택지 버튼
```
rounded-full border-[1.5px] border-accent-blue px-4 py-1.5 text-sm font-medium text-accent-blue hover:bg-accent-blue/10 disabled:opacity-40
```

### 예시 칩
```
위치: 대화 목록(role="log") 밖, 입력창 바로 위 — flex flex-wrap gap-2 px-4 pb-2
칩:   rounded-full border border-accent-orange/30 bg-accent-orange/15 px-3.5 py-1.5 text-sm font-semibold text-ink hover:bg-accent-orange/25 disabled:opacity-40
```
- 선택지 버튼(파랑 테두리)과 모양을 다르게 해서 "대화에 대한 답"과 "시작 예시"를 구분한다.

### 입력 중 표시
```
봇 말풍선 자리에 w-fit rounded-[18px] rounded-bl-md bg-bubble px-4 py-3, 점 3개(•) text-ink-soft 각 점 animate-pulse
스크린리더용 텍스트 "답변 작성 중"
```

### 첫 화면 안내 문구
```
대화 목록 가운데, text-sm text-ink-soft — 말풍선 아님
문구: "잔액·거래내역, 대출, 이자·연체 문의를 입력해 주세요."
```

### 입력 필드 / 전송 버튼
```
폼:   flex gap-2 border-t border-ink/10 p-4
입력: flex-1 rounded-full border border-ink/20 bg-white px-5 py-3 text-sm text-ink focus:border-accent-blue focus:outline-none disabled:opacity-40
전송: rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white hover:bg-ink/90 disabled:opacity-40
```

## 레이아웃
- 랜딩: 엔진 기본. 장면은 화면 전체에 고정(데스크톱 `contain`, 모바일 `cover`), 섹션별 스크롤 길이는 PRD "랜딩" 표의 `scroll`(1.6 / 1.4 / 1.2 / 1.3 화면 높이).
- 챗: 봇은 좌측, 고객은 우측 정렬. 말풍선 사이 `space-y-3`, 선택지·칩 사이 `gap-2`.
- 대화 목록: `flex-1 overflow-y-auto overscroll-contain p-4`.
- `<html lang="ko">`, 메타데이터 제목 "Local LLM — 은행 상담 AI".

## 타이포그래피
| 용도 | 스타일 |
|------|--------|
| 폰트 | Pretendard Variable — jsdelivr CDN `pretendard@1.3.9/dist/web/variable/pretendardvariable.min.css`를 `layout.tsx`의 `<link>`로 불러온다. `@theme`의 `--font-sans`와 엔진 `--sw-font-*`에 같은 스택 `"Pretendard Variable", Pretendard, -apple-system, system-ui, sans-serif`. 못 받으면 시스템 폰트 |
| 한국어 제목·본문 | `word-break: keep-all` (엔진 카피, 챗 섹션 카피) |
| 챗 섹션 제목 | 700, `clamp(2rem, 4.4vw, 3.5rem)` — 엔진 섹션 제목과 같은 크기 |
| 말풍선 본문 | `text-sm leading-relaxed` |
| 금액(치환된 슬롯) | `font-semibold tabular-nums` |

## 애니메이션
- 랜딩: 엔진 기본(영상 스크럽, 장면 크로스페이드, 스틸 켄번스 줌, 카피 fade와 살짝 이동, 데스크톱 파티클). 추가하지 않는다.
- 챗: 새 말풍선 fade-in(0.2s, `globals.css`의 `@theme`에 정의한 `--animate-fade-in`), 입력 중 점 `animate-pulse`. 그 외 애니메이션 금지.
- `prefers-reduced-motion`: 움직임(영상 스크럽·파티클·줌·이동)만 끈다. 엔진이 처리한다. 투명도 변화(장면 크로스페이드, 말풍선 fade, 점 깜빡임)는 유지한다. 챗 코드는 따로 처리하지 않는다.

## 에셋 규칙 (웹사이트에서 이관)
- 원본은 `~/Projects/local-llm-cs-support-website/`(git 저장소 아님)이고, `frontend/public/scroll-world/`에 복사본을 둔다. `scrub-engine.js`는 수정하지 않는다(FE-008).
- 새 에셋은 MVP 범위 밖이다(PRD 제외). 아래는 나중에 추가할 때의 규격이다.
  - 영상 인코딩: `ffmpeg -i src.mp4 -an -vf "unsharp=5:5:0.8:5:5:0.0" -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -g 8 -keyint_min 8 -sc_threshold 0 -movflags +faststart out.mp4`. 해상도를 줄이거나 all-intra로 인코딩하면 화질이 떨어지거나 파일이 커진다.
  - 영상 섹션의 `still`은 그 영상의 첫 프레임이어야 한다. 영상이 뜨기 전 포스터와 첫 프레임이 다르면 튄다.
  - 새 장면 이미지는 크림 배경(`#FCF1E6` 부근)이어야 한다. 데스크톱은 `contain`이라 배경색이 다르면 여백이 드러난다.

## 아이콘
- 쓰지 않는 것을 기본으로 한다. 필요하면 SVG 인라인, strokeWidth 1.5, 배경 박스로 감싸지 않는다.
