/**
 * Safe client-side palette suggestion from a club logo.
 *
 * Decodes the image on a small canvas, builds a quantised colour histogram, and proposes a coordinated
 * palette (primary / secondary / third / fourth / accent). It deliberately avoids producing unreadable
 * interfaces: near-white and near-black pixels are excluded from the candidate pool, strongly-saturated
 * colours are preferred, and if the logo is monochrome it derives complementary hues rather than
 * inventing arbitrary "official" colours. The administrator always reviews and can edit every value
 * before saving — nothing here is applied automatically.
 */
import { rgbToHex, toRgbTuple } from "./color";

export interface SuggestedPalette {
  primary: string;
  secondary: string;
  third: string;
  fourth: string;
  accent: string;
}

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0;
  const l = (max + min) / 2;
  const d = max - min;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  if (d !== 0) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  return [h, s, l];
}
function hslToHex(h: number, s: number, l: number): string {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  let r = 0, g = 0, b = 0;
  if (h < 60) [r, g, b] = [c, x, 0];
  else if (h < 120) [r, g, b] = [x, c, 0];
  else if (h < 180) [r, g, b] = [0, c, x];
  else if (h < 240) [r, g, b] = [0, x, c];
  else if (h < 300) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  return rgbToHex((r + m) * 255, (g + m) * 255, (b + m) * 255);
}

async function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((res, rej) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => res(img);
    img.onerror = () => rej(new Error("decode"));
    img.src = src;
  });
}

/** Extract a coordinated, readable palette suggestion from a logo image URL. */
export async function suggestPaletteFromLogo(src: string): Promise<SuggestedPalette> {
  const img = await loadImage(src);
  const dim = 64;
  const scale = Math.min(1, dim / Math.max(img.width, img.height));
  const w = Math.max(1, Math.round(img.width * scale));
  const h = Math.max(1, Math.round(img.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("no_canvas");
  ctx.drawImage(img, 0, 0, w, h);
  const { data } = ctx.getImageData(0, 0, w, h);

  // Quantised histogram with a saturation-weighted score, excluding near-white/near-black/transparent.
  const buckets = new Map<string, { count: number; r: number; g: number; b: number; score: number }>();
  for (let i = 0; i < data.length; i += 4) {
    const a = data[i + 3];
    if (a < 128) continue;
    const r = data[i], g = data[i + 1], b = data[i + 2];
    const [, s, l] = rgbToHsl(r, g, b);
    if (l > 0.93 || l < 0.06) continue;        // skip paper-white and near-black
    const key = `${r >> 4}-${g >> 4}-${b >> 4}`; // 4-bit quantise
    const cur = buckets.get(key) ?? { count: 0, r: 0, g: 0, b: 0, score: 0 };
    cur.count += 1; cur.r += r; cur.g += g; cur.b += b;
    cur.score += 1 + s * 3;                     // prefer saturated colours
    buckets.set(key, cur);
  }

  const ranked = [...buckets.values()]
    .map((v) => ({ hex: rgbToHex(v.r / v.count, v.g / v.count, v.b / v.count), score: v.score }))
    .sort((a, b) => b.score - a.score);

  // Pick distinct hues for a coordinated set.
  const chosen: string[] = [];
  const hueOf = (hex: string) => { const [r, g, b] = toRgbTuple(hex); return rgbToHsl(r, g, b)[0]; };
  for (const cand of ranked) {
    const hc = hueOf(cand.hex);
    if (chosen.every((c) => Math.abs(hueOf(c) - hc) > 25 || Math.abs(hueOf(c) - hc) > 335)) {
      chosen.push(cand.hex);
    }
    if (chosen.length >= 5) break;
  }
  // Top up (monochrome logo, or too few distinct hues) with derived complementary hues.
  if (chosen.length === 0) chosen.push("#334155");
  while (chosen.length < 5) {
    const [r, g, b] = toRgbTuple(chosen[0]);
    const [bh, bs, bl] = rgbToHsl(r, g, b);
    const rot = [180, 30, 210, 150][chosen.length - 1] ?? 60;
    chosen.push(hslToHex((bh + rot) % 360, Math.max(0.35, bs), Math.min(0.6, Math.max(0.35, bl))));
  }

  const [primary, secondary, third, fourth, accent] = chosen;
  return { primary, secondary, third, fourth, accent };
}
