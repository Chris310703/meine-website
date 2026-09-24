import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTooltip, Legend, axisProps, barRadius, gridProps } from "../components/charts";
import { Card, ConfirmButton, Empty, ErrorBox, Field, Loading, PageHeader, ProgressBar, Ring, Stat, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { C } from "../lib/colors";
import { addDays, dateShort, dayLabel, isoDate, num, relativeDay, signed, todayIso, weekdayLong, dateLong } from "../lib/format";

const TYPE_ICON = { Frühstück: "🥣", Mittagessen: "🍝", Abendessen: "🍲", Snack: "🍎" };

function defaultType() {
  const h = new Date().getHours();
  if (h < 10) return "Frühstück";
  if (h < 15) return "Mittagessen";
  if (h < 17) return "Snack";
  return "Abendessen";
}

export default function Naehrwerte() {
  const [day, setDay] = useState(todayIso());
  const { data, error, loading, reload } = useApi(`/nutrition?day=${day}`);
  const [form, setForm] = useState({ meal_type: defaultType(), name: "", kcal: "", protein: "", carbs: "", fat: "" });
  const toast = useToast();

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  const s = data.summary;

  async function add(payload) {
    try {
      await api.post("/nutrition/meals", {
        date: day,
        meal_type: payload.meal_type,
        name: payload.name,
        kcal: Number(payload.kcal) || 0,
        protein: Number(payload.protein) || 0,
        carbs: Number(payload.carbs) || 0,
        fat: Number(payload.fat) || 0,
      });
      toast(`${payload.name} eingetragen.`, "success");
      reload();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function submit(e) {
    e.preventDefault();
    await add(form);
    setForm({ ...form, name: "", kcal: "", protein: "", carbs: "", fat: "" });
  }

  const remaining = s.goal - s.intake;
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <div>
      <PageHeader
        title="Nährwerte"
        icon="🥗"
        subtitle={`${weekdayLong(day)}, ${dateLong(day)}`}
        actions={
          <>
            <button className="btn" onClick={() => setDay(isoDate(addDays(day, -1)))}>
              ‹
            </button>
            <button className="btn" onClick={() => setDay(todayIso())}>
              Heute
            </button>
            <button className="btn" onClick={() => setDay(isoDate(addDays(day, 1)))} disabled={day >= todayIso()}>
              ›
            </button>
          </>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <Card title={`Tagesbilanz · ${relativeDay(day)}`} className="col-span-12 xl:col-span-5">
          <div className="flex items-center gap-6">
            <Ring value={s.intake} max={s.goal} size={130} stroke={10} color={s.intake > s.goal ? "#f59e0b" : C.orange}>
              <span className="text-2xl font-bold">{num(s.intake)}</span>
              <span className="text-[0.65rem] uppercase text-ink-3">von {num(s.goal)} kcal</span>
            </Ring>
            <div className="grid flex-1 grid-cols-2 gap-4">
              <Stat label={remaining >= 0 ? "Noch offen" : "Über Ziel"} value={num(Math.abs(remaining))} unit="kcal" />
              <Stat label="Verbrauch (Garmin)" value={s.burned ? num(s.burned) : "–"} unit="kcal" />
              <Stat
                label="Bilanz"
                value={s.balance === null ? "–" : signed(s.balance)}
                unit="kcal"
                color={s.balance === null ? undefined : s.balance > 0 ? "#f59e0b" : "#22d3ee"}
                sub={s.balance === null ? "kein Garmin-Wert" : s.balance > 0 ? "Überschuss" : "Defizit"}
              />
              <Stat label="Mahlzeiten" value={s.meals} />
            </div>
          </div>
          <div className="mt-5 space-y-3">
            {[
              ["Protein", s.protein, s.protein_goal],
              ["Kohlenhydrate", s.carbs, s.carbs_goal],
              ["Fett", s.fat, s.fat_goal],
            ].map(([label, v, goal]) => (
              <div key={label}>
                <div className="mb-1 flex justify-between text-xs text-ink-2">
                  <span>{label}</span>
                  <span>
                    {num(v)} / {num(goal)} g
                  </span>
                </div>
                <ProgressBar value={v} max={goal} color={C.cyan} height={6} label={label} />
              </div>
            ))}
          </div>
        </Card>

        <Card title="Mahlzeit eintragen" className="col-span-12 xl:col-span-7">
          <form onSubmit={submit} className="grid grid-cols-6 gap-3">
            <Field label="Mahlzeit" className="col-span-2">
              <select className="input" value={form.meal_type} onChange={set("meal_type")}>
                {data.meal_types.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </Field>
            <Field label="Was?" className="col-span-4">
              <input className="input" value={form.name} onChange={set("name")} placeholder="z. B. Mensa: Chili sin Carne" required />
            </Field>
            <Field label="kcal" className="col-span-2">
              <input type="number" min="0" className="input" value={form.kcal} onChange={set("kcal")} required />
            </Field>
            <Field label="Protein (g)">
              <input type="number" min="0" className="input" value={form.protein} onChange={set("protein")} />
            </Field>
            <Field label="KH (g)">
              <input type="number" min="0" className="input" value={form.carbs} onChange={set("carbs")} />
            </Field>
            <Field label="Fett (g)">
              <input type="number" min="0" className="input" value={form.fat} onChange={set("fat")} />
            </Field>
            <div className="flex items-end">
              <button className="btn btn-primary w-full">+ Eintragen</button>
            </div>
          </form>
          {data.favorites.length > 0 && (
            <div className="mt-4">
              <div className="label">Schnell eintragen (häufig gegessen)</div>
              <div className="flex flex-wrap gap-1.5">
                {data.favorites.map((f) => (
                  <button key={f.name} className="chip hover:border-accent/50 hover:text-accent" onClick={() => add(f)} title={`${num(f.kcal)} kcal · P ${num(f.protein)} g`}>
                    {TYPE_ICON[f.meal_type]} {f.name} · {num(f.kcal)}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Card>

        <Card title="Mahlzeiten" className="col-span-12 xl:col-span-5">
          {data.meal_types.map((t) => (
            <div key={t} className="mb-3">
              <div className="mb-1 flex items-center justify-between text-xs uppercase tracking-wider text-ink-3">
                <span>
                  {TYPE_ICON[t]} {t}
                </span>
                <span>{num((data.meals[t] || []).reduce((a, m) => a + m.kcal, 0))} kcal</span>
              </div>
              {(data.meals[t] || []).length ? (
                <ul className="space-y-1">
                  {data.meals[t].map((m) => (
                    <li key={m.id} className="flex items-center gap-2 rounded-lg border border-line/60 px-2.5 py-1.5 text-sm">
                      <span className="min-w-0 flex-1 truncate">{m.name}</span>
                      <span className="text-xs text-ink-3">
                        P {num(m.protein)} · K {num(m.carbs)} · F {num(m.fat)}
                      </span>
                      <span className="w-16 text-right font-semibold">{num(m.kcal)}</span>
                      <ConfirmButton onConfirm={() => api.del(`/nutrition/meals/${m.id}`).then(reload)} question="?">
                        ✕
                      </ConfirmButton>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="rounded-lg border border-dashed border-line px-3 py-2 text-xs text-ink-3">noch nichts</div>
              )}
            </div>
          ))}
        </Card>

        <Card title="Verlauf 14 Tage" className="col-span-12 xl:col-span-7">
          <div className="mb-3 grid grid-cols-3 gap-4">
            <Stat label="Ø Kalorien (7 T.)" value={num(data.avg_7.intake)} unit="kcal" sub={`${data.avg_7.days} Tage erfasst`} />
            <Stat label="Ø Protein (7 T.)" value={num(data.avg_7.protein)} unit="g" />
            <Stat label="Ø Bilanz (7 T.)" value={data.avg_7.balance === null ? "–" : signed(data.avg_7.balance)} unit="kcal" />
          </div>
          {data.history.some((h) => h.intake !== null) ? (
            <>
              <ResponsiveContainer width="100%" height={260}>
                <ComposedChart data={data.history} margin={{ top: 8, right: 8, left: -6, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} />
                  <YAxis {...axisProps} width={48} />
                  <Tooltip content={<ChartTooltip labelFormatter={dayLabel} valueFormatter={(v) => `${num(v)} kcal`} />} />
                  <ReferenceLine y={data.history[0].goal} stroke={C.accent} strokeDasharray="5 4" />
                  <Bar dataKey="intake" name="Gegessen" fill={C.orange} radius={barRadius} maxBarSize={26} />
                  <Line dataKey="burned" name="Verbrauch (Garmin)" stroke={C.accent} strokeWidth={2} dot={{ r: 2.5, fill: C.accent }} />
                </ComposedChart>
              </ResponsiveContainer>
              <Legend items={[{ label: "Gegessen", color: C.orange }, { label: "Verbrauch laut Garmin", color: C.accent, line: true }, { label: "Kalorienziel", color: C.accent, dashed: true, line: true }]} />
            </>
          ) : (
            <Empty icon="🥗">Noch keine Mahlzeiten erfasst.</Empty>
          )}
        </Card>
      </div>
    </div>
  );
}
