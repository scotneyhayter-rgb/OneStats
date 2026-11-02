import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge conditional class names, resolving Tailwind conflicts. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a recorded-match year span for display: "1919–2020", or just "1919" when first and last are the
 * same year, or null when there is no recorded match (so callers can omit the segment entirely). Never
 * invents a year — an unknown span (no dated match on record) yields null.
 */
export function yearSpan(first?: number | null, last?: number | null): string | null {
  if (!first && !last) return null;
  const a = first ?? last;
  const b = last ?? first;
  return a === b ? `${a}` : `${a}–${b}`;
}

/**
 * Open/save a blob: URL produced after an await. Calling window.open() after an await is outside the
 * click gesture, so popup blockers stop it ("does not open"). A programmatic anchor with `download` is not
 * popup-blocked and works in both the browser and the Tauri webview. The object URL is revoked afterwards.
 */
/**
 * Downscale and re-encode an image on the client before upload, so large phone photos fit comfortably
 * (and storage stays small). Resizes so the longest side is at most `maxDim`px and re-encodes as JPEG.
 * Passes the file through unchanged if it isn't a decodable raster image or is already small.
 */
export async function compressImage(file: File, maxDim = 1280, quality = 0.85): Promise<File> {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return file;
  try {
    const dataUrl: string = await new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(String(r.result));
      r.onerror = () => rej(new Error("read"));
      r.readAsDataURL(file);
    });
    const img: HTMLImageElement = await new Promise((res, rej) => {
      const i = new Image();
      i.onload = () => res(i);
      i.onerror = () => rej(new Error("decode"));
      i.src = dataUrl;
    });
    const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
    if (scale >= 1 && file.size <= 1_500_000) return file;   // already small enough
    const w = Math.max(1, Math.round(img.width * scale));
    const h = Math.max(1, Math.round(img.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(img, 0, 0, w, h);
    const blob: Blob | null = await new Promise((res) => canvas.toBlob(res, "image/jpeg", quality));
    if (!blob || blob.size >= file.size) return blob && blob.size < file.size ? new File([blob], file.name, { type: "image/jpeg" }) : file;
    return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
  } catch {
    return file;   // on any failure, let the server validate the original
  }
}

export function openBlobUrl(url: string, filename: string): void {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => { try { URL.revokeObjectURL(url); } catch { /* already revoked */ } }, 30000);
}
