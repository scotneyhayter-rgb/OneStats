import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { Button } from "./button";

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

/** Lightweight modal (no portal dependency) with an overlay; used for forms and confirmations.
 *  Closes on Escape, keeps Tab focus inside the dialog while open, and restores focus to the
 *  element that opened it on close. */
export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    // Remember what was focused so we can hand focus back when the dialog closes.
    const restoreTo = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key === "Tab") {
        const dialog = dialogRef.current;
        if (!dialog) return;
        const items = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
          (el) => el.offsetParent !== null || el === dialog,
        );
        if (items.length === 0) {
          e.preventDefault();
          dialog.focus();
          return;
        }
        const first = items[0];
        const last = items[items.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey && (active === first || active === dialog)) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    // Move focus into the dialog so keyboard users land inside it and Escape works immediately.
    dialogRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      // Return focus to the control that opened the dialog, if it is still around.
      if (restoreTo && document.contains(restoreTo)) restoreTo.focus();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden />
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative z-10 flex w-full max-w-lg flex-col rounded-[var(--radius-app)] border border-border bg-card shadow-lg outline-none"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-[var(--radius-app)] p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-auto p-5">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-border px-5 py-3">{footer}</div>
        )}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onCancel}
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={onConfirm}
            disabled={busy}
            className={danger ? "bg-danger text-white hover:opacity-90" : undefined}
          >
            {busy ? "Working..." : confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-sm text-muted-foreground">{description}</div>
    </Modal>
  );
}
