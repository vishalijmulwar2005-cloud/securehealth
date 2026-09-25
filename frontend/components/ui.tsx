"use client";
/** Design-system primitives adopted from the verified console's ui.jsx
 * (spec-exact): Button - Card - Stat - Badge - HashChip - Table - Tabs -
 * Slider - Skeleton - EmptyState. Status is NEVER color alone. */
import { useEffect, useState } from "react";

const btnBase = "inline-flex items-center justify-center gap-2 rounded-md px-3.5 py-2 text-sm font-semibold transition-all active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed focus-visible:ring-2 focus-visible:ring-teal";
const btnTones = {
  solid: "bg-ink text-white hover:bg-ink-soft",
  outline: "bg-white text-ink border border-line hover:border-ink-faint",
  teal: "bg-teal-wash text-teal-deep border border-teal/30 hover:bg-teal hover:text-white",
  amber: "bg-amber-wash text-amber-deep border border-amber/30 hover:bg-amber hover:text-white",
  alarm: "bg-alarm text-white hover:bg-[#a8352f]",
  ghost: "text-ink-soft hover:bg-paper hover:text-ink",
};

export function Button({ tone, kind, loading, className = "", children, ...rest }:
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    tone?: "solid" | "outline" | "teal" | "amber" | "alarm" | "ghost"; loading?: boolean;
    kind?: "primary" | "secondary" | "danger" | "ghost";
  }) {
  const effective = tone ?? ({ primary: "solid", secondary: "outline", danger: "alarm", ghost: "ghost" } as const)[kind ?? "primary"];
  return (
    <button className={`${btnBase} ${btnTones[effective]} ${className}`}
      disabled={loading || rest.disabled} {...rest}>
      {loading && <span className="inline-block h-4 w-4 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input {...props}
      className={`w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-ink
        placeholder:text-ink-faint focus:border-teal focus:outline-none ${props.className ?? ""}`} />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props}
      className={`w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-ink
        focus:border-teal focus:outline-none ${props.className ?? ""}`} />
  );
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea {...props}
      className={`w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-ink
        focus:border-teal focus:outline-none ${props.className ?? ""}`} />
  );
}

export function Card({ className = "", title, action, children }: {
  className?: string; title?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className={`bg-white border border-line rounded-lg p-5 ${className}`}>
      {title && (
        <div className={`mb-3 ${action ? "flex items-center justify-between gap-2" : ""}`}>
          <h2 className="flex items-center gap-2 text-sm font-bold text-ink">
            <span aria-hidden className="h-3.5 w-1 rounded-full bg-teal" />
            {title}
          </h2>
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

export function PageHead({ kicker, title, sub, actions }: {
  kicker?: string; title: string; sub?: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
      <div>
        {kicker && <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-faint mb-1">{kicker}</div>}
        <h1 className="text-[28px] font-bold leading-tight text-ink">{title}</h1>
        {sub && <p className="text-[15px] text-ink-soft mt-1">{sub}</p>}
      </div>
      {actions && <div className="flex gap-2 flex-wrap">{actions}</div>}
    </div>
  );
}

export function SectionHead({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-3">
      <h2 className="text-base font-bold text-ink">{title}</h2>
      {sub && <p className="text-sm text-ink-soft">{sub}</p>}
    </div>
  );
}

export function Stat({ label, value, note, mono }: { label: string; value: string | number; note?: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-sm text-ink-soft">{label}</div>
      <div className={`text-[27px] font-bold tnum leading-tight text-ink ${mono ? "font-mono" : ""}`}>{value}</div>
      {note && <div className="text-xs text-ink-faint">{note}</div>}
    </div>
  );
}

const badgeTones = {
  teal: "bg-teal-wash text-teal-deep",
  amber: "bg-amber-wash text-amber-deep",
  alarm: "bg-alarm-wash text-alarm",
  ink: "bg-ink text-white",
  plain: "bg-paper text-ink-soft border border-line",
};
const glyphs = { done: "✓", progress: "◐", failed: "✕", expired: "○" };

export function Badge({ tone = "plain", glyph, children }: {
  tone?: keyof typeof badgeTones; glyph?: "done" | "progress" | "failed" | "expired"; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${badgeTones[tone]}`}>
      {glyph && <span aria-hidden>{glyphs[glyph]}</span>}{children}
    </span>
  );
}

/** Status badge with glyph + text (never color alone). */
const STATUS_MAP: Record<string, { tone: keyof typeof badgeTones; glyph: keyof typeof glyphs; label: string }> = {
  PENDING: { tone: "amber", glyph: "progress", label: "PENDING" },
  ACTIVE: { tone: "teal", glyph: "done", label: "ACTIVE" },
  APPROVED: { tone: "teal", glyph: "done", label: "APPROVED" },
  COMPLETED: { tone: "teal", glyph: "done", label: "COMPLETED" },
  GRANTED: { tone: "teal", glyph: "done", label: "GRANTED" },
  SUCCESS: { tone: "teal", glyph: "done", label: "SUCCESS" },
  REJECTED: { tone: "alarm", glyph: "failed", label: "REJECTED" },
  REVOKED: { tone: "alarm", glyph: "failed", label: "REVOKED" },
  EXPIRED: { tone: "alarm", glyph: "expired", label: "EXPIRED" },
  DELETED: { tone: "alarm", glyph: "failed", label: "DELETED" },
  FAILED: { tone: "alarm", glyph: "failed", label: "FAILED" },
  DENIED: { tone: "alarm", glyph: "failed", label: "DENIED" },
  SUSPENDED: { tone: "amber", glyph: "progress", label: "SUSPENDED" },
  DISABLED: { tone: "plain", glyph: "expired", label: "DISABLED" },
  QUEUED: { tone: "amber", glyph: "progress", label: "QUEUED" },
  PROCESSING: { tone: "amber", glyph: "progress", label: "PROCESSING" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS_MAP[status] ?? { tone: "plain" as const, glyph: "progress" as const, label: status };
  return <Badge tone={s.tone} glyph={s.glyph}>{s.label}</Badge>;
}

export function HashChip({ hash, label }: { hash: string | null | undefined; label?: string }) {
  const [copied, setCopied] = useState(false);
  const short = hash && hash.length > 14 ? `${hash.slice(0, 10)}…${hash.slice(-4)}` : (hash || "—");
  return (
    <button
      title={label ? `${label}: ${hash}` : (hash ?? "")}
      onClick={() => { if (hash) { navigator.clipboard?.writeText(hash).catch(() => {}); setCopied(true); setTimeout(() => setCopied(false), 1200); } }}
      className="font-mono text-xs bg-paper border border-line rounded px-2 py-0.5 hover:border-teal transition-colors">
      {copied ? "copied ✓" : short}
    </button>
  );
}

export function Table({ columns, rows, empty = "No rows yet." }: {
  columns: string[]; rows: React.ReactNode[][]; empty?: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line">
            {columns.map((c) => (
              <th key={c} className="text-left text-xs font-semibold uppercase tracking-wide text-ink-faint pb-2 pr-4">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line/60 last:border-0 hover:bg-paper/60">
              {r.map((cell, j) => <td key={j} className="py-2 pr-4 tnum align-top">{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <EmptyState title="Nothing here" hint={empty} />}
    </div>
  );
}

export function Tabs({ options, value, onChange }: {
  options: { value: string; label: string }[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex gap-2 flex-wrap" role="tablist">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} onClick={() => onChange(o.value)}
          className={`rounded-md px-3 py-1.5 text-sm font-semibold border transition ${
            value === o.value ? "bg-teal-wash border-teal/40 text-teal-deep" : "bg-white border-line text-ink-soft hover:text-ink"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Slider({ label, min, max, step, value, onChange, disabled }: {
  label: string; min: number; max: number; step: number; value: number;
  onChange: (v: number) => void; disabled?: boolean }) {
  return (
    <label className="block text-sm font-medium text-ink-soft">
      <span className="flex justify-between"><span>{label}</span>
        <span className="font-semibold text-ink tnum">{value}</span></span>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))} className="mt-1 w-full" />
    </label>
  );
}

export function EmptyState({ title, hint, what, next }: {
  title?: string; hint?: string; what?: string; next?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-line bg-paper px-4 py-8 text-center">
      <p className="text-sm text-ink-soft">{title ?? what ?? "Nothing here."}</p>
      {(hint ?? next) && <p className="mt-1 text-xs text-ink-faint">{hint ?? next}</p>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-alarm/30 bg-alarm-wash px-4 py-3">
      <p className="text-sm text-alarm">⚠ {message}</p>
      {onRetry && <button onClick={onRetry} className="mt-1 text-xs font-medium text-teal-deep underline">Retry</button>}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="space-y-2" role="status" aria-live="polite">
      <div className="skeleton-shine h-4 w-1/3 rounded" />
      <div className="skeleton-shine h-4 w-2/3 rounded" />
      <div className="skeleton-shine h-4 w-1/2 rounded" />
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function Banner({ kind, children }: { kind: "ok" | "error" | "info"; children: React.ReactNode }) {
  const styles = {
    ok: "border-teal/30 bg-teal-wash text-teal-deep",
    error: "border-alarm/30 bg-alarm-wash text-alarm",
    info: "border-line bg-paper text-ink-soft",
  }[kind];
  return (
    <div role="status" className={`rounded-lg border px-3 py-2 text-sm ${styles}`}>
      {kind === "ok" ? "✓ " : kind === "error" ? "⚠ " : ""}{children}
    </div>
  );
}

/** Destructive confirmation: deliberate two-step with consequence stated. */
export function ConfirmButton({ label, confirmLabel, consequence, onConfirm, disabled }:
  { label: string; confirmLabel: string; consequence: string; onConfirm: () => void; disabled?: boolean }) {
  const [arming, setArming] = useState(false);
  useEffect(() => {
    if (!arming) return;
    const t = setTimeout(() => setArming(false), 4000);
    return () => clearTimeout(t);
  }, [arming]);
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <Button tone={arming ? "alarm" : "outline"} disabled={disabled}
        onClick={() => (arming ? onConfirm() : setArming(true))}>
        {arming ? confirmLabel : label}
      </Button>
      {arming && <span className="text-[11px] text-alarm">{consequence}</span>}
    </span>
  );
}

export function StatTile(props: { label: string; value: string | number; href?: string; tone?: string }) {
  return <Stat label={props.label} value={props.value} />;
}
