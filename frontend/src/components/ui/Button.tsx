import type { ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
}

export const buttonClass = (variant: ButtonProps["variant"] = "primary", size: ButtonProps["size"] = "md") =>
  cn(
    "inline-flex items-center justify-center gap-1.5 rounded-lg border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
    size === "md" ? "px-3.5 py-2 text-[13.5px]" : "px-2.5 py-1 text-[12.5px]",
    variant === "primary" && "border-brand-700 bg-brand-700 text-white shadow-sm hover:bg-brand-800",
    variant === "secondary" && "border-stone-300 bg-white text-stone-800 shadow-sm hover:border-stone-400 hover:bg-stone-50",
    variant === "ghost" && "border-transparent bg-transparent text-stone-600 hover:bg-stone-100 hover:text-stone-900",
    variant === "danger" && "border-transparent bg-transparent text-stone-500 hover:bg-red-50 hover:text-red-700",
  );

export function Button({ variant = "primary", size = "md", className, ...props }: ButtonProps) {
  return <button className={cn(buttonClass(variant, size), className)} {...props} />;
}
