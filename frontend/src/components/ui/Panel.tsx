import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export function Panel({
  title,
  description,
  children,
  className,
  actions,
  icon,
  bodyClassName,
}: {
  title?: string;
  description?: string;
  children: ReactNode;
  className?: string;
  actions?: ReactNode;
  icon?: ReactNode;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("rounded-xl border border-stone-200/80 bg-paper shadow-card", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-stone-100 px-5 py-3.5">
          <div className="flex min-w-0 items-start gap-2.5">
            {icon && <span className="mt-0.5 text-brand-600">{icon}</span>}
            <div className="min-w-0">
              {title && <h2 className="text-[14px] font-semibold text-stone-900">{title}</h2>}
              {description && <p className="mt-0.5 text-[12.5px] leading-relaxed text-stone-500">{description}</p>}
            </div>
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </header>
      )}
      <div className={cn("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 pb-1">
      <div className="min-w-0">
        {eyebrow && <p className="text-[11.5px] font-semibold uppercase tracking-[0.12em] text-brand-600">{eyebrow}</p>}
        <h1 className="mt-0.5 text-[22px] font-semibold tracking-tight text-stone-900 sm:text-[24px]">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-[14px] leading-relaxed text-stone-600">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({
  label,
  value,
  sub,
  icon,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  tone?: "default" | "danger" | "warn" | "ok" | "brand";
}) {
  const toneRing = {
    default: "bg-stone-100 text-stone-600",
    danger: "bg-red-50 text-risk-extreme",
    warn: "bg-orange-50 text-risk-heavy",
    ok: "bg-emerald-50 text-emerald-700",
    brand: "bg-brand-50 text-brand-600",
  }[tone];
  return (
    <div className="rounded-xl border border-stone-200/80 bg-paper p-4 shadow-card">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[12.5px] font-medium text-stone-500">{label}</p>
        {icon && <span className={cn("grid h-8 w-8 place-items-center rounded-lg", toneRing)}>{icon}</span>}
      </div>
      <div className="mt-1.5 text-[26px] font-semibold leading-none tracking-tight text-stone-900 tabular-nums">{value}</div>
      {sub && <div className="mt-2 text-[12.5px] leading-snug text-stone-500">{sub}</div>}
    </div>
  );
}
