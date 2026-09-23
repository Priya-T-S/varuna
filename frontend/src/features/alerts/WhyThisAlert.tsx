import type { ReactNode } from "react";
import type { AlertResponse } from "../../types/api";
import { FLOOD_BAND_LABEL } from "../../components/ui/FloodBandChip";
import {
  IconActivity,
  IconAlertTriangle,
  IconArrowRight,
  IconBrain,
  IconDrop,
  IconHistory,
  IconMapPin,
  IconTarget,
} from "../../components/ui/Icons";

const ICONS: Record<string, ReactNode> = {
  rain: <IconDrop size={15} />,
  soil: <IconTarget size={15} />,
  river: <IconActivity size={15} />,
  terrain: <IconMapPin size={15} />,
  dam: <IconAlertTriangle size={15} />,
  tide: <IconActivity size={15} />,
  drainage: <IconDrop size={15} />,
  history: <IconHistory size={15} />,
  ai: <IconBrain size={15} />,
};

/** Compact, scannable reasons for a warning, with a link to the full SHAP explanation. */
export function WhyThisAlert({
  alert,
  onOpenExplanation,
  limit,
}: {
  alert: AlertResponse;
  onOpenExplanation?: () => void;
  limit?: number;
}) {
  const items = alert.why?.length
    ? alert.why
    : (alert.top_drivers ?? []).map((text) => ({ icon: "history", text, modelled: false }));
  const shown = limit ? items.slice(0, limit) : items;

  return (
    <section className="rounded-xl border border-stone-200 bg-stone-50/60 p-4">
      <h4 className="text-[14px] font-semibold text-stone-900">Why {FLOOD_BAND_LABEL[alert.flood_level]} risk?</h4>
      <ul className="mt-2.5 space-y-2">
        {shown.map((w) => (
          <li className="flex items-start gap-2.5 text-[13.5px] leading-snug text-stone-800" key={w.text}>
            <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md bg-white text-brand-600 shadow-sm ring-1 ring-stone-200">
              {ICONS[w.icon] ?? <IconArrowRight size={14} />}
            </span>
            <span className="pt-0.5">
              {w.text}
              {w.modelled && (
                <span className="ml-1.5 rounded-full bg-violet-50 px-1.5 py-0.5 text-[10.5px] font-medium text-violet-700 ring-1 ring-inset ring-violet-600/20">
                  modelled
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
      {onOpenExplanation && (
        <button
          className="mt-3 inline-flex items-center gap-1 text-[13px] font-medium text-brand-700 hover:underline"
          onClick={onOpenExplanation}
          type="button"
        >
          View full explanation <IconArrowRight size={14} />
        </button>
      )}
    </section>
  );
}
