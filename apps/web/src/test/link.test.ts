import { describe, expect, it } from "vitest";

import { normalizeLinkUrl } from "@/lib/link";

describe("normalizeLinkUrl", () => {
  it("keeps allowed absolute URLs", () => {
    expect(normalizeLinkUrl("https://example.com/a?b=1")).toBe(
      "https://example.com/a?b=1",
    );
    expect(normalizeLinkUrl("http://127.0.0.1:8000")).toBe("http://127.0.0.1:8000");
    expect(normalizeLinkUrl("mailto:reader@example.com")).toBe(
      "mailto:reader@example.com",
    );
  });

  it("upgrades a bare domain to https", () => {
    expect(normalizeLinkUrl("example.com")).toBe("https://example.com");
    expect(normalizeLinkUrl("example.com/path")).toBe("https://example.com/path");
  });

  it("rejects unsafe and ambiguous targets", () => {
    expect(normalizeLinkUrl("javascript:alert(1)")).toBeNull();
    expect(normalizeLinkUrl("JavaScript:alert(1)")).toBeNull();
    expect(normalizeLinkUrl("data:text/html,<script>")).toBeNull();
    expect(normalizeLinkUrl("file:///etc/passwd")).toBeNull();
    expect(normalizeLinkUrl("//evil.example")).toBeNull();
    expect(normalizeLinkUrl("example")).toBeNull();
    expect(normalizeLinkUrl("two words")).toBeNull();
    expect(normalizeLinkUrl("")).toBeNull();
    expect(normalizeLinkUrl("https://")).toBeNull();
  });
});
