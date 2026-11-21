import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Accessibility guard for the design tokens.
 *
 * Warning badges and several accent presets used to put white text on colours
 * that only reached 2.95:1-3.5:1, which fails WCAG AA for normal-size text.
 * These checks read the real token file so a future colour change cannot quietly
 * regress contrast.
 */

const candidates = [
  resolve(process.cwd(), "../../packages/design-tokens/src/tokens.css"),
  resolve(process.cwd(), "packages/design-tokens/src/tokens.css"),
];
const tokenPath = candidates.find((candidate) => existsSync(candidate));
if (!tokenPath) throw new Error(`Design tokens not found in: ${candidates.join(", ")}`);
const css = readFileSync(tokenPath, "utf8");

type Tokens = Record<string, string>;

function block(selectorPattern: RegExp): Tokens {
  const match = selectorPattern.exec(css);
  if (!match) throw new Error(`Token block not found: ${selectorPattern}`);
  const body = match[1];
  const tokens: Tokens = {};
  for (const line of body.split("\n")) {
    const declaration = /^\s*--([\w-]+):\s*([^;]+);/.exec(line);
    if (declaration) tokens[declaration[1]] = declaration[2].trim();
  }
  return tokens;
}

function channels(token: string): [number, number, number] {
  const match = /^([\d.]+)\s+([\d.]+)%\s+([\d.]+)%$/.exec(token);
  if (!match) throw new Error(`Unsupported colour token: ${token}`);
  return [Number(match[1]) / 360, Number(match[2]) / 100, Number(match[3]) / 100];
}

function rgb(token: string): [number, number, number] {
  const [h, s, l] = channels(token);
  if (s === 0) return [l, l, l];
  const hue = (p: number, q: number, t: number): number => {
    let value = t;
    if (value < 0) value += 1;
    if (value > 1) value -= 1;
    if (value < 1 / 6) return p + (q - p) * 6 * value;
    if (value < 1 / 2) return q;
    if (value < 2 / 3) return p + (q - p) * (2 / 3 - value) * 6;
    return p;
  };
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  return [hue(p, q, h + 1 / 3), hue(p, q, h), hue(p, q, h - 1 / 3)];
}

function luminance(token: string): number {
  const [r, g, b] = rgb(token).map((value) =>
    value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(foreground: string, background: string): number {
  const a = luminance(foreground);
  const b = luminance(background);
  const lighter = Math.max(a, b);
  const darker = Math.min(a, b);
  return (lighter + 0.05) / (darker + 0.05);
}

/** A colour laid over another at the opacity used by tinted badges. */
function blend(foreground: string, background: string, alpha: number): string {
  const [fr, fg, fb] = rgb(foreground);
  const [br, bg, bb] = rgb(background);
  const toHsl = (value: number): string => (value * 100).toFixed(2);
  const mixed: [number, number, number] = [
    alpha * fr + (1 - alpha) * br,
    alpha * fg + (1 - alpha) * bg,
    alpha * fb + (1 - alpha) * bb,
  ];
  const [r, g, b] = mixed;
  // Convert back to HSL channels so the contrast helper can parse it.
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const lightness = (max + min) / 2;
  let hue = 0;
  let saturation = 0;
  if (max !== min) {
    const delta = max - min;
    saturation = lightness > 0.5 ? delta / (2 - max - min) : delta / (max + min);
    if (max === r) hue = ((g - b) / delta + (g < b ? 6 : 0)) / 6;
    else if (max === g) hue = ((b - r) / delta + 2) / 6;
    else hue = ((r - g) / delta + 4) / 6;
  }
  return `${(hue * 360).toFixed(4)} ${toHsl(saturation)}% ${toHsl(lightness)}%`;
}

const light = block(/:root\s*\{([\s\S]*?)\n\}/);
const dark = block(/\.dark\s*\{([\s\S]*?)\n\}/);

const accents = [
  "indigo",
  "violet",
  "blue",
  "teal",
  "emerald",
  "amber",
  "rose",
] as const;

function accentTokens(name: string, theme: "light" | "dark"): Tokens {
  return theme === "light"
    ? block(new RegExp(`:root\\[data-accent="${name}"\\]\\s*\\{([\\s\\S]*?)\\n\\}`))
    : block(new RegExp(`\\.dark\\[data-accent="${name}"\\]\\s*\\{([\\s\\S]*?)\\n\\}`));
}

function expectAtLeast(value: number, minimum: number, label: string): void {
  expect(value, `${label} is ${value.toFixed(2)}:1`).toBeGreaterThanOrEqual(minimum);
}

describe("design token contrast", () => {
  it("keeps body and muted text readable on both themes", () => {
    for (const [name, tokens] of [
      ["light", light],
      ["dark", dark],
    ] as const) {
      expectAtLeast(
        contrast(tokens.foreground, tokens.background),
        4.5,
        `${name} foreground on background`,
      );
      expectAtLeast(
        contrast(tokens["card-foreground"] ?? tokens.foreground, tokens.card),
        4.5,
        `${name} card foreground`,
      );
      expectAtLeast(
        contrast(tokens["muted-foreground"], tokens.background),
        4.5,
        `${name} muted text on background`,
      );
      expectAtLeast(
        contrast(tokens["muted-foreground"], tokens.muted),
        4.5,
        `${name} muted text on muted surface`,
      );
      expectAtLeast(
        contrast(tokens["secondary-foreground"], tokens.secondary),
        4.5,
        `${name} secondary label`,
      );
    }
  });

  it("keeps status labels above 4.5:1", () => {
    for (const [name, tokens] of [
      ["light", light],
      ["dark", dark],
    ] as const) {
      for (const role of ["primary", "destructive", "success", "warning", "info"]) {
        expectAtLeast(
          contrast(tokens[`${role}-foreground`], tokens[role]),
          4.5,
          `${name} ${role} label`,
        );
      }
    }
  });

  it("keeps status colours usable as text and icons on the page", () => {
    for (const [name, tokens] of [
      ["light", light],
      ["dark", dark],
    ] as const) {
      // Warning is rendered as small text (stale OCR, unsaved corrections).
      expectAtLeast(
        contrast(tokens.warning, tokens.background),
        4.5,
        `${name} warning text`,
      );
      // Success and destructive are used for icons and badges.
      expectAtLeast(
        contrast(tokens.success, tokens.background),
        3,
        `${name} success icon`,
      );
      expectAtLeast(
        contrast(tokens.destructive, tokens.background),
        3,
        `${name} destructive icon`,
      );
      // Badge text sits on a 12% tint of the same colour.
      for (const role of ["success", "warning", "destructive"]) {
        expectAtLeast(
          contrast(tokens[role], blend(tokens[role], tokens.background, 0.12)),
          4.5,
          `${name} ${role} badge text`,
        );
      }
    }
  });

  it("keeps every accent preset readable in both themes", () => {
    for (const accent of accents) {
      const lightAccent = accentTokens(accent, "light");
      expectAtLeast(
        contrast(lightAccent.primary, light["primary-foreground"]),
        4.5,
        `light ${accent} button label`,
      );
      expectAtLeast(
        contrast(lightAccent.primary, light.background),
        4.5,
        `light ${accent} accent text`,
      );

      const darkAccent = accentTokens(accent, "dark");
      expectAtLeast(
        contrast(darkAccent.primary, darkAccent["primary-foreground"]),
        4.5,
        `dark ${accent} button label`,
      );
      expectAtLeast(
        contrast(darkAccent.primary, dark.background),
        4.5,
        `dark ${accent} accent text`,
      );
    }
  });
});
