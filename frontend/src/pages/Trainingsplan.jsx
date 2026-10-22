import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTooltip, Legend, axisProps, gridProps } from "../components/charts";
import { Badge, Card, ConfirmButton, Empty, ErrorBox, Field, Loading, Modal, PageHeader, Segmented, Stat, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { C, STATUS } from "../lib/colors";
import { dateShort, dayLabel, num, relativeDay, todayIso } from "../lib/format";

const KIND = {
  kraft: { icon: "🏋️", color: "#fb923c", label: "Krafttraining" },
  praevention: { icon: "🧘", color: "#22d3ee", label: "Athletik & Prävention" },
  fussball: { icon: "⚽", color: "#4ade80", label: "Fußball" },
  handball: { icon: "🤾", color: "#a78bfa", label: "Handball" },
  lauf: { icon: "🏃", color: "#38bdf8", label: "Laufen" },
  ruhe: { icon: "😴", color: "#66788a", label: "Ruhetag" },
  sonstiges: { icon: "✨", color: "#9fb0bf", label: "Sonstiges" },
};
const LOGGABLE = (kind) => kind !== "ruhe";
const HAS_EXERCISES = (kind) => kind === "kraft" || kind === "praevention" || kind === "sonstiges";
const RATING = [
  { value: 1, icon: "😫", label: "sehr schwer" },
  { value: 2, icon: "😕", label: "zäh" },
  { value: 3, icon: "😐", label: "okay" },
  { value: 4, icon: "🙂", label: "gut" },
  { value: 5, icon: "💪", label: "stark" },
];
const WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];

function kg(value) {
  return value === null || value === undefined ? "–" : `${num(value, value % 1 ? 1 : 0)} kg`;
}

function restText(sec) {
  if (!sec) return "–";
  return sec >= 60 ? `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")} min` : `${sec} s`;
}

function setsText(sets, timed) {
  return sets
    .map((s) => {
      const r = s.reps ?? "–";
      const unit = timed ? " s" : "";
      return s.weight_kg ? `${num(s.weight_kg, s.weight_kg % 1 ? 1 : 0)}×${r}${unit}` : `${r}${unit}`;
    })
    .join(" · ");
}

// ---------------------------------------------------------------- Wochenansicht

function WeekStrip({ days, todayWd, selectedId, onSelect, editMode, onAddSession }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
      {days.map((d) => {
        const today = d.weekday === todayWd;
        return (
          <div
            key={d.weekday}
            className={`rounded-xl border bg-[#0a1118] p-3 ${today ? "border-accent/70 shadow-[0_0_16px_rgba(34,211,238,0.18)]" : "border-line/70"}`}
          >
            <div className={`font-display text-[0.7rem] font-bold uppercase ${today ? "text-accent" : "text-ink-3"}`}>
              {today ? "Heute · " : ""}
              {d.label}
            </div>
            <div className="mb-2 text-[0.65rem] text-ink-3">{dateShort(d.date)}</div>
            <div className="space-y-1.5">
              {d.sessions.map((s) => {
                const k = KIND[s.kind] || KIND.sonstiges;
                const active = s.id === selectedId;
                return (
                  <button
                    key={s.id}
                    onClick={() => onSelect(s.id)}
                    className={`w-full rounded-lg border px-2 py-1.5 text-left text-xs transition ${active ? "border-accent/70 bg-accent/10" : "border-line/60 hover:border-accent/40"}`}
                    style={{ borderLeft: `3px solid ${k.color}` }}
                  >
                    <div className="flex items-start gap-1.5">
                      <span aria-hidden>{k.icon}</span>
                      <span className="min-w-0 flex-1 hyphens-auto break-words font-medium leading-snug" lang="de">{s.title}</span>
                      {s.done_this_week && (
                        <span className="text-emerald-400" title="Diese Woche eingetragen">
                          ✓
                        </span>
                      )}
                    </div>
                    {s.exercises.length > 0 && <div className="mt-0.5 pl-5 text-[0.65rem] text-ink-3">{s.exercises.length} Übungen</div>}
                  </button>
                );
              })}
              {!d.sessions.length && <div className="text-xs text-ink-3">frei</div>}
              {editMode && (
                <button className="btn btn-sm w-full" onClick={() => onAddSession(d.weekday)}>
                  + Einheit
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- Einheit bearbeiten

function SessionForm({ initial, onSave, onCancel }) {
  const [f, setF] = useState(initial);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <form
      className="grid grid-cols-2 gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({ weekday: Number(f.weekday), kind: f.kind, title: f.title, notes: f.notes || "", duration_min: f.duration_min ? Number(f.duration_min) : null });
      }}
    >
      <Field label="Titel" className="col-span-2">
        <input className="input" value={f.title} onChange={set("title")} required maxLength={150} placeholder="z. B. Oberkörper A" />
      </Field>
      <Field label="Tag">
        <select className="input" value={f.weekday} onChange={set("weekday")}>
          {WEEKDAYS.map((w, i) => (
            <option key={w} value={i}>
              {w}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Art">
        <select className="input" value={f.kind} onChange={set("kind")}>
          {Object.entries(KIND).map(([k, v]) => (
            <option key={k} value={k}>
              {v.icon} {v.label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Dauer (min, optional)">
        <input type="number" min="0" className="input" value={f.duration_min ?? ""} onChange={set("duration_min")} />
      </Field>
      <Field label="Hinweise" className="col-span-2">
        <textarea className="input" rows={3} value={f.notes || ""} onChange={set("notes")} />
      </Field>
      <div className="col-span-2 flex justify-end gap-2">
        <button type="button" className="btn" onClick={onCancel}>
          Abbrechen
        </button>
        <button className="btn btn-primary">Speichern</button>
      </div>
    </form>
  );
}

function ExerciseForm({ initial, onSave, onCancel }) {
  const [f, setF] = useState(initial);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <form
      className="grid grid-cols-6 gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({
          name: f.name,
          sets: Number(f.sets),
          reps: f.reps,
          rest_seconds: Number(f.rest_seconds),
          increment_kg: Number(f.increment_kg),
          notes: f.notes || "",
          alternative: f.alternative || "",
        });
      }}
    >
      <Field label="Übung" className="col-span-6">
        <input className="input" value={f.name} onChange={set("name")} required maxLength={150} placeholder="z. B. Kniebeuge (Langhantel)" />
      </Field>
      <Field label="Sätze" className="col-span-2">
        <input type="number" min="1" max="10" className="input" value={f.sets} onChange={set("sets")} required />
      </Field>
      <Field label="Wdh. (z. B. 6–8, 30 s)" className="col-span-2">
        <input className="input" value={f.reps} onChange={set("reps")} required maxLength={30} />
      </Field>
      <Field label="Pause (s)" className="col-span-2">
        <input type="number" min="0" max="600" step="15" className="input" value={f.rest_seconds} onChange={set("rest_seconds")} />
      </Field>
      <Field label="Steigerung (kg, 0 = Körpergewicht)" className="col-span-3">
        <input type="number" min="0" max="20" step="0.5" className="input" value={f.increment_kg} onChange={set("increment_kg")} />
      </Field>
      <Field label="Alternative" className="col-span-3">
        <input className="input" value={f.alternative || ""} onChange={set("alternative")} maxLength={250} />
      </Field>
      <Field label="Technik-Tipp" className="col-span-6">
        <textarea className="input" rows={2} value={f.notes || ""} onChange={set("notes")} />
      </Field>
      <div className="col-span-6 flex justify-end gap-2">
        <button type="button" className="btn" onClick={onCancel}>
          Abbrechen
        </button>
        <button className="btn btn-primary">Speichern</button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- Einheit anzeigen

function SessionDetail({ sessionId, editMode, onChanged, onLog, version }) {
  const { data: s, error, loading, reload } = useApi(sessionId ? `/training/sessions/${sessionId}` : null, [sessionId, version]);
  const [editSession, setEditSession] = useState(false);
  const [exForm, setExForm] = useState(null); // { initial, id }
  const [openTip, setOpenTip] = useState(null);
  const toast = useToast();

  if (!sessionId) return <Card><Empty icon="🏋️">Wähle oben eine Einheit aus.</Empty></Card>;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!s || (loading && s.id !== sessionId)) return <Card><Loading /></Card>;
  const k = KIND[s.kind] || KIND.sonstiges;

  async function run(fn, msg) {
    try {
      await fn();
      if (msg) toast(msg, "success");
      reload();
      onChanged();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function move(index, dir) {
    const ids = s.exercises.map((e) => e.id);
    const j = index + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[index], ids[j]] = [ids[j], ids[index]];
    await run(() => api.post(`/training/sessions/${s.id}/reorder`, { exercise_ids: ids }));
  }

  return (
    <Card
      title={`${k.icon} ${s.title}`}
      actions={
        <>
          {editMode && (
            <>
              <button className="btn btn-sm" onClick={() => setEditSession(true)}>
                ✎ Einheit
              </button>
              <ConfirmButton onConfirm={() => run(() => api.del(`/training/sessions/${s.id}`), "Einheit gelöscht.")} question="Einheit löschen?">
                Löschen
              </ConfirmButton>
            </>
          )}
          {LOGGABLE(s.kind) && (
            <button className="btn btn-primary btn-sm" onClick={() => onLog(s)}>
              ▶ Training eintragen
            </button>
          )}
        </>
      }
    >
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <Badge color={k.color}>{s.kind_label}</Badge>
        <span className="text-ink-3">{s.weekday_label}</span>
        {s.duration_min ? <span className="text-ink-3">· ca. {s.duration_min} min</span> : null}
        {s.last_log && <span className="text-ink-3">· zuletzt {relativeDay(s.last_log.date)}</span>}
      </div>
      {s.notes && <p className="mb-4 rounded-lg border border-line/70 bg-[#0a1118] px-3 py-2 text-sm text-ink-2">{s.notes}</p>}

      {s.exercises.length > 0 ? (
        <ol className="space-y-2">
          {s.exercises.map((e, i) => (
            <li key={e.id} className="rounded-lg border border-line/70 bg-[#0a1118] px-3 py-2.5">
              <div className="flex items-start gap-3">
                {editMode ? (
                  <div className="flex flex-col pt-0.5">
                    <button className="text-[0.6rem] leading-none text-ink-3 hover:text-accent" onClick={() => move(i, -1)} aria-label="nach oben">
                      ▲
                    </button>
                    <button className="text-[0.6rem] leading-none text-ink-3 hover:text-accent" onClick={() => move(i, 1)} aria-label="nach unten">
                      ▼
                    </button>
                  </div>
                ) : (
                  <span className="font-display w-5 pt-0.5 text-sm font-bold text-ink-3">{i + 1}</span>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                    <button className="text-left font-semibold hover:text-accent" onClick={() => setOpenTip(openTip === e.id ? null : e.id)} title="Technik-Tipp anzeigen">
                      {e.name}
                    </button>
                    <span className="text-sm tabular-nums">
                      <b className="text-accent">
                        {e.sets} × {e.reps}
                      </b>
                      <span className="text-ink-3"> · Pause {restText(e.rest_seconds)}</span>
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs">
                    {e.last ? (
                      <span className="text-ink-2">
                        Letztes Mal ({dateShort(e.last.date)}): <span className="tabular-nums text-ink">{setsText(e.last.sets, e.timed)}</span>
                      </span>
                    ) : (
                      <span className="text-ink-3">Noch nicht eingetragen</span>
                    )}
                    {e.suggestion && (
                      <span className={e.suggestion.increase ? "font-semibold text-emerald-400" : "text-ink-3"}>
                        {e.suggestion.increase ? "↑ " : "→ "}
                        {e.suggestion.text}
                      </span>
                    )}
                  </div>
                  {(openTip === e.id || editMode) && (e.notes || e.alternative) && (
                    <div className="mt-2 space-y-1 border-t border-line/60 pt-2 text-xs text-ink-2">
                      {e.notes && <div>💡 {e.notes}</div>}
                      {e.alternative && <div className="text-ink-3">↔ Alternative: {e.alternative}</div>}
                    </div>
                  )}
                </div>
                {editMode && (
                  <div className="flex gap-1">
                    <button className="btn btn-sm" onClick={() => setExForm({ id: e.id, initial: e })}>
                      ✎
                    </button>
                    <ConfirmButton onConfirm={() => run(() => api.del(`/training/exercises/${e.id}`), "Übung entfernt.")} question="?">
                      ✕
                    </ConfirmButton>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        HAS_EXERCISES(s.kind) && <Empty icon="🏋️">Noch keine Übungen.</Empty>
      )}
      {!editMode && s.exercises.length > 0 && <p className="mt-2 text-xs text-ink-3">Tipp: Klick auf eine Übung zeigt den Technik-Tipp und eine Alternative.</p>}
      {editMode && HAS_EXERCISES(s.kind) && (
        <button className="btn mt-3" onClick={() => setExForm({ id: null, initial: { name: "", sets: 3, reps: "8–12", rest_seconds: 90, increment_kg: 2.5, notes: "", alternative: "" } })}>
          + Übung
        </button>
      )}

      <Modal open={editSession} title="Einheit bearbeiten" onClose={() => setEditSession(false)}>
        <SessionForm
          initial={s}
          onCancel={() => setEditSession(false)}
          onSave={(body) => run(() => api.patch(`/training/sessions/${s.id}`, body), "Einheit gespeichert.").then(() => setEditSession(false))}
        />
      </Modal>
      <Modal open={Boolean(exForm)} title={exForm?.id ? "Übung bearbeiten" : "Übung hinzufügen"} onClose={() => setExForm(null)}>
        {exForm && (
          <ExerciseForm
            initial={exForm.initial}
            onCancel={() => setExForm(null)}
            onSave={(body) =>
              run(() => (exForm.id ? api.patch(`/training/exercises/${exForm.id}`, body) : api.post(`/training/sessions/${s.id}/exercises`, body)), "Übung gespeichert.").then(() =>
                setExForm(null),
              )
            }
          />
        )}
      </Modal>
    </Card>
  );
}

// ---------------------------------------------------------------- Training eintragen

function emptySets(n, weight) {
  return Array.from({ length: n }, () => ({ weight_kg: weight ?? "", reps: "", done: false }));
}

function draftFromSession(s) {
  return {
    id: null,
    session_id: s.id,
    date: todayIso(),
    title: s.title,
    kind: s.kind,
    notes: "",
    rating: null,
    duration_min: s.duration_min || "",
    exercises: s.exercises.map((e) => ({
      exercise_id: e.id,
      name: e.name,
      meta: e,
      sets: emptySets(e.sets, e.suggestion?.weight_kg),
    })),
  };
}

function draftFromLog(log, session) {
  const metaById = Object.fromEntries((session?.exercises || []).map((e) => [e.id, e]));
  const metaByName = Object.fromEntries((session?.exercises || []).map((e) => [e.name, e]));
  return {
    id: log.id,
    session_id: log.session_id,
    date: log.date,
    title: log.title,
    kind: log.kind,
    notes: log.notes || "",
    rating: log.rating,
    duration_min: log.duration_min ?? "",
    exercises: log.exercises.map((g) => ({
      exercise_id: g.exercise_id,
      name: g.name,
      meta: metaById[g.exercise_id] || metaByName[g.name] || null,
      sets: g.sets.map((st) => ({ weight_kg: st.weight_kg ?? "", reps: st.reps ?? "", done: st.done })),
    })),
  };
}

function RestTimer({ endsAt, onClear }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!endsAt) return undefined;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [endsAt]);
  if (!endsAt) return null;
  const left = Math.max(0, Math.round((endsAt - now) / 1000));
  return (
    <div className={`sticky top-0 z-10 mb-3 flex items-center justify-between rounded-lg border px-3 py-2 text-sm backdrop-blur ${left ? "border-accent/40 bg-[#0a1118]/95" : "border-emerald-500/50 bg-emerald-500/10"}`}>
      <span>{left ? <>⏱ Pause: <b className="tabular-nums text-accent">{Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}</b></> : <b className="text-emerald-300">✓ Pause vorbei – nächster Satz!</b>}</span>
      <button type="button" className="btn btn-sm" onClick={onClear}>
        Ausblenden
      </button>
    </div>
  );
}

function LogForm({ initial, onSaved, onCancel }) {
  const [f, setF] = useState(initial);
  const [newEx, setNewEx] = useState("");
  const [restEnd, setRestEnd] = useState(null);
  const [saving, setSaving] = useState(false);
  const toast = useToast();
  const showExercises = HAS_EXERCISES(f.kind) || f.exercises.length > 0;

  function updateSet(ei, si, patch) {
    setF((cur) => ({
      ...cur,
      exercises: cur.exercises.map((ex, i) => (i === ei ? { ...ex, sets: ex.sets.map((st, j) => (j === si ? { ...st, ...patch } : st)) } : ex)),
    }));
  }

  function toggleDone(ei, si) {
    const ex = f.exercises[ei];
    const st = ex.sets[si];
    const done = !st.done;
    // Beim Abhaken ohne eingetragene Wiederholungen das Ziel übernehmen
    const patch = { done };
    if (done && (st.reps === "" || st.reps === null) && ex.meta?.rep_target) patch.reps = ex.meta.rep_target;
    updateSet(ei, si, patch);
    if (done && ex.meta?.rest_seconds) setRestEnd(Date.now() + ex.meta.rest_seconds * 1000);
  }

  function addSet(ei) {
    setF((cur) => ({
      ...cur,
      exercises: cur.exercises.map((ex, i) => {
        if (i !== ei) return ex;
        const last = ex.sets[ex.sets.length - 1];
        return { ...ex, sets: [...ex.sets, { weight_kg: last?.weight_kg ?? "", reps: "", done: false }] };
      }),
    }));
  }

  function removeSet(ei, si) {
    setF((cur) => ({ ...cur, exercises: cur.exercises.map((ex, i) => (i === ei ? { ...ex, sets: ex.sets.filter((_, j) => j !== si) } : ex)) }));
  }

  async function save(e) {
    e.preventDefault();
    setSaving(true);
    const sets = [];
    f.exercises.forEach((ex) =>
      ex.sets.forEach((st, i) => {
        const weight = st.weight_kg === "" || st.weight_kg === null ? null : Number(String(st.weight_kg).replace(",", "."));
        let reps = st.reps === "" || st.reps === null ? null : Number(st.reps);
        // Nur vorausgefülltes Gewicht ohne Wiederholungen = Satz nicht gemacht → nicht speichern
        if (reps === null && !st.done) return;
        if (reps === null) reps = ex.meta?.rep_target ?? null;
        sets.push({ exercise_id: ex.exercise_id || null, exercise_name: ex.name, set_number: i + 1, weight_kg: weight, reps, done: true });
      }),
    );
    const body = {
      session_id: f.session_id,
      date: f.date,
      title: f.title,
      kind: f.kind,
      notes: f.notes,
      rating: f.rating,
      duration_min: f.duration_min === "" ? null : Number(f.duration_min),
      sets,
    };
    try {
      if (f.id) await api.put(`/training/logs/${f.id}`, body);
      else await api.post("/training/logs", body);
      toast(f.id ? "Training gespeichert." : "Training eingetragen – stark! 💪", "success");
      onSaved();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    try {
      await api.del(`/training/logs/${f.id}`);
      toast("Eintrag gelöscht.", "success");
      onSaved();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  return (
    <form onSubmit={save}>
      <RestTimer endsAt={restEnd} onClear={() => setRestEnd(null)} />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="Datum">
          <input type="date" className="input" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} required />
        </Field>
        <Field label="Dauer (min)">
          <input type="number" min="0" className="input" value={f.duration_min} onChange={(e) => setF({ ...f, duration_min: e.target.value })} />
        </Field>
        <Field label="Titel" className="col-span-2">
          <input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="z. B. Freies Training" maxLength={150} />
        </Field>
        {!f.session_id && (
          <Field label="Art" className="col-span-2">
            <select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
              {Object.entries(KIND)
                .filter(([k2]) => LOGGABLE(k2))
                .map(([k2, v]) => (
                  <option key={k2} value={k2}>
                    {v.icon} {v.label}
                  </option>
                ))}
            </select>
          </Field>
        )}
      </div>

      {showExercises && (
        <div className="mt-4 space-y-3">
          {f.exercises.map((ex, ei) => {
            const timed = ex.meta?.timed;
            const bodyweight = ex.meta && !ex.meta.increment_kg;
            return (
              <div key={`${ex.name}-${ei}`} className="rounded-lg border border-line/70 bg-[#0a1118] p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="font-semibold">{ex.name}</div>
                  {ex.meta && (
                    <div className="text-xs text-ink-3">
                      Ziel <b className="text-accent">{ex.meta.sets} × {ex.meta.reps}</b> · Pause {restText(ex.meta.rest_seconds)}
                    </div>
                  )}
                </div>
                {ex.meta?.last && ex.meta.last.log_id !== f.id && (
                  <div className="mt-0.5 text-xs text-ink-3">
                    Letztes Mal: <span className="tabular-nums text-ink-2">{setsText(ex.meta.last.sets, timed)}</span>
                  </div>
                )}
                {ex.meta?.suggestion && !f.id && (
                  <div className={`mt-0.5 text-xs ${ex.meta.suggestion.increase ? "font-semibold text-emerald-400" : "text-ink-3"}`}>
                    {ex.meta.suggestion.increase ? "↑ " : "→ "}
                    {ex.meta.suggestion.text}
                  </div>
                )}
                <table className="mt-2 w-full text-sm">
                  <thead>
                    <tr className="text-left text-[0.65rem] uppercase tracking-wide text-ink-3">
                      <th className="w-10 pb-1 font-semibold">Satz</th>
                      <th className="pb-1 font-semibold">{bodyweight ? "Zusatz-kg" : "Gewicht (kg)"}</th>
                      <th className="pb-1 font-semibold">{timed ? "Sekunden" : "Wdh."}</th>
                      <th className="w-20 pb-1 text-center font-semibold">Geschafft</th>
                      <th className="w-8" />
                    </tr>
                  </thead>
                  <tbody>
                    {ex.sets.map((st, si) => (
                      <tr key={si} className={st.done ? "text-emerald-200" : ""}>
                        <td className="py-1 font-display text-xs font-bold text-ink-3">{si + 1}</td>
                        <td className="py-1 pr-2">
                          <input
                            type="number"
                            inputMode="decimal"
                            step="0.5"
                            min="0"
                            className="input px-2 py-1"
                            value={st.weight_kg}
                            onChange={(e) => updateSet(ei, si, { weight_kg: e.target.value })}
                            placeholder={bodyweight ? "0" : "kg"}
                            aria-label={`${ex.name} Satz ${si + 1} Gewicht`}
                          />
                        </td>
                        <td className="py-1 pr-2">
                          <input
                            type="number"
                            inputMode="numeric"
                            min="0"
                            className="input px-2 py-1"
                            value={st.reps}
                            onChange={(e) => updateSet(ei, si, { reps: e.target.value })}
                            placeholder={ex.meta?.rep_target ? String(ex.meta.rep_target) : ""}
                            aria-label={`${ex.name} Satz ${si + 1} Wiederholungen`}
                          />
                        </td>
                        <td className="py-1 text-center">
                          <button
                            type="button"
                            className={`btn btn-sm ${st.done ? "!border-emerald-500/60 !bg-emerald-500/15 !text-emerald-300" : ""}`}
                            onClick={() => toggleDone(ei, si)}
                            aria-pressed={st.done}
                            aria-label={`Satz ${si + 1} geschafft`}
                          >
                            ✓
                          </button>
                        </td>
                        <td className="py-1 text-right">
                          <button type="button" className="text-xs text-ink-3 hover:text-red-300" onClick={() => removeSet(ei, si)} aria-label="Satz entfernen">
                            ✕
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <button type="button" className="btn btn-sm mt-2" onClick={() => addSet(ei)}>
                  + Satz
                </button>
              </div>
            );
          })}
          <div className="flex gap-2">
            <input className="input" value={newEx} onChange={(e) => setNewEx(e.target.value)} placeholder="Weitere Übung hinzufügen, z. B. Liegestütze" maxLength={150} />
            <button
              type="button"
              className="btn"
              disabled={!newEx.trim()}
              onClick={() => {
                setF({ ...f, exercises: [...f.exercises, { exercise_id: null, name: newEx.trim(), meta: null, sets: emptySets(3) }] });
                setNewEx("");
              }}
            >
              + Übung
            </button>
          </div>
        </div>
      )}

      <div className="mt-4">
        <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-3">Wie war das Training?</div>
        <div className="flex flex-wrap gap-2">
          {RATING.map((r) => (
            <button
              type="button"
              key={r.value}
              onClick={() => setF({ ...f, rating: f.rating === r.value ? null : r.value })}
              className={`btn btn-sm ${f.rating === r.value ? "!border-accent/70 !bg-accent/15 !text-accent" : ""}`}
              aria-pressed={f.rating === r.value}
            >
              <span className="text-base">{r.icon}</span> {r.label}
            </button>
          ))}
        </div>
      </div>
      <Field label="Notizen" className="mt-3">
        <textarea
          className="input"
          rows={3}
          value={f.notes}
          onChange={(e) => setF({ ...f, notes: e.target.value })}
          placeholder="Wie hast du dich gefühlt? Was lief gut, was zwickt? z. B. „Bankdrücken leicht, nächstes Mal mehr. Knie links etwas gespürt.“"
        />
      </Field>

      <div className="mt-4 flex items-center justify-end gap-2">
        {f.id && (
          <span className="mr-auto">
            <ConfirmButton onConfirm={remove} question="Eintrag löschen?">
              Löschen
            </ConfirmButton>
          </span>
        )}
        <button type="button" className="btn" onClick={onCancel}>
          Abbrechen
        </button>
        <button className="btn btn-primary" disabled={saving}>
          {saving ? "Speichere …" : "Speichern"}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- Tagebuch & Fortschritt

function LogList({ logs, onOpen }) {
  if (!logs.length) return <Empty icon="📓">Noch keine Trainings eingetragen. Wähle eine Einheit und klick auf „▶ Training eintragen“.</Empty>;
  return (
    <ul className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
      {logs.map((l) => {
        const k = KIND[l.kind] || KIND.sonstiges;
        const rating = RATING.find((r) => r.value === l.rating);
        return (
          <li key={l.id}>
            <button className="w-full rounded-lg border border-line/70 bg-[#0a1118] px-3 py-2 text-left transition hover:border-accent/50" style={{ borderLeft: `3px solid ${k.color}` }} onClick={() => onOpen(l)}>
              <div className="flex items-center gap-2">
                <span aria-hidden>{k.icon}</span>
                <span className="min-w-0 flex-1 truncate text-sm font-semibold">{l.title}</span>
                {rating && (
                  <span title={rating.label} aria-label={`Bewertung: ${rating.label}`}>
                    {rating.icon}
                  </span>
                )}
              </div>
              <div className="mt-0.5 text-xs text-ink-3">
                {dayLabel(l.date)}
                {l.duration_min ? ` · ${l.duration_min} min` : ""}
                {l.sets_done ? ` · ${l.sets_done} Sätze` : ""}
                {l.volume_kg ? ` · ${num(l.volume_kg)} kg bewegt` : ""}
              </div>
              {l.notes && <div className="mt-1 line-clamp-2 text-xs text-ink-2">„{l.notes}“</div>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function ProgressCard({ version }) {
  const { data: names } = useApi("/training/exercises", [version]);
  const [exercise, setExercise] = useState("");
  const chosen = exercise || names?.[0]?.name || "";
  const { data, error } = useApi(chosen ? `/training/progress?exercise=${encodeURIComponent(chosen)}` : null, [chosen, version]);

  return (
    <Card
      title="📈 Fortschritt je Übung"
      actions={
        names?.length > 0 && (
          <select className="input w-auto py-1 text-sm" value={chosen} onChange={(e) => setExercise(e.target.value)} aria-label="Übung wählen">
            {names.map((n) => (
              <option key={n.name} value={n.name}>
                {n.name} ({n.sessions}×)
              </option>
            ))}
          </select>
        )
      }
    >
      {!names?.length ? (
        <Empty icon="📈">Sobald du Gewichte einträgst, siehst du hier, wie du stärker wirst.</Empty>
      ) : error ? (
        <ErrorBox error={error} />
      ) : !data ? (
        <Loading />
      ) : (
        <>
          <div className="mb-3 grid grid-cols-3 gap-4">
            <Stat label="Start" value={kg(data.first_weight)} />
            <Stat label="Bestes Gewicht" value={kg(data.best_weight)} sub={data.first_weight && data.best_weight ? `+${num(data.best_weight - data.first_weight, 1)} kg` : null} />
            <Stat label="Geschätztes Maximum" value={kg(data.best_e1rm)} sub="1 Wiederholung (Schätzung)" />
          </div>
          {data.points.some((p) => p.best_weight) ? (
            <>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={data.points} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={24} />
                  <YAxis {...axisProps} domain={["auto", "auto"]} unit=" kg" width={64} />
                  <Tooltip
                    cursor={{ stroke: C.axis, strokeDasharray: "3 3" }}
                    content={<ChartTooltip labelFormatter={(l) => dayLabel(l)} valueFormatter={(v) => kg(v)} />}
                  />
                  <Line type="monotone" dataKey="best_weight" name="Bestes Gewicht" stroke={C.orange} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, stroke: "#0d151d" }} activeDot={{ r: 6 }} connectNulls />
                  <Line type="monotone" dataKey="e1rm" name="Geschätztes Maximum" stroke={C.cyan} strokeWidth={2} strokeDasharray="5 4" dot={{ r: 4, strokeWidth: 2, stroke: "#0d151d" }} activeDot={{ r: 6 }} connectNulls />
                </LineChart>
              </ResponsiveContainer>
              <Legend
                items={[
                  { label: "Bestes Gewicht", color: C.orange, line: true },
                  { label: "Geschätztes Maximum (1 Wdh.)", color: C.cyan, line: true, dashed: true },
                ]}
              />
            </>
          ) : (
            <p className="text-sm text-ink-3">Bei dieser Übung trägst du nur Wiederholungen ein – beste Leistung: {Math.max(...data.points.map((p) => p.best_reps))}.</p>
          )}
        </>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- Seite

export default function Trainingsplan() {
  const [version, setVersion] = useState(0);
  const { data, error, loading, reload } = useApi("/training/plan", [version]);
  const { data: logs, reload: reloadLogs } = useApi("/training/logs?limit=40", [version]);
  const [selected, setSelected] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [logForm, setLogForm] = useState(null);
  const [newSession, setNewSession] = useState(null);
  const [showGuide, setShowGuide] = useState(false);
  const [params, setParams] = useSearchParams();
  const toast = useToast();

  const sessions = useMemo(() => (data ? data.days.flatMap((d) => d.sessions) : []), [data]);

  useEffect(() => {
    if (!data) return;
    const fromUrl = Number(params.get("einheit"));
    if (fromUrl && sessions.some((s) => s.id === fromUrl)) {
      setSelected(fromUrl);
      return;
    }
    if (selected && sessions.some((s) => s.id === selected)) return;
    const today = data.days[data.today_weekday].sessions;
    const pick = today.find((s) => HAS_EXERCISES(s.kind)) || today[0] || sessions.find((s) => s.kind === "kraft") || sessions[0];
    setSelected(pick ? pick.id : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, sessions]);

  // Von „Heute“ aus direkt das Eintragen öffnen (?eintragen=<id>)
  useEffect(() => {
    const id = Number(params.get("eintragen"));
    if (!id || !data) return;
    params.delete("eintragen");
    setParams(params, { replace: true });
    if (sessions.some((s) => s.id === id)) {
      setSelected(id);
      openLog({ id });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;

  const refresh = () => {
    setVersion((v) => v + 1);
  };

  async function openLog(session) {
    try {
      const full = await api.get(`/training/sessions/${session.id}`);
      setLogForm({ initial: draftFromSession(full) });
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function openExisting(log) {
    try {
      const session = log.session_id ? await api.get(`/training/sessions/${log.session_id}`).catch(() => null) : null;
      setLogForm({ initial: draftFromLog(log, session) });
    } catch (e) {
      toast(e.message, "error");
    }
  }

  function freeLog() {
    setLogForm({ initial: { id: null, session_id: null, date: todayIso(), title: "", kind: "kraft", notes: "", rating: null, duration_min: "", exercises: [] } });
  }

  async function resetPlan() {
    try {
      await api.post("/training/plan/reset");
      toast("Vorgeschlagener Plan wiederhergestellt. Dein Trainingstagebuch bleibt erhalten.", "success");
      setSelected(null);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  const tl = data.traffic_light;
  const st = tl ? STATUS[tl.color] || STATUS.grau : null;

  return (
    <div>
      <PageHeader
        title="Trainingsplan"
        icon="🏋️"
        subtitle={data.guide.goal}
        actions={
          <>
            <button className="btn" onClick={() => setShowGuide(true)}>
              📖 So funktioniert der Plan
            </button>
            <Segmented
              value={editMode ? "edit" : "view"}
              onChange={(v) => setEditMode(v === "edit")}
              options={[
                { value: "view", label: "Ansehen" },
                { value: "edit", label: "✎ Plan bearbeiten" },
              ]}
            />
            <button className="btn btn-primary" onClick={freeLog}>
              + Freies Training
            </button>
          </>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <Card className="col-span-12">
          <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
            <Stat label="Krafteinheiten diese Woche" value={`${data.week.done_strength} / ${data.week.planned_strength}`} sub="inkl. Athletik & Prävention" />
            <Stat label="Einträge diese Woche" value={data.week.logs} />
            <Stat label="Ruhetage" value={data.days.filter((d) => d.sessions.length && d.sessions.every((s) => s.kind === "ruhe")).map((d) => d.label.slice(0, 2)).join(" + ") || "–"} />
            <div>
              <div className="text-[0.68rem] font-semibold uppercase tracking-wider text-ink-3">Recovery heute</div>
              {tl ? (
                <div className="mt-1 text-sm">
                  <span className="font-semibold" style={{ color: st.color }}>
                    {st.icon} {tl.headline}
                  </span>
                  <div className="text-xs text-ink-2">{tl.recommendation}</div>
                </div>
              ) : (
                <div className="mt-1 text-sm text-ink-3">keine Daten</div>
              )}
            </div>
          </div>
          <WeekStrip
            days={data.days}
            todayWd={data.today_weekday}
            selectedId={selected}
            onSelect={(id) => {
              setSelected(id);
              if (params.get("einheit")) {
                params.delete("einheit");
                setParams(params, { replace: true });
              }
            }}
            editMode={editMode}
            onAddSession={(weekday) => setNewSession({ weekday, kind: "kraft", title: "", notes: "", duration_min: "" })}
          />
          {editMode && (
            <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-ink-3">
              <span>Bearbeiten: Einheit oben wählen, dann Übungen ändern, verschieben oder hinzufügen.</span>
              <ConfirmButton className="btn btn-sm" onConfirm={resetPlan} question="Wirklich? Eigene Änderungen am Plan gehen verloren">
                ↺ Vorgeschlagenen Plan wiederherstellen
              </ConfirmButton>
            </div>
          )}
        </Card>

        <div className="col-span-12 xl:col-span-8">
          <SessionDetail sessionId={selected} editMode={editMode} version={version} onChanged={refresh} onLog={openLog} />
        </div>

        <Card title="📓 Trainingstagebuch" className="col-span-12 xl:col-span-4">
          <LogList logs={logs || []} onOpen={openExisting} />
        </Card>

        <div className="col-span-12">
          <ProgressCard version={version} />
        </div>
      </div>

      <Modal open={Boolean(logForm)} title={logForm?.initial.id ? "Training bearbeiten" : `Training eintragen${logForm?.initial.title ? `: ${logForm.initial.title}` : ""}`} onClose={() => setLogForm(null)} wide>
        {logForm && (
          <LogForm
            key={logForm.initial.id ?? `neu-${logForm.initial.session_id}`}
            initial={logForm.initial}
            onCancel={() => setLogForm(null)}
            onSaved={() => {
              setLogForm(null);
              refresh();
              reloadLogs();
            }}
          />
        )}
      </Modal>

      <Modal open={Boolean(newSession)} title="Neue Einheit" onClose={() => setNewSession(null)}>
        {newSession && (
          <SessionForm
            initial={newSession}
            onCancel={() => setNewSession(null)}
            onSave={async (body) => {
              try {
                const s = await api.post("/training/sessions", body);
                setNewSession(null);
                setSelected(s.id);
                refresh();
              } catch (e) {
                toast(e.message, "error");
              }
            }}
          />
        )}
      </Modal>

      <Modal open={showGuide} title="So funktioniert dein Plan" onClose={() => setShowGuide(false)} wide>
        <p className="mb-3 text-sm text-ink-2">{data.guide.goal}</p>
        <ul className="space-y-2 text-sm text-ink-2">
          {data.guide.rules.map((r) => (
            <li key={r} className="flex gap-2">
              <span className="text-accent">›</span>
              {r}
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-ink-3">
          Beim Eintragen schlägt Life OS das Gewicht vor: Hast du letztes Mal alle Sätze mit der oberen Wiederholungszahl geschafft, steht dort schon das höhere Gewicht. Die Pause startet automatisch, wenn du einen Satz abhakst.
        </p>
      </Modal>
    </div>
  );
}
