import type { ReactNode } from "react";
import type { StatusKey, Tone } from "@/lib/types";

/* Small presentational primitives. No state, no client boundary: every page is a
   server component, so these render once on the server and ship as HTML. */

const STATUS: Record<StatusKey, { label: string; tone: Tone }> = {
  verified: { label: "Verified", tone: "good" },
  inspected: { label: "Inspected", tone: "info" },
  modelled: { label: "Modelled", tone: "warn" },
  assumption: { label: "Assumption", tone: "accent" },
  next: { label: "Next", tone: "muted" },
};

export function Chip({ status, tone }: { status?: StatusKey; tone?: Tone }) {
  if (status) {
    const entry = STATUS[status] ?? STATUS.inspected;
    return (
      <span className="chip" data-tone={entry.tone}>
        {entry.label}
      </span>
    );
  }
  return (
    <span className="chip" data-tone={tone}>
      {tone ?? "plain"}
    </span>
  );
}

export function Stat({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="stat" data-tone={tone}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {note ? <div className="note">{note}</div> : null}
    </div>
  );
}

export function Card({
  title,
  children,
  tone,
}: {
  title?: string;
  children: ReactNode;
  tone?: Tone;
}) {
  const style =
    tone === "warn"
      ? { borderColor: "var(--warn-line)" }
      : tone === "good"
        ? { borderColor: "var(--good-line)" }
        : tone === "bad"
          ? { borderColor: "var(--bad-line)" }
          : undefined;
  return (
    <section className="card" style={style}>
      {title ? <h3>{title}</h3> : null}
      {children}
    </section>
  );
}

export function Callout({
  children,
  tone = "warn",
}: {
  children: ReactNode;
  tone?: "warn" | "bad" | "info" | "good";
}) {
  return (
    <div className="callout" data-tone={tone}>
      {children}
    </div>
  );
}

export function Formula({
  children,
  wrap = false,
}: {
  children: ReactNode;
  wrap?: boolean;
}) {
  return (
    <div className="formula" style={wrap ? { whiteSpace: "normal" } : undefined}>
      {children}
    </div>
  );
}

export function ErrorPanel({ message }: { message: string }) {
  return (
    <div className="error-panel">
      <b>No data.</b> {message}
    </div>
  );
}

export function Section({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      <h2 className="section-title">{title}</h2>
      {sub ? <p className="section-sub">{sub}</p> : null}
      {children}
    </>
  );
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${(100 * value).toFixed(digits)}%`;
}

export function num(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function signed(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}
