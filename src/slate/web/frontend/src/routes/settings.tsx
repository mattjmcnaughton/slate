import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { signOut } from "../components/Palette";
import { PageHeader, usePageContext } from "../components/TaskList";
import type { ApiKeyCreated, ApiKeyKind } from "../lib/api";
import { formatShort } from "../lib/dates";
import {
  useApiKeyMutations,
  useApiKeys,
  useMe,
  usePatchSettings,
  useSettings,
} from "../lib/queries";
import { useTheme } from "../stores/theme";

export const Route = createFileRoute("/settings")({
  component: Settings,
});

function zones(current: string | undefined): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (k: string) => string[] };
  const list = intl.supportedValuesOf?.("timeZone") ?? ["UTC", "America/New_York", "Europe/London"];
  return current && !list.includes(current) ? [current, ...list] : list;
}

function Row({
  label,
  hint,
  children,
}: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 border-b border-line py-4 desk:flex-row desk:items-center desk:gap-6">
      <div className="desk:w-60">
        <div className="text-[13.5px] font-medium">{label}</div>
        {hint && <div className="mt-0.5 text-[12.5px] text-ink3">{hint}</div>}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  );
}

function Settings() {
  const settings = useSettings().data;
  const me = useMe().data;
  const patch = usePatchSettings();
  const theme = useTheme();
  usePageContext({}, []);
  const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  return (
    <div className="mx-auto max-w-[760px] pb-10">
      <PageHeader title="Settings" />
      <div className="mt-4 px-4 desk:px-5">
        <Row label="Time zone" hint="Due dates and Today follow this zone.">
          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label="Time zone"
              value={settings?.timezone ?? ""}
              onChange={(e) => patch.mutate({ timezone: e.target.value })}
              className="h-8 w-full max-w-[280px] rounded-md border border-line2 bg-panel px-2 text-[13px] outline-none focus:border-accent"
            >
              {zones(settings?.timezone).map((z) => (
                <option key={z} value={z}>
                  {z.replace(/_/g, " ")}
                </option>
              ))}
            </select>
            {settings && browserZone && browserZone !== settings.timezone && (
              <button
                type="button"
                onClick={() => patch.mutate({ timezone: browserZone })}
                className="text-[12.5px] text-accent hover:underline"
              >
                Use this device’s zone ({browserZone.replace(/_/g, " ")})
              </button>
            )}
          </div>
        </Row>
        <Row label="Theme" hint="Saved on this device.">
          <div
            className="inline-flex rounded-md border border-line p-0.5"
            role="group"
            aria-label="Theme"
          >
            {(["light", "dark"] as const).map((t) => (
              <button
                key={t}
                type="button"
                aria-pressed={theme.theme === t}
                onClick={() => theme.setTheme(t)}
                className={`h-7 rounded px-3 text-[12.5px] ${
                  theme.theme === t ? "bg-hover text-ink" : "text-ink3 hover:text-ink"
                }`}
              >
                {t === "light" ? "Light" : "Dark"}
              </button>
            ))}
          </div>
        </Row>
        <Row
          label="API keys"
          hint="For agents and scripts: send Authorization: Bearer <key>. Keys act as you, in your workspace."
        >
          <ApiKeys />
        </Row>
        <Row
          label="Account"
          hint={me ? `Signed in as ${me.name}${me.email ? ` (${me.email})` : ""}` : undefined}
        >
          <button
            type="button"
            onClick={signOut}
            className="h-8 rounded-md border border-line2 px-3 text-[13px] text-ink2 hover:bg-hover"
          >
            Sign out
          </button>
        </Row>
      </div>
    </div>
  );
}

const inputCls =
  "h-8 rounded-md border border-line2 bg-panel px-2 text-[13px] outline-none focus:border-accent";

function ApiKeys() {
  const keys = useApiKeys().data ?? [];
  const { create, revoke } = useApiKeyMutations();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<ApiKeyKind>("rest");
  const [fresh, setFresh] = useState<ApiKeyCreated | null>(null);
  const live = keys.filter((k) => !k.revoked_at);

  return (
    <div className="flex flex-col gap-3">
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim()) return;
          create.mutate(
            { name: name.trim(), kind },
            {
              onSuccess: (k) => {
                setFresh(k);
                setName("");
              },
            },
          );
        }}
      >
        <input
          aria-label="Key name"
          placeholder="Key name, such as laptop agent"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={`${inputCls} w-56`}
        />
        <select
          aria-label="Key kind"
          value={kind}
          onChange={(e) => setKind(e.target.value as ApiKeyKind)}
          className={inputCls}
        >
          <option value="rest">REST API</option>
          <option value="mcp">MCP (reserved)</option>
        </select>
        <button
          type="submit"
          disabled={!name.trim() || create.isPending}
          className="h-8 rounded-md bg-accent px-3 text-[13px] text-white disabled:opacity-50"
        >
          Create key
        </button>
      </form>
      {fresh && (
        <div className="rounded-md border border-accent/40 bg-hover p-3 text-[12.5px]">
          <div className="mb-1 font-medium">
            Copy “{fresh.name}” now. It will not be shown again.
          </div>
          <code data-testid="new-key" className="block break-all font-mono text-[12px]">
            {fresh.secret}
          </code>
          <button
            type="button"
            onClick={() => setFresh(null)}
            className="mt-2 text-accent hover:underline"
          >
            Done
          </button>
        </div>
      )}
      {live.length > 0 && (
        <ul className="divide-y divide-line rounded-md border border-line">
          {live.map((k) => (
            <li key={k.id} className="flex items-center gap-3 px-3 py-2 text-[13px]">
              <span className="flex-1 truncate">{k.name}</span>
              <span className="chip">{k.kind === "rest" ? "REST" : "MCP"}</span>
              <span className="w-28 text-[12px] text-ink3">
                {k.last_used_at ? `used ${formatShort(k.last_used_at.slice(0, 10))}` : "never used"}
              </span>
              <button
                type="button"
                onClick={() => revoke.mutate(k.id)}
                className="text-[12.5px] text-ink3 hover:text-red-500"
              >
                Revoke
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
