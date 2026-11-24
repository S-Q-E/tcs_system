import {
  BarChart3,
  Bell,
  Building2,
  CalendarClock,
  CheckSquare,
  ChevronDown,
  Coins,
  LogOut,
  MessagesSquare,
  Moon,
  MoreHorizontal,
  Search,
  Settings,
  Sun,
  Users,
} from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useLogout, useMe } from "@/api/auth";
import { useEventStream } from "@/api/stream";
import { BellBadge, BellDropdown } from "@/components/bell";
import { RealtimeStatus } from "@/components/realtime-status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { initials } from "@/lib/format";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/deals", label: "Deals", icon: Coins, adminOnly: false, group: "workspace" },
  { to: "/dialogs", label: "Dialogs", icon: MessagesSquare, adminOnly: false, group: "workspace" },
  { to: "/contacts", label: "Contacts", icon: Users, adminOnly: false, group: "workspace" },
  { to: "/units", label: "Units", icon: Building2, adminOnly: false, group: "leasing" },
  { to: "/schedule", label: "Schedule", icon: CalendarClock, adminOnly: false, group: "leasing" },
  { to: "/tasks", label: "Tasks", icon: CheckSquare, adminOnly: false, group: "leasing" },
  { to: "/analytics", label: "Analytics", icon: BarChart3, adminOnly: false, group: "system" },
  { to: "/settings", label: "Settings", icon: Settings, adminOnly: false, group: "system" },
];

export function Layout() {
  const { data: me } = useMe();
  useEventStream();
  const logout = useLogout();
  const navigate = useNavigate();
  const { theme, toggle } = useTheme();
  const [query, setQuery] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [bellOpen, setBellOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

  const onSearch = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    navigate(trimmed ? `/contacts?q=${encodeURIComponent(trimmed)}` : "/contacts");
  };

  const onLogout = async () => {
    try {
      await logout.mutateAsync();
    } catch {
      // Session may already be gone; still leave.
    }
    navigate("/login", { replace: true });
  };

  const visibleNav = NAV.filter((item) => !item.adminOnly || me?.role === "admin");
  // Mobile bottom bar fits five slots: four sections plus "More".
  const tabNav = visibleNav.slice(0, 4);
  const moreNav = visibleNav.slice(4);

  return (
    <div className="flex min-h-screen bg-[#F8F9FB] text-slate-900 dark:bg-[#0B0C0E] dark:text-slate-100">
      <aside className="hidden w-[216px] shrink-0 flex-col border-r border-slate-200/80 bg-white/80 backdrop-blur-sm dark:border-slate-800/80 dark:bg-[#0E1014] md:flex">
        <div className="flex h-13 items-center gap-2.5 border-b border-slate-200/70 px-4 py-3 dark:border-slate-800/70">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-brand-500 to-brand-700 text-xs font-bold tracking-tight text-white shadow-subtle">
            TC
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-semibold leading-tight tracking-[-0.01em] text-slate-900 dark:text-slate-100">
              TCS Leasing
            </p>
            <p className="truncate text-[10px] font-medium text-slate-400 dark:text-slate-500">
              Property CRM
            </p>
          </div>
        </div>

        <div className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2.5 py-3">
          <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            Workspace
          </p>
          {visibleNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              title={item.label}
              className={({ isActive }) =>
                cn(
                  "group flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium transition-all duration-150",
                  isActive
                    ? "bg-slate-900/[0.06] text-slate-950 shadow-[inset_0_1px_0_rgba(255,255,255,0.5)] dark:bg-white/[0.08] dark:text-white"
                    : "text-slate-600 hover:bg-slate-100/70 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/[0.04] dark:hover:text-slate-200",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon
                    className={cn(
                      "h-4 w-4 shrink-0 transition-colors",
                      isActive
                        ? "text-brand-600 dark:text-brand-400"
                        : "text-slate-400 group-hover:text-slate-600 dark:text-slate-500 dark:group-hover:text-slate-300",
                    )}
                  />
                  <span className="truncate">{item.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </div>

        <div className="border-t border-slate-200/70 p-2.5 dark:border-slate-800/70">
          <div className="flex items-center gap-2 rounded-md bg-slate-50/80 px-2.5 py-2 dark:bg-[#14171D]">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600/10 text-[10px] font-semibold text-brand-700 dark:bg-brand-400/15 dark:text-brand-300">
              {initials(me?.name ?? "U")}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-slate-800 dark:text-slate-200">
                {me?.name ?? "Manager"}
              </p>
              <p className="truncate text-[10px] capitalize text-slate-400 dark:text-slate-500">
                {me?.role ?? "member"}
              </p>
            </div>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex flex-wrap items-center gap-2 border-b border-slate-200/80 bg-white/85 px-3 py-2 backdrop-blur-md dark:border-slate-800/80 dark:bg-[#0E1014]/85 md:h-13 md:flex-nowrap md:gap-3 md:px-6">
          <form
            onSubmit={onSearch}
            className="relative order-first w-full md:order-none md:w-auto md:min-w-0 md:max-w-sm md:flex-1"
          >
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search contacts and deals"
              className="pl-8 pr-10"
            />
            <kbd className="pointer-events-none absolute right-2 top-1/2 hidden -translate-y-1/2 rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[10px] text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500 md:inline-block">
              ↵
            </kbd>
          </form>

          <div className="ml-auto flex items-center gap-1.5">
            <div className="hidden items-center gap-1.5 rounded-full border border-amber-300/80 bg-amber-50/90 px-2.5 py-0.5 text-[11px] font-medium text-amber-800 dark:border-amber-800/70 dark:bg-amber-950/40 dark:text-amber-300 sm:inline-flex">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
              DEMO — fictional data
            </div>
            <RealtimeStatus />
            <Button variant="ghost" size="icon" onClick={toggle} title="Toggle theme">
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
            <div className="relative">
              <Button
                variant="ghost"
                size="icon"
                title="Notifications"
                onClick={() => {
                  setBellOpen((open) => !open);
                  setMenuOpen(false);
                }}
              >
                <span className="relative">
                  <Bell className="h-4 w-4" />
                  <BellBadge />
                </span>
              </Button>
              {bellOpen && <BellDropdown onClose={() => setBellOpen(false)} />}
            </div>
            <div className="relative">
              <Button
                variant="secondary"
                size="sm"
                className="max-w-36 gap-1.5 truncate md:max-w-none"
                onClick={() => {
                  setMenuOpen((open) => !open);
                  setBellOpen(false);
                }}
              >
                <span className="truncate">{me?.name ?? "Menu"}</span>
                <ChevronDown className="h-3 w-3 shrink-0 opacity-60" />
              </Button>
              {menuOpen && (
                <div className="absolute right-0 z-30 mt-2 w-56 rounded-lg border border-slate-200/90 bg-white p-1.5 text-xs shadow-elevated dark:border-slate-800 dark:bg-[#14171E]">
                  <div className="border-b border-slate-100 px-2.5 py-2 dark:border-slate-800/80">
                    <p className="font-semibold text-slate-900 dark:text-slate-100">{me?.name}</p>
                    <p className="mt-0.5 truncate text-[11px] text-slate-500 dark:text-slate-400">
                      {me?.email}
                    </p>
                  </div>
                  <button
                    className="mt-1 flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left font-medium text-slate-700 transition-colors hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800/70"
                    onClick={() => {
                      void onLogout();
                    }}
                  >
                    <LogOut className="h-3.5 w-3.5 text-slate-400" />
                    Log out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="min-w-0 flex-1 p-3 pb-24 md:p-6 md:pb-6">
          <div className="mb-3 flex items-center gap-1.5 rounded-md border border-amber-300/80 bg-amber-50/90 px-2.5 py-1 text-[11px] font-medium text-amber-800 dark:border-amber-800/70 dark:bg-amber-950/40 dark:text-amber-300 sm:hidden">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
            DEMO — fictional data
          </div>
          <Outlet />
        </main>
      </div>

      <nav
        aria-label="Main navigation"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200/80 bg-white/95 backdrop-blur-md dark:border-slate-800/80 dark:bg-[#0E1014]/95 md:hidden"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="flex items-stretch">
          {tabNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setMoreOpen(false)}
              className={({ isActive }) =>
                cn(
                  "flex min-h-11 flex-1 flex-col items-center justify-center gap-0.5 py-1.5 text-slate-500 transition-colors dark:text-slate-400",
                  isActive && "font-medium text-brand-600 dark:text-brand-400",
                )
              }
            >
              <item.icon className="h-4 w-4" />
              <span className="text-[10px] leading-none">{item.label}</span>
            </NavLink>
          ))}
          {moreNav.length > 0 && (
            <div className="relative flex-1">
              <button
                type="button"
                aria-expanded={moreOpen}
                onClick={() => setMoreOpen((open) => !open)}
                className={cn(
                  "flex min-h-11 w-full flex-col items-center justify-center gap-0.5 py-1.5 text-slate-500 transition-colors dark:text-slate-400",
                  moreOpen && "font-medium text-brand-600 dark:text-brand-400",
                )}
              >
                <MoreHorizontal className="h-4 w-4" />
                <span className="text-[10px] leading-none">More</span>
              </button>
              {moreOpen && (
                <div className="absolute inset-x-2 bottom-full mb-2 rounded-lg border border-slate-200/90 bg-white p-1 shadow-elevated dark:border-slate-800 dark:bg-[#14171E]">
                  {moreNav.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      onClick={() => setMoreOpen(false)}
                      className={({ isActive }) =>
                        cn(
                          "flex min-h-10 items-center gap-2 rounded-md px-3 text-xs text-slate-600 dark:text-slate-300",
                          isActive &&
                            "bg-brand-50 font-medium text-brand-700 dark:bg-brand-950/40 dark:text-brand-300",
                        )
                      }
                    >
                      <item.icon className="h-4 w-4" />
                      {item.label}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </nav>
    </div>
  );
}
