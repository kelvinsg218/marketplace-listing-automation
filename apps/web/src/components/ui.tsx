"use client";

import { forwardRef, useEffect, useId, useRef } from "react";
import { Loader2, X } from "lucide-react";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
const BUTTON: Record<ButtonVariant, string> = {
  primary: "bg-accent text-on-accent hover:bg-accent-2 font-semibold",
  secondary: "bg-card text-fg border border-line hover:border-line-strong hover:bg-card-hover",
  ghost: "text-muted hover:text-fg hover:bg-card",
  danger: "bg-transparent text-danger border border-danger/40 hover:bg-danger/10",
};

export const Button = forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant; busy?: boolean; size?: "sm" | "md";
}>(function Button({ variant = "secondary", busy, size = "md", className, children, disabled, ...rest }, ref) {
  return (
    <button ref={ref} disabled={disabled || busy} {...rest}
      className={cx("inline-flex items-center justify-center gap-2 rounded-md transition-colors duration-150",
        "disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap",
        size === "sm" ? "h-8 px-3 text-[13px]" : "h-10 px-4 text-sm", BUTTON[variant], className)}>
      {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
});

export function Field({ label, hint, error, children, className }: {
  label: string; hint?: string; error?: string; children: (id: string, describedBy?: string) => React.ReactNode; className?: string;
}) {
  const id = useId();
  const msgId = error || hint ? `${id}-msg` : undefined;
  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-[13px] font-medium text-muted">{label}</label>
      {children(id, msgId)}
      {(error || hint) && (
        <p id={msgId} className={cx("text-xs", error ? "text-danger" : "text-faint")}>{error ?? hint}</p>
      )}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }>(
  function Input({ className, invalid, ...rest }, ref) {
    return (
      <input ref={ref} aria-invalid={invalid || undefined} {...rest}
        className={cx("h-10 w-full rounded-md bg-bg-2 border px-3 text-sm text-fg placeholder:text-faint",
          "transition-colors focus:outline-none focus:border-accent",
          invalid ? "border-danger" : "border-line hover:border-line-strong", className)} />
    );
  });

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx("min-h-28 w-full rounded-md bg-bg-2 border border-line px-3 py-2 text-sm",
    "hover:border-line-strong focus:outline-none focus:border-accent", props.className)} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx("h-10 rounded-md bg-bg-2 border border-line px-3 text-sm text-fg",
    "hover:border-line-strong focus:outline-none focus:border-accent", props.className)} />;
}

export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div {...rest} className={cx("rounded-lg border border-line bg-card", className)}>{children}</div>;
}

const TONE = {
  neutral: "bg-line text-muted",
  accent: "bg-accent-soft text-accent-2",
  ok: "bg-ok/12 text-ok",
  warn: "bg-warn/12 text-warn",
  danger: "bg-danger/12 text-danger",
  info: "bg-info/12 text-info",
};
export function Badge({ tone = "neutral", children, className }: { tone?: keyof typeof TONE; children: React.ReactNode; className?: string }) {
  return <span className={cx("inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-medium", TONE[tone], className)}>{children}</span>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("rounded-md bg-line animate-shimmer", className)} />;
}

export function Alert({ tone = "danger", children }: { tone?: "danger" | "info" | "ok"; children: React.ReactNode }) {
  const style = { danger: "border-danger/40 text-danger bg-danger/8", info: "border-info/30 text-info bg-info/8", ok: "border-ok/30 text-ok bg-ok/8" }[tone];
  return <div role={tone === "danger" ? "alert" : "status"} className={cx("rounded-md border px-3 py-2.5 text-sm", style)}>{children}</div>;
}

export function EmptyState({ icon, title, children, action }: { icon: React.ReactNode; title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center text-center gap-3 py-14 px-6">
      <div className="grid place-items-center size-12 rounded-lg bg-accent-soft text-accent">{icon}</div>
      <h3 className="text-base font-semibold">{title}</h3>
      {children && <p className="max-w-md text-sm text-muted">{children}</p>}
      {action}
    </div>
  );
}

/** Right-side panel on desktop, full screen on phones. Escape closes; focus moves into the panel. */
export function Drawer({ open, title, onClose, children, footer }: {
  open: boolean; title: string; onClose: () => void; children: React.ReactNode; footer?: React.ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>("input,select,textarea,button")?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); prev?.focus(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} aria-hidden />
      <div ref={panel} role="dialog" aria-modal="true" aria-label={title}
        className="relative flex h-full w-full sm:max-w-lg flex-col bg-bg-2 border-l border-line shadow-2xl">
        <header className="flex items-center justify-between border-b border-line px-5 h-14 shrink-0">
          <h2 className="text-base font-semibold">{title}</h2>
          <button onClick={onClose} className="rounded-md p-1.5 text-muted hover:text-fg hover:bg-card" aria-label="Fechar">
            <X className="size-5" />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-5 py-5">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-5 py-3 shrink-0">{footer}</footer>}
      </div>
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
      <div className="min-w-0">
        <h1 className="text-[26px] leading-tight font-bold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted max-w-2xl">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
