import { useSearchParams } from "react-router-dom";

export function StubPage({ title, hint }: { title: string; hint: string }) {
  const [params] = useSearchParams();
  const query = params.get("q");
  return (
    <div className="ui-card p-6">
      <h1 className="text-base font-semibold tracking-[-0.015em]">{title}</h1>
      <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">{hint}</p>
      {query && (
        <p className="mt-2 text-xs">
          Search: <span className="font-medium">{query}</span>
        </p>
      )}
    </div>
  );
}

export function DealsPage() {
  return <StubPage title="Deals (legacy)" hint="Old stub, replaced by the kanban board." />;
}

export function ForbiddenPage() {
  return (
    <div className="ui-card p-6">
      <h1 className="text-base font-semibold tracking-[-0.015em]">Access denied</h1>
      <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
        This section is available to administrators only.
      </p>
    </div>
  );
}
