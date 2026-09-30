import { act, render, screen } from "@testing-library/react";
import type { ScriptProps } from "next/script";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ScrollWorld } from "./ScrollWorld";

// 가짜 Script — 실제 스크립트는 불러오지 않고 props만 남긴다. onReady·onError는 테스트가 직접 부른다.
const script = vi.hoisted(() => ({ props: undefined as ScriptProps | undefined }));
vi.mock("next/script", () => ({
  default: (props: ScriptProps) => {
    script.props = props;
    return null;
  },
}));

type Landing = {
  brand: { name: string; href: string };
  cta: { label: string; href: string };
  connectors: unknown[];
  sections: {
    id: string;
    still: string;
    clip?: string;
    cta?: { primary: { label: string; href: string }; secondary?: unknown };
  }[];
};

// 실제 엔진처럼 컨테이너에 자식 요소를 붙인다.
function fakeMount() {
  return vi.fn((container: HTMLElement) => {
    container.appendChild(document.createElement("div"));
  });
}

function ready() {
  act(() => {
    script.props?.onReady?.();
  });
}

beforeEach(() => {
  script.props = undefined;
  delete window.mountScrollWorld;
  window.location.hash = "";
});

describe("ScrollWorld", () => {
  it("엔진을 afterInteractive로 불러온다", () => {
    render(<ScrollWorld />);

    expect(script.props).toMatchObject({
      src: "/scroll-world/scrub-engine.js",
      strategy: "afterInteractive",
    });
  });

  it("처음 렌더에서는 min-h-dvh 컨테이너만 있고 아직 마운트하지 않는다", () => {
    const mount = fakeMount();
    window.mountScrollWorld = mount;
    render(<ScrollWorld />);

    const container = screen.getByTestId("scroll-world");
    expect(container).toHaveClass("min-h-dvh");
    expect(container).not.toHaveClass("hidden");
    expect(mount).not.toHaveBeenCalled();
  });

  it("onReady에서 컨테이너와 랜딩 설정으로 한 번 마운트한다", () => {
    const mount = fakeMount();
    window.mountScrollWorld = mount;
    render(<ScrollWorld />);

    ready();

    expect(mount).toHaveBeenCalledTimes(1);
    const [container, config] = mount.mock.calls[0] as unknown as [HTMLElement, Landing];
    expect(container).toBe(screen.getByTestId("scroll-world"));
    expect(config.sections.map((s) => s.id)).toEqual(["backlog", "finetune", "onboard", "privacy"]);
    for (const s of config.sections) expect(s.still.startsWith("/scroll-world/")).toBe(true);
    expect(config.sections[0].clip).toBe("/scroll-world/vid/scene02.mp4");
    expect(config.brand.name).toBe("Local LLM");
    expect(config.cta.href).toBe("#chat");
    expect(config.sections[3].cta?.primary.href).toBe("#chat");
    expect(config.connectors).toEqual([]);
    expect(container).not.toHaveClass("hidden");
  });

  it("onReady가 두 번 와도 같은 컨테이너에 한 번만 마운트한다", () => {
    const mount = fakeMount();
    window.mountScrollWorld = mount;
    render(<ScrollWorld />);

    ready();
    ready();

    expect(mount).toHaveBeenCalledTimes(1);
  });

  it("onError면 컨테이너를 숨기고 마운트하지 않는다", () => {
    const mount = fakeMount();
    window.mountScrollWorld = mount;
    render(<ScrollWorld />);

    act(() => {
      script.props?.onError?.(new Event("error"));
    });

    expect(screen.getByTestId("scroll-world")).toHaveClass("hidden");
    expect(mount).not.toHaveBeenCalled();
  });

  it("onReady인데 window.mountScrollWorld가 없으면 컨테이너를 숨긴다", () => {
    render(<ScrollWorld />);

    ready();

    expect(screen.getByTestId("scroll-world")).toHaveClass("hidden");
  });

  it("mountScrollWorld가 예외를 던지면 밖으로 내보내지 않고 컨테이너를 숨긴다", () => {
    window.mountScrollWorld = vi.fn(() => {
      throw new Error("boom");
    });
    render(<ScrollWorld />);

    expect(() => ready()).not.toThrow();

    expect(screen.getByTestId("scroll-world")).toHaveClass("hidden");
  });

  it("hash가 #chat이면 마운트 뒤 챗 섹션으로 스크롤한다", () => {
    window.mountScrollWorld = fakeMount();
    window.location.hash = "#chat";
    render(
      <>
        <ScrollWorld />
        <section id="chat" />
      </>,
    );
    const scrollIntoView = vi.fn();
    document.getElementById("chat")!.scrollIntoView = scrollIntoView;

    ready();

    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("hash가 없으면 스크롤하지 않는다", () => {
    window.mountScrollWorld = fakeMount();
    render(
      <>
        <ScrollWorld />
        <section id="chat" />
      </>,
    );
    const scrollIntoView = vi.fn();
    document.getElementById("chat")!.scrollIntoView = scrollIntoView;

    ready();

    expect(scrollIntoView).not.toHaveBeenCalled();
  });
});
