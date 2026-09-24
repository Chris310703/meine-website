import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartTooltip, Legend, axisProps, barRadius, gridProps } from "../components/charts";
import { Card, ConfirmButton, Empty, ErrorBox, Field, Loading, PageHeader, ProgressBar, Segmented, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { C } from "../lib/colors";
import { dateShort, dayLabel, duration, km, num, paceText, timeText, todayIso } from "../lib/format";

const CAT_LABEL = { laufen: "Laufen", rad: "Rad", kraft: "Kraft", schwimmen: "Schwimmen", sonstiges: "Sonstiges" };
const CAT_ICON = { laufen: "🏃", rad: "🚴", kraft: "🏋️", schwimmen: "🏊", sonstiges: "⚡" };

function ZoneBar({ a }) {
  const zones = [a.z1_s, a.z2_s, a.z3_s, a.z4_s, a.z5_s];
  const total = zones.reduce((x, y) => x + (y || 0), 0);
  if (!total) return <span className="text-xs text-ink-3">–</span>;
  const shades = ["#5a2a0c", "#8a3b0d", "#b24c0e", C.orange, "#ff8a3d"];
  return (
    <div className="flex h-2 w-24 overflow-hidden rounded-full bg-[#15202a]" title={zones.map((z, i) => `Z${i + 1}: ${Math.round((z || 0) / 60)} min`).join(" · ")}>
      {zones.map((z, i) => (
        <div key={i} style={{ width: `${((z || 0) / total) * 100}%`, background: shades[i] }} />
      ))}
    </div>
  );
}

function PlannedWorkouts() {
  const { data, reload } = useApi("/fitness/planned");
  const toast = useToast();
  const [form, setForm] = useState({ date: todayIso(), start_time: "18:00", duration_min: 60, type: "running", title: "Lockerer Lauf" });

  async function add(e) {
    e.preventDefault();
    try {
      await api.post("/fitness/planned", { ...form, duration_min: Number(form.duration_min) });
      toast("Training geplant – Lernplan wurde angepasst.", "success");
      reload();
    } catch (err) {
      toast(err.message, "error");
    }
  }
  async function toggleDone(w) {
    await api.patch(`/fitness/planned/${w.id}`, { done: !w.done });
    reload();
  }
  async function remove(w) {
    await api.del(`/fitness/planned/${w.id}`);
    reload();
  }

  return (
    <Card title="Geplante Trainings">
      <form onSubmit={add} className="mb-4 grid grid-cols-2 gap-2">
        <Field label="Titel" className="col-span-2">
          <input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
        </Field>
        <Field label="Datum">
          <input type="date" className="input" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} required />
        </Field>
        <Field label="Uhrzeit">
          <input type="time" className="input" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} required />
        </Field>
        <Field label="Dauer (min)">
          <input type="number" min="5" className="input" value={form.duration_min} onChange={(e) => setForm({ ...form, duration_min: e.target.value })} />
        </Field>
        <Field label="Art">
          <select className="input" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            <option value="running">Laufen</option>
            <option value="cycling">Radfahren</option>
            <option value="strength_training">Krafttraining</option>
            <option value="swimming">Schwimmen</option>
            <option value="yoga">Yoga / Mobility</option>
            <option value="other">Sonstiges</option>
          </select>
        </Field>
        <button className="btn btn-primary col-span-2">+ Training planen</button>
      </form>
      {data?.length ? (
        <ul className="space-y-1.5">
          {data.map((w) => (
            <li key={w.id} className={`flex items-center gap-2 rounded-lg border border-line/70 px-2.5 py-1.5 text-sm ${w.done ? "opacity-60" : ""}`}>
              <button className={`h-5 w-5 shrink-0 rounded border text-xs ${w.done ? "border-accent text-accent" : "border-ink-3"}`} onClick={() => toggleDone(w)} aria-label="erledigt">
                {w.done ? "✓" : ""}
              </button>
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">{w.title}</div>
                <div className="text-xs text-ink-3">
                  {dayLabel(w.date)} · {w.start_time} · {w.duration_min} min · {w.type_label}
                  {w.synced ? " · 📅 Google" : ""}
                </div>
              </div>
              <ConfirmButton onConfirm={() => remove(w)} question="Löschen?">
                ✕
              </ConfirmButton>
            </li>
          ))}
        </ul>
      ) : (
        <Empty icon="🏃">Noch keine Trainings geplant.</Empty>
      )}
    </Card>
  );
}

export default function Fitness() {
  const { data, error, loading, reload } = useApi("/fitness/summary");
  const { data: acts } = useApi("/fitness/activities?days=120");
  const [period, setPeriod] = useState("weekly");
  const [metric, setMetric] = useState("km");
  const [cat, setCat] = useState("alle");

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;

  const vol = data[period];
  const metricLabel = { km: "Kilometer", hours: "Stunden", sessions: "Einheiten" }[metric];
  const filtered = (acts || []).filter((a) => cat === "alle" || a.category === cat);
  const z2 = data.z2;
  const z2Change = z2.change_sec_per_km_per_month;

  return (
    <div>
      <PageHeader title="Fitness" icon="🏃" subtitle="Training, Umfang, Herzfrequenzzonen und Leistungsentwicklung" />

      <div className="grid grid-cols-12 gap-5">
        <Card title="Wochenziele" className="col-span-12 lg:col-span-5">
          <div className="space-y-4">
            {data.goals.map((g) => (
              <div key={g.key}>
                <div className="mb-1.5 flex items-baseline justify-between text-sm">
                  <span className="text-ink-2">{g.label}</span>
                  <span>
                    <b className="text-lg">{num(g.value, g.unit === "" ? 0 : 1)}</b>
                    <span className="text-ink-3">
                      {" "}
                      / {num(g.goal)} {g.unit}
                    </span>
                  </span>
                </div>
                <ProgressBar value={g.value} max={g.goal} color={g.value >= g.goal ? "#22c55e" : C.orange} label={g.label} />
              </div>
            ))}
          </div>
        </Card>

        <Card title="Letzte 30 Tage" className="col-span-12 lg:col-span-7">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries(data.categories).map(([k, v]) => (
              <div key={k} className="rounded-lg border border-line bg-[#0a1118] p-3">
                <div className="text-xs text-ink-3">
                  {CAT_ICON[k]} {CAT_LABEL[k]}
                </div>
                <div className="mt-1 text-xl font-semibold">{v.sessions}×</div>
                <div className="text-xs text-ink-2">
                  {num(v.hours, 1)} h{v.km ? ` · ${num(v.km, 0)} km` : ""}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card
          title={`Umfang pro ${period === "weekly" ? "Woche" : "Monat"}`}
          className="col-span-12 xl:col-span-7"
          actions={
            <>
              <Segmented size="sm" value={metric} onChange={setMetric} options={[{ value: "km", label: "km" }, { value: "hours", label: "Std." }, { value: "sessions", label: "Einh." }]} />
              <Segmented size="sm" value={period} onChange={setPeriod} options={[{ value: "weekly", label: "Woche" }, { value: "monthly", label: "Monat" }]} />
            </>
          }
        >
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={vol} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="label" {...axisProps} interval={0} tick={{ ...axisProps.tick, fontSize: 10 }} />
              <YAxis {...axisProps} />
              <Tooltip content={<ChartTooltip valueFormatter={(v) => num(v, metric === "sessions" ? 0 : 1)} />} />
              <Bar dataKey={metric} name={metricLabel} fill={C.orange} radius={barRadius} maxBarSize={36} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Zeit in HF-Zonen · 28 Tage" className="col-span-12 xl:col-span-5">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data.zones} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="zone" {...axisProps} />
              <YAxis {...axisProps} tickFormatter={(v) => `${num(v / 60, v % 60 ? 1 : 0)} h`} width={44} />
              <Tooltip
                content={
                  <ChartTooltip
                    labelFormatter={(l, p) => `${l} · ${p?.[0]?.payload?.range ?? ""} · ${p?.[0]?.payload?.share ?? 0} %`}
                    valueFormatter={(v) => `${num(v)} min`}
                  />
                }
              />
              <Bar dataKey="prev_minutes" name="Vorperiode" fill="#3a2a1f" radius={barRadius} maxBarSize={22} />
              <Bar dataKey="minutes" name="Letzte 28 Tage" fill={C.orange} radius={barRadius} maxBarSize={22} />
            </BarChart>
          </ResponsiveContainer>
          <Legend items={[{ label: "Letzte 28 Tage", color: C.orange }, { label: "28 Tage davor", color: "#3a2a1f" }]} />
        </Card>

        <Card title={`Zone-2-Pace bei ${z2.reference_hr} bpm`} className="col-span-12 xl:col-span-7">
          {z2.points.length ? (
            <>
              <p className="-mt-1 mb-2 text-xs text-ink-3">
                Lockere Läufe (Zone 2: {z2.zone_range}) auf {z2.reference_hr} bpm normalisiert – sinkt die Kurve, wirst du bei gleichem Puls schneller.
                {z2Change !== null && (
                  <b className={`ml-1 ${z2Change < 0 ? "text-emerald-400" : "text-amber-400"}`}>
                    Trend: {z2Change < 0 ? "−" : "+"}
                    {num(Math.abs(z2Change), 1)} s/km pro Monat
                  </b>
                )}
              </p>
              <ResponsiveContainer width="100%" height={230}>
                <ComposedChart data={z2.points} margin={{ top: 8, right: 8, left: -4, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={30} />
                  <YAxis {...axisProps} reversed domain={["dataMin - 0.1", "dataMax + 0.1"]} tickFormatter={(v) => paceText(v).replace(" /km", "")} width={48} />
                  <Tooltip
                    content={
                      <ChartTooltip
                        labelFormatter={(l, p) => `${dayLabel(l)} · Ø ${p?.[0]?.payload?.hr ?? "–"} bpm, echt ${paceText(p?.[0]?.payload?.pace)}`}
                        valueFormatter={(v) => paceText(v)}
                      />
                    }
                  />
                  <Scatter dataKey="pace_ref" name={`Pace @ ${z2.reference_hr} bpm`} fill={C.accent} />
                  <Line dataKey="trend" name="Trend" stroke={C.orange} strokeWidth={2} strokeDasharray="6 4" dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
              <Legend items={[{ label: `Pace @ ${z2.reference_hr} bpm (Einzelläufe)`, color: C.accent }, { label: "Trend", color: C.orange, line: true }]} />
            </>
          ) : (
            <Empty icon="🏃">Noch keine lockeren Läufe in Zone 2 gefunden.</Empty>
          )}
        </Card>

        <Card title="VO2max-Verlauf" className="col-span-12 xl:col-span-5">
          {data.vo2max.length ? (
            <>
              <div className="-mt-1 mb-2 text-sm">
                Aktuell <b className="text-lg text-accent">{num(data.vo2max[data.vo2max.length - 1].vo2max, 1)}</b>
                <span className="text-ink-3"> ml/kg/min</span>
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={data.vo2max} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={40} />
                  <YAxis {...axisProps} domain={["dataMin - 1", "dataMax + 1"]} tickFormatter={(v) => num(v, 0)} />
                  <Tooltip content={<ChartTooltip labelFormatter={dayLabel} valueFormatter={(v) => num(v, 1)} />} />
                  <Line dataKey="vo2max" name="VO2max" stroke={C.accent} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </>
          ) : (
            <Empty icon="🫁">Noch keine VO2max-Werte.</Empty>
          )}
        </Card>

        <Card
          title="Aktivitäten"
          className="col-span-12 xl:col-span-8"
          actions={
            <Segmented
              size="sm"
              value={cat}
              onChange={setCat}
              options={[{ value: "alle", label: "Alle" }, { value: "laufen", label: "Laufen" }, { value: "rad", label: "Rad" }, { value: "kraft", label: "Kraft" }]}
            />
          }
        >
          <div className="max-h-[520px] overflow-y-auto">
            <table className="table">
              <thead className="sticky top-0 bg-card">
                <tr>
                  <th>Datum</th>
                  <th>Aktivität</th>
                  <th>Dauer</th>
                  <th>Distanz</th>
                  <th>Pace / Tempo</th>
                  <th>Ø HF</th>
                  <th>Last</th>
                  <th>HF-Zonen</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a) => (
                  <tr key={a.id}>
                    <td className="whitespace-nowrap text-ink-2">
                      {dayLabel(a.date)} <span className="text-ink-3">{timeText(a.start_time)}</span>
                    </td>
                    <td>
                      <div className="font-medium">
                        {CAT_ICON[a.category]} {a.name}
                      </div>
                      <div className="text-xs text-ink-3">{a.type_label}</div>
                    </td>
                    <td>{duration(a.duration_s)}</td>
                    <td>{a.distance_m ? km(a.distance_m, 2) : "–"}</td>
                    <td>{a.pace ? paceText(a.pace) : a.speed_kmh ? `${num(a.speed_kmh, 1)} km/h` : "–"}</td>
                    <td>{a.avg_hr ? `${num(a.avg_hr)} bpm` : "–"}</td>
                    <td>{num(a.training_load)}</td>
                    <td>
                      <ZoneBar a={a} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!filtered.length && <Empty icon="🏃">Keine Aktivitäten im Zeitraum.</Empty>}
          </div>
        </Card>

        <div className="col-span-12 xl:col-span-4">
          <PlannedWorkouts />
        </div>
      </div>
    </div>
  );
}
