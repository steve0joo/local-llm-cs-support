# UI 디자인 가이드 (초안 — 프론트 담당 확정)

## 디자인 원칙
1. 은행 상담 도구처럼 보여야 한다. 마케팅 페이지가 아니라 매일 쓰는 상담 창이다.
2. 금액과 선택지가 가장 잘 보여야 한다. 장식보다 읽기 쉬운 것이 먼저다.
3. 고객이 다음에 무엇을 누르면 되는지 한눈에 보여야 한다(선택지 버튼, 상담원 안내).

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

## 색상 (라이트 테마 고정)
### 배경
| 용도 | 값 |
|------|------|
| 페이지 | `#f5f5f4` |
| 대화 영역 | `#ffffff` |
| 봇 말풍선 | `#f5f5f4` |
| 고객 말풍선 | `#1c1917` |

### 텍스트
| 용도 | 값 |
|------|------|
| 주 텍스트 | `text-stone-900` |
| 본문 | `text-stone-700` |
| 보조 | `text-stone-500` |
| 고객 말풍선 | `text-white` |

### 데이터/시맨틱 색상
| 용도 | 값 |
|------|------|
| 포인트(버튼·링크) | `#0f766e` (teal-700) |
| 오류 | `#b91c1c` |
| 중립 | `#57534e` |

## 컴포넌트
### 말풍선
```
봇:   max-w-[80%] rounded-lg bg-stone-100 px-4 py-3 text-sm text-stone-800
고객: max-w-[80%] rounded-lg bg-stone-900 px-4 py-3 text-sm text-white ml-auto
```

### 선택지 버튼
```
rounded-md border border-teal-700 px-3 py-1.5 text-sm text-teal-700 hover:bg-teal-50 disabled:opacity-40
```

### 입력 필드 / 전송 버튼
```
입력: flex-1 rounded-md border border-stone-300 px-4 py-3 text-sm focus:border-teal-700 focus:outline-none
전송: rounded-md bg-teal-700 px-4 py-3 text-sm text-white hover:bg-teal-800 disabled:opacity-40
```

## 레이아웃
- 대화 영역 너비: `max-w-2xl mx-auto`, 화면 높이를 채우고 대화 목록만 스크롤한다
- 봇은 좌측, 고객은 우측 정렬
- 간격: 말풍선 사이 `space-y-3`, 선택지 버튼 사이 `gap-2`
- 상단: 서비스 이름(텍스트) + 데모 고객 선택 드롭다운

## 타이포그래피
| 용도 | 스타일 |
|------|--------|
| 서비스 이름 | `text-base font-semibold text-stone-900` |
| 말풍선 본문 | `text-sm leading-relaxed` |
| 금액(치환된 슬롯) | `font-semibold tabular-nums` |

## 애니메이션
- 새 말풍선 fade-in (0.2s)
- 입력 중 표시: 점 3개 깜빡임
- 그 외 애니메이션 금지

## 아이콘
- 쓰지 않는 것을 기본으로 한다. 필요하면 SVG 인라인, strokeWidth 1.5, 배경 박스로 감싸지 않는다.
