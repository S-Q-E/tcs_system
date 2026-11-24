import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import type { Task } from "@/api/tasks";
import {
  useCompleteTask,
  useCreateTaskFull,
  useDeleteTask,
  useTasks,
  useUpdateTask,
} from "@/api/tasks";
import { useUsersLite } from "@/api/deals";
import { useToast, toastError } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isoToLocalInput, localInputToIso } from "@/lib/datetime";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const taskSchema = z.object({
  title: z.string().min(1, "Enter a title").max(255),
  type: z.enum(["call", "meeting", "message", "other"]),
  assignee_id: z.string().optional(),
  due_at: z.string().optional(),
});

type TaskForm = z.infer<typeof taskSchema>;

const TYPE_LABEL: Record<string, string> = {
  call: "Call",
  meeting: "Meeting",
  message: "Message",
  other: "Other",
};

function dayKey(iso: string | null | undefined): string | null {
  if (!iso) {
    return null;
  }
  return iso.slice(0, 10);
}

function todayKey(): string {
  return new Date().toISOString().slice(0, 10);
}

function addDaysKey(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
}

function TaskModal({ task, onClose }: { task?: Task; onClose: () => void }) {
  const { push } = useToast();
  const users = useUsersLite();
  const createTask = useCreateTaskFull();
  const updateTask = useUpdateTask();
  const form = useForm<TaskForm>({
    resolver: zodResolver(taskSchema),
    defaultValues: {
      title: task?.title ?? "",
      type: (task?.type as TaskForm["type"]) ?? "other",
      assignee_id: task?.assignee_id ?? "",
      due_at: isoToLocalInput(task?.due_at),
    },
  });

  const save = async (values: TaskForm) => {
    try {
      if (task) {
        await updateTask.mutateAsync({
          id: task.id,
          patch: {
            title: values.title,
            type: values.type,
            assignee_id: values.assignee_id || null,
            due_at: localInputToIso(values.due_at ?? ""),
          },
        });
      } else {
        await createTask.mutateAsync({
          title: values.title,
          type: values.type,
          assignee_id: values.assignee_id || null,
          due_at: localInputToIso(values.due_at ?? ""),
        });
      }
      onClose();
    } catch (error) {
      toastError(push, error);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={task ? "Edit task" : "New task"}
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <form
        onSubmit={form.handleSubmit((values) => void save(values))}
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-md rounded-xl border border-slate-200/90 bg-white p-5 shadow-modal dark:border-slate-800 dark:bg-[#14171E]"
      >
        <h2 className="text-base font-semibold tracking-[-0.015em] text-slate-900 dark:text-slate-100">
          {task ? "Edit task" : "New task"}
        </h2>
        <label className="mt-3.5 block text-xs font-medium text-slate-700 dark:text-slate-300">
          Title
          <Input className="mt-1" {...form.register("title")} />
          {form.formState.errors.title && (
            <span className="mt-0.5 block text-xs text-red-600">
              {form.formState.errors.title.message}
            </span>
          )}
        </label>
        <div className="mt-3 grid grid-cols-2 gap-2.5">
          <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
            Type
            <select {...form.register("type")} className="ui-select mt-1 w-full">
              {Object.entries(TYPE_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
            Due
            <Input className="mt-1" type="datetime-local" {...form.register("due_at")} />
          </label>
        </div>
        <label className="mt-3 block text-xs font-medium text-slate-700 dark:text-slate-300">
          Assignee
          <select {...form.register("assignee_id")} className="ui-select mt-1 w-full">
            <option value="">Unassigned</option>
            {users.data?.items.map((user) => (
              <option key={user.id} value={user.id}>
                {user.name}
              </option>
            ))}
          </select>
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={createTask.isPending || updateTask.isPending}>
            Save
          </Button>
        </div>
      </form>
    </div>
  );
}

function TaskRow({ task, onEdit }: { task: Task; onEdit: (task: Task) => void }) {
  const navigate = useNavigate();
  const complete = useCompleteTask();
  const remove = useDeleteTask();
  const { push } = useToast();
  const done = task.done_at !== null;
  const overdue = !done && task.due_at !== null && new Date(task.due_at) < new Date();

  return (
    <div
      data-task-row={task.id}
      className={cn(
        "flex items-center gap-2.5 rounded-lg border px-3 py-2 text-xs shadow-subtle transition-colors",
        overdue
          ? "border-red-300/80 bg-red-50/70 dark:border-red-900/70 dark:bg-red-950/30"
          : "border-slate-200/80 bg-white hover:border-slate-300 dark:border-slate-800/90 dark:bg-[#121418] dark:hover:border-slate-700",
      )}
    >
      <input
        type="checkbox"
        aria-label={done ? `Reopen ${task.title}` : `Complete ${task.title}`}
        checked={done}
        onChange={() =>
          complete.mutate(
            { id: task.id, done: !done },
            { onError: (error) => toastError(push, error) },
          )
        }
        className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
      />
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "truncate text-[13px] font-medium text-slate-900 dark:text-slate-100",
            done && "text-slate-400 line-through dark:text-slate-500",
          )}
        >
          {task.title}
        </p>
        <p className="mt-0.5 text-[11px] text-slate-500">
          {TYPE_LABEL[task.type] ?? task.type}
          {task.due_at ? ` · due ${formatDate(task.due_at)}` : ""}
          {overdue ? (
            <span className="font-semibold text-red-600 dark:text-red-400"> · overdue</span>
          ) : (
            ""
          )}
        </p>
      </div>
      {task.deal_id && (
        <button
          type="button"
          className="shrink-0 text-xs font-medium text-brand-600 hover:underline dark:text-brand-400"
          onClick={() => navigate(`/deals/${task.deal_id}`)}
        >
          Deal
        </button>
      )}
      <button
        type="button"
        className="shrink-0 text-xs text-slate-500 hover:text-slate-900 hover:underline dark:hover:text-slate-200"
        onClick={() => onEdit(task)}
      >
        Edit
      </button>
      <button
        type="button"
        aria-label={`Delete ${task.title}`}
        disabled={remove.isPending}
        className="shrink-0 rounded px-1 text-xs text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50 dark:hover:bg-red-950/40"
        onClick={() => remove.mutate(task.id, { onError: (error) => toastError(push, error) })}
      >
        ×
      </button>
    </div>
  );
}

export function TasksPage() {
  const [view, setView] = useState<"groups" | "week">("groups");
  const [editing, setEditing] = useState<Task | undefined>(undefined);
  const [creating, setCreating] = useState(false);
  const openTasks = useTasks({ open_only: true });
  const doneTasks = useTasks({});

  const open = (openTasks.data?.items ?? []).filter((task) => task.done_at === null);
  const done = (doneTasks.data?.items ?? []).filter((task) => task.done_at !== null).slice(0, 50);
  const today = todayKey();
  const tomorrow = addDaysKey(1);
  const isOverdue = (task: Task) => task.due_at !== null && new Date(task.due_at) < new Date();
  const overdue = open.filter((task) => isOverdue(task));
  const dueToday = open.filter((task) => !isOverdue(task) && dayKey(task.due_at) === today);
  const dueTomorrow = open.filter((task) => !isOverdue(task) && dayKey(task.due_at) === tomorrow);
  const later = open.filter(
    (task) => !isOverdue(task) && (!task.due_at || (dayKey(task.due_at) as string) > tomorrow),
  );

  const weekDays = Array.from({ length: 7 }, (_, index) => {
    const key = addDaysKey(index - 1);
    return {
      key,
      label: new Date(`${key}T00:00:00`).toLocaleDateString("en-US", {
        weekday: "short",
        day: "numeric",
        month: "short",
      }),
      tasks: open.filter((task) => dayKey(task.due_at) === key),
    };
  });

  const group = (title: string, tasks: Task[]) => (
    <section
      aria-label={title}
      role="region"
      className="flex flex-col rounded-lg border border-slate-200/75 bg-slate-100/50 p-3 dark:border-slate-800/80 dark:bg-[#111318]"
    >
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          {title} ({tasks.length})
        </h2>
      </div>
      <div className="flex flex-col gap-1.5">
        {tasks.map((task) => (
          <TaskRow key={task.id} task={task} onEdit={setEditing} />
        ))}
        {tasks.length === 0 && <p className="py-2 text-xs text-slate-400">Empty.</p>}
      </div>
    </section>
  );

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center gap-2.5">
        <h1 className="text-base font-semibold tracking-[-0.015em] text-slate-900 dark:text-slate-100">
          Tasks
        </h1>
        <div className="inline-flex rounded-md border border-slate-200/90 bg-slate-100/80 p-0.5 dark:border-slate-800 dark:bg-[#14171D]">
          {(["groups", "week"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setView(mode)}
              className={cn(
                "rounded-[5px] px-2.5 py-1 text-xs font-medium transition-all",
                view === mode
                  ? "bg-white text-slate-900 shadow-subtle dark:bg-[#1E222B] dark:text-white"
                  : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200",
              )}
            >
              {mode === "groups" ? "Lists" : "Week"}
            </button>
          ))}
        </div>
        <Button size="sm" onClick={() => setCreating(true)}>
          New task
        </Button>
      </div>

      {view === "groups" ? (
        <div className="grid gap-3.5 md:grid-cols-2 xl:grid-cols-3">
          {group("Overdue", overdue)}
          {group("Today", dueToday)}
          {group("Tomorrow", dueTomorrow)}
          {group("Later", later)}
          {group("Done", done)}
        </div>
      ) : (
        <div className="grid gap-2.5 md:grid-cols-7">
          {weekDays.map((day) => (
            <section key={day.key} aria-label={day.label} className="ui-card p-2.5">
              <h2 className="mb-2 border-b border-slate-100 pb-1.5 text-xs font-semibold text-slate-800 dark:border-slate-800 dark:text-slate-200">
                {day.label}
              </h2>
              <div className="flex flex-col gap-1.5">
                {day.tasks.map((task) => (
                  <TaskRow key={task.id} task={task} onEdit={setEditing} />
                ))}
                {day.tasks.length === 0 && <p className="text-[11px] text-slate-400">—</p>}
              </div>
            </section>
          ))}
        </div>
      )}

      {(creating || editing !== undefined) && (
        <TaskModal
          task={editing}
          onClose={() => {
            setCreating(false);
            setEditing(undefined);
          }}
        />
      )}
    </div>
  );
}
