import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef } from "react";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-xs font-medium tracking-[-0.01em] transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/30 disabled:pointer-events-none disabled:opacity-45 select-none",
  {
    variants: {
      variant: {
        default:
          "bg-brand-600 text-white shadow-[0_1px_2px_rgba(0,0,0,0.12),inset_0_1px_0_rgba(255,255,255,0.15)] hover:bg-brand-500 active:bg-brand-700 dark:bg-brand-500 dark:text-white dark:hover:bg-brand-400",
        secondary:
          "border border-slate-200/90 bg-white text-slate-700 shadow-subtle hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 active:bg-slate-100 dark:border-slate-800 dark:bg-[#161920] dark:text-slate-200 dark:hover:border-slate-700 dark:hover:bg-[#1D212A] dark:hover:text-white",
        ghost:
          "text-slate-600 hover:bg-slate-100/80 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-100",
        danger:
          "bg-red-600 text-white shadow-subtle hover:bg-red-500 active:bg-red-700 dark:bg-red-600/90 dark:hover:bg-red-500",
      },
      size: {
        default: "h-10 px-3.5 py-2 text-[13px] md:h-8",
        sm: "h-8 px-2.5 text-xs md:h-7",
        icon: "h-10 w-10 md:h-8 md:w-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, ...props },
  ref,
) {
  return (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  );
});
