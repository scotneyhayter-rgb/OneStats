import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge conditional class names, resolving Tailwind conflicts. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Open/save a blob: URL produced after an await. Calling window.open() after an await is outside the
 * click gesture, so popup blockers stop it ("does not open"). A programmatic anchor with `download` is not
 * popup-blocked and works in both the browser and the Tauri webview. The object URL is revoked afterwards.
 */
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
