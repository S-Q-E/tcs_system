import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { useLogin } from "@/api/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await login.mutateAsync({ email: email.trim(), password });
      navigate(params.get("next") || "/deals", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError("Too many attempts. Please try again later.");
      } else if (err instanceof Error) {
        setError(
          err.message === "Authentication required" ? "Invalid email or password" : err.message,
        );
      } else {
        setError("Invalid email or password");
      }
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#F8F9FB] p-4 dark:bg-[#0B0C0E]">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-brand-500/10 via-transparent to-transparent dark:from-brand-500/15"
      />
      <form
        onSubmit={onSubmit}
        className="relative w-full max-w-[360px] rounded-xl border border-slate-200/90 bg-white/95 p-7 shadow-elevated backdrop-blur-md dark:border-slate-800/90 dark:bg-[#12141A]/95"
      >
        <div className="mb-5 flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-xs font-bold tracking-tight text-white shadow-subtle">
            TC
          </div>
          <div>
            <h1 className="text-base font-semibold leading-tight tracking-[-0.015em] text-slate-900 dark:text-slate-100">
              TCS Leasing CRM
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">Manager sign in</p>
          </div>
        </div>

        <label className="mt-4 block text-xs font-medium text-slate-700 dark:text-slate-300">
          Email
          <Input
            className="mt-1.5"
            type="email"
            autoComplete="username"
            placeholder="name@company.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>
        <label className="mt-3.5 block text-xs font-medium text-slate-700 dark:text-slate-300">
          Password
          <Input
            className="mt-1.5"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        {error && (
          <p
            role="alert"
            className="mt-3 rounded-md border border-red-200 bg-red-50 px-2.5 py-1.5 text-xs font-medium text-red-700 dark:border-red-900/60 dark:bg-red-950/60 dark:text-red-300"
          >
            {error}
          </p>
        )}
        <Button className="mt-5 w-full" type="submit" disabled={login.isPending}>
          {login.isPending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </div>
  );
}
