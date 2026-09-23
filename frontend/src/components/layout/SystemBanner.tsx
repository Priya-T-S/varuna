import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getSystemStatus } from "../../api/systemApi";
import { cn } from "../../lib/cn";
import { formatDateTime } from "../../lib/format";
import { IconAlertTriangle } from "../ui/Icons";

function useOnline(): boolean {
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);
  return online;
}

/**
 * Degraded-state banner: stale rainfall data, AI model down, notification
 * failures, monitor errors, and lost connectivity. Real disaster systems can't
 * assume every feed is healthy, so the UI says so plainly.
 */
export function SystemBanner() {
  const online = useOnline();
  const status = useQuery({ queryKey: ["system-status"], queryFn: getSystemStatus, refetchInterval: 20000 });
  const lastGood = status.dataUpdatedAt ? new Date(status.dataUpdatedAt).toISOString() : null;

  const items: { key: string; severity: "warning" | "critical"; title: string; message: string }[] = [];
  if (!online || status.isError) {
    items.push({
      key: "offline",
      severity: "critical",
      title: online ? "Server unreachable" : "Connection lost",
      message: lastGood
        ? `Showing the last known data from ${formatDateTime(lastGood)}. Updates resume automatically when the connection returns.`
        : "Updates resume automatically when the connection returns.",
    });
  }
  if (online && status.data) {
    for (const d of status.data.degradations) items.push({ key: d.component, ...d });
  }
  const prototype = status.data?.prototype_mode !== false;

  return (
    <div className="border-b border-stone-200 bg-white">
      {prototype && (
        <div className="border-b border-violet-100 bg-violet-50/70">
          <p className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-2 gap-y-0.5 px-4 py-1.5 text-[12.5px] text-violet-900 sm:px-6">
            <b className="font-semibold">Prototype · Simulation mode.</b>
            <span>
              {status.data?.prototype_notice ??
                "Weather and river inputs are operator-provided, simulated or estimated. AI inference and risk analysis run on the supplied conditions."}
            </span>
            <Link className="ml-auto font-medium underline-offset-2 hover:underline" to="/status">Data sources</Link>
          </p>
        </div>
      )}
      {items.length > 0 && (
      <div className="mx-auto max-w-[1440px] space-y-1.5 px-4 py-2 sm:px-6">
        {items.map((i) => (
          <div
            className={cn(
              "flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-lg px-3 py-2 text-[13px]",
              i.severity === "critical" ? "bg-red-50 text-red-900" : "bg-amber-50 text-amber-900",
            )}
            key={i.key}
            role="status"
          >
            <IconAlertTriangle className={i.severity === "critical" ? "text-red-600" : "text-amber-600"} size={16} />
            <b className="font-semibold">{i.title}.</b>
            <span>{i.message}</span>
            <Link className="ml-auto text-[12.5px] font-medium underline-offset-2 hover:underline" to="/status">Details</Link>
          </div>
        ))}
      </div>
      )}
    </div>
  );
}
