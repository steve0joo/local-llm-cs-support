const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625
pres.title = "로컬 LLM 은행 상담 보조 AI — 발표 뼈대";

const F = "맑은 고딕";
const C = {
  ink: "1B2A3A", inkSoft: "2C3E50", teal: "0F766E", tealLight: "CCEBE8",
  amber: "B45309", amberLight: "FDECC8", violet: "6D28D9", violetLight: "E9DDFB",
  gray: "64748B", line: "94A3B8", ph: "F1F5F9", white: "FFFFFF", text: "1E293B",
};
const BADGE = {
  doc: { t: "문서 기반", c: C.teal, bg: C.tealLight },
  team: { t: "팀원 지표 필요", c: C.amber, bg: C.amberLight },
  cap: { t: "캡처·데모 필요", c: C.violet, bg: C.violetLight },
};
const SECTIONS = [
  { n: "01", t: "배경과 목표", p: "3–4", time: "1:30" },
  { n: "02", t: "시스템 설계", p: "5–7", time: "2:40" },
  { n: "03", t: "모델 학습과 평가", p: "8–12", time: "3:50" },
  { n: "04", t: "데모와 결과", p: "13–14", time: "2:10" },
];

let pageNo = 0;
function txt(s, text, o) { s.addText(text, Object.assign({ isTextBox: true, fontFace: F, color: C.text, margin: 0 }, o)); }

function ph(s, x, y, w, h, label, hint, kind) {
  const k = kind ? BADGE[kind] : null;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.08,
    fill: { color: k && kind !== "doc" ? k.bg : C.ph },
    line: { color: k && kind !== "doc" ? k.c : C.line, width: 1, dashType: "dash" },
  });
  const parts = [{ text: label, options: { bold: true, fontSize: 13, color: C.inkSoft, breakLine: !!hint } }];
  if (hint) parts.push({ text: hint, options: { fontSize: 10.5, color: C.gray } });
  txt(s, parts, { x: x + 0.15, y: y + 0.1, w: w - 0.3, h: h - 0.2, valign: "middle", align: "center", paraSpaceAfter: 4 });
}

function content(section, title, message, badge, time, notes) {
  const s = pres.addSlide();
  pageNo++;
  s.background = { color: C.white };
  txt(s, `${section.n}  ${section.t}`, { x: 0.5, y: 0.3, w: 4, h: 0.3, fontSize: 11, bold: true, color: C.teal });
  const b = BADGE[badge];
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.15, y: 0.28, w: 1.45, h: 0.32, rectRadius: 0.16, fill: { color: b.bg }, line: { color: b.bg } });
  txt(s, b.t, { x: 7.15, y: 0.28, w: 1.45, h: 0.32, fontSize: 10, bold: true, color: b.c, align: "center", valign: "middle" });
  txt(s, time, { x: 8.7, y: 0.28, w: 0.8, h: 0.32, fontSize: 11, color: C.gray, align: "right", valign: "middle" });
  txt(s, title, { x: 0.5, y: 0.65, w: 9, h: 0.6, fontSize: 26, bold: true, color: C.ink });
  txt(s, message, { x: 0.5, y: 1.25, w: 9, h: 0.4, fontSize: 13, color: C.gray, italic: true });
  txt(s, String(pageNo), { x: 9.0, y: 5.2, w: 0.5, h: 0.25, fontSize: 9, color: C.line, align: "right" });
  s.addNotes(notes);
  return s;
}

function arrow(s, x, y) {
  s.addShape(pres.shapes.RIGHT_ARROW, { x: x - 0.03, y, w: 0.2, h: 0.2, fill: { color: C.line }, line: { color: C.line } });
}

// 1. 표지
{
  const s = pres.addSlide(); pageNo++;
  s.background = { color: C.ink };
  txt(s, "MINI PROJECT", { x: 0.7, y: 1.2, w: 6, h: 0.35, fontSize: 12, bold: true, color: "5EEAD4", charSpacing: 4 });
  txt(s, "로컬 LLM 은행 상담 보조 AI", { x: 0.7, y: 1.6, w: 8.6, h: 0.9, fontSize: 36, bold: true, color: C.white });
  txt(s, "개인정보를 모델에 보내지 않는 파인튜닝 상담 챗봇 (MVP)", { x: 0.7, y: 2.5, w: 8.6, h: 0.45, fontSize: 16, color: "CBD5E1" });
  txt(s, "[팀명 · 발표자 · 발표일]", { x: 0.7, y: 4.4, w: 6, h: 0.35, fontSize: 12, color: "94A3B8" });
  s.addNotes("근거: CLAUDE.md 프로젝트 정의, PRD 팀 분담. 시간 0:20.");
}

// 2. 목차
{
  const s = pres.addSlide(); pageNo++;
  s.background = { color: C.white };
  txt(s, "목차", { x: 0.5, y: 0.5, w: 4, h: 0.6, fontSize: 30, bold: true, color: C.ink });
  txt(s, "총 11분", { x: 7.5, y: 0.6, w: 2, h: 0.4, fontSize: 12, color: C.gray, align: "right" });
  SECTIONS.forEach((sec, i) => {
    const x = 0.5 + i * 2.3, y = 1.6;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 2.1, h: 2.9, rectRadius: 0.1, fill: { color: i % 2 ? C.ph : C.tealLight }, line: { color: i % 2 ? C.ph : C.tealLight } });
    txt(s, sec.n, { x: x + 0.25, y: y + 0.25, w: 1.6, h: 0.7, fontSize: 34, bold: true, color: C.teal });
    txt(s, sec.t, { x: x + 0.25, y: y + 1.05, w: 1.7, h: 0.8, fontSize: 16, bold: true, color: C.ink, valign: "top" });
    txt(s, `p.${sec.p}\n약 ${sec.time}`, { x: x + 0.25, y: y + 2.0, w: 1.6, h: 0.6, fontSize: 11, color: C.gray, valign: "top" });
  });
  txt(s, String(pageNo), { x: 9.0, y: 5.2, w: 0.5, h: 0.25, fontSize: 9, color: C.line, align: "right" });
  s.addNotes("시간 0:20. 섹션 구성과 시간 배분은 논의 후 확정.");
}

const [S1, S2, S3, S4] = SECTIONS;

// 3. 문제와 목표
{
  const s = content(S1, "문제와 목표", "기존 챗봇은 단계가 많고, 은행 상담 데이터는 외부 모델로 보낼 수 없다", "doc", "0:50",
    "근거: docs/PRD.md 목표·사용자·제약.\n말할 것: 문제(단계 많은 챗봇, 개인정보) → 목표(한 번에 주제 분류·전문 에이전트, 로컬 모델).");
  ph(s, 0.5, 1.85, 4.35, 3.2, "문제", "기존 챗봇의 한계 · 개인정보 제약");
  arrow(s, 4.95, 3.35);
  ph(s, 5.15, 1.85, 4.35, 3.2, "목표", "주제 분류 → 전문 에이전트 · 전부 로컬 추론");
}

// 4. 인수 기준
{
  const s = content(S1, "성공 기준", "PM이 고정 시나리오로 직접 합격·불합격을 판정한다", "doc", "0:40",
    "근거: docs/PRD.md 인수 기준 1~8.\n말할 것: 라우팅·복합 문의·답변 품질·사실 생성·마스킹·잔액 화면·응답 시간·실행 환경. 14번 달성 현황과 짝을 이룸.");
  for (let i = 0; i < 8; i++) {
    const col = i % 4, row = Math.floor(i / 4);
    ph(s, 0.5 + col * 2.3, 1.85 + row * 1.65, 2.1, 1.45, `기준 ${i + 1}`, "이름 · 목표치");
  }
}

// 5. 전체 구조
{
  const s = content(S2, "전체 구조", "질문 한 번이 마스킹 → 분류 → 전문 에이전트 → 화면 치환을 거친다", "doc", "1:00",
    "근거: docs/ARCHITECTURE.md 데이터 흐름, 계약 1~5.\n말할 것: 모델에는 마스킹된 텍스트와 슬롯 이름만 들어간다.");
  const steps = ["고객 질문", "게이트웨이\n(마스킹)", "라우터\n(주제 분류)", "전문 에이전트\n× 3", "화면\n(슬롯 치환)"];
  steps.forEach((t, i) => {
    const x = 0.5 + i * 1.86;
    ph(s, x, 2.0, 1.6, 1.3, t);
    if (i < steps.length - 1) arrow(s, x + 1.66, 2.55);
  });
  ph(s, 0.5, 3.6, 9.0, 1.45, "다이어그램 자리", "Ollama 모델 4개 · mock API · 모델 입력 로그 위치 표시");
}

// 6. 설계 원칙
{
  const s = content(S2, "핵심 설계 원칙 3가지", "개인정보는 모델에 닿지 않고, 모든 추론은 로컬에서 돈다", "doc", "0:50",
    "근거: CLAUDE.md 아키텍처 규칙, docs/ADR.md ADR-004·006.\n말할 것: ① 정규식 마스킹 ② {{슬롯}}만 생성, 금액은 화면에서 치환 ③ Ollama + GGUF로 Windows·Mac 로컬 추론.");
  ["① 개인정보 마스킹", "② 슬롯 치환", "③ 로컬 추론"].forEach((t, i) => {
    ph(s, 0.5 + i * 3.05, 1.85, 2.85, 3.2, t, "원칙 한 줄 · 예시 한 개");
  });
}

// 7. 라우터와 에이전트
{
  const s = content(S2, "라우터와 전문 에이전트", "9개 주제로 나누고, 두 주제에 걸치면 되묻는다", "doc", "0:50",
    "근거: docs/router/ADR.md RT-001·002, ARCHITECTURE 계약 2·3, docs/agent-*/PRD.md.\n말할 것: 복합 문의 예시(대출 잔액 + 이자), 미지원 6개 주제는 안내.");
  ph(s, 0.5, 1.85, 4.2, 3.2, "라우터", "9개 주제 · 복합 문의 되묻기 · 미지원 안내");
  ["잔액조회", "대출문의", "이자/연체"].forEach((t, i) => {
    ph(s, 5.0, 1.85 + i * 1.1, 4.5, 0.95, `${t} 에이전트`, "담당 · 슬롯 예시");
  });
}

// 8. 학습 파이프라인
{
  const s = content(S3, "학습 파이프라인", "공통 베이스 모델 하나를 영역별로 QLoRA 학습해 GGUF로 배포한다", "doc", "0:40",
    "근거: docs/ARCHITECTURE.md 학습 파이프라인, router/ADR.md RT-005, training/interest/export.md.\n말할 것: 학습 장비 1대(RTX 4060 8GB), 데이터·가중치는 git 제외.");
  const steps = ["AI Hub\n원본", "공통 분할", "마스킹·정제", "QLoRA\n학습", "병합·GGUF", "Ollama\n배포"];
  steps.forEach((t, i) => {
    const x = 0.5 + i * 1.55;
    ph(s, x, 2.2, 1.3, 1.2, t);
    if (i < steps.length - 1) arrow(s, x + 1.35, 2.7);
  });
  ph(s, 0.5, 3.75, 9.0, 1.3, "환경·제약 한 줄", "학습 장비 · 베이스 모델 · 데이터 이용 조건");
}

// 9. 학습 데이터와 실험 흐름
{
  const s = content(S3, "학습 데이터와 실험 흐름", "원본 데이터의 정답이 우리 규칙과 맞지 않아 정제와 합성으로 보완했다", "team", "0:50",
    "근거: docs/agent-interest/REPORT.md §2, FINETUNE.md §4·5, TRAINING_DATA_PLAN.md.\n팀원 추가: v04 이후 최신 버전 결과.");
  ph(s, 0.5, 1.85, 3.0, 3.2, "데이터 구성", "원본 문제 · 정제 규칙 · 합성 샘플", "doc");
  ph(s, 3.8, 1.85, 5.7, 3.2, "버전 타임라인", "v01 → v02 → v03 → … 최신\n버전별 변경점과 배운 점", "team");
}

// 10. 평가 방법
{
  const s = content(S3, "평가 방법", "학습 안정성부터 사람 평가까지 네 가지 질문으로 판단한다", "doc", "0:40",
    "근거: docs/agent-interest/EVALUATION.md.\n말할 것: 규칙 준수율 정의(4개 모두 충족), Golden Set 구성.");
  ["Q1 학습은 안정적인가", "Q2 목표 능력이 생겼나", "Q3 기존 능력은 유지되나", "Q4 사람이 보아도 좋은가"].forEach((t, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    ph(s, 0.5 + col * 4.6, 1.85 + row * 1.65, 4.4, 1.45, t, "지표 · 기준");
  });
}

// 11. 평가 결과
{
  const s = content(S3, "평가 결과", "파인튜닝 모델이 Base보다 나아졌는가", "team", "1:00",
    "근거: training/interest/outputs/eval (gitignore라 수치를 슬라이드에 직접 기입).\n팀원 추가: 이자/연체 Base 대비 지표, 라우터 정확도, 잔액·대출 에이전트 결과.");
  ph(s, 0.5, 1.85, 2.9, 3.2, "핵심 수치 1개", "예: 규칙 준수율 Base → 최신", "team");
  ph(s, 3.7, 1.85, 5.8, 1.9, "Base 대비 지표 표·차트", "이자/연체 에이전트", "team");
  ph(s, 3.7, 3.95, 5.8, 1.1, "다른 모델 지표", "라우터 정확도 · 잔액 · 대출", "team");
}

// 12. 실패 분석과 교훈
{
  const s = content(S3, "실패 분석과 교훈", "자동 지표만으로는 지어낸 답을 다 잡지 못한다", "doc", "0:40",
    "근거: docs/agent-interest/REPORT.md §3-1·4.\n말할 것: 실제 문제 2유형(단정·약속), Base가 더 심하게 지어냈지만 점수에 안 드러남 → 사람 평가·출력 검증.");
  ph(s, 0.5, 1.85, 4.35, 3.2, "틀린 답 사례", "질문 · 모델 답 · 판정");
  ph(s, 5.15, 1.85, 4.35, 3.2, "교훈과 대응", "출력 검증 · 사람 평가 · 데이터 보강");
}

// 13. 데모
{
  const s = content(S4, "데모", "대표 시나리오 네 가지를 실제 화면으로 보여준다", "cap", "1:30",
    "근거: backend/README.md 구동 절차, docs/frontend/PRD.md.\n준비: 라이브 데모 또는 녹화 영상. 실패 대비 캡처 백업.");
  ph(s, 0.5, 1.85, 5.6, 3.2, "화면 캡처 · 영상", "챗봇 UI", "cap");
  ["잔액 조회 (슬롯 치환)", "복합 문의 되묻기", "이자/연체 답변", "미지원 주제 안내"].forEach((t, i) => {
    ph(s, 6.4, 1.85 + i * 0.82, 3.1, 0.7, `${i + 1}. ${t}`);
  });
}

// 14. 달성 현황과 향후 과제
{
  const s = content(S4, "달성 현황과 향후 과제", "인수 기준 8개 중 무엇을 달성했고, 무엇이 남았나", "team", "0:40",
    "근거: docs/PRD.md 인수 기준·MVP 제외, REPORT.md §5.\n팀원 추가: 응답 시간 측정, Windows·Mac 동작, 기준별 결과.");
  ph(s, 0.5, 1.85, 5.6, 3.2, "인수 기준 달성 표", "기준 8개 × 결과", "team");
  ph(s, 6.4, 1.85, 3.1, 3.2, "향후 과제", "미지원 주제 · 사람 평가 · 스트리밍 등");
}

// 15. Q&A
{
  const s = pres.addSlide(); pageNo++;
  s.background = { color: C.ink };
  txt(s, "Q&A", { x: 0.7, y: 1.9, w: 8.6, h: 1.0, fontSize: 44, bold: true, color: C.white });
  txt(s, "감사합니다", { x: 0.7, y: 2.9, w: 8.6, h: 0.5, fontSize: 18, color: "CBD5E1" });
  txt(s, "[저장소 링크 · 연락처]", { x: 0.7, y: 4.4, w: 6, h: 0.35, fontSize: 12, color: "94A3B8" });
}

pres.writeFile({ fileName: process.argv[2] }).then(f => console.log("wrote", f));
