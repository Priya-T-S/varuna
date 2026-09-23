import { IconAlertTriangle } from "./Icons";

export function SimulatedBanner({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className="flex gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-amber-950"
      data-testid="simulated-banner"
      role="status"
    >
      <IconAlertTriangle className="mt-0.5 shrink-0 text-amber-600" size={18} />
      <div>
        <p className="text-[13px] font-semibold">Simulated — not a real model output</p>
        {!compact && (
          <p className="mt-0.5 text-[12.5px] leading-5 text-amber-900">
            The rainfall model isn't available right now, so these values were generated locally to let you try the
            workflow. Don't use them for real decisions.
          </p>
        )}
      </div>
    </div>
  );
}
