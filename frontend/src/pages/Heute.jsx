import { Link } from "react-router-dom";
import AgendaList from "../components/AgendaList";
import TrafficLight from "../components/TrafficLight";
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader, PriorityBadge, ProgressBar, Ring, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { STATUS } from "../lib/colors";
import { dateShort, dateTimeText, hours, num, relativeDay, signed, timeText } from "../lib/format";

function scoreColor(v) {
  if (v === null || v === undefined) return "#66788a";
  if (v >= 75) return "#22c55e";
  if (v >= 50) return "#eab308";
  return "#ef4444";
}

export default function Heute() {
  const { data, error, loading, reload } = useApi("/today");
  const toast = useToast();

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  const d = data;
  const tl = d.traffic_light;
  const st = STATUS[tl.color] || STATUS.grau;

  async function toggleHabit(h) {
    try {
      await api.post(`/habits/${h.id}/toggle`, { date: d.date });
      reload();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function doneTodo(t) {
    try {
      await api.patch(`/todos/${t.id}`, { done: true });
      toast(`„${t.title}“ erledigt ✓`, "success");
      reload();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function blockDone(b) {
    try {
      await api.post(`/study/blocks/${b.id}/status`, { status: "erledigt" });
      toast("Lernblock erledigt – stark! 💪", "success");
      reload();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  const n = d.nutrition;
  const agendaToday = d.agenda.filter((a) => a.status !== "verpasst");
  const habitsDone = d.habits.filter((h) => h.done).length;

  return (
    <div>
      <PageHeader
        title={d.greeting}
        subtitle={d.date_label}
        actions={
          d.next_exam && (
            <Badge color={d.next_exam.color}>
              📝 {d.next_exam.subject}: {d.next_exam.days_left === 0 ? "heute" : `noch ${d.next_exam.days_left} Tage`}
            </Badge>
          )
        }
      />

      {d.demo_active && (
        <div className="mb-5 rounded-lg border border-accent/25 bg-accent/5 px-4 py-2.5 text-sm text-ink-2">
          Du siehst <b className="text-accent">Beispieldaten</b>. Verbinde Garmin und Google unter{" "}
          <Link className="text-accent underline" to="/einstellungen">
            Einstellungen
          </Link>{" "}
          – dort kannst du die Beispieldaten auch löschen.
        </div>
      )}

      <div className="grid grid-cols-12 gap-5">
        {/* Recovery-Ampel */}
        <Card title="Recovery-Ampel" className="col-span-12 xl:col-span-6" actions={<Link to="/recovery" className="btn btn-sm">Details</Link>}>
          <div className="flex gap-5">
            <TrafficLight color={tl.color} />
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-3">
                <span className="font-display text-xl font-extrabold" style={{ color: st.color, textShadow: `0 0 12px ${st.glow}` }}>
                  {tl.headline}
                </span>
                {tl.score !== null && <span className="text-sm text-ink-3">Score {tl.score}/100</span>}
              </div>
              <p className="mt-1 text-sm text-ink-2">{tl.recommendation}</p>
              <ul className="mt-3 space-y-1 text-sm">
                {tl.reasons.map((r) => (
                  <li key={r} className="flex gap-2 text-ink-2">
                    <span style={{ color: st.color }}>›</span>
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Card>

        {/* Schlaf */}
        <Card title="Schlafscore" className="col-span-6 xl:col-span-3" actions={<Link to="/schlaf" className="btn btn-sm">›</Link>}>
          {d.sleep ? (
            <div className="flex items-center gap-4">
              <Ring value={d.sleep.score ?? 0} color={scoreColor(d.sleep.score)} size={92}>
                <span className="text-2xl font-bold">{num(d.sleep.score)}</span>
                <span className="text-[0.6rem] uppercase text-ink-3">Score</span>
              </Ring>
              <div className="space-y-1 text-sm">
                <div>
                  <b>{hours(d.sleep.duration_h)}</b> <span className="text-ink-3">/ Ziel {num(d.sleep.goal_h, 1)} h</span>
                </div>
                <div className="text-ink-2">Tief {hours(d.sleep.deep_h)}</div>
                <div className="text-ink-2">REM {hours(d.sleep.rem_h)}</div>
                <div className="text-xs text-ink-3">
                  {timeText(d.sleep.start)} – {timeText(d.sleep.end)}
                </div>
              </div>
            </div>
          ) : (
            <Empty icon="🌙">Noch keine Schlafdaten für heute.</Empty>
          )}
        </Card>

        {/* Body Battery */}
        <Card title="Body Battery" className="col-span-6 xl:col-span-3" actions={<Link to="/recovery" className="btn btn-sm">›</Link>}>
          {d.metrics ? (
            <div className="flex items-center gap-4">
              <Ring value={d.metrics.body_battery_wake ?? d.metrics.body_battery_high ?? 0} color={scoreColor(d.metrics.body_battery_wake ?? d.metrics.body_battery_high)} size={92}>
                <span className="text-2xl font-bold">{num(d.metrics.body_battery_wake ?? d.metrics.body_battery_high)}</span>
                <span className="text-[0.6rem] uppercase text-ink-3">Morgens</span>
              </Ring>
              <div className="space-y-1 text-sm text-ink-2">
                <div>Höchst {num(d.metrics.body_battery_high)}</div>
                <div>Tiefst {num(d.metrics.body_battery_low)}</div>
                <div>Ruhepuls {num(d.metrics.resting_hr)} bpm</div>
                <div>
                  Schritte {num(d.metrics.steps)}
                  {d.metrics.step_goal ? <span className="text-ink-3"> / {num(d.metrics.step_goal)}</span> : null}
                </div>
              </div>
            </div>
          ) : (
            <Empty icon="🔋">Noch keine Garmin-Tageswerte.</Empty>
          )}
        </Card>

        {/* Termine */}
        <Card title="Heute: Termine & Vorlesungen" className="col-span-12 lg:col-span-6 xl:col-span-4" actions={<Link to="/kalender" className="btn btn-sm">Kalender</Link>}>
          <AgendaList items={agendaToday} emptyText="Heute stehen keine Termine an." />
        </Card>

        {/* Lernblöcke */}
        <Card title="Anstehende Lernblöcke" className="col-span-12 lg:col-span-6 xl:col-span-4" actions={<Link to="/lernplan" className="btn btn-sm">Lernplan</Link>}>
          {d.study_blocks.length ? (
            <ul className="space-y-2">
              {d.study_blocks.map((b) => (
                <li key={b.id} className="flex items-center gap-3 rounded-lg border border-line/70 bg-[#0a1118] px-3 py-2">
                  <span className="h-8 w-1 rounded-full" style={{ background: b.color, boxShadow: `0 0 6px ${b.color}` }} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{b.title}</div>
                    <div className="text-xs text-ink-3">
                      {dateTimeText(b.start)}–{timeText(b.end)} · {b.kind === "lernen" ? "Lernen" : b.kind === "wiederholung" ? "Wiederholung" : "Puffer"}
                    </div>
                  </div>
                  {new Date(b.start) <= new Date() && (
                    <button className="btn btn-sm" onClick={() => blockDone(b)} title="Als erledigt markieren">
                      ✓
                    </button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <Empty icon="📚">Keine geplanten Lernblöcke.</Empty>
          )}
        </Card>

        {/* Kalorienbilanz */}
        <Card title="Kalorienbilanz" className="col-span-12 lg:col-span-6 xl:col-span-4" actions={<Link to="/naehrwerte" className="btn btn-sm">+ Mahlzeit</Link>}>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div>
              <div className="text-[0.65rem] uppercase tracking-wider text-ink-3">Gegessen</div>
              <div className="text-xl font-semibold">{num(n.intake)}</div>
              <div className="text-xs text-ink-3">kcal</div>
            </div>
            <div>
              <div className="text-[0.65rem] uppercase tracking-wider text-ink-3">Verbrauch</div>
              <div className="text-xl font-semibold">{n.burned ? num(n.burned) : "–"}</div>
              <div className="text-xs text-ink-3">laut Garmin</div>
            </div>
            <div>
              <div className="text-[0.65rem] uppercase tracking-wider text-ink-3">Bilanz</div>
              <div className="text-xl font-semibold" style={{ color: n.balance === null ? undefined : n.balance > 0 ? "#f59e0b" : "#22d3ee" }}>
                {n.balance === null ? "–" : signed(n.balance)}
              </div>
              <div className="text-xs text-ink-3">kcal</div>
            </div>
          </div>
          <div className="mt-4 space-y-2.5 text-xs">
            {[
              ["Kalorien", n.intake, n.goal, "kcal"],
              ["Protein", n.protein, n.protein_goal, "g"],
              ["Kohlenhydrate", n.carbs, n.carbs_goal, "g"],
              ["Fett", n.fat, n.fat_goal, "g"],
            ].map(([label, v, goal, unit]) => (
              <div key={label}>
                <div className="mb-1 flex justify-between text-ink-2">
                  <span>{label}</span>
                  <span>
                    {num(v)} / {num(goal)} {unit}
                  </span>
                </div>
                <ProgressBar value={v} max={goal} color={label === "Kalorien" ? "#e0620f" : "#0ea5b7"} height={6} label={label} />
              </div>
            ))}
          </div>
        </Card>

        {/* To-dos */}
        <Card title={`Offene To-dos (${d.todo_count})`} className="col-span-12 lg:col-span-7" actions={<Link to="/todos" className="btn btn-sm">Alle</Link>}>
          {d.todos.length ? (
            <ul className="divide-y divide-line/60">
              {d.todos.map((t) => (
                <li key={t.id} className="flex items-center gap-3 py-2">
                  <button
                    className="flex h-5 w-5 shrink-0 items-center justify-center rounded border border-ink-3 text-xs hover:border-accent hover:text-accent"
                    onClick={() => doneTodo(t)}
                    aria-label={`${t.title} erledigen`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm">{t.title}</div>
                    <div className="text-xs text-ink-3">
                      {t.category}
                      {t.subject ? ` · ${t.subject}` : ""}
                    </div>
                  </div>
                  <PriorityBadge priority={t.priority} />
                  {t.due_date && (
                    <span className={`w-20 text-right text-xs ${t.overdue ? "font-semibold text-red-400" : "text-ink-2"}`}>
                      {t.overdue ? `überfällig ${dateShort(t.due_date)}` : relativeDay(t.due_date)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <Empty icon="🎉">Alles erledigt!</Empty>
          )}
        </Card>

        {/* Habits */}
        <Card title={`Habits heute (${habitsDone}/${d.habits.length})`} className="col-span-12 lg:col-span-5" actions={<Link to="/habits" className="btn btn-sm">Habits</Link>}>
          {d.habits.length ? (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {d.habits.map((h) => (
                <button
                  key={h.id}
                  onClick={() => toggleHabit(h)}
                  className={`flex items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-sm transition ${
                    h.done ? "border-accent/50 bg-accent/10 shadow-[0_0_10px_rgba(34,211,238,0.15)]" : "border-line hover:border-accent/40"
                  }`}
                  aria-pressed={h.done}
                >
                  <span className="text-lg">{h.emoji}</span>
                  <span className="min-w-0 flex-1 truncate">{h.name}</span>
                  <span className="text-xs text-ink-3" title="Serie">
                    🔥{h.streak}
                  </span>
                  <span className={`text-sm ${h.done ? "text-accent" : "text-ink-3"}`}>{h.done ? "✓" : "○"}</span>
                </button>
              ))}
            </div>
          ) : (
            <Empty icon="✅">Lege Habits in den Einstellungen an.</Empty>
          )}
        </Card>
      </div>
    </div>
  );
}
