import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { timeText } from "../lib/format";
import { Field, Ring, Segmented, useToast } from "./ui";

const MODES = {
  fokus: { label: "Fokus", minutes: 25, color: "#22d3ee" },
  pause: { label: "Pause", minutes: 5, color: "#1f9d55" },
  lang: { label: "Lange Pause", minutes: 15, color: "#8b5cf6" },
};
const STORE_KEY = "lifeos.pomodoro";

function load() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY)) || null;
  } catch {
    return null;
  }
}

function save(state) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(state));
  } catch {
    /* privater Modus o. Ä. – Timer läuft trotzdem */
  }
}

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [0, 0.25, 0.5].forEach((t) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.18, ctx.currentTime + t);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + t + 0.2);
      osc.connect(gain).connect(ctx.destination);
      osc.start(ctx.currentTime + t);
      osc.stop(ctx.currentTime + t + 0.22);
    });
  } catch {
    /* kein Audio verfügbar */
  }
}

function notify(text) {
  try {
    if ("Notification" in window && Notification.permission === "granted") new Notification("Life OS", { body: text });
  } catch {
    /* ignorieren */
  }
}

const INITIAL = { mode: "fokus", running: false, endsAt: null, remaining: MODES.fokus.minutes * 60, startedAt: null, cycles: 0, subjectId: "", blockId: "", markDone: true, note: "" };

export default function Pomodoro({ subjects, blocks, onLogged }) {
  const [st, setSt] = useState(() => ({ ...INITIAL, ...(load() || {}) }));
  const [now, setNow] = useState(Date.now());
  const toast = useToast();
  const finishing = useRef(false);

  useEffect(() => save(st), [st]);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);

  const total = MODES[st.mode].minutes * 60;
  const remaining = st.running && st.endsAt ? Math.max(0, Math.round((st.endsAt - now) / 1000)) : st.remaining;

  const logFocus = useCallback(
    async (minutes, endTime) => {
      const start = new Date(st.startedAt || endTime - minutes * 60000);
      try {
        await api.post("/focus", {
          start: start.toISOString(),
          end: new Date(endTime).toISOString(),
          minutes,
          subject_id: st.subjectId ? Number(st.subjectId) : null,
          study_block_id: st.blockId ? Number(st.blockId) : null,
          mark_block_done: Boolean(st.blockId && st.markDone),
          note: st.note,
        });
        onLogged?.();
      } catch (e) {
        toast(e.message, "error");
      }
    },
    [st, onLogged, toast],
  );

  useEffect(() => {
    if (!st.running || remaining > 0 || finishing.current) return;
    finishing.current = true;
    const end = st.endsAt || Date.now();
    (async () => {
      beep();
      if (st.mode === "fokus") {
        await logFocus(MODES.fokus.minutes, end);
        const cycles = st.cycles + 1;
        const next = cycles % 4 === 0 ? "lang" : "pause";
        notify("Fokus-Einheit geschafft – Zeit für eine Pause!");
        toast(`🍅 Fokus-Einheit gespeichert. ${next === "lang" ? "Lange Pause" : "Kurze Pause"}!`, "success");
        setSt((s) => ({ ...s, mode: next, running: false, endsAt: null, remaining: MODES[next].minutes * 60, startedAt: null, cycles, blockId: s.markDone ? "" : s.blockId }));
      } else {
        notify("Pause vorbei – weiter geht's!");
        toast("Pause vorbei – bereit für die nächste Fokus-Einheit.");
        setSt((s) => ({ ...s, mode: "fokus", running: false, endsAt: null, remaining: MODES.fokus.minutes * 60, startedAt: null }));
      }
      finishing.current = false;
    })();
  }, [remaining, st, logFocus, toast]);

  function start() {
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission().catch(() => {});
    setSt((s) => ({ ...s, running: true, endsAt: Date.now() + s.remaining * 1000, startedAt: s.startedAt || Date.now() }));
  }
  function pause() {
    setSt((s) => ({ ...s, running: false, endsAt: null, remaining }));
  }
  function reset(mode = st.mode) {
    setSt((s) => ({ ...s, mode, running: false, endsAt: null, remaining: MODES[mode].minutes * 60, startedAt: null }));
  }
  async function stopAndSave() {
    const elapsed = Math.round((total - remaining) / 60);
    if (st.mode === "fokus" && elapsed >= 5) {
      await logFocus(elapsed, Date.now());
      toast(`${elapsed} Minuten Fokus gespeichert.`, "success");
    }
    reset("fokus");
  }

  const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
  const ss = String(remaining % 60).padStart(2, "0");
  const color = MODES[st.mode].color;
  const blockOptions = (blocks || []).filter((b) => !st.subjectId || String(b.subject_id) === String(st.subjectId));

  return (
    <div className="flex flex-col items-center gap-4">
      <Segmented value={st.mode} onChange={(m) => !st.running && reset(m)} options={Object.entries(MODES).map(([k, v]) => ({ value: k, label: `${v.label} ${v.minutes}` }))} />
      <Ring value={total - remaining} max={total} size={210} stroke={10} color={color}>
        <span className="font-display text-5xl font-extrabold tabular-nums" style={{ color, textShadow: `0 0 16px ${color}99` }}>
          {mm}:{ss}
        </span>
        <span className="mt-1 text-xs uppercase tracking-widest text-ink-3">
          {MODES[st.mode].label} · Runde {(st.cycles % 4) + 1}/4
        </span>
      </Ring>
      <div className="flex gap-2">
        {st.running ? (
          <button className="btn btn-primary w-28" onClick={pause}>
            ❚❚ Pause
          </button>
        ) : (
          <button className="btn btn-primary w-28" onClick={start}>
            ▶ Start
          </button>
        )}
        <button className="btn" onClick={() => reset()} disabled={st.running}>
          ↺ Zurücksetzen
        </button>
        {st.mode === "fokus" && st.startedAt && (
          <button className="btn" onClick={stopAndSave}>
            ■ Beenden & speichern
          </button>
        )}
      </div>
      <div className="grid w-full grid-cols-2 gap-3">
        <Field label="Fach">
          <select className="input" value={st.subjectId} onChange={(e) => setSt({ ...st, subjectId: e.target.value, blockId: "" })}>
            <option value="">– ohne Fach –</option>
            {subjects.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Lernblock">
          <select
            className="input"
            value={st.blockId}
            onChange={(e) => {
              const b = blocks.find((x) => String(x.id) === e.target.value);
              setSt({ ...st, blockId: e.target.value, subjectId: b ? String(b.subject_id) : st.subjectId });
            }}
          >
            <option value="">– kein Block –</option>
            {blockOptions.map((b) => (
              <option key={b.id} value={b.id}>
                {timeText(b.start)} {b.title}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Notiz (optional)" className="col-span-2">
          <input className="input" value={st.note} onChange={(e) => setSt({ ...st, note: e.target.value })} placeholder="Woran arbeitest du?" />
        </Field>
        {st.blockId && (
          <label className="col-span-2 flex items-center gap-2 text-sm text-ink-2">
            <input type="checkbox" checked={st.markDone} onChange={(e) => setSt({ ...st, markDone: e.target.checked })} />
            Lernblock nach der Fokus-Einheit als erledigt markieren
          </label>
        )}
      </div>
    </div>
  );
}
