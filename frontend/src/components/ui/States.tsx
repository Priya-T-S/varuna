import type { ReactNode } from "react";
import { cn } from "../../lib/cn";
import { IconAlertTriangle } from "./Icons";

export function EmptyState({
  title,
  body,
  icon,
  action,
  className,
}: {
  title: string;
  body: string;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-xl border border-dashed border-stone-300 bg-stone-50/60 px-6 py-10 text-center", className)}>
      {icon && <div className="mx-auto mb-3 grid h-11 w-11 place-items-center rounded-full bg-brand-50 text-brand-600">{icon}</div>}
      <p className="text-[15px] font-semibold text-stone-800">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-[13px] leading-6 text-stone-500">{body}</p>
      {action && <div className="mt-4 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3" role="alert">
      <IconAlertTriangle className="mt-0.5 shrink-0 text-red-600" size={18} />
      <div>
        <p className="text-sm font-semibold text-red-900">{title}</p>
        <p className="mt-0.5 text-[13px] leading-5 text-red-800">{body}</p>
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-stone-200/70 ${className ?? "h-4 w-full"}`} />;
}
