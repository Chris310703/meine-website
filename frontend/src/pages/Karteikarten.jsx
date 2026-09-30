import { useCallback, useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import Markdown from "../components/Markdown";
import { ChartTooltip, Legend, axisProps, gridProps } from "../components/charts";
import { Card, ConfirmButton, Empty, ErrorBox, Field, Loading, Modal, PageHeader, ProgressBar, Ring, Segmented, Stat, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { dateShort, dayLabel, num, weekdayShort } from "../lib/format";

const COLORS = ["#22d3ee", "#a78bfa", "#f472b6", "#facc15", "#34d399", "#fb923c", "#60a5fa", "#f87171"];
const EMOJIS = ["📚", "⚖️", "💶", "📊", "🏛️", "🧾", "🧠", "📈", "🌍", "🔬", "💡", "📝"];

const GRADE = {
  1: { label: "Nochmal", key: "1", color: "#f87171", hint: "falsch" },
  2: { label: "Schwer", key: "2", color: "#fb923c", hint: "richtig, mühsam" },
  3: { label: "Gut", key: "3", color: "#22d3ee", hint: "richtig" },
  4: { label: "Leicht", key: "4", color: "#34d399", hint: "sofort gewusst" },
};

const STATUS = {
  neu: { label: "Neu", color: "#a78bfa" },
  faellig: { label: "Fällig", color: "#fb923c" },
  lernen: { label: "Im Lernen", color: "#22d3ee" },
  sitzt: { label: "Sitzt", color: "#34d399" },
};

const RIGHT = "#1f9d55";
const WRONG = "#e0620f";

function Chip({ color, children, title }) {
  return (
    <span className="chip" title={title} style={{ borderColor: `${color}55`, color, background: `${color}14` }}>
      {children}
    </span>
  );
}

function CountChips({ counts }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {counts.faellig > 0 && <Chip color={STATUS.faellig.color}>{counts.faellig} fällig</Chip>}
      {counts.neu > 0 && <Chip color={STATUS.neu.color}>{counts.neu} neu</Chip>}
      <Chip color="#66788a">{counts.total} Karten</Chip>
    </div>
  );
}

function masteryParts(counts) {
  return [
    { key: "sitzt", value: counts.sitzt, color: STATUS.sitzt.color },
    { key: "lernen", value: counts.lernen, color: STATUS.lernen.color },
    { key: "faellig", value: counts.faellig, color: STATUS.faellig.color },
    { key: "neu", value: counts.neu, color: "#2a3845" },
  ];
}

/** Gestapelter Balken: wie viele Karten sitzen / im Lernen / fällig / neu */
function MasteryBar({ counts, height = 6 }) {
  if (!counts.total) return <div className="rounded-full bg-[#15202a]" style={{ height }} />;
  return (
    <div className="flex w-full overflow-hidden rounded-full bg-[#15202a]" style={{ height }} title={`${counts.sitzt} sitzen · ${counts.lernen} im Lernen · ${counts.faellig} fällig · ${counts.neu} neu`}>
      {masteryParts(counts).map((p) =>
        p.value ? <div key={p.key} style={{ width: `${(p.value / counts.total) * 100}%`, background: p.color, boxShadow: p.key === "neu" ? undefined : `0 0 6px ${p.color}` }} /> : null,
      )}
    </div>
  );
}

// ---------------------------------------------------------------- Fach anlegen / bearbeiten

function SubjectModal({ open, subject, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ name: "", emoji: "📚", color: COLORS[0] });
  const [studySubjects, setStudySubjects] = useState([]);

  useEffect(() => {
    if (!open) return;
    setF(subject ? { name: subject.name, emoji: subject.emoji, color: subject.color } : { name: "", emoji: "📚", color: COLORS[Math.floor(Math.random() * COLORS.length)] });
    if (!subject) {
      api.get("/study/subjects").then((r) => setStudySubjects(Array.isArray(r) ? r : r.subjects || [])).catch(() => setStudySubjects([]));
    }
  }, [open, subject]);

  async function save(e) {
    e.preventDefault();
    try {
      if (subject) await api.patch(`/cards/subjects/${subject.id}`, f);
      else await api.post("/cards/subjects", f);
      toast(subject ? "Fach gespeichert." : `Fach „${f.name}“ angelegt.`, "success");
      onSaved();
      onClose();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  return (
    <Modal open={open} title={subject ? "Fach bearbeiten" : "Neues Fach"} onClose={onClose}>
      <form onSubmit={save} className="space-y-4">
        {!subject && studySubjects.length > 0 && (
          <div>
            <span className="label">Aus dem Lernplan übernehmen</span>
            <div className="flex flex-wrap gap-1.5">
              {studySubjects.map((s) => (
                <button type="button" key={s.id} className="chip hover:text-ink" style={{ borderColor: `${s.color}66`, color: s.color }} onClick={() => setF({ ...f, name: s.name, color: s.color })}>
                  {s.short || s.name}
                </button>
              ))}
            </div>
          </div>
        )}
        <Field label="Name">
          <input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required placeholder="z. B. Zivilrecht" autoFocus />
        </Field>
        <div>
          <span className="label">Symbol</span>
          <div className="flex flex-wrap gap-1.5">
            {EMOJIS.map((e) => (
              <button type="button" key={e} onClick={() => setF({ ...f, emoji: e })} className={`h-9 w-9 rounded-lg border text-lg transition ${f.emoji === e ? "border-accent bg-accent/15" : "border-line hover:border-accent/50"}`}>
                {e}
              </button>
            ))}
          </div>
        </div>
        <div>
          <span className="label">Farbe</span>
          <div className="flex flex-wrap gap-2">
            {COLORS.map((c) => (
              <button
                type="button"
                key={c}
                aria-label={`Farbe ${c}`}
                onClick={() => setF({ ...f, color: c })}
                className="h-7 w-7 rounded-full border-2 transition"
                style={{ background: c, borderColor: f.color === c ? "#e6edf3" : "transparent", boxShadow: f.color === c ? `0 0 12px ${c}` : undefined }}
              />
            ))}
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn" onClick={onClose}>
            Abbrechen
          </button>
          <button className="btn btn-primary">Speichern</button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------- Übersicht

function TopicRow({ topic, color, selected, onToggle, onStudy, onRename, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(topic.name);
  return (
    <li className={`flex items-center gap-3 rounded-lg border px-3 py-2 transition ${selected ? "border-accent/50 bg-accent/[0.06]" : "border-line/60 bg-[#0a1118]"}`}>
      <button
        type="button"
        onClick={onToggle}
        aria-label={selected ? "Abwählen" : "Für Abfrage auswählen"}
        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border text-xs ${selected ? "border-accent bg-accent/20 text-accent" : "border-ink-3 hover:border-accent"}`}
      >
        {selected ? "✓" : ""}
      </button>
      <div className="min-w-0 flex-1">
        {editing ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              onRename(name);
              setEditing(false);
            }}
            className="flex gap-2"
          >
            <input className="input py-1 text-sm" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
            <button className="btn btn-sm btn-primary">OK</button>
          </form>
        ) : (
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium">{topic.name}</span>
            <span className="text-xs text-ink-3">{topic.counts.total}</span>
          </div>
        )}
        <div className="mt-1.5">
          <MasteryBar counts={topic.counts} height={4} />
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {topic.counts.faellig > 0 && <Chip color={STATUS.faellig.color}>{topic.counts.faellig}</Chip>}
        {topic.counts.neu > 0 && <Chip color={STATUS.neu.color}>+{topic.counts.neu}</Chip>}
        <button className="btn btn-sm" disabled={!topic.counts.total} onClick={() => onStudy("faellig")} title="Fällige & neue Karten dieses Themas">
          ▶
        </button>
        <button className="btn btn-sm" disabled={!topic.counts.total} onClick={() => onStudy("alle")} title="Alle Karten dieses Themas abfragen">
          ⟳
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => setEditing(!editing)} title="Umbenennen">
          ✎
        </button>
        <ConfirmButton className="btn btn-ghost btn-sm" onConfirm={onDelete} question="Mit Karten löschen?">
          🗑
        </ConfirmButton>
      </div>
    </li>
  );
}

function SubjectCard({ subject, selection, setSelection, onStudy, onEdit, reload }) {
  const toast = useToast();
  const [topicName, setTopicName] = useState("");
  const [open, setOpen] = useState(true);
  const c = subject.counts;
  const selectedHere = subject.topics.filter((t) => selection.includes(t.id));
  const known = c.total ? Math.round(((c.sitzt + c.lernen) / c.total) * 100) : 0;

  async function addTopic(e) {
    e.preventDefault();
    if (!topicName.trim()) return;
    try {
      await api.post("/cards/topics", { subject_id: subject.id, name: topicName });
      setTopicName("");
      reload();
    } catch (err) {
      toast(err.message, "error");
    }
  }
  async function run(fn, msg) {
    try {
      await fn();
      if (msg) toast(msg, "success");
      reload();
    } catch (err) {
      toast(err.message, "error");
    }
  }
  const toggle = (id) => setSelection(selection.includes(id) ? selection.filter((x) => x !== id) : [...selection, id]);

  return (
    <section className="card relative overflow-hidden" style={{ borderColor: `${subject.color}40` }}>
      <div className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full opacity-20 blur-3xl" style={{ background: subject.color }} />
      <div className="relative flex flex-wrap items-start gap-4">
        <button className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border text-2xl" style={{ borderColor: `${subject.color}66`, background: `${subject.color}14`, boxShadow: `0 0 14px ${subject.color}33` }} onClick={() => setOpen(!open)} aria-label={open ? "Themen einklappen" : "Themen ausklappen"}>
          {subject.emoji}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-sm font-bold" style={{ color: subject.color, textShadow: `0 0 10px ${subject.color}66` }}>
              {subject.name}
            </h2>
            <span className="text-xs text-ink-3">
              {subject.topics.length} {subject.topics.length === 1 ? "Thema" : "Themen"} · {known} % gelernt
            </span>
          </div>
          <div className="mt-2">
            <MasteryBar counts={c} />
          </div>
          <div className="mt-2">
            <CountChips counts={c} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn btn-primary btn-sm" disabled={!c.faellig && !c.neu} onClick={() => onStudy({ mode: "faellig", subject })}>
            ▶ Fällige lernen
          </button>
          <button className="btn btn-sm" disabled={!c.total} onClick={() => onStudy({ mode: "alle", subject })}>
            ⟳ Alle abfragen
          </button>
          <button className="btn btn-ghost btn-sm" onClick={onEdit} title="Fach bearbeiten">
            ✎
          </button>
          <ConfirmButton className="btn btn-ghost btn-sm" onConfirm={() => run(() => api.del(`/cards/subjects/${subject.id}`), "Fach gelöscht.")} question="Fach samt Karten löschen?">
            🗑
          </ConfirmButton>
        </div>
      </div>

      {open && (
        <div className="relative mt-4">
          {subject.topics.length > 0 && (
            <ul className="space-y-1.5">
              {subject.topics.map((t) => (
                <TopicRow
                  key={t.id}
                  topic={t}
                  color={subject.color}
                  selected={selection.includes(t.id)}
                  onToggle={() => toggle(t.id)}
                  onStudy={(mode) => onStudy({ mode, subject, topics: [t] })}
                  onRename={(name) => run(() => api.patch(`/cards/topics/${t.id}`, { name }))}
                  onDelete={() => run(() => api.del(`/cards/topics/${t.id}`), "Thema gelöscht.")}
                />
              ))}
            </ul>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <form onSubmit={addTopic} className="flex min-w-[240px] flex-1 gap-2">
              <input className="input py-1.5 text-sm" placeholder="+ Neues Thema, z. B. Anfechtung" value={topicName} onChange={(e) => setTopicName(e.target.value)} />
              <button className="btn btn-sm" disabled={!topicName.trim()}>
                Anlegen
              </button>
            </form>
            {selectedHere.length > 0 && (
              <div className="flex items-center gap-2 text-xs text-ink-2">
                {selectedHere.length} ausgewählt:
                <button className="btn btn-primary btn-sm" onClick={() => onStudy({ mode: "faellig", subject, topics: selectedHere })}>
                  ▶ Fällige
                </button>
                <button className="btn btn-sm" onClick={() => onStudy({ mode: "alle", subject, topics: selectedHere })}>
                  ⟳ Alle
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function Forecast({ forecast }) {
  const max = Math.max(1, ...forecast.map((f) => f.count));
  return (
    <div className="flex h-28 items-end gap-2">
      {forecast.map((f, i) => (
        <div key={f.date} className="flex flex-1 flex-col items-center gap-1">
          <span className="text-[0.7rem] font-semibold text-ink-2">{f.count || ""}</span>
          <div
            className="w-full rounded-t-md transition-all"
            style={{
              height: `${Math.max(3, (f.count / max) * 64)}px`,
              background: i === 0 ? "var(--color-accent)" : "#1d4652",
              boxShadow: i === 0 && f.count ? "0 0 10px rgba(34,211,238,0.6)" : undefined,
            }}
          />
          <span className={`text-[0.68rem] ${i === 0 ? "font-bold text-accent" : "text-ink-3"}`}>{i === 0 ? "Heute" : weekdayShort(f.date)}</span>
        </div>
      ))}
    </div>
  );
}

function Overview({ data, reload, onStudy, onImport }) {
  const [editing, setEditing] = useState(null);
  const [selection, setSelection] = useState([]);
  const c = data.counts;

  return (
    <div className="grid grid-cols-12 gap-5">
      <Card className="col-span-12 xl:col-span-8">
        <div className="flex flex-wrap items-center gap-6">
          <Ring value={data.today.reviews} max={Math.max(1, c.faellig + Math.min(c.neu, 20) + data.today.reviews)} size={104} color="var(--color-accent)">
            <div className="text-2xl font-bold text-accent">{c.faellig}</div>
            <div className="text-[0.62rem] uppercase tracking-wider text-ink-3">fällig</div>
          </Ring>
          <div className="grid flex-1 grid-cols-2 gap-5 sm:grid-cols-4">
            <Stat label="Neu" value={num(c.neu)} color={STATUS.neu.color} />
            <Stat label="Sitzen" value={num(c.sitzt)} color={STATUS.sitzt.color} sub={c.total ? `${Math.round((c.sitzt / c.total) * 100)} % aller Karten` : null} />
            <Stat label="Heute ✓ / ✗" value={`${data.today.correct} / ${data.today.wrong}`} sub={`${data.today.reviews} Abfragen`} />
            <Stat label="Serie" value={`${data.streak} 🔥`} sub={data.streak === 1 ? "Tag in Folge" : "Tage in Folge"} />
          </div>
          <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:flex-col">
            <button className="btn btn-primary" disabled={!c.faellig && !c.neu} onClick={() => onStudy({ mode: "faellig" })}>
              ▶ Alles Fällige lernen
            </button>
            <button className="btn" disabled={!c.total} onClick={() => onStudy({ mode: "alle" })}>
              ⟳ Alle Fächer mischen
            </button>
          </div>
        </div>
      </Card>

      <Card title="Nächste 7 Tage" className="col-span-12 xl:col-span-4">
        <Forecast forecast={data.forecast} />
      </Card>

      <div className="col-span-12 flex flex-wrap items-center justify-between gap-3">
        <h2 className="card-title">Fächer & Themen</h2>
        <div className="flex flex-wrap gap-2">
          {selection.length > 0 && (
            <button className="btn btn-sm" onClick={() => setSelection([])}>
              Auswahl aufheben ({selection.length})
            </button>
          )}
          <button className="btn btn-sm" onClick={onImport}>
            📥 Aus Claude importieren
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => setEditing("new")}>
            + Fach
          </button>
        </div>
      </div>

      <div className="col-span-12 space-y-4">
        {data.subjects.length ? (
          data.subjects.map((s) => (
            <SubjectCard key={s.id} subject={s} selection={selection} setSelection={setSelection} onStudy={onStudy} onEdit={() => setEditing(s)} reload={reload} />
          ))
        ) : (
          <Card>
            <Empty icon="🗂️">
              Noch keine Karteikarten. Lege ein <b>Fach</b> an (z. B. Zivilrecht), darin <b>Themen</b> – oder importiere Karten direkt aus Claude.
              <div className="mt-3 flex justify-center gap-2">
                <button className="btn btn-primary" onClick={() => setEditing("new")}>
                  + Erstes Fach
                </button>
                <button className="btn" onClick={onImport}>
                  📥 Aus Claude importieren
                </button>
              </div>
            </Empty>
          </Card>
        )}
      </div>

      <SubjectModal open={Boolean(editing)} subject={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={reload} />
    </div>
  );
}

// ---------------------------------------------------------------- Abfrage

function StudySession({ scope, onExit }) {
  const toast = useToast();
  const [queue, setQueue] = useState(null);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState({ correct: 0, wrong: 0, grades: { 1: 0, 2: 0, 3: 0, 4: 0 } });
  const [wrongIds, setWrongIds] = useState([]);
  const [total, setTotal] = useState(0);
  // Zweite Runde „Falsche nochmal üben“: nur diese Karten, alle abfragen
  const [retry, setRetry] = useState(null);
  const mode = retry ? "alle" : scope.mode;

  const query = useMemo(() => {
    const p = new URLSearchParams({ mode });
    if (scope.topics?.length) p.set("topic_ids", scope.topics.map((t) => t.id).join(","));
    else if (scope.subject) p.set("subject_id", scope.subject.id);
    return p.toString();
  }, [scope, mode]);

  useEffect(() => {
    let alive = true;
    api
      .get(`/cards/study?${query}`)
      .then((r) => {
        if (!alive) return;
        const cards = retry ? r.cards.filter((c) => retry.includes(c.id)) : r.cards;
        setQueue(cards);
        setTotal(cards.length);
      })
      .catch((e) => toast(e.message, "error"));
    return () => {
      alive = false;
    };
  }, [query, retry, toast]);

  const card = queue?.[index];
  const done = queue && index >= queue.length;

  const grade = useCallback(
    async (g) => {
      if (!card || !flipped || busy) return;
      setBusy(true);
      try {
        const r = await api.post(`/cards/cards/${card.id}/review`, { grade: g, mode });
        setResults((x) => ({ correct: x.correct + (g >= 2 ? 1 : 0), wrong: x.wrong + (g === 1 ? 1 : 0), grades: { ...x.grades, [g]: x.grades[g] + 1 } }));
        if (g === 1) {
          setWrongIds((ids) => (ids.includes(card.id) ? ids : [...ids, card.id]));
          // Falsche Karten kommen am Ende der Runde noch einmal
          setQueue((q) => [...q, { ...r.card, again: true }]);
        }
        setFlipped(false);
        setIndex((i) => i + 1);
      } catch (e) {
        toast(e.message, "error");
      } finally {
        setBusy(false);
      }
    },
    [card, flipped, busy, mode, toast],
  );

  useEffect(() => {
    function onKey(e) {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        if (!flipped) setFlipped(true);
        else if (e.key === "Enter") grade(3);
      } else if (["1", "2", "3", "4"].includes(e.key)) grade(Number(e.key));
      else if (e.key === "Escape") onExit();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [flipped, grade, onExit]);

  const title = scope.topics?.length === 1 ? `${scope.subject.name} · ${scope.topics[0].name}` : scope.topics?.length ? `${scope.subject.name} · ${scope.topics.length} Themen` : scope.subject ? scope.subject.name : "Alle Fächer";
  const color = scope.subject?.color || "#22d3ee";

  if (!queue) return <Loading text="Karten werden gemischt …" />;

  const header = (
    <div className="mb-5 flex flex-wrap items-center gap-4">
      <button className="btn btn-sm" onClick={onExit}>
        ‹ Zurück
      </button>
      <div className="min-w-0 flex-1">
        <div className="font-display truncate text-xs font-bold" style={{ color }}>
          {title}
        </div>
        <div className="text-xs text-ink-3">{retry ? "Falsch beantwortete Karten üben" : mode === "alle" ? "Alle Karten abfragen" : "Spaced Repetition: fällige & neue Karten"}</div>
      </div>
      <div className="flex items-center gap-3 text-sm">
        <span className="font-semibold text-emerald-400">✓ {results.correct}</span>
        <span className="font-semibold text-orange-400">✗ {results.wrong}</span>
        <span className="text-ink-3">
          {Math.min(index + (done ? 0 : 1), queue.length)} / {queue.length}
        </span>
      </div>
    </div>
  );

  if (!queue.length) {
    return (
      <div className="mx-auto max-w-2xl">
        {header}
        <Card>
          <Empty icon="🎉">
            Hier ist gerade nichts fällig – super! Die nächsten Karten kommen, wenn ihr Abstand abgelaufen ist.
            <div className="mt-3 flex justify-center gap-2">
              <button className="btn" onClick={onExit}>
                Zur Übersicht
              </button>
            </div>
          </Empty>
        </Card>
      </div>
    );
  }

  if (done) {
    const answered = results.correct + results.wrong;
    const acc = answered ? Math.round((results.correct / answered) * 100) : 0;
    return (
      <div className="mx-auto max-w-2xl card-in">
        {header}
        <Card>
          <div className="flex flex-col items-center gap-5 py-4 text-center">
            <div className="font-display glow-text text-lg font-extrabold text-accent">Runde geschafft!</div>
            <Ring value={acc} max={100} size={140} stroke={10} color={acc >= 80 ? "#34d399" : acc >= 50 ? "#22d3ee" : "#fb923c"}>
              <div className="text-3xl font-bold">{acc} %</div>
              <div className="text-[0.65rem] uppercase tracking-wider text-ink-3">richtig</div>
            </Ring>
            <div className="grid w-full grid-cols-3 gap-4">
              <Stat label="Karten" value={total} />
              <Stat label="Richtig" value={results.correct} color="#34d399" />
              <Stat label="Falsch" value={results.wrong} color="#fb923c" />
            </div>
            <div className="flex w-full gap-1">
              {[1, 2, 3, 4].map((g) =>
                results.grades[g] ? (
                  <div key={g} className="rounded py-1 text-[0.7rem] font-semibold text-[#081017]" style={{ flex: results.grades[g], background: GRADE[g].color }} title={`${GRADE[g].label}: ${results.grades[g]}`}>
                    {GRADE[g].label} {results.grades[g]}
                  </div>
                ) : null,
              )}
            </div>
            <p className="text-sm text-ink-2">
              {mode === "faellig"
                ? "Die Karten kommen automatisch wieder, wenn sie fällig sind – schwere früher, leichte später."
                : "Falsch beantwortete Karten wurden zurück in die Wiederholung gelegt."}
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {wrongIds.length > 0 && (
                <button
                  className="btn"
                  onClick={() => {
                    setRetry([...wrongIds]);
                    setWrongIds([]);
                    setResults({ correct: 0, wrong: 0, grades: { 1: 0, 2: 0, 3: 0, 4: 0 } });
                    setIndex(0);
                    setQueue(null);
                  }}
                >
                  ✗ Falsche nochmal üben ({wrongIds.length})
                </button>
              )}
              <button className="btn btn-primary" onClick={onExit}>
                Fertig
              </button>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  const progress = (index / queue.length) * 100;

  return (
    <div className="mx-auto max-w-3xl">
      {header}
      <ProgressBar value={progress} max={100} height={4} color={color} label="Fortschritt" />

      <div className="flip-scene mt-6" key={`${card.id}-${index}`}>
        <div className={`flip-card card-in h-[min(52vh,440px)] cursor-pointer ${flipped ? "flipped" : ""}`} onClick={() => setFlipped(!flipped)} role="button" tabIndex={0} aria-label={flipped ? "Frage zeigen" : "Antwort zeigen"}>
          {[false, true].map((back) => (
            <div
              key={String(back)}
              className={`flip-face ${back ? "flip-back" : ""} border p-7`}
              style={{
                borderColor: `${color}${back ? "88" : "44"}`,
                background: back ? `linear-gradient(160deg, ${color}14, rgba(13,20,27,0.97) 55%)` : "linear-gradient(180deg, rgba(17,26,35,0.97), rgba(10,16,22,0.97))",
                boxShadow: `0 0 0 1px ${color}10, 0 20px 50px rgba(0,0,0,0.45), 0 0 30px ${color}${back ? "22" : "10"}`,
              }}
            >
              <div className="flex items-center justify-between text-[0.68rem] uppercase tracking-[0.18em] text-ink-3">
                <span style={{ color }}>
                  {card.subject} · {card.topic}
                </span>
                <span className="flex items-center gap-2">
                  {card.again && <Chip color="#fb923c">nochmal</Chip>}
                  <Chip color={STATUS[card.status]?.color || "#66788a"}>{STATUS[card.status]?.label || card.status}</Chip>
                  <span>{back ? "Antwort" : "Frage"}</span>
                </span>
              </div>
              <div className="flex flex-1 items-center justify-center overflow-y-auto py-4">
                <div className={`w-full text-center ${back ? "text-base leading-relaxed text-ink" : "text-xl font-semibold leading-snug"}`}>
                  {back && <div className="mb-4 border-b border-line/60 pb-3 text-sm text-ink-3">{card.front}</div>}
                  <div className={back ? "mx-auto max-w-xl text-left" : ""}>
                    <Markdown text={back ? card.back : card.front} />
                  </div>
                </div>
              </div>
              <div className="text-center text-xs text-ink-3">{back ? "Wie gut wusstest du es? Tasten 1–4" : "Klicken oder Leertaste zum Umdrehen"}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-6 min-h-[64px]">
        {flipped ? (
          <div className="grid grid-cols-4 gap-2 card-in">
            {[1, 2, 3, 4].map((g) => (
              <button
                key={g}
                disabled={busy}
                onClick={() => grade(g)}
                className="group flex flex-col items-center rounded-xl border px-2 py-2.5 transition hover:-translate-y-0.5"
                style={{ borderColor: `${GRADE[g].color}66`, background: `${GRADE[g].color}12`, color: GRADE[g].color }}
                onMouseEnter={(e) => (e.currentTarget.style.boxShadow = `0 0 16px ${GRADE[g].color}55`)}
                onMouseLeave={(e) => (e.currentTarget.style.boxShadow = "none")}
              >
                <span className="text-sm font-bold">
                  {GRADE[g].label} <span className="text-[0.65rem] opacity-60">[{g}]</span>
                </span>
                <span className="text-[0.68rem] text-ink-3">{g === 1 || mode !== "alle" || card.status === "neu" || card.status === "faellig" || card.again ? `in ${card.preview?.[g] ?? "–"}` : GRADE[g].hint}</span>
              </button>
            ))}
          </div>
        ) : (
          <button className="btn btn-primary w-full py-3" onClick={() => setFlipped(true)}>
            Antwort zeigen <span className="text-xs opacity-60">[Leertaste]</span>
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Karten verwalten

function CardForm({ subjects, initial, onSave, onCancel, keepOpen = false }) {
  const [f, setF] = useState(initial);
  const topics = subjects.flatMap((s) => s.topics.map((t) => ({ ...t, subject: s.name })));
  async function submit(e) {
    e.preventDefault();
    const ok = await onSave({ topic_id: Number(f.topic_id), front: f.front, back: f.back });
    if (ok && keepOpen) setF({ ...f, front: "", back: "" });
  }
  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-3">
      <Field label="Thema" className="col-span-2">
        <select className="input" value={f.topic_id} onChange={(e) => setF({ ...f, topic_id: e.target.value })} required>
          <option value="">– Thema wählen –</option>
          {subjects.map((s) => (
            <optgroup key={s.id} label={`${s.emoji} ${s.name}`}>
              {s.topics.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </Field>
      <Field label="Vorderseite (Frage)" className="col-span-2 md:col-span-1">
        <textarea className="input" rows={4} value={f.front} onChange={(e) => setF({ ...f, front: e.target.value })} required placeholder="Was ist …?" />
      </Field>
      <Field label="Rückseite (Antwort)" className="col-span-2 md:col-span-1">
        <textarea className="input" rows={4} value={f.back} onChange={(e) => setF({ ...f, back: e.target.value })} required placeholder="**Fett** und Aufzählungen mit - gehen auch" />
      </Field>
      <div className="col-span-2 flex items-center justify-end gap-2">
        {!topics.length && <span className="mr-auto text-xs text-ink-3">Lege zuerst in der Übersicht ein Fach mit Thema an.</span>}
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            Abbrechen
          </button>
        )}
        <button className="btn btn-primary" disabled={!f.topic_id}>
          {keepOpen ? "+ Karte hinzufügen" : "Speichern"}
        </button>
      </div>
    </form>
  );
}

function dueText(card) {
  if (card.status === "neu") return "noch nie abgefragt";
  if (!card.due) return "–";
  const d = new Date(card.due);
  const days = Math.round((new Date(d.toDateString()) - new Date(new Date().toDateString())) / 86400000);
  if (days <= 0) return "jetzt fällig";
  if (days === 1) return "morgen";
  return `in ${days} Tagen (${dateShort(card.due.slice(0, 10))})`;
}

function CardsTab({ data, reload }) {
  const toast = useToast();
  const [subjectId, setSubjectId] = useState("");
  const [topicId, setTopicId] = useState("");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState(null);
  const [showBack, setShowBack] = useState(true);
  const params = new URLSearchParams();
  if (topicId) params.set("topic_id", topicId);
  else if (subjectId) params.set("subject_id", subjectId);
  if (q.trim()) params.set("q", q.trim());
  const list = useApi(`/cards/list?${params}`);
  const subject = data.subjects.find((s) => String(s.id) === subjectId);

  async function create(payload) {
    try {
      await api.post("/cards/cards", payload);
      toast("Karte hinzugefügt.", "success");
      list.reload();
      reload();
      return true;
    } catch (e) {
      toast(e.message, "error");
      return false;
    }
  }
  async function update(payload) {
    try {
      await api.patch(`/cards/cards/${editing.id}`, payload);
      setEditing(null);
      list.reload();
      reload();
      return true;
    } catch (e) {
      toast(e.message, "error");
      return false;
    }
  }
  async function act(fn, msg) {
    try {
      await fn();
      if (msg) toast(msg, "success");
      list.reload();
      reload();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  const firstTopic = topicId || subject?.topics[0]?.id || data.subjects[0]?.topics[0]?.id || "";

  return (
    <div className="grid grid-cols-12 gap-5">
      <Card title="Neue Karte" className="col-span-12">
        <CardForm key={firstTopic} subjects={data.subjects} initial={{ topic_id: String(firstTopic), front: "", back: "" }} onSave={create} keepOpen />
      </Card>
      <Card
        className="col-span-12"
        title={`Karten${list.data ? ` (${list.data.cards.length})` : ""}`}
        actions={
          <label className="flex items-center gap-2 text-xs text-ink-2">
            <input type="checkbox" checked={showBack} onChange={(e) => setShowBack(e.target.checked)} /> Antworten zeigen
          </label>
        }
      >
        <div className="mb-4 grid grid-cols-12 gap-2">
          <select
            className="input col-span-12 md:col-span-3"
            value={subjectId}
            onChange={(e) => {
              setSubjectId(e.target.value);
              setTopicId("");
            }}
            aria-label="Fach filtern"
          >
            <option value="">Alle Fächer</option>
            {data.subjects.map((s) => (
              <option key={s.id} value={s.id}>
                {s.emoji} {s.name}
              </option>
            ))}
          </select>
          <select className="input col-span-12 md:col-span-3" value={topicId} onChange={(e) => setTopicId(e.target.value)} disabled={!subject} aria-label="Thema filtern">
            <option value="">Alle Themen</option>
            {subject?.topics.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <input className="input col-span-12 md:col-span-6" placeholder="Karten durchsuchen …" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Karten durchsuchen" />
        </div>
        {list.error && <ErrorBox error={list.error} onRetry={list.reload} />}
        {!list.data ? (
          <Loading />
        ) : list.data.cards.length ? (
          <ul className="space-y-2">
            {list.data.cards.map((c) => (
              <li key={c.id} className="flex gap-3 rounded-lg border border-line/60 bg-[#0a1118] px-3 py-2.5">
                <span className="w-1 shrink-0 rounded-full" style={{ background: c.color, boxShadow: `0 0 6px ${c.color}` }} />
                <div className="grid min-w-0 flex-1 gap-2 md:grid-cols-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium [&_p]:my-0">
                      <Markdown text={c.front} />
                    </div>
                  </div>
                  {showBack && (
                    <div className="min-w-0 text-sm text-ink-2 [&_p]:my-0">
                      <Markdown text={c.back} />
                    </div>
                  )}
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-ink-3 md:col-span-2">
                    <Chip color={STATUS[c.status].color}>{STATUS[c.status].label}</Chip>
                    <span>
                      {c.subject} · {c.topic}
                    </span>
                    <span>· {dueText(c)}</span>
                    {c.lapses > 0 && <span>· {c.lapses}× vergessen</span>}
                  </div>
                </div>
                <div className="flex shrink-0 flex-col gap-1 sm:flex-row sm:items-start">
                  <button className="btn btn-ghost btn-sm" onClick={() => setEditing(c)} title="Bearbeiten">
                    ✎
                  </button>
                  {c.status !== "neu" && (
                    <ConfirmButton className="btn btn-ghost btn-sm" onConfirm={() => act(() => api.post(`/cards/cards/${c.id}/reset`), "Fortschritt zurückgesetzt.")} question="Zurücksetzen?">
                      ↺
                    </ConfirmButton>
                  )}
                  <ConfirmButton className="btn btn-ghost btn-sm" onConfirm={() => act(() => api.del(`/cards/cards/${c.id}`))} question="Löschen?">
                    🗑
                  </ConfirmButton>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <Empty icon="🗂️">Keine Karten gefunden.</Empty>
        )}
      </Card>
      <Modal open={Boolean(editing)} title="Karte bearbeiten" onClose={() => setEditing(null)} wide>
        {editing && <CardForm subjects={data.subjects} initial={{ topic_id: String(editing.topic_id), front: editing.front, back: editing.back }} onSave={update} onCancel={() => setEditing(null)} />}
      </Modal>
    </div>
  );
}

// ---------------------------------------------------------------- Import

const EXAMPLE = `# Fach: Zivilrecht
## Thema: Vertragsschluss
F: Wie kommt ein Vertrag zustande?
A: Durch zwei übereinstimmende Willenserklärungen: Angebot und Annahme (§§ 145 ff. BGB).

Was ist eine invitatio ad offerendum? | Aufforderung zur Abgabe eines Angebots, z. B. Schaufensterauslage`;

function ImportTab({ data, reload, onDone }) {
  const toast = useToast();
  const [text, setText] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [topicId, setTopicId] = useState("");
  const [subjectName, setSubjectName] = useState("");
  const [topicName, setTopicName] = useState("");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [material, setMaterial] = useState("");
  const [count, setCount] = useState(15);
  const subject = data.subjects.find((s) => String(s.id) === subjectId);

  const body = (dry) => ({
    text,
    subject_id: subjectId ? Number(subjectId) : null,
    topic_id: topicId ? Number(topicId) : null,
    subject_name: subjectId ? "" : subjectName,
    topic_name: topicId ? "" : topicName,
    dry_run: dry,
  });

  async function runPreview(t = text) {
    if (!t.trim()) return;
    setBusy(true);
    try {
      setPreview(await api.post("/cards/import", { ...body(true), text: t }));
    } catch (e) {
      setPreview(null);
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function runImport() {
    setBusy(true);
    try {
      const r = await api.post("/cards/import", body(false));
      toast(`${r.created} Karten importiert${r.skipped ? `, ${r.skipped} doppelte übersprungen` : ""}.`, "success");
      setText("");
      setPreview(null);
      reload();
      onDone();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(data.claude_prompt);
      toast("Prompt kopiert – jetzt in Claude einfügen und deinen Stoff anhängen.", "success");
    } catch {
      toast("Kopieren nicht möglich – bitte den Text unten markieren und kopieren.", "error");
    }
  }

  async function generate() {
    setBusy(true);
    try {
      const r = await api.post("/cards/generate", { text: material, count });
      setText(r.text);
      await runPreview(r.text);
      toast("Claude hat Karten erstellt – prüfe die Vorschau.", "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  // Vorschau aktualisieren, wenn sich das Ziel ändert
  useEffect(() => {
    if (preview && text.trim()) runPreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subjectId, topicId]);

  return (
    <div className="grid grid-cols-12 gap-5">
      <Card title="So geht's" className="col-span-12 xl:col-span-5">
        <ol className="space-y-3 text-sm text-ink-2">
          <li className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-accent/50 text-xs font-bold text-accent">1</span>
            <div>
              <b className="text-ink">Prompt kopieren</b> und in Claude (claude.ai oder App) einfügen.
              <div className="mt-2">
                <button className="btn btn-primary btn-sm" onClick={copyPrompt}>
                  📋 Prompt für Claude kopieren
                </button>
              </div>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-accent/50 text-xs font-bold text-accent">2</span>
            <div>
              <b className="text-ink">Stoff anhängen</b> – Skript, Folien-PDF, Mitschrift oder einfach „Erstelle Karten zu § 119 BGB“.
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-accent/50 text-xs font-bold text-accent">3</span>
            <div>
              <b className="text-ink">Antwort komplett kopieren</b> und rechts einfügen. Fach und Themen aus der Antwort werden automatisch angelegt.
            </div>
          </li>
        </ol>
        <details className="mt-4 text-xs text-ink-3">
          <summary className="cursor-pointer text-ink-2 hover:text-accent">Welche Formate funktionieren?</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>JSON aus dem Prompt (empfohlen – mehrere Themen auf einmal)</li>
            <li>
              <code>F: …</code> / <code>A: …</code> Blöcke, Antworten auch mehrzeilig
            </li>
            <li>
              Eine Karte pro Zeile: <code>Frage | Antwort</code> (auch Tab oder <code>;</code>)
            </li>
            <li>Markdown-Tabelle mit den Spalten Frage | Antwort</li>
            <li>
              Überschriften <code># Fach: …</code> und <code>## Thema: …</code> legen Fach/Thema fest
            </li>
          </ul>
          <button className="btn btn-sm mt-2" onClick={() => setText(EXAMPLE)}>
            Beispiel einfügen
          </button>
        </details>
        <details className="mt-3 text-xs text-ink-3">
          <summary className="cursor-pointer text-ink-2 hover:text-accent">Prompt ansehen</summary>
          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-[#081017] p-3 text-[0.72rem] text-ink-2">{data.claude_prompt}</pre>
        </details>

        {data.claude_available && (
          <div className="mt-5 border-t border-line/60 pt-4">
            <div className="card-title mb-2">⚡ Direkt mit Claude erzeugen</div>
            <p className="mb-2 text-xs text-ink-3">Dein API-Schlüssel ist eingerichtet – füge Stoff ein und Claude erstellt die Karten ohne Umweg.</p>
            <textarea className="input text-sm" rows={5} placeholder="Skript, Mitschrift oder Stichpunkte einfügen …" value={material} onChange={(e) => setMaterial(e.target.value)} />
            <div className="mt-2 flex items-center gap-2">
              <label className="flex items-center gap-2 text-xs text-ink-2">
                ca.
                <input type="number" min={3} max={80} className="input w-20 py-1" value={count} onChange={(e) => setCount(Number(e.target.value) || 15)} />
                Karten
              </label>
              <button className="btn btn-primary btn-sm ml-auto" disabled={busy || material.trim().length < 20} onClick={generate}>
                {busy ? "Claude denkt nach …" : "Karten erzeugen"}
              </button>
            </div>
          </div>
        )}
      </Card>

      <Card title="Antwort von Claude einfügen" className="col-span-12 xl:col-span-7">
        <textarea
          className="input font-mono text-[0.8rem]"
          rows={12}
          placeholder={'```json\n{ "fach": "Zivilrecht", "themen": [ … ] }\n```\n\noder\n\nF: Frage\nA: Antwort'}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setPreview(null);
          }}
        />
        <div className="mt-3 grid grid-cols-12 gap-2">
          <div className="col-span-12 text-xs text-ink-3">Ziel für Karten, bei denen im Text kein Fach/Thema steht:</div>
          <select
            className="input col-span-12 md:col-span-6"
            value={subjectId}
            onChange={(e) => {
              setSubjectId(e.target.value);
              setTopicId("");
            }}
            aria-label="Ziel-Fach"
          >
            <option value="">➕ Neues Fach …</option>
            {data.subjects.map((s) => (
              <option key={s.id} value={s.id}>
                {s.emoji} {s.name}
              </option>
            ))}
          </select>
          {subject ? (
            <select className="input col-span-12 md:col-span-6" value={topicId} onChange={(e) => setTopicId(e.target.value)} aria-label="Ziel-Thema">
              <option value="">➕ Neues Thema …</option>
              {subject.topics.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          ) : (
            <input className="input col-span-12 md:col-span-6" placeholder="Name des neuen Fachs" value={subjectName} onChange={(e) => setSubjectName(e.target.value)} />
          )}
          {!topicId && <input className="input col-span-12" placeholder="Name des neuen Themas (sonst „Allgemein“)" value={topicName} onChange={(e) => setTopicName(e.target.value)} />}
        </div>
        <div className="mt-3 flex justify-end gap-2">
          <button className="btn" disabled={busy || !text.trim()} onClick={() => runPreview()}>
            👁 Vorschau
          </button>
          <button className="btn btn-primary" disabled={busy || !preview} onClick={runImport}>
            📥 {preview ? `${preview.count} Karten importieren` : "Importieren"}
          </button>
        </div>

        {preview && (
          <div className="mt-4 space-y-3 card-in">
            <div className="flex flex-wrap gap-2">
              {preview.groups.map((g) => (
                <span key={`${g.subject}-${g.topic}`} className="chip" style={g.new ? { borderColor: "#34d39966", color: "#34d399" } : undefined}>
                  {g.subject} → {g.topic} · {g.count}
                  {g.new && " · neu"}
                </span>
              ))}
            </div>
            {preview.new_subjects.length > 0 && <div className="text-xs text-emerald-300">Neue Fächer werden angelegt: {preview.new_subjects.join(", ")}</div>}
            <ul className="max-h-80 space-y-1.5 overflow-y-auto pr-1">
              {preview.cards.map((c, i) => (
                <li key={i} className="grid gap-2 rounded-lg border border-line/60 bg-[#0a1118] px-3 py-2 text-sm md:grid-cols-2">
                  <div className="font-medium [&_p]:my-0">
                    <Markdown text={c.front} />
                  </div>
                  <div className="text-ink-2 [&_p]:my-0">
                    <Markdown text={c.back} />
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- Wochenrückblick

function Delta({ cur, prev, suffix = "", better = "up" }) {
  if (typeof cur !== "number" || typeof prev !== "number" || cur === prev) return <span className="text-xs text-ink-3">± 0{suffix} zur Vorwoche</span>;
  const d = cur - prev;
  const good = d > 0 === (better === "up");
  return (
    <span className={`text-xs ${good ? "text-emerald-400" : "text-orange-400"}`}>
      {d > 0 ? "▲" : "▼"} {num(Math.abs(d))}
      {suffix} zur Vorwoche
    </span>
  );
}

function AccuracyRow({ row }) {
  return (
    <div className="py-2">
      <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
        <span className="flex min-w-0 items-center gap-2">
          <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: row.color, boxShadow: `0 0 6px ${row.color}` }} />
          <span className="truncate">{row.name}</span>
          {row.subject && <span className="truncate text-xs text-ink-3">{row.subject}</span>}
        </span>
        <span className="shrink-0 text-xs text-ink-2">
          <b className="text-emerald-400">{row.correct}</b> ✓ · <b className="text-orange-400">{row.wrong}</b> ✗ · <b className="text-ink">{row.accuracy} %</b>
        </span>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full bg-[#15202a]">
        <div style={{ width: `${(row.correct / row.reviews) * 100}%`, background: RIGHT }} />
        <div style={{ width: `${(row.wrong / row.reviews) * 100}%`, background: WRONG }} />
      </div>
    </div>
  );
}

function WeekTab() {
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useApi(`/cards/week?offset=${offset}`);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  const t = data.totals;
  const p = data.previous;
  const chart = data.days.map((d) => ({ ...d, label: weekdayShort(d.date) }));

  return (
    <div className="grid grid-cols-12 gap-5">
      <div className="col-span-12 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-display text-sm font-bold text-accent">{data.label}</div>
          <div className="text-xs text-ink-3">{offset === 0 ? "Diese Woche (läuft noch)" : offset === 1 ? "Letzte Woche" : `Vor ${offset} Wochen`}</div>
        </div>
        <div className="flex gap-2">
          <button className="btn" onClick={() => setOffset(offset + 1)} aria-label="Woche zurück">
            ‹
          </button>
          <button className="btn" onClick={() => setOffset(0)} disabled={offset === 0}>
            Heute
          </button>
          <button className="btn" onClick={() => setOffset(Math.max(0, offset - 1))} disabled={offset === 0} aria-label="Woche vor">
            ›
          </button>
        </div>
      </div>

      <Card className="col-span-12">
        <div className="flex flex-wrap items-center gap-8">
          <Ring value={t.accuracy ?? 0} max={100} size={120} stroke={10} color={t.accuracy === null ? "#2a3845" : t.accuracy >= 80 ? "#34d399" : t.accuracy >= 50 ? "#22d3ee" : "#fb923c"}>
            <div className="text-2xl font-bold">{t.accuracy === null ? "–" : `${t.accuracy} %`}</div>
            <div className="text-[0.62rem] uppercase tracking-wider text-ink-3">richtig</div>
          </Ring>
          <div className="grid flex-1 grid-cols-2 gap-6 md:grid-cols-4">
            <div>
              <Stat label="Abfragen" value={num(t.reviews)} big />
              <Delta cur={t.reviews} prev={p.reviews} />
            </div>
            <div>
              <Stat label="Richtig" value={num(t.correct)} color="#34d399" big />
              <Delta cur={t.correct} prev={p.correct} />
            </div>
            <div>
              <Stat label="Falsch" value={num(t.wrong)} color="#fb923c" big />
              <Delta cur={t.wrong} prev={p.wrong} better="down" />
            </div>
            <div>
              <Stat label="Trefferquote" value={t.accuracy === null ? "–" : `${t.accuracy} %`} big />
              {t.accuracy !== null && p.accuracy !== null && <Delta cur={t.accuracy} prev={p.accuracy} suffix=" %" />}
            </div>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-4 border-t border-line/50 pt-4 md:grid-cols-4">
          <Stat label="Verschiedene Karten" value={num(t.cards)} />
          <Stat label="Neu gelernt" value={num(t.new_learned)} />
          <Stat label="Karten hinzugefügt" value={num(t.added)} />
          <Stat label="Lerntage" value={`${t.days_active} / 7`} />
        </div>
      </Card>

      <Card title="Richtig & falsch pro Tag" className="col-span-12 xl:col-span-7">
        {t.reviews ? (
          <>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chart} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="label" {...axisProps} />
                  <YAxis allowDecimals={false} {...axisProps} />
                  <Tooltip cursor={{ fill: "rgba(34,211,238,0.06)" }} content={<ChartTooltip labelFormatter={(_, pl) => (pl?.[0] ? dayLabel(pl[0].payload.date) : "")} hideZero />} />
                  <Bar dataKey="correct" name="Richtig" stackId="a" fill={RIGHT} />
                  <Bar dataKey="wrong" name="Falsch" stackId="a" fill={WRONG} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <Legend items={[{ label: "Richtig", color: RIGHT }, { label: "Falsch", color: WRONG }]} />
          </>
        ) : (
          <Empty icon="📭">In dieser Woche wurden keine Karten abgefragt.</Empty>
        )}
      </Card>

      <Card title="Am häufigsten falsch" className="col-span-12 xl:col-span-5">
        {data.hardest.length ? (
          <ul className="space-y-2">
            {data.hardest.map((h) => (
              <li key={h.id} className="flex items-start gap-3 rounded-lg border border-line/60 bg-[#0a1118] px-3 py-2">
                <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: h.color }} />
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-2 text-sm">{h.front}</div>
                  <div className="text-xs text-ink-3">{h.topic}</div>
                </div>
                <Chip color="#fb923c">{h.wrong}× ✗</Chip>
              </li>
            ))}
          </ul>
        ) : (
          <Empty icon="💪">Keine Karte falsch beantwortet.</Empty>
        )}
      </Card>

      <Card title="Nach Fach" className="col-span-12 lg:col-span-6">
        {data.subjects.length ? data.subjects.map((r) => <AccuracyRow key={r.id ?? r.name} row={r} />) : <Empty>Keine Daten.</Empty>}
      </Card>
      <Card title="Nach Thema" className="col-span-12 lg:col-span-6">
        {data.topics.length ? data.topics.map((r) => <AccuracyRow key={r.id ?? r.name} row={r} />) : <Empty>Keine Daten.</Empty>}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- Seite

export default function Karteikarten() {
  const [tab, setTab] = useState("lernen");
  const [session, setSession] = useState(null);
  const { data, error, loading, reload } = useApi("/cards");

  const exit = useCallback(() => {
    setSession(null);
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (session) return <StudySession scope={session} onExit={exit} />;
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;

  return (
    <div>
      <PageHeader
        title="Karteikarten"
        icon="🗂️"
        subtitle="Fächer → Themen → Karten · Spaced Repetition bringt jede Karte genau dann zurück, wenn du sie sonst vergessen würdest"
        actions={
          <Segmented
            value={tab}
            onChange={setTab}
            options={[
              { value: "lernen", label: "🎯 Lernen" },
              { value: "karten", label: "🗂️ Karten" },
              { value: "import", label: "📥 Import" },
              { value: "woche", label: "📊 Wochenrückblick" },
            ]}
          />
        }
      />
      {tab === "lernen" && <Overview data={data} reload={reload} onStudy={(s) => setSession({ ...s })} onImport={() => setTab("import")} />}
      {tab === "karten" && <CardsTab data={data} reload={reload} />}
      {tab === "import" && <ImportTab data={data} reload={reload} onDone={() => setTab("lernen")} />}
      {tab === "woche" && <WeekTab />}
    </div>
  );
}
