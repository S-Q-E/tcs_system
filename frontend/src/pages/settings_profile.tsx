import { useState } from "react";

import { useMe } from "@/api/auth";
import {
  DEFAULT_PREFS,
  formatInTimezone,
  loadProfilePrefs,
  saveProfilePrefs,
  useChangePassword,
  useRevokeOtherSessions,
  useRevokeSession,
  useSessions,
  useUpdateProfile,
} from "@/api/settings";
import { toastError, useToast } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { inputClass } from "@/pages/settings";

const TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "UTC",
];

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="ui-card p-4">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function ProfileTab() {
  const me = useMe();
  const { push } = useToast();
  const [name, setName] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [prefs, setPrefs] = useState(loadProfilePrefs);
  const updateProfile = useUpdateProfile();
  const changePassword = useChangePassword();
  const sessions = useSessions();
  const revokeOne = useRevokeSession();
  const revokeOthers = useRevokeOtherSessions();

  const nameValue = name ?? me.data?.name ?? "";

  const saveName = async () => {
    try {
      await updateProfile.mutateAsync({ name: nameValue.trim() });
      setName(null);
      push({ title: "Name updated", variant: "default" });
    } catch (error) {
      toastError(push, error);
    }
  };

  const savePassword = async () => {
    try {
      await changePassword.mutateAsync({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      push({ title: "Password changed. Other devices were signed out.", variant: "default" });
    } catch (error) {
      toastError(push, error);
    }
  };

  const savePrefs = (next: typeof prefs) => {
    setPrefs(next);
    saveProfilePrefs(next);
  };

  return (
    <div className="grid max-w-3xl gap-3.5">
      <Card title="Personal details">
        <div className="flex flex-col gap-2.5">
          <p className="text-xs text-slate-500">
            {me.data?.email} · role {me.data?.role === "admin" ? "administrator" : "manager"}
          </p>
          <div className="flex gap-2">
            <Input value={nameValue} onChange={(e) => setName(e.target.value)} aria-label="Name" />
            <Button
              size="sm"
              disabled={updateProfile.isPending || !nameValue.trim() || nameValue === me.data?.name}
              onClick={() => void saveName()}
            >
              Save
            </Button>
          </div>
        </div>
      </Card>

      <Card title="Change password">
        <div className="flex flex-col gap-2.5">
          <Input
            type="password"
            placeholder="Current password"
            aria-label="Current password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
          <Input
            type="password"
            placeholder="New password (at least 10 characters)"
            aria-label="New password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <div>
            <Button
              size="sm"
              disabled={changePassword.isPending || newPassword.length < 10 || !currentPassword}
              onClick={() => void savePassword()}
            >
              Change password
            </Button>
          </div>
        </div>
      </Card>

      <Card title="Display">
        <div className="flex flex-col gap-3">
          <label className="flex items-center gap-2 text-xs font-medium text-slate-700 dark:text-slate-300">
            Timezone
            <select
              value={prefs.timezone}
              onChange={(e) => savePrefs({ ...prefs, timezone: e.target.value })}
              className={inputClass}
            >
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs font-medium text-slate-700 dark:text-slate-300">
            <input
              type="checkbox"
              checked={prefs.sound}
              onChange={(e) => savePrefs({ ...prefs, sound: e.target.checked })}
            />
            Notification sound
          </label>
          <button
            type="button"
            className="self-start text-xs text-slate-500 underline"
            onClick={() => savePrefs(DEFAULT_PREFS)}
          >
            Reset to defaults
          </button>
        </div>
      </Card>

      <Card title="Active sessions">
        {sessions.isPending && <p className="text-xs text-slate-500">Loading…</p>}
        {sessions.data && (
          <div className="flex flex-col gap-2">
            {sessions.data.items.map((item) => (
              <div
                key={item.id}
                className="flex items-center gap-2 rounded-md border border-slate-100 px-3 py-2 text-xs dark:border-slate-800"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-slate-800 dark:text-slate-100">
                    {item.user_agent || "Unknown device"}
                    {item.is_current && (
                      <span className="ml-2 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-500/20 dark:bg-emerald-950/60 dark:text-emerald-300">
                        this device
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 font-mono text-[11px] text-slate-500">
                    {item.ip || "—"} · signed in{" "}
                    {formatInTimezone(item.created_at, prefs.timezone)}
                  </p>
                </div>
                {!item.is_current && (
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={revokeOne.isPending}
                    onClick={() =>
                      revokeOne.mutate(item.id, { onError: (e) => toastError(push, e) })
                    }
                  >
                    Sign out
                  </Button>
                )}
              </div>
            ))}
            {sessions.data.items.length > 1 && (
              <div>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={revokeOthers.isPending}
                  onClick={() =>
                    revokeOthers.mutate(undefined, {
                      onSuccess: (data) =>
                        push({ title: `Sessions closed: ${data.revoked}`, variant: "default" }),
                      onError: (e) => toastError(push, e),
                    })
                  }
                >
                  Sign out other devices
                </Button>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
