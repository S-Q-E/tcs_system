import { forwardRef } from "react";
import type { InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export type InputProps = InputHTMLAttributes<HTMLInputElement>;

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded-md border border-slate-200/90 bg-white px-3 py-1.5 text-base text-slate-900 shadow-subtle transition-all md:h-8 md:text-[13px]",
        "placeholder:text-slate-400 hover:border-slate-300 focus-visible:border-brand-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/20",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "dark:border-slate-800 dark:bg-[#121418] dark:text-slate-100 dark:placeholder:text-slate-500 dark:hover:border-slate-700 dark:focus-visible:border-brand-400",
        className,
      )}
      {...props}
    />
  );
});
