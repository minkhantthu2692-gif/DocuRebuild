import { describe, expect, it } from "vitest";

import { isLoopbackUrl, needsPaidApproval } from "@/lib/ai-cost";

describe("AI cost classification", () => {
  it("treats an empty URL and loopback hosts as local", () => {
    expect(isLoopbackUrl("")).toBe(true);
    expect(isLoopbackUrl("   ")).toBe(true);
    expect(isLoopbackUrl("http://127.0.0.1:11434")).toBe(true);
    expect(isLoopbackUrl("http://localhost:1234/v1")).toBe(true);
    expect(isLoopbackUrl("http://[::1]:1234/v1")).toBe(true);
    expect(isLoopbackUrl(undefined)).toBe(true);
  });

  it("does not treat remote hosts as local", () => {
    expect(isLoopbackUrl("https://api.example.com/v1")).toBe(false);
    expect(isLoopbackUrl("http://192.0.2.10:1234")).toBe(false);
    expect(isLoopbackUrl("not a url")).toBe(false);
  });

  it("needs approval for a remote profile unless it is declared free", () => {
    expect(needsPaidApproval(undefined)).toBe(false);
    expect(
      needsPaidApproval({ base_url: "http://127.0.0.1:1234/v1", cost_class: "paid" }),
    ).toBe(false);
    expect(
      needsPaidApproval({ base_url: "https://api.example.com/v1", cost_class: "paid" }),
    ).toBe(true);
    expect(
      needsPaidApproval({ base_url: "https://api.example.com/v1", cost_class: "local" }),
    ).toBe(true);
    expect(
      needsPaidApproval({ base_url: "https://api.example.com/v1", cost_class: "free" }),
    ).toBe(false);
  });
});
