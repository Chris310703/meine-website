import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTooltip, axisProps, gridProps } from "../components/charts";
import { Card, Empty, ErrorBox, Field, Loading, PageHeader, Stat, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { C } from "../lib/colors";
import { addDays, dateLong, dateShort, dayLabel, isoDate, num, todayIso, weekdayLong } from "../lib/format";

const MOODS = [
  { v: 1, e: "😞", l: "sehr schlecht" },
  { v: 2, e: "🙁", l: "schlecht" },
  { v: 3, e: "😐", l: "okay" },
  { v: 4, e: "🙂", l: "gut" },
  { v: 5, e: "😄", l: "sehr gut" },
];

function MoodPicker({ value, onChange }) {
  return (
    <div className="flex gap-1.5" role="radiogroup" aria-label="Stimmung">
      {MOODS.map((m) => (
        <button
          key={m.v}
          type="button"
          role="radio"
          aria-checked={value === m.v}
          title={`${m.v} – ${m.l}`}
          onClick={() => onChange(value === m.v ? null : m.v)}
          className={`flex h-11 w-11 flex-col items-center justify-center rounded-xl border text-xl transition ${
            value === m.v ? "scale-105 border-accent bg-accent/15 shadow-[0_0_10px_rgba(34,211,238,0.35)]" : "border-line opacity-60 hover:opacity-100"
          }`}
        >
          {m.e}
          <span className="text-[0.5rem] text-ink-3">{m.v}</span>
        </button>
      ))}
    </div>
  );
}

function EntryEditor({ day, kind, questions, entry, onSaved }) {
  const [mood, setMood] = useState(entry?.mood ?? null);
  const [answers, setAnswers] = useState(entry?.answers || {});
  const [text, setText] = useState(entry?.text || "");
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  useEffect(() => {
    setMood(entry?.mood ?? null);
    setAnswers(entry?.answers || {});
    setText(entry?.text || "");
  }, [entry, day]);

  async function save() {
    setSaving(true);
    try {
      await api.put(`/journal/day/${day}/${kind}`, { mood, answers, text });
      toast(`${kind === "morgen" ? "Morgen" : "Abend"}eintrag gespeichert.`, "success");
      onSaved();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title={kind === "morgen" ? "☀️ Morgen" : "🌙 Abend"} actions={entry && <span className="text-xs text-ink-3">gespeichert</span>}>
      <div className="space-y-3">
        <Field label="Stimmung">
          <MoodPicker value={mood} onChange={setMood} />
        </Field>
        {questions.map((q) => (
          <Field key={q} label={q}>
            <textarea className="input" rows={2} value={answers[q] || ""} onChange={(e) => setAnswers({ ...answers, [q]: e.target.value })} />
          </Field>
        ))}
        <Field label="Freitext">
          <textarea className="input" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Was dir sonst noch durch den Kopf geht …" />
        </Field>
        <button className="btn btn-primary w-full" onClick={save} disabled={saving}>
          Speichern
        </button>
      </div>
    </Card>
  );
}

export default function Journal() {
  const [day, setDay] = useState(todayIso());
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [mood, setMood] = useState("");
  const { data: dayData, error, reload: reloadDay } = useApi(`/journal/day/${day}`);
  const { data: list, reload: reloadList } = useApi(`/journal?q=${encodeURIComponent(query)}${mood ? `&mood=${mood}` : ""}`);

  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  if (error) return <ErrorBox error={error} />;
  if (!dayData) return <Loading />;

  const refresh = () => {
    reloadDay();
    reloadList();
  };

  function highlight(text) {
    if (!query.trim()) return text;
    const words = query.trim().split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const parts = text.split(new RegExp(`(${words.join("|")})`, "gi"));
    return parts.map((p, i) => (i % 2 ? <mark key={i} className="rounded bg-accent/30 px-0.5 text-ink">{p}</mark> : p));
  }

  return (
    <div>
      <PageHeader
        title="Journal"
        icon="📓"
        subtitle={`${weekdayLong(day)}, ${dateLong(day)}`}
        actions={
          <>
            <button className="btn" onClick={() => setDay(isoDate(addDays(day, -1)))}>
              ‹
            </button>
            <input type="date" className="input w-40" value={day} max={todayIso()} onChange={(e) => e.target.value && setDay(e.target.value)} />
            <button className="btn" onClick={() => setDay(isoDate(addDays(day, 1)))} disabled={day >= todayIso()}>
              ›
            </button>
          </>
        }
      />
      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-12 lg:col-span-4">
          <EntryEditor day={day} kind="morgen" questions={dayData.questions.morgen} entry={dayData.morgen} onSaved={refresh} />
        </div>
        <div className="col-span-12 lg:col-span-4">
          <EntryEditor day={day} kind="abend" questions={dayData.questions.abend} entry={dayData.abend} onSaved={refresh} />
        </div>
        <div className="col-span-12 space-y-5 lg:col-span-4">
          <Card title="Stimmung · 30 Tage">
            {list && (
              <>
                <div className="mb-2 grid grid-cols-2 gap-4">
                  <Stat label="Ø Stimmung" value={list.avg_mood_30 ? `${num(list.avg_mood_30, 1)} / 5` : "–"} />
                  <Stat label="Journal-Serie" value={`${list.streak} Tage`} />
                </div>
                <ResponsiveContainer width="100%" height={150}>
                  <LineChart data={list.trend} margin={{ top: 8, right: 8, left: -24, bottom: 0 }}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={24} />
                    <YAxis {...axisProps} domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} />
                    <Tooltip content={<ChartTooltip labelFormatter={dayLabel} valueFormatter={(v) => `${num(v, 1)} ${MOODS[Math.round(v) - 1]?.e ?? ""}`} />} />
                    <Line dataKey="mood" name="Stimmung" stroke={C.accent} strokeWidth={2} dot={{ r: 2.5, fill: C.accent }} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </>
            )}
          </Card>
          <Card title="Einträge durchsuchen">
            <div className="mb-3 flex gap-2">
              <input className="input flex-1" placeholder="Stichwort …" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Journal durchsuchen" />
              <select className="input w-24" value={mood} onChange={(e) => setMood(e.target.value)} aria-label="Stimmung filtern">
                <option value="">alle</option>
                {MOODS.map((m) => (
                  <option key={m.v} value={m.v}>
                    {m.e} {m.v}
                  </option>
                ))}
              </select>
            </div>
            {list?.entries.length ? (
              <ul className="max-h-[520px] space-y-2 overflow-y-auto pr-1">
                {list.entries.map((e) => (
                  <li key={e.id}>
                    <button className="w-full rounded-lg border border-line/60 px-3 py-2 text-left hover:border-accent/40" onClick={() => setDay(e.date)}>
                      <div className="flex items-center justify-between text-xs text-ink-3">
                        <span>
                          {dayLabel(e.date)} · {e.kind === "morgen" ? "☀️ Morgen" : "🌙 Abend"}
                        </span>
                        <span className="text-base">{e.mood ? MOODS[e.mood - 1].e : ""}</span>
                      </div>
                      <div className="mt-1 line-clamp-3 text-sm text-ink-2">
                        {highlight([...Object.values(e.answers || {}), e.text].filter(Boolean).join(" · "))}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty icon="📓">{query ? "Nichts gefunden." : "Noch keine Einträge."}</Empty>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
