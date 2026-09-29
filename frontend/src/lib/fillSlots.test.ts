import { describe, expect, it } from "vitest";
import { fillSlots, type SlotPart } from "./fillSlots";

const MISSING = "확인할 수 없습니다";

describe("fillSlots", () => {
  describe("문서 예시", () => {
    it("값이 있는 슬롯은 slot: true 조각으로 치환한다", () => {
      const parts: SlotPart[] = fillSlots("현재 잔액은 {{balance}}입니다.", {
        balance: "1,234,567원",
      });
      expect(parts).toEqual([
        { text: "현재 잔액은 ", slot: false },
        { text: "1,234,567원", slot: true },
        { text: "입니다.", slot: false },
      ]);
    });

    it("slots에 없는 슬롯은 '확인할 수 없습니다'(slot: false)로 바꾸고 앞뒤 조각과 합치지 않는다", () => {
      expect(fillSlots("현재 잔액은 {{balance}}입니다.", {})).toEqual([
        { text: "현재 잔액은 ", slot: false },
        { text: MISSING, slot: false },
        { text: "입니다.", slot: false },
      ]);
    });
  });

  describe("슬롯이 없는 문장", () => {
    it("조각 하나를 돌려준다", () => {
      expect(fillSlots("무엇을 도와드릴까요?", {})).toEqual([
        { text: "무엇을 도와드릴까요?", slot: false },
      ]);
    });

    it("text에 없는 slots 키는 무시한다", () => {
      expect(fillSlots("무엇을 도와드릴까요?", { balance: "1,234,567원" })).toEqual([
        { text: "무엇을 도와드릴까요?", slot: false },
      ]);
    });

    it("빈 문자열이면 []를 돌려준다", () => {
      expect(fillSlots("", {})).toEqual([]);
      expect(fillSlots("", { balance: "1,234,567원" })).toEqual([]);
    });
  });

  describe("여러 슬롯", () => {
    it("한 문장의 여러 슬롯을 모두 치환한다", () => {
      expect(
        fillSlots("{{account}} 계좌의 잔액은 {{balance}}입니다.", {
          account: "입출금 1",
          balance: "1,234,567원",
        }),
      ).toEqual([
        { text: "입출금 1", slot: true },
        { text: " 계좌의 잔액은 ", slot: false },
        { text: "1,234,567원", slot: true },
        { text: "입니다.", slot: false },
      ]);
    });

    it("같은 슬롯이 반복되면 매번 치환한다", () => {
      expect(fillSlots("{{balance}} 맞나요? {{balance}}", { balance: "10원" })).toEqual([
        { text: "10원", slot: true },
        { text: " 맞나요? ", slot: false },
        { text: "10원", slot: true },
      ]);
    });

    it("값이 있는 슬롯과 없는 슬롯이 섞여 있으면 없는 슬롯만 바꾼다", () => {
      expect(fillSlots("잔액 {{balance}}, 한도 {{limit}}", { balance: "10원" })).toEqual([
        { text: "잔액 ", slot: false },
        { text: "10원", slot: true },
        { text: ", 한도 ", slot: false },
        { text: MISSING, slot: false },
      ]);
    });
  });

  describe("슬롯 이름", () => {
    it("이름 앞뒤 공백은 trim한 뒤 찾는다", () => {
      expect(fillSlots("잔액 {{ balance }}", { balance: "10원" })).toEqual([
        { text: "잔액 ", slot: false },
        { text: "10원", slot: true },
      ]);
    });

    it("이름이 빈 문자열인 토큰은 slots를 보지 않고 값이 없는 슬롯으로 본다", () => {
      const slots = { "": "빈 키", " ": "공백 키" };
      expect(fillSlots("{{}}", slots)).toEqual([{ text: MISSING, slot: false }]);
      expect(fillSlots("{{ }}", slots)).toEqual([{ text: MISSING, slot: false }]);
    });

    it("상속 속성 이름은 slots의 자기 속성이 아니므로 값이 없는 슬롯이다", () => {
      expect(fillSlots("{{toString}}", {})).toEqual([{ text: MISSING, slot: false }]);
      expect(fillSlots("{{constructor}}", {})).toEqual([{ text: MISSING, slot: false }]);
      expect(fillSlots("{{hasOwnProperty}}", {})).toEqual([{ text: MISSING, slot: false }]);
      expect(fillSlots("{{__proto__}}", {})).toEqual([{ text: MISSING, slot: false }]);
    });

    it("자기 속성이면 상속 속성과 이름이 같아도 그 값을 쓴다", () => {
      expect(fillSlots("{{toString}}", { toString: "값" })).toEqual([
        { text: "값", slot: true },
      ]);
    });
  });

  describe("슬롯 값", () => {
    it("값이 빈 문자열이면 값이 없는 슬롯이다", () => {
      expect(fillSlots("잔액 {{balance}}", { balance: "" })).toEqual([
        { text: "잔액 ", slot: false },
        { text: MISSING, slot: false },
      ]);
    });

    it("공백만 있는 값은 빈 문자열이 아니므로 그대로 넣는다", () => {
      expect(fillSlots("{{balance}}", { balance: " " })).toEqual([
        { text: " ", slot: true },
      ]);
    });

    it("값 안의 슬롯 토큰은 다시 치환하지 않는다", () => {
      expect(fillSlots("{{a}}", { a: "{{b}}", b: "치환되면 안 됨" })).toEqual([
        { text: "{{b}}", slot: true },
      ]);
    });

    it("값 안의 $ 패턴도 글자 그대로 넣는다", () => {
      expect(fillSlots("잔액 {{balance}}", { balance: "$& $1 $$원" })).toEqual([
        { text: "잔액 ", slot: false },
        { text: "$& $1 $$원", slot: true },
      ]);
    });
  });

  describe("토큰이 아닌 중괄호", () => {
    it("단일 중괄호는 일반 글자다", () => {
      expect(fillSlots("{a} 입니다", { a: "값" })).toEqual([
        { text: "{a} 입니다", slot: false },
      ]);
    });

    it("짝이 맞지 않는 중괄호는 일반 글자다", () => {
      expect(fillSlots("{{a 입니다", { a: "값" })).toEqual([
        { text: "{{a 입니다", slot: false },
      ]);
      expect(fillSlots("a}} 입니다", { a: "값" })).toEqual([
        { text: "a}} 입니다", slot: false },
      ]);
      expect(fillSlots("{{a} 입니다", { a: "값" })).toEqual([
        { text: "{{a} 입니다", slot: false },
      ]);
    });

    it("이름에 중괄호가 들어가면 토큰이 아니다", () => {
      expect(fillSlots("{{a{b}}", { a: "값", "a{b": "값" })).toEqual([
        { text: "{{a{b}}", slot: false },
      ]);
    });

    it("토큰 바깥의 남는 중괄호는 일반 글자 조각이 된다", () => {
      expect(fillSlots("{{{a}}}", { a: "값" })).toEqual([
        { text: "{", slot: false },
        { text: "값", slot: true },
        { text: "}", slot: false },
      ]);
    });
  });

  describe("조각 경계", () => {
    it("문장이 토큰으로 시작하고 끝나도 빈 조각을 만들지 않는다", () => {
      expect(fillSlots("{{a}}와 {{b}}", { a: "가", b: "나" })).toEqual([
        { text: "가", slot: true },
        { text: "와 ", slot: false },
        { text: "나", slot: true },
      ]);
    });

    it("토큰이 붙어 있어도 빈 조각을 만들지 않는다", () => {
      expect(fillSlots("{{a}}{{b}}", { a: "가", b: "나" })).toEqual([
        { text: "가", slot: true },
        { text: "나", slot: true },
      ]);
    });

    it("붙어 있는 값이 없는 슬롯끼리도 합치지 않는다", () => {
      expect(fillSlots("{{a}}{{b}}", {})).toEqual([
        { text: MISSING, slot: false },
        { text: MISSING, slot: false },
      ]);
    });
  });

  describe("줄바꿈", () => {
    it("text와 슬롯 값의 \\n을 글자 그대로 남긴다", () => {
      expect(
        fillSlots("최근 거래내역\n{{transactions}}\n끝", {
          transactions: "09-01 입금 10원\n09-02 출금 5원",
        }),
      ).toEqual([
        { text: "최근 거래내역\n", slot: false },
        { text: "09-01 입금 10원\n09-02 출금 5원", slot: true },
        { text: "\n끝", slot: false },
      ]);
    });
  });

  describe("순수 함수", () => {
    it("slots 인자를 바꾸지 않는다", () => {
      const slots = Object.freeze({ balance: "10원" });
      fillSlots("{{balance}} {{missing}}", slots);
      expect(slots).toEqual({ balance: "10원" });
    });

    it("같은 입력으로 연달아 불러도 결과가 같다", () => {
      const first = fillSlots("{{a}} 그리고 {{a}}", { a: "가" });
      const second = fillSlots("{{a}} 그리고 {{a}}", { a: "가" });
      expect(second).toEqual(first);
    });
  });
});
