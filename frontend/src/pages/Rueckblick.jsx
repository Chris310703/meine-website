import { useState } from "react";
import { Link } from "react-router-dom";
import Markdown from "../components/Markdown";
import { Card, ErrorBox, Loading, PageHeader, Segmented, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { euro, hours, minutesText, num } from "../lib/format";

const TONE = { good: "text-emerald-300 border-emerald-500/30 bg-emerald-500/5", bad: "text-amber-200 border-amber-500/30 bg-amber-500/5", neutral: "text-ink-2 border-line bg-white/[0.02]" };

/** Wert mit Veränderung zum Vorzeitraum; `better` = "up" | "down" | null (neutral) */
function Row({ label, value, cur, prev, better = "up", format = (v) => num(v, 1) }) {
  let delta = null;
  if (typeof cur === "number" && typeof prev === "number") delta = cur - prev;
  const good = delta === null || delta === 0 || !better ? null : (delta > 0) === (better === "up");
  return (
    <div className="flex items-baseline justify-between border-b border-line/40 py-1.5 text-sm last:border-0">
      <span className="text-ink-2">{label}</span>
      <span className="flex items-baseline gap-2">
        <b className="text-ink">{value}</b>
        {delta !== null && delta !== 0 && (
          <span className={`text-xs ${good === null ? "text-ink-3" : good ? "text-emerald-400" : "text-red-400"}`}>
            {delta > 0 ? "▲" : "▼"} {format(Math.abs(delta))}
          </span>
        )}
      </span>
    </div>
  );
}

export default function Rueckblick() {
  const [period, setPeriod] = useState("woche");
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useApi(`/review?period=${period}&offset=${offset}`);
  const [summary, setSummary] = useState({});
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;

  const c = data.current;
  const p = data.previous;
  const key = `${period}-${offset}`;

  async function aiSummary() {
    setBusy(true);
    try {
      const r = await api.post("/review/ai-summary", { period, offset });
      setSummary({ ...summary, [key]: r.text });
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  const vs = period === "woche" ? "Vorwoche" : "Vormonat";

  return (
    <div>
      <PageHeader
        title="Rückblick"
        icon="🔭"
        subtitle={`${data.label}${data.is_running ? ` · läuft noch · Vergleich mit den ersten ${data.compare_days} Tagen der ${vs}` : ` · Vergleich zur ${vs}`}`}
        actions={
          <>
            <Segmented
              value={period}
              onChange={(v) => {
                setPeriod(v);
                setOffset(0);
              }}
              options={[{ value: "woche", label: "Woche" }, { value: "monat", label: "Monat" }]}
            />
            <button className="btn" onClick={() => setOffset(offset + 1)}>
              ‹
            </button>
            <button className="btn" onClick={() => setOffset(Math.max(0, offset - 1))} disabled={offset === 0}>
              ›
            </button>
          </>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <Card title="Auf einen Blick" className="col-span-12 xl:col-span-7">
          {data.highlights.length ? (
            <ul className="space-y-2">
              {data.highlights.map((h) => (
                <li key={h.text} className={`flex gap-3 rounded-lg border px-3 py-2 text-sm ${TONE[h.tone]}`}>
                  <span className="text-base">{h.icon}</span>
                  <span>{h.text}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-3">Für diesen Zeitraum gibt es noch keine Daten.</p>
          )}
        </Card>

        <Card title="KI-Zusammenfassung" className="col-span-12 xl:col-span-5">
          {summary[key] ? (
            <Markdown text={summary[key]} />
          ) : data.claude_available ? (
            <div className="flex flex-col items-start gap-3 text-sm text-ink-2">
              <p>Claude fasst den Zeitraum zusammen: was gut lief, was nicht und drei konkrete Vorsätze.</p>
              <button className="btn btn-primary" onClick={aiSummary} disabled={busy}>
                {busy ? <span className="spin inline-block h-3 w-3 rounded-full border-2 border-accent border-t-transparent" /> : "✨"} Zusammenfassung erstellen
              </button>
            </div>
          ) : (
            <p className="text-sm text-ink-3">
              Mit einem Claude-API-Schlüssel schreibt dir die KI hier eine persönliche Zusammenfassung. Einrichtung:{" "}
              <Link to="/einstellungen" className="text-accent underline">
                Einstellungen
              </Link>
              .
            </p>
          )}
        </Card>

        <Card title="🏃 Training" className="col-span-12 md:col-span-6 xl:col-span-4">
          <Row label="Einheiten" value={c.training.sessions} cur={c.training.sessions} prev={p.training.sessions} format={(v) => num(v)} />
          <Row label="Trainingszeit" value={`${num(c.training.hours, 1)} h`} cur={c.training.hours} prev={p.training.hours} />
          <Row label="Laufkilometer" value={`${num(c.training.run_km, 1)} km`} cur={c.training.run_km} prev={p.training.run_km} />
          <Row label="Zeit in Zone 2" value={minutesText(c.training.z2_minutes)} cur={c.training.z2_minutes} prev={p.training.z2_minutes} format={(v) => `${num(v)} min`} />
          <Row label="Harte Minuten (Z4/Z5)" value={minutesText(c.training.hard_minutes)} cur={c.training.hard_minutes} prev={p.training.hard_minutes} better={null} format={(v) => `${num(v)} min`} />
          <Row label="Trainingslast" value={num(c.training.load)} cur={c.training.load} prev={p.training.load} better={null} format={(v) => num(v)} />
        </Card>

        <Card title="🌙 Schlaf" className="col-span-12 md:col-span-6 xl:col-span-4">
          <Row label="Ø Schlafdauer" value={hours(c.sleep.avg_hours)} cur={c.sleep.avg_hours} prev={p.sleep.avg_hours} format={(v) => `${num(v * 60)} min`} />
          <Row label="Ø Schlafscore" value={num(c.sleep.avg_score)} cur={c.sleep.avg_score} prev={p.sleep.avg_score} format={(v) => num(v)} />
          <Row label="Ø Tiefschlaf" value={hours(c.sleep.avg_deep_h)} cur={c.sleep.avg_deep_h} prev={p.sleep.avg_deep_h} format={(v) => `${num(v * 60)} min`} />
          <Row label="Ø REM" value={hours(c.sleep.avg_rem_h)} cur={c.sleep.avg_rem_h} prev={p.sleep.avg_rem_h} format={(v) => `${num(v * 60)} min`} />
          <Row label={`Ziel (${num(c.sleep.goal_h, 1)} h) erreicht`} value={`${c.sleep.goal_met}/${c.sleep.nights}`} />
        </Card>

        <Card title="🔋 Recovery" className="col-span-12 md:col-span-6 xl:col-span-4">
          <Row label="Ø HRV" value={`${num(c.recovery.avg_hrv)} ms`} cur={c.recovery.avg_hrv} prev={p.recovery.avg_hrv} format={(v) => `${num(v)} ms`} />
          <Row label="Ø Ruhepuls" value={`${num(c.recovery.avg_rhr, 1)} bpm`} cur={c.recovery.avg_rhr} prev={p.recovery.avg_rhr} better="down" />
          <Row label="Ø Stress" value={num(c.recovery.avg_stress)} cur={c.recovery.avg_stress} prev={p.recovery.avg_stress} better="down" format={(v) => num(v)} />
          <Row label="Ø Body Battery morgens" value={num(c.recovery.avg_body_battery)} cur={c.recovery.avg_body_battery} prev={p.recovery.avg_body_battery} format={(v) => num(v)} />
          <Row label="Ampel grün / gelb / rot" value={`${c.recovery.traffic_lights.gruen} / ${c.recovery.traffic_lights.gelb} / ${c.recovery.traffic_lights.rot}`} />
          <Row label="Ø Schritte" value={num(c.recovery.avg_steps)} cur={c.recovery.avg_steps} prev={p.recovery.avg_steps} format={(v) => num(v)} />
        </Card>

        <Card title="📚 Lernen" className="col-span-12 md:col-span-6 xl:col-span-4">
          <Row label="Gelernt" value={minutesText(c.study.done_minutes)} cur={c.study.done_minutes} prev={p.study.done_minutes} format={(v) => `${num(v)} min`} />
          <Row label="Erledigte Blöcke" value={c.study.done_blocks} cur={c.study.done_blocks} prev={p.study.done_blocks} format={(v) => num(v)} />
          <Row label="Verpasste Blöcke" value={c.study.missed_blocks} cur={c.study.missed_blocks} prev={p.study.missed_blocks} better="down" format={(v) => num(v)} />
          <Row label="Quote" value={c.study.completion === null ? "–" : `${c.study.completion} %`} cur={c.study.completion} prev={p.study.completion} format={(v) => `${num(v)} %`} />
          <Row label="Fokuszeit (Pomodoro)" value={minutesText(c.study.focus_minutes)} cur={c.study.focus_minutes} prev={p.study.focus_minutes} format={(v) => `${num(v)} min`} />
          {Object.entries(c.study.per_subject).map(([s, m]) => (
            <Row key={s} label={`· ${s}`} value={minutesText(m)} />
          ))}
        </Card>

        <Card title="✅ Habits & To-dos" className="col-span-12 md:col-span-6 xl:col-span-4">
          <Row label="Habits erfüllt" value={c.habits.rate === null ? "–" : `${c.habits.rate} %`} cur={c.habits.rate} prev={p.habits.rate} format={(v) => `${num(v)} %`} />
          <Row label="Stärkster Habit" value={c.habits.best ? `${c.habits.best.emoji} ${c.habits.best.name}` : "–"} />
          <Row label="Aufgaben erledigt" value={c.todos.completed} cur={c.todos.completed} prev={p.todos.completed} format={(v) => num(v)} />
          <Row label="Neue Aufgaben" value={c.todos.created} />
          <Row label="Überfällig offen" value={c.todos.open_overdue} />
          <Row label="Ø Stimmung (Journal)" value={c.journal.avg_mood ? `${num(c.journal.avg_mood, 1)} / 5` : "–"} cur={c.journal.avg_mood} prev={p.journal.avg_mood} />
        </Card>

        <Card title="🥗 Ernährung & 💶 Finanzen" className="col-span-12 md:col-span-6 xl:col-span-4">
          <Row label="Ø Kalorien" value={`${num(c.nutrition.avg_kcal)} kcal`} cur={c.nutrition.avg_kcal} prev={p.nutrition.avg_kcal} better={null} format={(v) => num(v)} />
          <Row label="Ø Protein" value={`${num(c.nutrition.avg_protein)} g`} cur={c.nutrition.avg_protein} prev={p.nutrition.avg_protein} format={(v) => `${num(v)} g`} />
          <Row label="Ø Bilanz" value={c.nutrition.avg_balance === null ? "–" : `${num(c.nutrition.avg_balance)} kcal`} />
          <Row label="Einnahmen" value={euro(c.finance.income)} cur={c.finance.income} prev={p.finance.income} format={(v) => euro(v, 0)} />
          <Row label="Ausgaben" value={euro(c.finance.expense)} cur={c.finance.expense} prev={p.finance.expense} better="down" format={(v) => euro(v, 0)} />
          <Row label="Saldo" value={euro(c.finance.saldo)} />
          <Row label="Größter Posten" value={c.finance.top_category ? `${c.finance.top_category.category} (${euro(c.finance.top_category.amount, 0)})` : "–"} />
        </Card>
      </div>
    </div>
  );
}
