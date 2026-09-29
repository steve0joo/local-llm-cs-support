"use client";

import Script from "next/script";
import { useRef, useState } from "react";

declare global {
  interface Window {
    mountScrollWorld?: (container: HTMLElement, config: object) => void;
  }
}

// 엔진이 innerHTML로 넣으므로 정적 문자열만 둔다. 카피는 docs/frontend/PRD.md "랜딩" 표와 같아야 한다.
const LANDING = {
  brand: { name: "Local LLM", href: "#top" },
  cta: { label: "직접 물어보기", href: "#chat" },
  hint: "스크롤해서 들어가기",
  diveScroll: 1.3,
  crossfade: 0.35, // 연결 클립이 없어서 디졸브를 넓게 둔다
  sections: [
    {
      id: "backlog",
      label: "쌓인 문의",
      still: "/scroll-world/scene02.webp",
      clip: "/scroll-world/vid/scene02.mp4",
      accent: "#E07B2E",
      scroll: 1.6,
      eyebrow: "은행 상담 창구의 하루",
      title: "같은 질문이 매일 쌓입니다.",
      body: "잔액은 얼마인지, 대출 만기는 언제인지, 연체 이자는 얼마인지. 비슷한 문의가 매일 상담 대기열을 채웁니다.",
      tags: ["잔액조회", "대출문의", "이자·연체"],
    },
    {
      id: "finetune",
      label: "상담 데이터 학습",
      still: "/scroll-world/finetune.webp",
      accent: "#3A6FD0",
      scroll: 1.4,
      eyebrow: "은행 상담 데이터로 파인튜닝",
      title: "상담 기록으로 배운 로컬 AI",
      body: "AI Hub 금융 고객상담 데이터 중 은행 상담으로 오픈 모델을 QLoRA 파인튜닝했습니다. 추론은 Ollama로 데모 장비에서 돌아갑니다.",
      tags: ["QLoRA", "로컬 추론"],
    },
    {
      id: "onboard",
      label: "AI 상담 창구",
      still: "/scroll-world/reception.webp",
      accent: "#E5A527",
      scroll: 1.2,
      eyebrow: "라우터 1 · 전문 상담원 3",
      title: "문의마다 맞는 상담원에게.",
      body: "라우터가 문의를 9개 주제로 나눠 잔액조회·대출문의·이자/연체 상담원에게 연결합니다. 두 주제가 섞이면 먼저 되묻고, 아직 못 하는 주제는 상담원 연결을 안내합니다.",
      tags: ["주제 분류", "되묻기", "상담원 안내"],
    },
    {
      id: "privacy",
      label: "개인정보 보호",
      still: "/scroll-world/office.webp",
      accent: "#3A6FD0",
      scroll: 1.3,
      eyebrow: "개인정보는 모델 앞에서 가립니다",
      title: "금액은 화면에서만 채워집니다.",
      body: "고객이 입력한 계좌번호·전화번호·금액은 모델에 닿기 전에 가리고, 조회한 금액은 모델에 넣지 않습니다. 모델은 {{자리표시자}}만 쓰고 실제 값은 화면에서 채웁니다.",
      tags: ["마스킹", "슬롯 치환"],
      cta: { primary: { label: "직접 물어보기", href: "#chat" } },
    },
  ],
  connectors: [],
};

export function ScrollWorld(): React.JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  // onReady는 로드 직후와 다시 마운트될 때마다 불린다. 엔진 DOM이 이미 있으면 다시 넣지 않는다.
  function mount() {
    const container = containerRef.current;
    if (!container || container.childElementCount > 0) return;
    if (typeof window.mountScrollWorld !== "function") {
      setFailed(true);
      return;
    }
    try {
      window.mountScrollWorld(container, LANDING);
    } catch {
      // effect 안에서 불리므로 예외를 올리면 챗까지 함께 내려간다.
      setFailed(true);
      return;
    }
    // /#chat에서 새로고침하면 트랙이 생기기 전 위치로 점프하므로 챗으로 다시 보낸다.
    if (location.hash === "#chat") document.getElementById("chat")?.scrollIntoView();
  }

  return (
    <>
      <div ref={containerRef} data-testid="scroll-world" className={failed ? "hidden" : "min-h-dvh"} />
      <Script
        src="/scroll-world/scrub-engine.js"
        strategy="afterInteractive"
        onReady={mount}
        onError={() => setFailed(true)}
      />
    </>
  );
}
