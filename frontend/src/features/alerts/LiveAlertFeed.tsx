import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { create } from "zustand";
import { alertStreamUrl } from "../../api/alertsApi";
import type { AlertStreamEvent, FloodLevel } from "../../types/api";
import { FloodBandChip } from "../../components/ui/FloodBandChip";

interface LiveState {
  connected: boolean;
  setConnected: (connected: boolean) => void;
}

/** Whether the SSE feed is up; pages fall back to polling when it is not. */
export const useLiveFeed = create<LiveState>((set) => ({
  connected: false,
  setConnected: (connected) => set({ connected }),
}));

interface Toast {
  key: number;
  alertId: number;
  level: FloodLevel;
  title: string;
  message: string;
}

const MAX_TOASTS = 3;

/** Mounted once in the app shell: keeps an EventSource open, refreshes alert
 *  queries on every event and pops a toast + browser notification for new alerts. */
export function LiveAlertFeed() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const setConnected = useLiveFeed((s) => s.setConnected);
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(alertStreamUrl());
    // The server ends each stream every ~10 s and EventSource reconnects by itself;
    // only report "disconnected" if it stays down past a short grace period.
    let dropTimer: number | undefined;
    source.onopen = () => {
      window.clearTimeout(dropTimer);
      setConnected(true);
    };
    source.onerror = () => {
      window.clearTimeout(dropTimer);
      dropTimer = window.setTimeout(() => setConnected(false), 5000);
    };
    source.onmessage = (message) => {
      let event: AlertStreamEvent;
      try {
        event = JSON.parse(message.data) as AlertStreamEvent;
      } catch {
        return;
      }
      if (event.type === "hello") return;
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["alerts-recent"] });
      if (event.type === "snapshot" || event.type === "alert") {
        queryClient.invalidateQueries({ queryKey: ["current-risk"] });
        queryClient.invalidateQueries({ queryKey: ["system-status"] });
      }
      if (event.type !== "alert") return;

      const toast: Toast = { key: Date.now(), alertId: event.alert_id, level: event.level, title: event.title, message: event.message };
      setToasts((current) => [toast, ...current].slice(0, MAX_TOASTS));
      window.setTimeout(() => setToasts((current) => current.filter((t) => t.key !== toast.key)), 15000);

      if ("Notification" in window && Notification.permission === "granted") {
        const note = new Notification(`VARUNA AI · ${event.title}`, { body: event.message.slice(0, 180), tag: `alert-${event.alert_id}` });
        note.onclick = () => {
          window.focus();
          navigate("/alerts");
        };
      }
    };
    return () => {
      window.clearTimeout(dropTimer);
      source.close();
      setConnected(false);
    };
  }, [navigate, queryClient, setConnected]);

  if (!toasts.length) return null;
  return (
    <div className="fixed bottom-4 right-4 z-[1200] flex w-[23rem] max-w-[calc(100vw-2rem)] flex-col gap-2" role="status">
      {toasts.map((t) => (
        <button
          className="animate-fade-up rounded-xl border border-stone-200 bg-white p-4 text-left shadow-lift transition-colors hover:border-brand-200"
          key={t.key}
          onClick={() => {
            setToasts((current) => current.filter((x) => x.key !== t.key));
            navigate("/alerts");
          }}
          type="button"
        >
          <div className="flex items-center gap-2">
            <FloodBandChip band={t.level} />
            <span className="text-[13px] font-semibold text-stone-900">{t.title}</span>
          </div>
          <p className="mt-1 line-clamp-3 text-xs leading-5 text-stone-700">{t.message}</p>
        </button>
      ))}
    </div>
  );
}
