import { useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartTooltip, Legend, axisProps, barRadius, gridProps } from "../components/charts";
import TrafficLight from "../components/TrafficLight";
import { Card, ErrorBox, Loading, PageHeader, ProgressBar, Segmented, Stat } from "../components/ui";
import { useApi } from "../lib/api";
import { C, STATUS } from "../lib/colors";
import { dateShort, dayLabel, num, signed, weekdayShort } from "../lib/format";

const HRV_STATUS = {
  BALANCED: ["ausgeglichen", "#22c55e"],
  UNBALANCED: ["unausgeglichen", "#eab308"],
  LOW: ["niedrig", "#f97316"],
  POOR: ["sehr niedrig", "#ef4444"],
};

function scoreColor(v) {
  return v >= 70 ? "#22c55e" : v >= 45 ? "#eab308" : "#ef4444";
}

export default function Recovery() {
  const [days, setDays] = useState(60);
  const { data, error, loading, reload } = useApi(`/recovery?days=${days}`);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;

  const tl = data.traffic_light;
  const st = STATUS[tl.color];
  const t = data.today;
  const tr = data.trends;
  const s = data.series;
  const hrvStatus = HRV_STATUS[t.hrv_status] || ["–", "#9fb0bf"];

  return (
    <div>
      <PageHeader
        title="Recovery"
        icon="🔋"
        subtitle="Erholung, Belastung und die Tagesampel für dein Training"
        actions={<Segmented value={days} onChange={setDays} options={[{ value: 30, label: "30 Tage" }, { value: 60, label: "60 Tage" }, { value: 120, label: "120 Tage" }]} />}
      />

      <div className="grid grid-cols-12 gap-5">
        <Card title="Tagesampel" className="col-span-12 xl:col-span-7">
          <div className="flex gap-6">
            <TrafficLight color={tl.color} size={44} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-3">
                <span className="font-display text-2xl font-extrabold" style={{ color: st.color, textShadow: `0 0 14px ${st.glow}` }}>
                  {tl.headline}
                </span>
                <span className="chip" style={{ color: st.color, borderColor: `${st.color}66` }}>
                  {st.icon} {st.label}
                  {tl.score !== null ? ` · ${tl.score}/100` : ""}
                </span>
              </div>
              <p className="mt-1.5 text-sm text-ink-2">{tl.recommendation}</p>
              <div className="mt-4 grid grid-cols-1 gap-x-6 gap-y-2.5 md:grid-cols-2">
                {tl.factors.map((f) => (
                  <div key={f.key}>
                    <div className="mb-1 flex justify-between text-xs">
                      <span className="text-ink-2">
                        {f.label}
                        {f.critical && <span className="ml-1 text-red-400">⚠</span>}
                      </span>
                      <span className="text-ink-3">{Math.round(f.score)}</span>
                    </div>
                    <ProgressBar value={f.score} color={scoreColor(f.score)} height={5} glow={false} label={f.label} />
                    <div className="mt-0.5 truncate text-[0.7rem] text-ink-3" title={f.text}>
                      {f.text}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>

        <Card title="Ampel der letzten 14 Tage" className="col-span-12 xl:col-span-5">
          <div className="grid grid-cols-7 gap-2">
            {data.history.map((h) => {
              const hs = STATUS[h.color];
              return (
                <div key={h.date} className="flex flex-col items-center gap-1 rounded-lg border border-line bg-[#0a1118] py-2" title={`${dayLabel(h.date)}: ${hs.label}${h.score ? ` (${h.score})` : ""}`}>
                  <span className="text-[0.62rem] text-ink-3">{weekdayShort(h.date)}</span>
                  <span className="flex h-6 w-6 items-center justify-center rounded-full text-[0.6rem] font-bold text-black" style={{ background: hs.color, boxShadow: `0 0 8px ${hs.glow}` }}>
                    {hs.icon}
                  </span>
                  <span className="text-[0.62rem] text-ink-3">{dateShort(h.date)}</span>
                </div>
              );
            })}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4">
            <Stat label="HRV-Status" value={<span style={{ color: hrvStatus[1] }}>{hrvStatus[0]}</span>} sub={`letzte Nacht ${num(t.hrv)} ms`} />
            <Stat label="Erholungszeit" value={t.recovery_h === null ? "–" : `${num(t.recovery_h)} h`} sub={`Bereitschaft ${num(t.readiness)}`} />
            <Stat label="Trainingsstatus" value={t.training_status || "–"} sub={`Akut/chronisch ${num(t.acwr, 2)}`} />
            <Stat label="Ruhepuls" value={`${num(t.rhr)} bpm`} sub={tr.rhr_30 ? `${signed(tr.rhr_7 - tr.rhr_30, 1)} (7 vs. 30 Tage)` : null} />
          </div>
        </Card>

        <Card title="HRV-Trend" className="col-span-12 xl:col-span-6">
          <p className="-mt-1 mb-2 text-xs text-ink-3">
            Ø 7 Tage {num(tr.hrv_7)} ms ({signed(tr.hrv_7 - tr.hrv_prev_7, 1)} zur Vorwoche). Das Band zeigt deinen Normalbereich.
          </p>
          <ResponsiveContainer width="100%" height={230}>
            <ComposedChart data={s} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={28} />
              <YAxis {...axisProps} domain={["dataMin - 5", "dataMax + 5"]} unit=" ms" width={56} />
              <Tooltip content={<ChartTooltip labelFormatter={dayLabel} valueFormatter={(v) => (Array.isArray(v) ? `${num(v[0])}–${num(v[1])} ms` : `${num(v)} ms`)} />} />
              <Area dataKey="baseline" name="Normalbereich" fill={C.accent} fillOpacity={0.08} stroke="none" isAnimationActive={false} />
              <Line dataKey="hrv" name="HRV (Nacht)" stroke={C.accent} strokeWidth={1.5} dot={{ r: 2, fill: C.accent }} />
              <Line dataKey="hrv_weekly" name="Ø 7 Tage" stroke={C.orange} strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
          <Legend items={[{ label: "HRV pro Nacht", color: C.accent, line: true }, { label: "Ø 7 Tage", color: C.orange, line: true }, { label: "Normalbereich", color: "#22d3ee33" }]} />
        </Card>

        <Card title="Ruhepuls-Trend" className="col-span-12 xl:col-span-6">
          <p className="-mt-1 mb-2 text-xs text-ink-3">
            Ø 7 Tage {num(tr.rhr_7, 1)} bpm · Ø 30 Tage {num(tr.rhr_30, 1)} bpm. Ein erhöhter Ruhepuls deutet auf Ermüdung, Stress oder Infekt hin.
          </p>
          <ResponsiveContainer width="100%" height={230}>
            <LineChart data={s} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={28} />
              <YAxis {...axisProps} domain={["dataMin - 2", "dataMax + 2"]} width={40} />
              <Tooltip content={<ChartTooltip labelFormatter={dayLabel} valueFormatter={(v) => `${num(v)} bpm`} />} />
              {tr.rhr_30 && <ReferenceLine y={tr.rhr_30} stroke={C.orange} strokeDasharray="5 4" label={{ value: "Ø 30 T.", fill: C.orange, fontSize: 11, position: "insideTopRight" }} />}
              <Line dataKey="rhr" name="Ruhepuls" stroke={C.accent} strokeWidth={2} dot={{ r: 2, fill: C.accent }} />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Body Battery" className="col-span-12 xl:col-span-6">
          <ResponsiveContainer width="100%" height={230}>
            <ComposedChart data={s} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={28} />
              <YAxis {...axisProps} domain={[0, 100]} />
              <Tooltip content={<ChartTooltip labelFormatter={dayLabel} valueFormatter={(v) => (Array.isArray(v) ? `${num(v[0])} → ${num(v[1])}` : num(v))} />} />
              <Bar dataKey="bb_range" name="Tiefst → Höchst" fill={C.orange} radius={[4, 4, 4, 4]} maxBarSize={12} />
              <Scatter dataKey="bb_wake" name="Beim Aufwachen" fill={C.accent} />
            </ComposedChart>
          </ResponsiveContainer>
          <Legend items={[{ label: "Spanne Tiefst- bis Höchstwert", color: C.orange }, { label: "Wert beim Aufwachen", color: C.accent }]} />
        </Card>

        <Card title="Stress (Tagesdurchschnitt)" className="col-span-12 xl:col-span-6">
          <p className="-mt-1 mb-2 text-xs text-ink-3">
            Ø 7 Tage {num(tr.stress_7)} ({signed(tr.stress_7 - tr.stress_prev_7, 1)} zur Vorwoche) · 0–25 ruhig, 26–50 niedrig, 51–75 mittel, 76–100 hoch
          </p>
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={s} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={28} />
              <YAxis {...axisProps} domain={[0, 100]} />
              <Tooltip content={<ChartTooltip labelFormatter={dayLabel} valueFormatter={(v) => num(v)} />} />
              <Bar dataKey="stress" name="Stress Ø" fill={C.orange} radius={barRadius} maxBarSize={14} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Trainingsbelastung: akut vs. chronisch" className="col-span-12 xl:col-span-8">
          <p className="-mt-1 mb-2 text-xs text-ink-3">
            Akut = letzte 7 Tage, chronisch = langfristiger Schnitt. Verhältnis aktuell <b className="text-ink">{num(t.acwr, 2)}</b> – optimal 0,8–1,3, über 1,5 steigt das
            Verletzungsrisiko.
          </p>
          <ResponsiveContainer width="100%" height={230}>
            <LineChart data={s} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={28} />
              <YAxis {...axisProps} />
              <Tooltip content={<ChartTooltip labelFormatter={dayLabel} valueFormatter={(v) => num(v)} />} />
              <Line dataKey="acute" name="Akute Last" stroke={C.orange} strokeWidth={2} dot={false} />
              <Line dataKey="chronic" name="Chronische Last" stroke={C.accent} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
          <Legend items={[{ label: "Akute Last (7 Tage)", color: C.orange, line: true }, { label: "Chronische Last", color: C.accent, line: true }]} />
        </Card>

        <Card title="Trainingsbereitschaft & Erholungszeit" className="col-span-12 xl:col-span-4">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={s.slice(-21)} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={20} />
              <YAxis {...axisProps} domain={[0, 100]} />
              <Tooltip
                content={
                  <ChartTooltip
                    labelFormatter={(l, p) => `${dayLabel(l)} · Erholungszeit ${num(p?.[0]?.payload?.recovery_h)} h`}
                    valueFormatter={(v) => num(v)}
                  />
                }
              />
              <Bar dataKey="readiness" name="Bereitschaft" fill={C.orange} radius={barRadius} maxBarSize={14} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>
    </div>
  );
}
