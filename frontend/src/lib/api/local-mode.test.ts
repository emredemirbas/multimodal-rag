import { describe, expect, it } from "vitest";
import { parseAnswerMode, parseRetrievalMode } from "@/lib/api/chat-contracts";

describe("portfolio answer mode contract", () => {
  it("accepts only explicit no-paid-provider modes", () => {
    expect(parseAnswerMode({ mode: "extractive", spend_policy: "no-paid-provider" })).toBe("extractive");
    expect(parseAnswerMode({ mode: "ollama", spend_policy: "no-paid-provider" })).toBe("ollama");
    expect(() => parseAnswerMode({ mode: "cloud", spend_policy: "no-paid-provider" })).toThrow();
    expect(() => parseAnswerMode({ mode: "ollama", spend_policy: "paid" })).toThrow();
  });
  it('requires an explicit supported retrieval mode', () => {
    expect(parseRetrievalMode({retrieval:'local-semantic-and-lexical'})).toBe('local-semantic-and-lexical');
    expect(() => parseRetrievalMode({retrieval:'cloud'})).toThrow();
    expect(() => parseRetrievalMode({})).toThrow();
  });
});
