import { describe, expect, it } from "vitest";

import { formulaInsertionContent } from "@/lib/formula-insertion";

describe("formula insertion content", () => {
  it("stores the reviewed LaTeX as a display equation", () => {
    const nodes = formulaInsertionContent({
      latex: "  E = mc^2  ",
      numbered: false,
      note: null,
    });

    expect(nodes).toEqual([
      { type: "blockMath", attrs: { latex: "E = mc^2", numbered: false, id: null } },
    ]);
  });

  it("keeps numbering on the node and appends the source note", () => {
    const nodes = formulaInsertionContent({
      latex: "\\frac{a}{b}",
      numbered: true,
      note: "Source: page 4 · equation reviewed from the region crop · unverified",
    });

    const [equation, note] = nodes;
    expect(equation.type).toBe("blockMath");
    expect(equation.attrs?.latex).toBe("\\frac{a}{b}");
    expect(equation.attrs?.numbered).toBe(true);
    // A numbered equation needs its own id so references can resolve it.
    expect(typeof equation.attrs?.id).toBe("string");
    expect(note).toEqual({
      type: "blockquote",
      content: [
        {
          type: "paragraph",
          content: [
            {
              type: "text",
              text: "Source: page 4 · equation reviewed from the region crop · unverified",
            },
          ],
        },
      ],
    });
  });
});
