import { useEffect } from "react";
import type { Task } from "../lib/api";
import { useLookups, useToday } from "../lib/queries";
import { type PageContext, useUI } from "../stores/ui";
import { TaskRow, useVisibleIds } from "./TaskRow";

export interface Group {
  key: string;
  title?: React.ReactNode;
  aside?: React.ReactNode;
  tasks: Task[];
  /** Extra rows after the tasks (ghost runs on Upcoming). */
  extra?: React.ReactNode;
  hideDue?: boolean;
  tone?: "red";
}

/** Grouped one-line task rows; registers the rows for j/k in display order. */
export function TaskGroups({
  groups,
  hideWhere,
  empty,
}: {
  groups: Group[];
  hideWhere?: boolean;
  empty?: React.ReactNode;
}) {
  const lookups = useLookups();
  const today = useToday();
  useVisibleIds(groups.flatMap((g) => g.tasks.map((t) => t.id)));
  const nonEmpty = groups.filter((g) => g.tasks.length || g.extra);
  if (!nonEmpty.length && empty) return <>{empty}</>;
  return (
    <div className="pb-10">
      {nonEmpty.map((g) => (
        <section key={g.key} className="mt-5 first:mt-2">
          {g.title && (
            <h2
              className={`flex items-baseline gap-2 border-b border-line px-4 pb-1.5 text-[13px] font-semibold desk:px-5 ${
                g.tone === "red" ? "text-red" : "text-ink"
              }`}
            >
              {g.title}
              <span className="text-[12px] font-normal tabular-nums text-ink3">
                {g.tasks.length || ""}
              </span>
              <span className="flex-1" />
              {g.aside}
            </h2>
          )}
          <div>
            {g.tasks.map((t) => (
              <TaskRow
                key={t.id}
                task={t}
                today={today}
                lookups={lookups}
                hideWhere={hideWhere}
                hideDue={g.hideDue && !t.due_time}
              />
            ))}
            {g.extra}
          </div>
        </section>
      ))}
    </div>
  );
}

/** Publish what this page means for quick add and page keys; cleared on unmount. */
export function usePageContext(ctx: PageContext, deps: unknown[]) {
  // biome-ignore lint/correctness/useExhaustiveDependencies: callers pass their own deps
  useEffect(() => {
    useUI.getState().setPage(ctx);
    return () => useUI.getState().setPage({});
  }, deps);
}

export function PageHeader({
  title,
  sub,
  serif,
  actions,
  children,
}: {
  title: React.ReactNode;
  sub?: React.ReactNode;
  /** Daybook headline: the serif date (light theme). */
  serif?: boolean;
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <header className={`px-4 desk:px-5 ${serif ? "pt-8 desk:pt-10" : "pt-5 desk:pt-6"}`}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h1
            className={
              serif
                ? "headline"
                : "text-[22px] font-semibold tracking-[-0.015em] text-ink desk:text-[19px]"
            }
          >
            {title}
          </h1>
          {sub && (
            <p className={`text-ink2 ${serif ? "mt-1.5 text-[14px]" : "mt-1 text-[13px]"}`}>
              {sub}
            </p>
          )}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-1.5 pt-1">{actions}</div>}
      </div>
      {children}
    </header>
  );
}

export function Empty({ title, body }: { title: string; body?: React.ReactNode }) {
  return (
    <div className="px-5 py-16 text-center">
      <p className="text-[14px] font-medium text-ink2">{title}</p>
      {body && <p className="mx-auto mt-1 max-w-[34ch] text-[13px] text-ink3">{body}</p>}
    </div>
  );
}
