import { createFileRoute } from "@tanstack/react-router";
import { signOut } from "../components/Palette";
import { PageHeader, usePageContext } from "../components/TaskList";
import { useMe, usePatchSettings, useSettings } from "../lib/queries";
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
