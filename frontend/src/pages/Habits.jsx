import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTooltip, axisProps, barRadius, gridProps } from "../components/charts";
import Pomodoro from "../components/Pomodoro";
import { Card, ConfirmButton, Empty, ErrorBox, Loading, Modal, PageHeader, Stat, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { C } from "../lib/colors";
import { dateShort, dayLabel, minutesText, num, timeText, relativeDay, toDate } from "../lib/format";

const WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
// Sequenzielle Skala in einer Farbe (Cyan), dunkel → hell
const HEAT = ["#15202a", "#155e6b", "#0f7f91", "#0fa5bb", "#22d3ee"];

function heatColor(share, total) {
  if (!total || share <= 0) return HEAT[0];
  if (share < 0.34) return HEAT[1];
  if (share < 0.67) return HEAT[2];
  if (share < 1) return HEAT[3];
  return HEAT[4];
}

function Heatmap({ days }) {
  const weeks = [];
  for (let i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7));
  return (
    <div>
      <div className="flex gap-1 overflow-x-auto pb-1">
        <div className="mr-1 flex flex-col gap-1 pt-4">
          {WD.map((w, i) => (
            <div key={w} className="h-3.5 text-[0.55rem] leading-[0.875rem] text-ink-3">
              {i % 2 === 0 ? w : ""}
            </div>
          ))}
        </div>
        {weeks.map((w, wi) => {
          const first = toDate(w[0].date);
          const showMonth = first.getDate() <= 7;
          return (
            <div key={wi} className="flex flex-col gap-1">
              <div className="h-3 text-[0.55rem] text-ink-3">{showMonth ? first.toLocaleDateString("de-DE", { month: "short" }) : ""}</div>
              {w.map((d) => (
                <div
                  key={d.date}
                  className="h-3.5 w-3.5 rounded-[3px]"
                  style={{ background: heatColor(d.share, d.total), boxShadow: d.share >= 1 ? "0 0 6px rgba(34,211,238,0.6)" : undefined }}
                  title={`${dayLabel(d.date)}: ${d.done}/${d.total} Habits`}
                />
              ))}
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex items-center gap-1.5 text-[0.65rem] text-ink-3">
        weniger
        {HEAT.map((c) => (
          <span key={c} className="h-3 w-3 rounded-[3px]" style={{ background: c }} />
        ))}
        mehr (alle erledigt)
      </div>
    </div>
  );
}

export default function Habits() {
  const { data, error, loading, reload } = useApi("/habits");
  const { data: focus, reload: reloadFocus } = useApi("/focus");
  const [manage, setManage] = useState(false);
  const [newHabit, setNewHabit] = useState({ emoji: "✨", name: "" });
  const toast = useToast();

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;

  const active = data.habits.filter((h) => h.active);
  const doneToday = active.filter((h) => h.done_today).length;

  async function toggle(h, date) {
    try {
      await api.post(`/habits/${h.id}/toggle`, date ? { date } : {});
      reload();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function addHabit(e) {
    e.preventDefault();
    await api.post("/habits", newHabit);
    setNewHabit({ emoji: "✨", name: "" });
    reload();
  }

  const weekDates = Array.from({ length: 7 }, (_, i) => {
    const d = toDate(data.week_start);
    d.setDate(d.getDate() + i);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  });
  const todayIdx = (new Date().getDay() + 6) % 7;

  return (
    <div>
      <PageHeader
        title="Habits"
        icon="✅"
        subtitle={`${doneToday} von ${active.length} Gewohnheiten heute erledigt`}
        actions={
          <button className="btn" onClick={() => setManage(true)}>
            ⚙ Habits verwalten
          </button>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <Card title="Diese Woche" className="col-span-12 xl:col-span-7">
          {active.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Gewohnheit</th>
                  {WD.map((w, i) => (
                    <th key={w} className={`text-center ${i === todayIdx ? "!text-accent" : ""}`}>
                      {w}
                    </th>
                  ))}
                  <th className="text-center">Serie</th>
                  <th className="text-center">30 T.</th>
                </tr>
              </thead>
              <tbody>
                {active.map((h) => (
                  <tr key={h.id}>
                    <td className="font-medium">
                      <span className="mr-2 text-lg">{h.emoji}</span>
                      {h.name}
                    </td>
                    {h.week.map((done, i) => (
                      <td key={i} className="text-center">
                        <button
                          disabled={i > todayIdx}
                          onClick={() => toggle(h, weekDates[i])}
                          aria-label={`${h.name} ${WD[i]}`}
                          aria-pressed={done}
                          className={`h-7 w-7 rounded-lg border text-sm transition disabled:opacity-20 ${
                            done ? "border-accent bg-accent/20 text-accent shadow-[0_0_8px_rgba(34,211,238,0.4)]" : "border-line hover:border-accent/50"
                          }`}
                        >
                          {done ? "✓" : ""}
                        </button>
                      </td>
                    ))}
                    <td className="text-center">
                      <span title={`Längste Serie: ${h.longest} Tage`}>🔥 {h.streak}</span>
                    </td>
                    <td className="whitespace-nowrap text-center text-ink-2">{h.rate_30} %</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty icon="✅">Noch keine Habits – lege welche unter „Habits verwalten“ an.</Empty>
          )}
          <div className="mt-5">
            <div className="card-title mb-2">Kalender-Heatmap · 26 Wochen</div>
            <Heatmap days={data.heatmap} />
          </div>
        </Card>

        <Card title="Fokus-Timer (Pomodoro)" className="col-span-12 xl:col-span-5">
          {focus ? <Pomodoro subjects={focus.subjects} blocks={focus.blocks} onLogged={() => { reloadFocus(); reload(); }} /> : <Loading />}
        </Card>

        {focus && (
          <>
            <Card title="Fokuszeit · 14 Tage" className="col-span-12 xl:col-span-7">
              <div className="mb-3 grid grid-cols-3 gap-4">
                <Stat label="Heute" value={minutesText(focus.today_minutes)} sub={`${focus.today_sessions} Sessions`} />
                <Stat label="14 Tage gesamt" value={minutesText(focus.daily.reduce((a, d) => a + d.minutes, 0))} />
                <Stat label="Ø pro Tag" value={minutesText(Math.round(focus.daily.reduce((a, d) => a + d.minutes, 0) / 14))} />
              </div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={focus.daily} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} />
                  <YAxis {...axisProps} />
                  <Tooltip content={<ChartTooltip labelFormatter={dayLabel} valueFormatter={(v) => `${num(v)} min`} />} />
                  <Bar dataKey="minutes" name="Fokus" fill={C.orange} radius={barRadius} maxBarSize={28} />
                </BarChart>
              </ResponsiveContainer>
              {focus.per_subject.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-ink-2">
                  {focus.per_subject.map((p) => (
                    <span key={p.subject} className="chip">
                      {p.subject}: {minutesText(p.minutes)}
                    </span>
                  ))}
                </div>
              )}
            </Card>

            <Card title="Protokoll" className="col-span-12 xl:col-span-5">
              {focus.sessions.length ? (
                <ul className="max-h-[330px] space-y-1.5 overflow-y-auto pr-1">
                  {focus.sessions.map((s) => (
                    <li key={s.id} className="flex items-center gap-2 rounded-lg border border-line/60 px-2.5 py-1.5 text-sm">
                      <span className="h-6 w-1 rounded-full" style={{ background: s.subject_color || "#66788a" }} />
                      <span className="w-28 text-xs text-ink-3">
                        {relativeDay(s.start)} {timeText(s.start)}
                      </span>
                      <span className="min-w-0 flex-1 truncate">
                        {s.subject || "Ohne Fach"}
                        {s.note ? <span className="text-ink-3"> · {s.note}</span> : null}
                      </span>
                      <span className="font-semibold">{num(s.minutes)} min</span>
                      <ConfirmButton onConfirm={() => api.del(`/focus/${s.id}`).then(reloadFocus)} question="?">
                        ✕
                      </ConfirmButton>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty icon="🍅">Noch keine Fokus-Sessions.</Empty>
              )}
            </Card>
          </>
        )}
      </div>

      <Modal open={manage} title="Habits verwalten" onClose={() => setManage(false)}>
        <form onSubmit={addHabit} className="mb-4 flex gap-2">
          <input className="input w-16 text-center" value={newHabit.emoji} onChange={(e) => setNewHabit({ ...newHabit, emoji: e.target.value })} aria-label="Emoji" />
          <input className="input flex-1" value={newHabit.name} onChange={(e) => setNewHabit({ ...newHabit, name: e.target.value })} placeholder="Neue Gewohnheit, z. B. 10 Min. Vokabeln" required />
          <button className="btn btn-primary">+</button>
        </form>
        <ul className="space-y-1.5">
          {data.habits.map((h) => (
            <li key={h.id} className="flex items-center gap-2 rounded-lg border border-line/60 px-2.5 py-1.5 text-sm">
              <span className="text-lg">{h.emoji}</span>
              <span className={`flex-1 ${h.active ? "" : "text-ink-3 line-through"}`}>{h.name}</span>
              <button className="btn btn-sm" onClick={() => api.patch(`/habits/${h.id}`, { active: !h.active }).then(reload)}>
                {h.active ? "Pausieren" : "Aktivieren"}
              </button>
              <ConfirmButton onConfirm={() => api.del(`/habits/${h.id}`).then(reload)} question="Samt Verlauf löschen?">
                ✕
              </ConfirmButton>
            </li>
          ))}
        </ul>
      </Modal>
    </div>
  );
}
