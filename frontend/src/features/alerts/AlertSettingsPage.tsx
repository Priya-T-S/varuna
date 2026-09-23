import { useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  createAlertRule,
  createRecipient,
  deleteAlertRule,
  deleteRecipient,
  evaluateRegion,
  getAlertRules,
  getProviders,
  getRecipients,
  sendTestAlert,
  updateAlertRule,
  updateRecipient,
} from "../../api/alertsApi";
import { getRegions } from "../../api/scenarioApi";
import { Button, buttonClass } from "../../components/ui/Button";
import { FloodBandChip } from "../../components/ui/FloodBandChip";
import { IconCheck, IconX } from "../../components/ui/Icons";
import { fieldClass, labelClass } from "../../components/ui/Input";
import { PageHeader, Panel } from "../../components/ui/Panel";
import { ErrorState, Skeleton } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import type {
  AlertChannel,
  AlertResponse,
  AlertRule,
  Antecedent,
  EvaluateRequest,
  EvaluateResponse,
  FloodLevel,
  Recipient,
  RecipientInput,
  RegionProfile,
} from "../../types/api";

const CHANNELS: AlertChannel[] = ["telegram", "email", "sms", "whatsapp"];
const CHANNEL_LABEL: Record<string, string> = {
  telegram: "Telegram", email: "E-mail", sms: "SMS", whatsapp: "WhatsApp", inapp: "Dashboard", console: "Server log",
};
const LEVELS: FloodLevel[] = ["moderate", "high", "severe"];
const field = cn(fieldClass, "mt-1.5");
const smallField = "rounded-md border border-stone-300 bg-white px-2 py-1 text-[12.5px] outline-none focus:border-brand-500";

const SETUP_HINTS: Record<string, string> = {
  telegram: "Create a bot with @BotFather, set TELEGRAM_BOT_TOKEN, and add each officer's chat id below. Optionally broadcast to a control-room group.",
  email: "With Gmail: turn on 2-step verification, create an App Password, then set SMTP_USER and SMTP_PASSWORD.",
  sms: "Twilio's free trial credit. Set the account SID, auth token and sender number. Trial accounts reach verified numbers only.",
  whatsapp: "Twilio's free WhatsApp sandbox. Each recipient sends the sandbox join code once.",
  inapp: "Always on. Pop-up and desktop notification on every open dashboard.",
  console: "Always on. Every alert is written to the server log for audit.",
};

function useInvalidate() {
  const qc = useQueryClient();
  return (...keys: string[]) => keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
}

export function AlertSettingsPage() {
  const regionsQuery = useQuery({ queryKey: ["regions"], queryFn: getRegions, staleTime: Infinity });
  const regions = regionsQuery.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        actions={<Link className={buttonClass("secondary")} to="/alerts">← Back to alerts</Link>}
        description="Choose who is alerted, how, and at what level. Alerts go out by Telegram, e-mail, SMS and WhatsApp, plus the live dashboard."
        eyebrow="Alerts"
        title="Recipients & channels"
      />
      <ProvidersPanel regions={regions} />
      <div className="grid gap-4 xl:grid-cols-2">
        <EvaluatePanel regions={regions} />
        <RulesPanel regions={regions} />
      </div>
      <RecipientsPanel regions={regions} />
    </div>
  );
}

// ---------------------------------------------------------------------------
function ProvidersPanel({ regions }: { regions: RegionProfile[] }) {
  const providersQuery = useQuery({ queryKey: ["providers"], queryFn: getProviders });
  const invalidate = useInvalidate();
  const [region, setRegion] = useState("Kerala");
  const [district, setDistrict] = useState<string>("");
  const [channels, setChannels] = useState<AlertChannel[]>([]);
  const [lastTest, setLastTest] = useState<AlertResponse | null>(null);
  const districts = regions.find((r) => r.name === region)?.districts ?? [];

  const test = useMutation({
    mutationFn: () =>
      sendTestAlert({ region, district: district || null, level: "high", channels: channels.length ? channels : null }),
    onSuccess: (alert) => {
      setLastTest(alert);
      invalidate("alerts");
    },
  });

  return (
    <Panel description="A channel switches on once its keys are added to backend/.env. Every option below has a free tier." title="Notification channels">
      {providersQuery.isLoading && <Skeleton className="h-24" />}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {providersQuery.data?.map((p) => (
          <div
            className={cn("rounded-xl border p-4", p.enabled ? "border-emerald-200 bg-emerald-50/40" : "border-stone-200 bg-white")}
            key={p.channel}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[14px] font-semibold text-stone-900">{p.name}</span>
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-medium",
                  p.enabled ? "bg-emerald-100 text-emerald-800" : "bg-stone-100 text-stone-500",
                )}
              >
                {p.enabled && <IconCheck size={12} />}
                {p.enabled ? "Active" : "Not set up"}
              </span>
            </div>
            <p className="mt-0.5 text-[12px] font-medium text-brand-700">{p.cost}</p>
            <p className="mt-2 text-[12.5px] leading-5 text-stone-600">{SETUP_HINTS[p.channel]}</p>
            {!p.enabled && p.missing_config.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {p.missing_config.map((k) => (
                  <code className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-[10.5px] text-stone-600" key={k}>{k}</code>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="mt-5 rounded-xl bg-stone-50 p-4">
        <p className="text-[14px] font-semibold text-stone-900">Send a test alert</p>
        <p className="mt-0.5 text-[12.5px] text-stone-500">Sends a realistic sample alert marked [TEST] to the chosen district's recipients.</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_1.6fr_auto] sm:items-end">
          <label className={labelClass}>
            Region
            <select className={field} onChange={(e) => { setRegion(e.target.value); setDistrict(""); }} value={region}>
              {regions.map((r) => <option key={r.name}>{r.name}</option>)}
            </select>
          </label>
          <label className={labelClass}>
            District
            <select className={field} onChange={(e) => setDistrict(e.target.value)} value={district}>
              <option value="">First district</option>
              {districts.map((d) => <option key={d.name}>{d.name}</option>)}
            </select>
          </label>
          <fieldset>
            <legend className={labelClass}>Only these channels (optional)</legend>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {CHANNELS.map((c) => (
                <ChannelPill
                  checked={channels.includes(c)}
                  key={c}
                  label={CHANNEL_LABEL[c]}
                  onChange={(on) => setChannels(on ? [...channels, c] : channels.filter((x) => x !== c))}
                />
              ))}
            </div>
          </fieldset>
          <Button disabled={test.isPending} onClick={() => test.mutate()} type="button">
            {test.isPending ? "Sending…" : "Send test"}
          </Button>
        </div>
        {test.isError && <div className="mt-3"><ErrorState body={(test.error as Error).message} title="Test failed" /></div>}
        {lastTest && (
          <div className="mt-3 rounded-lg border border-stone-200 bg-white p-3 text-[12.5px] text-stone-700">
            <p className="font-medium text-stone-900">
              Test alert #{lastTest.id} for {lastTest.district}
              {lastTest.deliveries.length === 0 && ": nothing sent. Add a recipient with contact details for this district."}
            </p>
            <ul className="mt-2 space-y-1">
              {lastTest.deliveries.map((d) => (
                <li className="flex flex-wrap items-center gap-2" key={d.id}>
                  <DeliveryBadge status={d.status} />
                  <span className="font-medium">{CHANNEL_LABEL[d.channel] ?? d.channel}</span> → {d.recipient_name}
                  {d.error ? <span className="text-stone-500">({d.error})</span> : null}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
function EvaluatePanel({ regions }: { regions: RegionProfile[] }) {
  const invalidate = useInvalidate();
  const [form, setForm] = useState<EvaluateRequest>({
    region: "Kerala", rain_event_mm: 350, duration_days: 3, antecedent: "saturated",
    dam_release: false, high_tide: false, dispatch: true, ignore_cooldown: false,
  });
  const [result, setResult] = useState<EvaluateResponse | null>(null);
  const run = useMutation({
    mutationFn: () => evaluateRegion(form),
    onSuccess: (data) => {
      setResult(data);
      invalidate("alerts");
    },
  });
  const patch = (p: Partial<EvaluateRequest>) => setForm({ ...form, ...p });

  return (
    <Panel description="Enter observed or forecast rain for a region. Any district that crosses its threshold is alerted straight away." title="Evaluate now">
      <div className="grid grid-cols-2 gap-3">
        <label className={labelClass}>
          Region
          <select className={field} onChange={(e) => patch({ region: e.target.value })} value={form.region}>
            {regions.map((r) => <option key={r.name}>{r.name}</option>)}
          </select>
        </label>
        <label className={labelClass}>
          Total rain (mm)
          <input className={field} min={0} onChange={(e) => patch({ rain_event_mm: Number(e.target.value) })} type="number" value={form.rain_event_mm ?? 0} />
        </label>
        <label className={labelClass}>
          Over how many days
          <input className={field} max={10} min={1} onChange={(e) => patch({ duration_days: Number(e.target.value) })} type="number" value={form.duration_days ?? 3} />
        </label>
        <label className={labelClass}>
          Soil before rain
          <select className={field} onChange={(e) => patch({ antecedent: e.target.value as Antecedent })} value={form.antecedent}>
            <option value="dry">Dry</option>
            <option value="normal">Normal</option>
            <option value="saturated">Saturated</option>
          </select>
        </label>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <ChannelPill checked={!!form.dam_release} label="Dam release" onChange={(v) => patch({ dam_release: v })} />
        <ChannelPill checked={!!form.high_tide} label="High tide" onChange={(v) => patch({ high_tide: v })} />
        <ChannelPill checked={!!form.ignore_cooldown} label="Ignore cooldown" onChange={(v) => patch({ ignore_cooldown: v })} />
      </div>
      <Button className="mt-4" disabled={run.isPending} onClick={() => run.mutate()} type="button">
        {run.isPending ? "Evaluating…" : "Evaluate & send alerts"}
      </Button>
      {run.isError && <div className="mt-3"><ErrorState body={(run.error as Error).message} title="Evaluation failed" /></div>}
      {result && (
        <div className="mt-4 overflow-hidden rounded-lg border border-stone-200">
          <table className="w-full text-[13px]">
            <thead className="bg-stone-50 text-[12px] text-stone-500">
              <tr>
                <th className="px-3 py-2 text-left font-medium">District</th>
                <th className="px-3 py-2 text-left font-medium">Level</th>
                <th className="px-3 py-2 text-right font-medium">Probability</th>
                <th className="px-3 py-2 text-left font-medium">Outcome</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {result.districts.map((d) => (
                <tr key={d.district}>
                  <td className="px-3 py-2 font-medium text-stone-800">{d.district}</td>
                  <td className="px-3 py-2"><FloodBandChip band={d.level} /></td>
                  <td className="px-3 py-2 text-right tabular-nums">{(d.flood_probability * 100).toFixed(0)}%</td>
                  <td className={cn("px-3 py-2 text-[12.5px]", d.action.includes("issued") ? "font-medium text-brand-700" : "text-stone-500")}>
                    {d.action.includes("issued") ? `Alert sent (${d.action.replace(" issued", "")})` : d.action.includes("cooldown") ? "Already alerted recently" : "Below threshold"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
function RulesPanel({ regions }: { regions: RegionProfile[] }) {
  const rulesQuery = useQuery({ queryKey: ["alert-rules"], queryFn: getAlertRules });
  const invalidate = useInvalidate();
  const save = useMutation({
    mutationFn: (rule: AlertRule) => updateAlertRule(rule.id, rule),
    onSuccess: () => invalidate("alert-rules"),
  });
  const add = useMutation({
    mutationFn: () => createAlertRule({ region: regions[0]?.name ?? "Kerala", district: null, min_level: "high", min_probability: 0, cooldown_minutes: 180, active: true }),
    onSuccess: () => invalidate("alert-rules"),
  });
  const remove = useMutation({ mutationFn: deleteAlertRule, onSuccess: () => invalidate("alert-rules") });

  return (
    <Panel
      actions={<Button onClick={() => add.mutate()} size="sm" type="button" variant="secondary">+ Add rule</Button>}
      description="When to alert. The most specific rule wins (district, then region, then everywhere). The cooldown prevents repeats unless the risk gets worse."
      title="Alert thresholds"
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[30rem] text-[13px]">
          <thead className="text-[12px] text-stone-500">
            <tr>
              <th className="pb-2 text-left font-medium">Applies to</th>
              <th className="pb-2 text-left font-medium">Alert from</th>
              <th className="pb-2 text-left font-medium">Min. probability</th>
              <th className="pb-2 text-left font-medium">Cooldown</th>
              <th />
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {rulesQuery.data?.map((rule) => (
              <RuleRow key={rule.id} onDelete={() => remove.mutate(rule.id)} onSave={(r) => save.mutate(r)} regions={regions} rule={rule} />
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function RuleRow({ rule, regions, onSave, onDelete }: { rule: AlertRule; regions: RegionProfile[]; onSave: (r: AlertRule) => void; onDelete: () => void }) {
  const [draft, setDraft] = useState(rule);
  const dirty = JSON.stringify(draft) !== JSON.stringify(rule);
  const districts = regions.find((r) => r.name === draft.region)?.districts ?? [];
  return (
    <tr>
      <td className="py-2 pr-2">
        <div className="flex flex-wrap gap-1">
          <select className={smallField} onChange={(e) => setDraft({ ...draft, region: e.target.value || null, district: null })} value={draft.region ?? ""}>
            <option value="">Everywhere</option>
            {regions.map((r) => <option key={r.name}>{r.name}</option>)}
          </select>
          {draft.region && (
            <select className={smallField} onChange={(e) => setDraft({ ...draft, district: e.target.value || null })} value={draft.district ?? ""}>
              <option value="">All districts</option>
              {districts.map((d) => <option key={d.name}>{d.name}</option>)}
            </select>
          )}
        </div>
      </td>
      <td className="py-2 pr-2">
        <select className={smallField} onChange={(e) => setDraft({ ...draft, min_level: e.target.value as FloodLevel })} value={draft.min_level}>
          {LEVELS.map((l) => <option key={l} value={l}>{l[0].toUpperCase() + l.slice(1)}</option>)}
        </select>
      </td>
      <td className="py-2 pr-2">
        <input className={cn(smallField, "w-16")} max={1} min={0} onChange={(e) => setDraft({ ...draft, min_probability: Number(e.target.value) })} step={0.05} type="number" value={draft.min_probability} />
      </td>
      <td className="whitespace-nowrap py-2 pr-2">
        <input className={cn(smallField, "w-16")} min={0} onChange={(e) => setDraft({ ...draft, cooldown_minutes: Number(e.target.value) })} type="number" value={draft.cooldown_minutes} />
        <span className="ml-1 text-stone-500">min</span>
      </td>
      <td className="whitespace-nowrap py-2 text-right">
        {dirty && <Button onClick={() => onSave(draft)} size="sm" type="button">Save</Button>}
        <Button aria-label="Delete rule" onClick={onDelete} size="sm" type="button" variant="danger"><IconX size={14} /></Button>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
const EMPTY_RECIPIENT: RecipientInput = {
  name: "", role: "collector", region: "Kerala", district: null, phone: "", whatsapp: "", email: "",
  telegram_chat_id: "", channels: [], min_level: "high", active: true,
};

function RecipientsPanel({ regions }: { regions: RegionProfile[] }) {
  const recipientsQuery = useQuery({ queryKey: ["recipients"], queryFn: getRecipients });
  const invalidate = useInvalidate();
  const [regionFilter, setRegionFilter] = useState("all");
  const [editing, setEditing] = useState<{ id: number | null; data: RecipientInput } | null>(null);

  const saveMutation = useMutation({
    mutationFn: ({ id, data }: { id: number | null; data: RecipientInput }) => {
      const clean = { ...data, phone: data.phone || null, whatsapp: data.whatsapp || null, email: data.email || null, telegram_chat_id: data.telegram_chat_id || null };
      return id === null ? createRecipient(clean) : updateRecipient(id, clean);
    },
    onSuccess: () => {
      setEditing(null);
      invalidate("recipients");
    },
  });
  const removeMutation = useMutation({ mutationFn: deleteRecipient, onSuccess: () => invalidate("recipients") });

  const all = recipientsQuery.data ?? [];
  const reachable = all.filter((r) => r.active && r.channels.length > 0).length;
  const rows = useMemo(
    () => all.filter((r) => regionFilter === "all" || r.region === regionFilter),
    [all, regionFilter],
  );

  return (
    <Panel
      actions={
        <div className="flex items-center gap-2">
          <select className={cn(smallField, "py-1.5")} onChange={(e) => setRegionFilter(e.target.value)} value={regionFilter}>
            <option value="all">All regions</option>
            {regions.map((r) => <option key={r.name}>{r.name}</option>)}
          </select>
          <Button onClick={() => setEditing({ id: null, data: { ...EMPTY_RECIPIENT } })} size="sm" type="button">+ Add recipient</Button>
        </div>
      }
      bodyClassName="p-0"
      description={`${reachable} of ${all.length} officials can currently be reached. District collectors are pre-listed: click Edit to add their contact details and channels.`}
      title="Recipients"
    >
      {editing && (
        <div className="border-b border-stone-100 p-5">
          <RecipientForm
            error={saveMutation.isError ? (saveMutation.error as Error).message : null}
            onCancel={() => setEditing(null)}
            onChange={(data) => setEditing({ ...editing, data })}
            onSave={() => saveMutation.mutate(editing)}
            regions={regions}
            saving={saveMutation.isPending}
            value={editing.data}
          />
        </div>
      )}
      <div className="scroll-quiet max-h-[30rem] overflow-auto">
        <table className="w-full min-w-[46rem] text-left text-[13.5px]">
          <thead className="sticky top-0 z-10 bg-stone-50 text-[12px] text-stone-500">
            <tr>
              <th className="px-5 py-2.5 font-medium">Official</th>
              <th className="px-3 py-2.5 font-medium">Area</th>
              <th className="px-3 py-2.5 font-medium">Channels</th>
              <th className="px-3 py-2.5 font-medium">Gets alerts from</th>
              <th />
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {rows.map((r) => (
              <tr className={cn("transition-colors hover:bg-stone-50", !r.active && "opacity-50")} key={r.id}>
                <td className="px-5 py-2.5">
                  <p className="font-medium text-stone-900">{r.name}</p>
                  <p className="text-[12px] text-stone-500">
                    {[r.email, r.phone, r.telegram_chat_id && `Telegram ${r.telegram_chat_id}`].filter(Boolean).join(" · ") || "No contact details yet"}
                  </p>
                </td>
                <td className="px-3 py-2.5 text-stone-600">{r.district ?? "Whole region"}<span className="text-stone-400"> · {r.region}</span></td>
                <td className="px-3 py-2.5">
                  {r.channels.length ? (
                    <span className="flex flex-wrap gap-1">
                      {r.channels.map((c) => <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[11.5px] font-medium text-brand-700" key={c}>{CHANNEL_LABEL[c]}</span>)}
                    </span>
                  ) : (
                    <span className="text-[12.5px] text-stone-400">Not set</span>
                  )}
                </td>
                <td className="px-3 py-2.5"><FloodBandChip band={r.min_level} /></td>
                <td className="whitespace-nowrap px-3 py-2.5 text-right">
                  <Button onClick={() => setEditing({ id: r.id, data: toInput(r) })} size="sm" type="button" variant="ghost">Edit</Button>
                  <Button aria-label={`Remove ${r.name}`} onClick={() => removeMutation.mutate(r.id)} size="sm" type="button" variant="danger"><IconX size={14} /></Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function toInput(r: Recipient): RecipientInput {
  const { id: _id, created_at: _created, ...rest } = r;
  return { ...rest, phone: rest.phone ?? "", whatsapp: rest.whatsapp ?? "", email: rest.email ?? "", telegram_chat_id: rest.telegram_chat_id ?? "" };
}

function RecipientForm({
  value, regions, onChange, onSave, onCancel, saving, error,
}: {
  value: RecipientInput; regions: RegionProfile[]; onChange: (v: RecipientInput) => void;
  onSave: () => void; onCancel: () => void; saving: boolean; error: string | null;
}) {
  const patch = (p: Partial<RecipientInput>) => onChange({ ...value, ...p });
  const districts = regions.find((r) => r.name === value.region)?.districts ?? [];
  return (
    <form
      className="grid gap-4 rounded-xl border border-brand-200 bg-brand-50/40 p-4 sm:grid-cols-2 lg:grid-cols-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSave();
      }}
    >
      <p className="text-[14px] font-semibold text-stone-900 sm:col-span-2 lg:col-span-4">{value.name ? `Edit ${value.name}` : "New recipient"}</p>
      <label className={labelClass}>Name<input className={field} onChange={(e) => patch({ name: e.target.value })} required value={value.name} /></label>
      <label className={labelClass}>
        Role
        <select className={field} onChange={(e) => patch({ role: e.target.value as Recipient["role"] })} value={value.role}>
          <option value="collector">District Collector / DC</option>
          <option value="adm">ADM / SDM</option>
          <option value="sdma">SDMA / State EOC</option>
          <option value="control_room">Control room</option>
          <option value="other">Other</option>
        </select>
      </label>
      <label className={labelClass}>
        Region
        <select className={field} onChange={(e) => patch({ region: e.target.value, district: null })} value={value.region}>
          {regions.map((r) => <option key={r.name}>{r.name}</option>)}
        </select>
      </label>
      <label className={labelClass}>
        District
        <select className={field} onChange={(e) => patch({ district: e.target.value || null })} value={value.district ?? ""}>
          <option value="">Whole region</option>
          {districts.map((d) => <option key={d.name}>{d.name}</option>)}
        </select>
      </label>
      <label className={labelClass}>E-mail<input className={field} onChange={(e) => patch({ email: e.target.value })} placeholder="collector@example.gov.in" type="email" value={value.email ?? ""} /></label>
      <label className={labelClass}>Phone<input className={field} onChange={(e) => patch({ phone: e.target.value })} placeholder="+91 98…" value={value.phone ?? ""} /></label>
      <label className={labelClass}>WhatsApp (if different)<input className={field} onChange={(e) => patch({ whatsapp: e.target.value })} placeholder="+91 98…" value={value.whatsapp ?? ""} /></label>
      <label className={labelClass}>Telegram chat id<input className={field} onChange={(e) => patch({ telegram_chat_id: e.target.value })} placeholder="e.g. 123456789" value={value.telegram_chat_id ?? ""} /></label>
      <fieldset className="sm:col-span-2">
        <legend className={labelClass}>Send alerts by</legend>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {CHANNELS.map((c) => (
            <ChannelPill
              checked={value.channels.includes(c)}
              key={c}
              label={CHANNEL_LABEL[c]}
              onChange={(on) => patch({ channels: on ? [...value.channels, c] : value.channels.filter((x) => x !== c) })}
            />
          ))}
        </div>
      </fieldset>
      <label className={labelClass}>
        Alert from level
        <select className={field} onChange={(e) => patch({ min_level: e.target.value as FloodLevel })} value={value.min_level}>
          {LEVELS.map((l) => <option key={l} value={l}>{l[0].toUpperCase() + l.slice(1)} and above</option>)}
        </select>
      </label>
      <label className="flex items-end gap-2 pb-2 text-[13px] text-stone-700">
        <input checked={value.active} className="accent-brand-700" onChange={(e) => patch({ active: e.target.checked })} type="checkbox" /> Active
      </label>
      {error && <p className="text-[12.5px] text-red-700 sm:col-span-2 lg:col-span-4">{error}</p>}
      <div className="flex gap-2 sm:col-span-2 lg:col-span-4">
        <Button disabled={saving} type="submit">{saving ? "Saving…" : "Save recipient"}</Button>
        <Button onClick={onCancel} type="button" variant="ghost">Cancel</Button>
      </div>
    </form>
  );
}

function ChannelPill({ checked, label, onChange }: { checked: boolean; label: string; onChange: (on: boolean) => void }): ReactNode {
  return (
    <label
      className={cn(
        "inline-flex cursor-pointer select-none items-center gap-1.5 rounded-full border px-3 py-1 text-[12.5px] font-medium transition-colors",
        checked ? "border-brand-600 bg-brand-700 text-white" : "border-stone-300 bg-white text-stone-600 hover:border-stone-400",
      )}
    >
      <input checked={checked} className="sr-only" onChange={(e) => onChange(e.target.checked)} type="checkbox" />
      {checked && <IconCheck size={12} />}
      {label}
    </label>
  );
}

function DeliveryBadge({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-[11px] font-medium capitalize",
        status === "sent" && "bg-emerald-50 text-emerald-700",
        status === "failed" && "bg-red-50 text-red-700",
        status === "skipped" && "bg-stone-100 text-stone-500",
      )}
    >
      {status}
    </span>
  );
}
