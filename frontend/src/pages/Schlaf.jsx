import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTooltip, Legend, axisProps, barRadius, gridProps } from "../components/charts";
import { Card, Empty, ErrorBox, Loading, PageHeader, Segmented, Stat } from "../components/ui";
import { useApi } from "../lib/api";
import { C, SLEEP_COLORS } from "../lib/colors";
import { dateShort, dayLabel, hours, num, signed, timeText } from "../lib/format";

/** Minuten relativ zu Mitternacht → "23:40" */
function clock(min) {
  if (min === null || min === undefined) return "–";
  const m = ((Math.round(min) % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

export default function Schlaf() {
  const [days, setDays] = useState(30);
  const { data, error, loading, reload } = useApi(`/sleep?days=${days}`);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data.nights.length)
    return (
      <div>
        <PageHeader title="Schlaf" icon="🌙" />
        <Card>
          <Empty icon="🌙">Noch keine Schlafdaten. Synchronisiere deine Garmin-Uhr.</Empty>
        </Card>
      </div>
    );

  const a7 = data.avg_7;
  const p7 = data.avg_prev_7;
  const a30 = data.avg_30;
  const reg = data.regularity_14;
  const nights = data.nights.map((n) => ({ ...n, window: n.bed_min !== null && n.wake_min !== null ? [n.bed_min, n.wake_min] : null }));
  const lastNights = [...data.nights].reverse().slice(0, 10);

  return (
    <div>
      <PageHeader
        title="Schlaf"
        icon="🌙"
        subtitle={`Schlafziel: ${num(data.goal_h, 1)} h · Zielzeiten ${data.bedtime_target}–${data.wake_target}`}
        actions={<Segmented value={days} onChange={setDays} options={[{ value: 14, label: "14 Tage" }, { value: 30, label: "30 Tage" }, { value: 90, label: "90 Tage" }]} />}
      />

      <div className="grid grid-cols-12 gap-5">
        <Card className="col-span-12">
          <div className="grid grid-cols-2 gap-5 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="Ø Dauer (7 Nächte)" value={hours(a7.duration_h)} sub={p7.nights ? `${signed((a7.duration_h - p7.duration_h) * 60, 0, " min")} zur Vorwoche` : null} />
            <Stat label="Ø Schlafscore" value={num(a7.score)} sub={p7.nights ? `${signed(a7.score - p7.score)} zur Vorwoche` : null} />
            <Stat label="Ø Tiefschlaf" value={hours(a7.deep_h)} sub={`${num((a7.deep_h / a7.duration_h) * 100)} % der Nacht`} />
            <Stat label="Ø REM" value={hours(a7.rem_h)} sub={`${num((a7.rem_h / a7.duration_h) * 100)} % der Nacht`} />
            <Stat label="Ziel erreicht" value={`${data.goal_met_7}/7`} sub={`${data.goal_met_30}/30 im Monat`} />
            <Stat
              label="Regelmäßigkeit (14 T.)"
              value={reg.score === null ? "–" : `${reg.score}/100`}
              sub={reg.score === null ? reg.label : `${reg.label} · ±${reg.bed_sd} min / ±${reg.wake_sd} min`}
            />
          </div>
        </Card>

        <Card title="Schlafdauer & Phasen pro Nacht" className="col-span-12 xl:col-span-8">
          <ResponsiveContainer width="100%" height={430}>
            <BarChart data={nights} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={18} />
              <YAxis {...axisProps} unit=" h" domain={[0, 10]} ticks={[0, 2, 4, 6, 8, 10]} allowDataOverflow={false} />
              <Tooltip
                content={
                  <ChartTooltip
                    labelFormatter={(l, p) => `${dayLabel(l)} · gesamt ${hours(p?.[0]?.payload?.duration_h)}`}
                    valueFormatter={(v) => hours(v)}
                  />
                }
              />
              <ReferenceLine y={data.goal_h} stroke={C.accent} strokeDasharray="5 4" label={{ value: `Ziel ${num(data.goal_h, 1)} h`, fill: C.accent, fontSize: 11, position: "insideTopRight" }} />
              <Bar dataKey="deep_h" name="Tief" stackId="s" fill={SLEEP_COLORS.deep} stroke="#0d141b" strokeWidth={1.5} maxBarSize={26} />
              <Bar dataKey="light_h" name="Leicht" stackId="s" fill={SLEEP_COLORS.light} stroke="#0d141b" strokeWidth={1.5} maxBarSize={26} />
              <Bar dataKey="rem_h" name="REM" stackId="s" fill={SLEEP_COLORS.rem} stroke="#0d141b" strokeWidth={1.5} maxBarSize={26} />
              <Bar dataKey="awake_h" name="Wach" stackId="s" fill={SLEEP_COLORS.awake} stroke="#0d141b" strokeWidth={1.5} radius={barRadius} maxBarSize={26} />
            </BarChart>
          </ResponsiveContainer>
          <Legend
            items={[
              { label: "Tiefschlaf", color: SLEEP_COLORS.deep },
              { label: "Leichtschlaf", color: SLEEP_COLORS.light },
              { label: "REM", color: SLEEP_COLORS.rem },
              { label: "Wach", color: SLEEP_COLORS.awake },
              { label: "Schlafziel", color: C.accent, dashed: true, line: true },
            ]}
          />
        </Card>

        <Card title="Letzte Nächte" className="col-span-12 xl:col-span-4">
          <table className="table text-sm">
            <thead>
              <tr>
                <th>Nacht</th>
                <th>Dauer</th>
                <th>Tief</th>
                <th>REM</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {lastNights.map((n) => (
                <tr key={n.date}>
                  <td className="whitespace-nowrap">
                    <div>{dayLabel(n.date)}</div>
                    <div className="text-xs text-ink-3">
                      {timeText(n.start)}–{timeText(n.end)}
                    </div>
                  </td>
                  <td className={n.goal_met ? "text-emerald-400" : ""}>{hours(n.duration_h)}</td>
                  <td>{hours(n.deep_h)}</td>
                  <td>{hours(n.rem_h)}</td>
                  <td>
                    <span className="font-semibold">{num(n.score)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card title="Schlafscore-Verlauf" className="col-span-12 xl:col-span-6">
          <ResponsiveContainer width="100%" height={230}>
            <LineChart data={nights} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={24} />
              <YAxis {...axisProps} domain={[30, 100]} />
              <Tooltip content={<ChartTooltip labelFormatter={dayLabel} valueFormatter={(v) => num(v)} />} />
              <ReferenceLine y={80} stroke="#22c55e55" strokeDasharray="4 4" />
              <Line dataKey="score" name="Schlafscore" stroke={C.accent} strokeWidth={2} dot={{ r: 2.5, fill: C.accent }} />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Einschlaf- & Aufwachzeiten" className="col-span-12 xl:col-span-6">
          <p className="-mt-1 mb-2 text-xs text-ink-3">
            Balken = Schlaffenster. Ø Einschlafen {clock(a7.bedtime_min)}, Ø Aufwachen {clock(a7.waketime_min)} (7 Nächte).
          </p>
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={nights} margin={{ top: 8, right: 8, left: -4, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={24} />
              <YAxis {...axisProps} reversed domain={[-240, 660]} ticks={[-180, -60, 60, 180, 300, 420, 540]} tickFormatter={clock} width={44} />
              <Tooltip
                content={
                  <ChartTooltip
                    labelFormatter={dayLabel}
                    valueFormatter={(v) => (Array.isArray(v) ? `${clock(v[0])} – ${clock(v[1])}` : clock(v))}
                  />
                }
              />
              <Bar dataKey="window" name="Schlaffenster" fill={C.orange} radius={[4, 4, 4, 4]} maxBarSize={14} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Durchschnitte" className="col-span-12">
          <table className="table text-sm">
            <thead>
              <tr>
                <th>Zeitraum</th>
                <th>Nächte</th>
                <th>Dauer</th>
                <th>Tief</th>
                <th>Leicht</th>
                <th>REM</th>
                <th>Wach</th>
                <th>Score</th>
                <th>Einschlafen</th>
                <th>Aufwachen</th>
              </tr>
            </thead>
            <tbody>
              {[
                { label: "Letzte 7 Nächte", ...a7, strong: true },
                { label: "Letzte 30 Nächte", ...a30, strong: true },
                ...[...data.weekly].reverse().map((w) => ({ label: `${w.week} (ab ${dateShort(w.start)})`, ...w })),
              ].map((r) => (
                <tr key={r.label} className={r.strong ? "font-semibold" : ""}>
                  <td>{r.label}</td>
                  <td>{r.nights}</td>
                  <td>{hours(r.duration_h)}</td>
                  <td>{hours(r.deep_h)}</td>
                  <td>{hours(r.light_h)}</td>
                  <td>{hours(r.rem_h)}</td>
                  <td>{hours(r.awake_h)}</td>
                  <td>{num(r.score)}</td>
                  <td>{clock(r.bedtime_min)}</td>
                  <td>{clock(r.waketime_min)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}
