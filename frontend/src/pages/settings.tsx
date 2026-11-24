import { useState } from "react";

import { useMe } from "@/api/auth";
import { ForbiddenPage } from "@/pages/stubs";
import { ActivityTab } from "@/pages/settings_system";
import { FieldsTab, FunnelsTab, RepliesTab, TagsTab } from "@/pages/settings_catalog";
import { AutomationTab, IntegrationsTab, UsersTab } from "@/pages/settings_system";
import { ProfileTab } from "@/pages/settings_profile";
import { cn } from "@/lib/utils";

export const inputClass = "ui-select w-full";

export function ModalShell({
  title,
  children,
  onClose,
  wide,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className={cn(
          "max-h-[90vh] w-full overflow-y-auto rounded-xl border border-slate-200/90 bg-white p-5 shadow-modal dark:border-slate-800 dark:bg-[#14171E]",
          wide ? "max-w-2xl" : "max-w-md",
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="text-base font-semibold tracking-[-0.015em] text-slate-900 dark:text-slate-100">
          {title}
        </h2>
        <div className="mt-3.5">{children}</div>
      </div>
    </div>
  );
}

export function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-slate-700 dark:text-slate-300">
      {children}
    </label>
  );
}

type AdminTabId =
  | "funnels"
  | "fields"
  | "tags"
  | "users"
  | "replies"
  | "automation"
  | "integrations"
  | "activity";

const ADMIN_TABS: { id: AdminTabId; label: string }[] = [
  { id: "funnels", label: "Pipelines" },
  { id: "fields", label: "Fields" },
  { id: "tags", label: "Tags" },
  { id: "users", label: "Users" },
  { id: "replies", label: "Templates" },
  { id: "automation", label: "Automation" },
  { id: "integrations", label: "Integrations" },
  { id: "activity", label: "Activity log" },
];

export function SettingsPage() {
  const me = useMe();
  const isAdmin = me.data?.role === "admin";
  const [tab, setTab] = useState<AdminTabId | "profile">("profile");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-base font-semibold tracking-[-0.015em] text-slate-900 dark:text-slate-100">
          Settings
        </h1>
        <div className="inline-flex flex-wrap rounded-md border border-slate-200/90 bg-slate-100/80 p-0.5 dark:border-slate-800 dark:bg-[#14171D]">
          <button
            type="button"
            onClick={() => setTab("profile")}
            className={cn(
              "rounded-[5px] px-2.5 py-1 text-xs font-medium transition-all",
              tab === "profile"
                ? "bg-white text-slate-900 shadow-subtle dark:bg-[#1E222B] dark:text-white"
                : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200",
            )}
          >
            Profile
          </button>
          {isAdmin &&
            ADMIN_TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={cn(
                  "rounded-[5px] px-2.5 py-1 text-xs font-medium transition-all",
                  tab === item.id
                    ? "bg-white text-slate-900 shadow-subtle dark:bg-[#1E222B] dark:text-white"
                    : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200",
                )}
              >
                {item.label}
              </button>
            ))}
        </div>
      </div>

      {tab === "profile" && <ProfileTab />}
      {tab !== "profile" && !isAdmin && <ForbiddenPage />}
      {tab !== "profile" && isAdmin && (
        <div className="flex flex-col gap-4">
          {tab === "funnels" && <FunnelsTab />}
          {tab === "fields" && <FieldsTab />}
          {tab === "tags" && <TagsTab />}
          {tab === "users" && <UsersTab />}
          {tab === "replies" && <RepliesTab />}
          {tab === "automation" && <AutomationTab />}
          {tab === "integrations" && <IntegrationsTab />}
          {tab === "activity" && <ActivityTab />}
        </div>
      )}
    </div>
  );
}
