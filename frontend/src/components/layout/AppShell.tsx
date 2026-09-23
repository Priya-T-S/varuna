import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSystemStatus } from "../../api/systemApi";
import { LiveAlertFeed } from "../../features/alerts/LiveAlertFeed";
import { useUiStore } from "../../store/uiStore";
import { cn } from "../../lib/cn";
import {
  IconActivity,
  IconBell,
  IconBrain,
  IconCpu,
  IconHistory,
  IconHome,
  IconMenu,
  IconSparkles,
  IconTarget,
  IconX,
  LogoMark,
} from "../ui/Icons";
import { SystemBanner } from "./SystemBanner";

const NAV: { to: string; label: string; icon: ReactNode; end?: boolean }[] = [
  { to: "/", label: "Overview", icon: <IconHome />, end: true },
  { to: "/what-if", label: "What-if", icon: <IconSparkles /> },
  { to: "/alerts", label: "Alerts", icon: <IconBell /> },
  { to: "/analysis", label: "Analysis", icon: <IconTarget /> },
  { to: "/explainability", label: "Explainability", icon: <IconBrain /> },
  { to: "/history", label: "History", icon: <IconHistory /> },
  { to: "/model", label: "Model", icon: <IconCpu /> },
  { to: "/status", label: "Status", icon: <IconActivity /> },
];

type Tone = "ok" | "warn" | "down" | "info";

const PILL_TONE: Record<Tone, string> = {
  ok: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warn: "border-amber-200 bg-amber-50 text-amber-800",
  down: "border-red-200 bg-red-50 text-red-800",
  info: "border-violet-200 bg-violet-50 text-violet-800",
};
const DOT_TONE: Record<Tone, string> = {
  ok: "bg-emerald-600",
  warn: "bg-amber-500",
  down: "bg-red-600",
  info: "bg-violet-500",
};

/** Honest, per-source status: the model can be online while data is demo or simulated. */
function useStatusPills(): { key: string; label: string; value: string; tone: Tone; title: string }[] {
  const simulatorMode = useUiStore((s) => s.simulatorMode);
  const status = useQuery({ queryKey: ["system-status"], queryFn: getSystemStatus, refetchInterval: 20000 });
  if (status.isError) return [{ key: "api", label: "Server", value: "Offline", tone: "down", title: "The backend can't be reached" }];
  const c = status.data?.components;
  if (!c) return [{ key: "api", label: "Status", value: "Connecting…", tone: "warn", title: "" }];

  const ai: Tone = c.ai_model.state === "online" && simulatorMode !== "forced" ? "ok" : "down";
  const weatherTone: Tone =
    c.weather_data.state === "observed" ? "ok"
      : c.weather_data.state === "delayed" ? "warn"
        : c.weather_data.state === "demo" || c.weather_data.state === "scenario" ? "info"
          : "warn";
  return [
    { key: "ai", label: "AI", value: simulatorMode === "forced" ? "Simulator" : c.ai_model.label, tone: ai, title: `AI model: ${c.ai_model.detail}` },
    { key: "weather", label: "Weather", value: c.weather_data.label, tone: weatherTone, title: `Weather data: ${c.weather_data.detail}` },
    { key: "river", label: "River", value: c.river_data.label, tone: "info", title: `River data: ${c.river_data.detail}` },
  ];
}

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const pills = useStatusPills();

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-stone-900">
      <header className="sticky top-0 z-[1100] border-b border-stone-200/80 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-4 px-4 sm:px-6">
          <NavLink className="flex shrink-0 items-center gap-2.5" to="/">
            <LogoMark />
            <span className="leading-tight">
              <span className="block text-[15px] font-semibold tracking-[0.06em] text-stone-950">VARUNA AI</span>
              <span className="hidden text-[11px] text-stone-500 sm:block">Flood & rainfall early warning</span>
            </span>
          </NavLink>

          <nav aria-label="Primary" className="hidden items-center gap-0.5 lg:flex">
            {NAV.map((item) => (
              <NavLink
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-[13.5px] transition-colors",
                    isActive
                      ? "bg-brand-50 font-semibold text-brand-800"
                      : "text-stone-600 hover:bg-stone-100 hover:text-stone-900",
                  )
                }
                end={item.end}
                key={item.to}
                to={item.to}
              >
                <span className="hidden 2xl:inline">{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <NavLink className="hidden items-center gap-1.5 md:flex" title="System status" to="/status">
              {pills.map((p) => (
                <span
                  className={cn("flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-[11.5px]", PILL_TONE[p.tone])}
                  key={p.key}
                  title={p.title}
                >
                  <span className={cn("h-1.5 w-1.5 rounded-full", DOT_TONE[p.tone])} />
                  <span className="opacity-75">{p.label}:</span>
                  <span className="font-semibold">{p.value}</span>
                </span>
              ))}
            </NavLink>
            <button
              aria-expanded={menuOpen}
              aria-label={menuOpen ? "Close navigation" : "Open navigation"}
              className="grid h-9 w-9 place-items-center rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-100 lg:hidden"
              onClick={() => setMenuOpen((open) => !open)}
              type="button"
            >
              {menuOpen ? <IconX size={18} /> : <IconMenu size={18} />}
            </button>
          </div>
        </div>
        {menuOpen && (
          <nav aria-label="Mobile" className="grid gap-1 border-t border-stone-200 bg-white px-4 py-3 sm:grid-cols-2 lg:hidden">
            {NAV.map((item) => (
              <NavLink
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 rounded-lg px-3 py-2.5 text-[14px]",
                    isActive ? "bg-brand-50 font-semibold text-brand-800" : "text-stone-600 hover:bg-stone-100",
                  )
                }
                end={item.end}
                key={item.to}
                onClick={() => setMenuOpen(false)}
                to={item.to}
              >
                {item.icon}
                {item.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>
      <SystemBanner />

      <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 sm:px-6" key={location.pathname}>
        <div className="animate-fade-up">
          <Outlet />
        </div>
      </main>

      <footer className="border-t border-stone-200/80 bg-white/60">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-2 px-4 py-4 text-[12px] text-stone-500 sm:px-6">
          <span>VARUNA AI · Explainable extreme-rainfall intelligence · SIH260006 (ISRO)</span>
          <span>Decision support only. Always verify conditions on the ground.</span>
        </div>
      </footer>
      <LiveAlertFeed />
    </div>
  );
}
