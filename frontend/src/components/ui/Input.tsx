import type { InputHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
}

export const fieldClass =
  "w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-[14px] text-stone-900 shadow-sm outline-none transition-colors placeholder:text-stone-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100";

export const labelClass = "text-[12.5px] font-medium text-stone-700";

export function Input({ label, hint, error, id, className, ...props }: InputProps) {
  const inputId = id ?? props.name;
  return (
    <label className="block" htmlFor={inputId}>
      <span className={cn("mb-1.5 block", labelClass)}>{label}</span>
      <input
        className={cn(fieldClass, error && "border-red-600 focus:border-red-600 focus:ring-red-100", className)}
        id={inputId}
        {...props}
      />
      {error ? (
        <span className="mt-1 block text-xs text-red-700">{error}</span>
      ) : hint ? (
        <span className="mt-1 block text-xs text-stone-500">{hint}</span>
      ) : null}
    </label>
  );
}
