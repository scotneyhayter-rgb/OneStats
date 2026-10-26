/** Client-side WCAG contrast helpers (mirror of the backend) for the live onboarding
 * preview, where no workspace exists yet to call the branding API. */

const HEX = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

export function isValidHex(v: string): boolean {
  return HEX.test(v);
}

function toRgb(hex: string): [number, number, number] {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function linear(c: number): number {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}
function luminance(hex: string): number {
  const [r, g, b] = toRgb(hex);
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}
export function contrastRatio(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}
export function bestForeground(bg: string): string {
  return contrastRatio(bg, "#000000") >= contrastRatio(bg, "#ffffff") ? "#000000" : "#ffffff";
}
export function meetsAA(bg: string): boolean {
  return contrastRatio(bg, bestForeground(bg)) >= 4.5;
}

function clamp(n: number): number {
  return Math.max(0, Math.min(255, Math.round(n)));
}
export function rgbToHex(r: number, g: number, b: number): string {
  return "#" + [r, g, b].map((c) => clamp(c).toString(16).padStart(2, "0")).join("");
}
export function toRgbTuple(hex: string): [number, number, number] {
  return toRgb(hex);
}
/** Linear blend of two hex colours: t=0 → a, t=1 → b. */
export function mix(a: string, b: string, t: number): string {
  const [r1, g1, b1] = toRgb(a);
  const [r2, g2, b2] = toRgb(b);
  return rgbToHex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t);
}
/** Lighten toward white by amount (0..1). */
export function lighten(hex: string, amount: number): string {
  return mix(hex, "#ffffff", amount);
}
/** Darken toward black by amount (0..1). */
export function darken(hex: string, amount: number): string {
  return mix(hex, "#000000", amount);
}
