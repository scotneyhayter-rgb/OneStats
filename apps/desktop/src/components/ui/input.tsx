import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

const base =
  "w-full rounded-[var(--radius-app)] border border-border bg-card text-sm text-foreground " +
  "placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-[var(--ring)] " +
  "disabled:pointer-events-none disabled:opacity-50";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(base, "h-9 px-3", className)} {...props} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(base, "min-h-[72px] px-3 py-2", className)} {...props} />;
}
