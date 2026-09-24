import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Badge, Card, ConfirmButton, Empty, ErrorBox, Field, Loading, PageHeader, Segmented, useToast } from "../components/ui";
import { api, useApi, useRefresh } from "../lib/api";
import { dateTimeText } from "../lib/format";

const TABS = [
  { value: "verbindungen", label: "Verbindungen" },
  { value: "ziele", label: "Ziele" },
  { value: "lernplan", label: "Lernplan" },
  { value: "habits", label: "Habits & Journal" },
  { value: "news", label: "News-Feeds" },
  { value: "daten", label: "Daten" },
];
const WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

function StatusDot({ ok, label }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className="h-2 w-2 rounded-full" style={{ background: ok ? "#22c55e" : "#66788a", boxShadow: ok ? "0 0 6px #22c55e" : "none" }} />
      {label}
    </span>
  );
}

// ---------------------------------------------------------------- Verbindungen

function GarminCard() {
  const { data: st, reload } = useApi("/garmin/status");
  const [form, setForm] = useState({ email: "", password: "" });
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const { bump } = useRefresh();

  useEffect(() => {
    if (!st?.sync?.running) return undefined;
    const t = setTimeout(reload, 2000);
    return () => clearTimeout(t);
  }, [st, reload]);

  if (!st) return <Card title="⌚ Garmin Connect"><Loading /></Card>;
  const connected = st.has_tokens;

  async function run(fn, ok) {
    setBusy(true);
    try {
      const r = await fn();
      if (r?.result === "needs_mfa") toast("Garmin hat dir einen Code geschickt – bitte unten eingeben.");
      else if (ok) toast(ok, "success");
      reload();
      bump();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="⌚ Garmin Connect" actions={<StatusDot ok={connected} label={connected ? "verbunden" : "nicht verbunden"} />}>
      <div className="space-y-3 text-sm">
        <p className="text-ink-2">
          Holt Aktivitäten, Schlaf, HRV, Body Battery, Ruhepuls, Stress, Trainingsbereitschaft, Trainingslast, Erholungszeit, VO2max, Schritte und Kalorien von deiner Forerunner 265.
        </p>
        {st.last_sync && <div className="text-ink-3">Letzter Sync: {dateTimeText(st.last_sync)}</div>}
        {st.last_status && st.last_status !== "ok" && st.last_log_message && <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-100">{st.last_log_message}</div>}
        {st.sync.running && (
          <div className="text-accent">
            ⟳ {st.sync.phase} ({st.sync.progress}/{st.sync.total})
          </div>
        )}

        {st.needs_mfa ? (
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              run(() => api.post("/garmin/mfa", { code }), "Code akzeptiert – Sync läuft.");
            }}
          >
            <input className="input flex-1 tracking-[0.3em]" value={code} onChange={(e) => setCode(e.target.value)} placeholder="Zwei-Faktor-Code" inputMode="numeric" autoFocus />
            <button className="btn btn-primary" disabled={busy || !code}>
              Bestätigen
            </button>
          </form>
        ) : connected ? (
          <div className="flex flex-wrap gap-2">
            <button className="btn btn-primary" disabled={busy || st.sync.running} onClick={() => run(() => api.post("/garmin/sync"), "Sync gestartet.")}>
              ⟳ Jetzt synchronisieren
            </button>
            <button className="btn" disabled={busy || st.sync.running} onClick={() => run(() => api.post("/garmin/sync", { days: 90 }), "Sync der letzten 90 Tage gestartet.")}>
              90 Tage nachladen
            </button>
            <ConfirmButton className="btn btn-danger" onConfirm={() => run(() => api.post("/garmin/logout"), "Garmin getrennt.")} question="Wirklich trennen?">
              Trennen
            </ConfirmButton>
          </div>
        ) : (
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              run(() => api.post("/garmin/login", form), "Angemeldet – der erste Sync läuft (ca. 1–2 Minuten).");
            }}
          >
            {st.credentials_in_env ? (
              <p className="text-ink-3">Zugangsdaten aus der .env werden verwendet.</p>
            ) : (
              <>
                <Field label="Garmin-E-Mail">
                  <input className="input" type="email" autoComplete="username" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
                </Field>
                <Field label="Passwort (wird nicht gespeichert)">
                  <input className="input" type="password" autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
                </Field>
              </>
            )}
            <button className="btn btn-primary" disabled={busy}>
              {busy ? "Melde an …" : "Mit Garmin verbinden"}
            </button>
            <p className="text-xs text-ink-3">Gespeichert wird nur ein Login-Token in backend/data/garmin_tokens (nicht im Git). Beim ersten echten Sync werden die Beispiel-Fitnessdaten entfernt.</p>
          </form>
        )}
      </div>
    </Card>
  );
}

function GoogleCard() {
  const { data: st, reload } = useApi("/google/status");
  const [cals, setCals] = useState(null);
  const toast = useToast();

  useEffect(() => {
    if (st?.connected) {
      api.get("/google/calendars").then(setCals).catch((e) => toast(e.message, "error"));
    }
  }, [st?.connected, toast]);

  useEffect(() => {
    if (!st?.sync?.running) return undefined;
    const t = setTimeout(reload, 2000);
    return () => clearTimeout(t);
  }, [st, reload]);

  if (!st) return <Card title="📅 Google Kalender"><Loading /></Card>;

  async function connect() {
    try {
      const { url } = await api.get("/google/auth-url");
      window.location.href = url;
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function toggleCal(id) {
    const selected = cals.selected.includes(id) ? cals.selected.filter((x) => x !== id) : [...cals.selected, id];
    setCals({ ...cals, selected });
    await api.put("/google/calendars", { ids: selected });
    toast("Kalenderauswahl gespeichert – Termine werden neu geladen.");
  }

  return (
    <Card title="📅 Google Kalender" actions={<StatusDot ok={st.connected} label={st.connected ? "verbunden" : "nicht verbunden"} />}>
      <div className="space-y-3 text-sm">
        <p className="text-ink-2">Liest deine Termine und schreibt Lernblöcke und Trainings in den eigenen Kalender „Life OS – Lernplan“ (wird bei Änderungen aktualisiert).</p>
        {!st.has_client_secret && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-100">
            Es fehlt noch die OAuth-Datei von Google. Lege sie hier ab: <code className="break-all text-xs">{st.client_secret_path}</code>
            <br />
            Als Weiterleitungs-URI in der Google Cloud Console eintragen: <code className="text-xs">{st.redirect_uri}</code> – Anleitung in der README.
          </div>
        )}
        {st.last_sync && <div className="text-ink-3">Letzter Sync: {dateTimeText(st.last_sync)}</div>}
        {st.sync.running && <div className="text-accent">⟳ Synchronisiere …</div>}
        {st.last_status === "fehler" && <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-amber-100">{st.last_log_message}</div>}
        {st.connected ? (
          <>
            {cals && (
              <div>
                <div className="label">Diese Kalender lesen</div>
                <div className="space-y-1">
                  {cals.calendars.map((c) => (
                    <label key={c.id} className="flex items-center gap-2">
                      <input type="checkbox" checked={cals.selected.includes(c.id)} onChange={() => toggleCal(c.id)} />
                      <span className="h-2.5 w-2.5 rounded-full" style={{ background: c.color || "#8b5cf6" }} />
                      {c.name}
                      {c.primary && <Badge>Hauptkalender</Badge>}
                    </label>
                  ))}
                </div>
              </div>
            )}
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={st.auto_push}
                onChange={async (e) => {
                  await api.put("/settings", { google_auto_push: e.target.checked });
                  reload();
                }}
              />
              Lernplan-Änderungen automatisch in Google schreiben
            </label>
            <div className="flex flex-wrap gap-2">
              <button className="btn btn-primary" onClick={() => api.post("/google/sync").then(reload).catch((e) => toast(e.message, "error"))} disabled={st.sync.running}>
                ⟳ Jetzt synchronisieren
              </button>
              <ConfirmButton className="btn btn-danger" onConfirm={() => api.post("/google/disconnect").then(reload)} question="Wirklich trennen?">
                Trennen
              </ConfirmButton>
            </div>
          </>
        ) : (
          <button className="btn btn-primary" onClick={connect} disabled={!st.has_client_secret}>
            Mit Google verbinden
          </button>
        )}
      </div>
    </Card>
  );
}

function ClaudeCard() {
  const { data: st } = useApi("/ai/status");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  if (!st) return <Card title="🤖 Claude API"><Loading /></Card>;
  async function test() {
    setBusy(true);
    try {
      const r = await api.post("/ai/test");
      setResult(r.text);
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card title="🤖 Claude API" actions={<StatusDot ok={st.configured} label={st.configured ? "Schlüssel vorhanden" : "kein Schlüssel"} />}>
      <div className="space-y-3 text-sm text-ink-2">
        <p>Für Themen-Extraktion im Lernplan, den KI-Chat und die KI-Zusammenfassung im Rückblick. Alles andere läuft auch ohne.</p>
        <div>
          Modell: <code className="text-accent">{st.model}</code> <span className="text-ink-3">(änderbar in der .env über CLAUDE_MODEL)</span>
        </div>
        {st.configured ? (
          <>
            <button className="btn btn-primary" onClick={test} disabled={busy}>
              {busy ? "Teste …" : "Verbindung testen"}
            </button>
            {result && <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-emerald-100">✓ {result}</div>}
          </>
        ) : (
          <p className="rounded-lg border border-accent/25 bg-accent/5 px-3 py-2">
            Schlüssel unter console.anthropic.com → „API Keys“ erstellen und in die <code>.env</code> eintragen: <code className="text-accent">ANTHROPIC_API_KEY=…</code> – danach App neu starten.
          </p>
        )}
      </div>
    </Card>
  );
}

function IcsCard() {
  const { data, reload } = useApi("/ics");
  const [form, setForm] = useState({ name: "FamilyWall", url: "" });
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const { bump } = useRefresh();

  useEffect(() => {
    if (!data?.status?.running) return undefined;
    const t = setTimeout(() => {
      reload();
      bump();
    }, 2500);
    return () => clearTimeout(t);
  }, [data, reload, bump]);

  async function add(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/ics", form);
      setForm({ name: "", url: "" });
      toast("Kalender verknüpft – Termine werden geladen.", "success");
      setTimeout(reload, 1500);
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  const feeds = data?.feeds || [];
  return (
    <Card title="🔗 Kalender per Link (z. B. FamilyWall)" actions={<StatusDot ok={feeds.length > 0 && feeds.every((f) => !f.last_error)} label={feeds.length ? `${feeds.length} verknüpft` : "keiner"} />}>
      <div className="space-y-3 text-sm">
        <p className="text-ink-2">
          Holt Termine direkt über einen Kalender-Link (iCal/ICS) – ohne Umweg über Google. Aktualisierung alle {data?.refresh_minutes ?? 15} Minuten und beim App-Start. Die Termine erscheinen im Kalender, auf „Heute“ und der Lernplan plant drumherum.
        </p>
        {feeds.length > 0 && (
          <ul className="space-y-1.5">
            {feeds.map((f) => (
              <li key={f.id} className="flex items-center gap-2 rounded-lg border border-line/60 px-2.5 py-1.5">
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{f.name}</div>
                  <div className="truncate text-xs text-ink-3">
                    {f.last_error ? <span className="text-amber-300">⚠ {f.last_error}</span> : f.last_fetched ? `${f.events} Termine · aktualisiert ${dateTimeText(f.last_fetched)}` : "wird geladen …"}
                  </div>
                </div>
                <ConfirmButton onConfirm={() => api.del(`/ics/${f.id}`).then(() => { reload(); bump(); })} question="Entfernen?">
                  ✕
                </ConfirmButton>
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={add} className="space-y-2">
          <Field label="Name">
            <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="FamilyWall" required />
          </Field>
          <Field label="Kalender-Link (webcal:// oder https://…)">
            <input className="input" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="webcal://…" required autoComplete="off" />
          </Field>
          <div className="flex gap-2">
            <button className="btn btn-primary" disabled={busy}>
              + Verknüpfen
            </button>
            {feeds.length > 0 && (
              <button type="button" className="btn" onClick={() => api.post("/ics/refresh").then(() => setTimeout(reload, 1500))} disabled={data?.status?.running}>
                ⟳ Jetzt aktualisieren
              </button>
            )}
          </div>
        </form>
        <p className="text-xs text-ink-3">
          Den Link findest du z. B. in Google Kalender beim abonnierten Kalender unter ⋮ → „Einstellungen und Freigabe“. Ist derselbe Kalender auch über Google verbunden, dort den Haken entfernen, sonst erscheinen Termine doppelt.
        </p>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- Ziele & Lernplan

function NumberField({ label, value, onChange, step = 1, min, suffix }) {
  return (
    <Field label={label}>
      <div className="flex items-center gap-2">
        <input type="number" className="input" step={step} min={min} value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />
        {suffix && <span className="text-xs text-ink-3">{suffix}</span>}
      </div>
    </Field>
  );
}

function GoalsForm({ settings, onSave }) {
  const [s, setS] = useState(settings);
  const set = (k) => (v) => setS({ ...s, [k]: v });
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
      <Card title="👤 Profil & Schlaf">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name" className="col-span-2">
            <input className="input" value={s.profile_name} onChange={(e) => set("profile_name")(e.target.value)} />
          </Field>
          <NumberField label="Schlafziel" value={s.sleep_goal_hours} onChange={set("sleep_goal_hours")} step={0.25} suffix="h" />
          <div />
          <Field label="Zielzeit Einschlafen">
            <input type="time" className="input" value={s.bedtime_target} onChange={(e) => set("bedtime_target")(e.target.value)} />
          </Field>
          <Field label="Zielzeit Aufwachen">
            <input type="time" className="input" value={s.wake_target} onChange={(e) => set("wake_target")(e.target.value)} />
          </Field>
        </div>
      </Card>
      <Card title="🥗 Ernährung">
        <div className="grid grid-cols-2 gap-3">
          <NumberField label="Kalorien pro Tag" value={s.kcal_goal} onChange={set("kcal_goal")} suffix="kcal" />
          <NumberField label="Protein" value={s.protein_goal} onChange={set("protein_goal")} suffix="g" />
          <NumberField label="Kohlenhydrate" value={s.carbs_goal} onChange={set("carbs_goal")} suffix="g" />
          <NumberField label="Fett" value={s.fat_goal} onChange={set("fat_goal")} suffix="g" />
        </div>
      </Card>
      <Card title="🏃 Training">
        <div className="grid grid-cols-2 gap-3">
          <NumberField label="Laufkilometer / Woche" value={s.weekly_run_km_goal} onChange={set("weekly_run_km_goal")} suffix="km" />
          <NumberField label="Trainingszeit / Woche" value={s.weekly_training_hours_goal} onChange={set("weekly_training_hours_goal")} step={0.5} suffix="h" />
          <NumberField label="Einheiten / Woche" value={s.weekly_sessions_goal} onChange={set("weekly_sessions_goal")} />
          <NumberField label="Maximale Herzfrequenz" value={s.max_hr} onChange={set("max_hr")} suffix="bpm" />
          <NumberField label="Referenz-HF Zone-2-Pace" value={s.z2_reference_hr} onChange={set("z2_reference_hr")} suffix="bpm" />
          <Field label="Zonen-Obergrenzen Z1–Z5 (% der max. HF)" className="col-span-2">
            <div className="flex gap-2">
              {s.hr_zone_limits.map((v, i) => (
                <input
                  key={i}
                  type="number"
                  className="input px-2 text-center"
                  value={v}
                  aria-label={`Zone ${i + 1}`}
                  onChange={(e) => set("hr_zone_limits")(s.hr_zone_limits.map((x, j) => (j === i ? Number(e.target.value) : x)))}
                />
              ))}
            </div>
          </Field>
        </div>
      </Card>
      <Card title="💶 Budget">
        <div className="grid grid-cols-2 gap-3">
          <NumberField label="Monatsbudget" value={s.monthly_budget} onChange={set("monthly_budget")} suffix="€" />
          <div className="self-end text-xs text-ink-3">Budgets je Kategorie stellst du im Reiter Finanzen → „Budget“ ein.</div>
        </div>
      </Card>
      <div className="xl:col-span-2">
        <button className="btn btn-primary" onClick={() => onSave(s)}>
          Ziele speichern
        </button>
      </div>
    </div>
  );
}

function StudyForm({ study, onSave }) {
  const [s, setS] = useState(study);
  const [reviewText, setReviewText] = useState(study.review_intervals.join(", "));
  const set = (k) => (v) => setS({ ...s, [k]: v });
  return (
    <Card title="📚 Regeln für den Lernplan">
      <p className="mb-4 text-sm text-ink-2">
        Der Planer legt Lernblöcke in freie Zeiten (Stundenplan, Google-Termine und Trainings werden berücksichtigt), verteilt Wiederholungen, hält Puffertage vor jeder Prüfung frei und plant verpasste Blöcke automatisch neu.
      </p>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Field label="Lernen ab">
          <input type="time" className="input" value={s.day_start} onChange={(e) => set("day_start")(e.target.value)} />
        </Field>
        <Field label="Lernen bis">
          <input type="time" className="input" value={s.day_end} onChange={(e) => set("day_end")(e.target.value)} />
        </Field>
        <NumberField label="Max. Lernzeit pro Tag" value={s.max_minutes_per_day} onChange={set("max_minutes_per_day")} suffix="min" />
        <NumberField label="Blocklänge" value={s.block_minutes} onChange={set("block_minutes")} suffix="min" />
        <NumberField label="Kürzester Block" value={s.min_block_minutes} onChange={set("min_block_minutes")} suffix="min" />
        <NumberField label="Pause zwischen Blöcken" value={s.break_minutes} onChange={set("break_minutes")} suffix="min" />
        <NumberField label="Puffertage vor Prüfung" value={s.buffer_days} onChange={set("buffer_days")} />
        <NumberField label="Max. Blöcke pro Fach & Tag" value={s.max_blocks_per_subject_per_day} onChange={set("max_blocks_per_subject_per_day")} />
        <Field label="Wiederholung nach (Tage)">
          <input className="input" value={reviewText} onChange={(e) => setReviewText(e.target.value)} placeholder="1, 3, 7" />
        </Field>
        <NumberField label="Dauer Wiederholung" value={s.review_minutes} onChange={set("review_minutes")} suffix="min" />
        <NumberField label="Abstand zu Terminen" value={s.event_padding_minutes} onChange={set("event_padding_minutes")} suffix="min" />
        <NumberField label="Puffer nach Training" value={s.workout_padding_minutes} onChange={set("workout_padding_minutes")} suffix="min" />
      </div>
      <div className="mt-4">
        <div className="label">Lerntage</div>
        <div className="flex gap-1.5">
          {WD.map((w, i) => {
            const on = s.weekdays.includes(i);
            return (
              <button
                key={w}
                type="button"
                className={`h-9 w-11 rounded-lg border text-sm font-semibold ${on ? "border-accent bg-accent/15 text-accent" : "border-line text-ink-3"}`}
                onClick={() => set("weekdays")(on ? s.weekdays.filter((x) => x !== i) : [...s.weekdays, i].sort())}
                aria-pressed={on}
              >
                {w}
              </button>
            );
          })}
        </div>
      </div>
      <button className="btn btn-primary mt-5" onClick={() => onSave({ ...s, review_intervals: reviewText.split(/[,; ]+/).map(Number).filter((x) => x > 0) })}>
        Speichern & neu planen
      </button>
    </Card>
  );
}

// ---------------------------------------------------------------- Habits & Journal

function HabitsJournal({ settings, onSave }) {
  const { data, reload } = useApi("/habits");
  const [newHabit, setNewHabit] = useState({ emoji: "✨", name: "" });
  const [questions, setQuestions] = useState(settings.journal_questions);
  const [cats, setCats] = useState(settings.todo_categories.join(", "));
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
      <Card title="✅ Habits">
        <form
          className="mb-3 flex gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            await api.post("/habits", newHabit);
            setNewHabit({ emoji: "✨", name: "" });
            reload();
          }}
        >
          <input className="input w-16 text-center" value={newHabit.emoji} onChange={(e) => setNewHabit({ ...newHabit, emoji: e.target.value })} aria-label="Emoji" />
          <input className="input flex-1" value={newHabit.name} onChange={(e) => setNewHabit({ ...newHabit, name: e.target.value })} placeholder="Neue Gewohnheit" required />
          <button className="btn btn-primary">+</button>
        </form>
        {data?.habits.length ? (
          <ul className="space-y-1.5">
            {data.habits.map((h) => (
              <li key={h.id} className="flex items-center gap-2 rounded-lg border border-line/60 px-2.5 py-1.5 text-sm">
                <input className="input w-14 px-1 py-1 text-center" defaultValue={h.emoji} onBlur={(e) => e.target.value !== h.emoji && api.patch(`/habits/${h.id}`, { emoji: e.target.value }).then(reload)} aria-label="Emoji" />
                <input className="input flex-1 py-1" defaultValue={h.name} onBlur={(e) => e.target.value !== h.name && api.patch(`/habits/${h.id}`, { name: e.target.value }).then(reload)} aria-label="Name" />
                <button className="btn btn-sm" onClick={() => api.patch(`/habits/${h.id}`, { active: !h.active }).then(reload)}>
                  {h.active ? "Pausieren" : "Aktivieren"}
                </button>
                <ConfirmButton onConfirm={() => api.del(`/habits/${h.id}`).then(reload)} question="Löschen?">
                  ✕
                </ConfirmButton>
              </li>
            ))}
          </ul>
        ) : (
          <Empty icon="✅">Noch keine Habits.</Empty>
        )}
      </Card>
      <Card title="📓 Journal-Leitfragen & To-do-Kategorien">
        {["morgen", "abend"].map((kind) => (
          <Field key={kind} label={kind === "morgen" ? "Morgen (eine Frage pro Zeile)" : "Abend (eine Frage pro Zeile)"} className="mb-3">
            <textarea
              className="input"
              rows={3}
              value={questions[kind].join("\n")}
              onChange={(e) => setQuestions({ ...questions, [kind]: e.target.value.split("\n") })}
            />
          </Field>
        ))}
        <Field label="To-do-Kategorien (durch Komma getrennt)">
          <input className="input" value={cats} onChange={(e) => setCats(e.target.value)} />
        </Field>
        <button
          className="btn btn-primary mt-3"
          onClick={() =>
            onSave({
              journal_questions: { morgen: questions.morgen.map((q) => q.trim()).filter(Boolean), abend: questions.abend.map((q) => q.trim()).filter(Boolean) },
              todo_categories: cats.split(",").map((c) => c.trim()).filter(Boolean),
            })
          }
        >
          Speichern
        </button>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- News-Feeds

function FeedsCard() {
  const { data, reload } = useApi("/news/feeds");
  const [f, setF] = useState({ name: "", url: "", category: "Wirtschaft" });
  const toast = useToast();
  return (
    <Card title="📰 News-Feeds (RSS)">
      <form
        className="mb-4 grid grid-cols-12 items-end gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api.post("/news/feeds", f);
            setF({ name: "", url: "", category: f.category });
            toast("Feed hinzugefügt.", "success");
            reload();
          } catch (err) {
            toast(err.message, "error");
          }
        }}
      >
        <Field label="Name" className="col-span-3">
          <input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required placeholder="z. B. Handelsblatt" />
        </Field>
        <Field label="RSS-Adresse" className="col-span-5">
          <input className="input" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} required placeholder="https://…" />
        </Field>
        <Field label="Kategorie" className="col-span-3">
          <input className="input" list="feed-cats" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} required />
          <datalist id="feed-cats">
            {["Wirtschaft", "Recht", "Steuern", "Sport", "Politik", "Technik"].map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </Field>
        <button className="btn btn-primary col-span-1">+</button>
      </form>
      <table className="table text-sm">
        <thead>
          <tr>
            <th>Aktiv</th>
            <th>Name</th>
            <th>Kategorie</th>
            <th>Adresse</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(data || []).map((feed) => (
            <tr key={feed.id}>
              <td>
                <input type="checkbox" checked={feed.active} onChange={() => api.patch(`/news/feeds/${feed.id}`, { active: !feed.active }).then(reload)} aria-label="aktiv" />
              </td>
              <td>{feed.name}</td>
              <td>
                <input className="input w-32 py-1" defaultValue={feed.category} onBlur={(e) => e.target.value !== feed.category && api.patch(`/news/feeds/${feed.id}`, { category: e.target.value }).then(reload)} aria-label="Kategorie" />
              </td>
              <td className="max-w-xs truncate text-xs text-ink-3" title={feed.url}>
                {feed.url}
              </td>
              <td className="text-xs">
                {feed.last_error ? <span className="text-amber-300" title={feed.last_error}>⚠ Fehler</span> : feed.last_fetched ? <span className="text-emerald-400">✓ {dateTimeText(feed.last_fetched)}</span> : <span className="text-ink-3">noch nicht abgerufen</span>}
              </td>
              <td className="text-right">
                <ConfirmButton onConfirm={() => api.del(`/news/feeds/${feed.id}`).then(reload)} question="?">
                  ✕
                </ConfirmButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

// ---------------------------------------------------------------- Daten

function DataCard({ demoActive, onChanged }) {
  const toast = useToast();
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
      <Card title="💾 Daten exportieren">
        <p className="mb-3 text-sm text-ink-2">Alle deine Daten (Training, Schlaf, Lernplan, Finanzen, Journal …) als Datei herunterladen.</p>
        <div className="flex gap-2">
          <a className="btn btn-primary" href="/api/export?format=json">
            JSON herunterladen
          </a>
          <a className="btn" href="/api/export?format=csv">
            CSV (ZIP) für Excel
          </a>
        </div>
        <p className="mt-3 text-xs text-ink-3">Die Datenbank selbst liegt unter backend/data/lifeos.db – für ein Backup einfach diese Datei kopieren.</p>
      </Card>
      <Card title="🧪 Beispieldaten">
        <p className="mb-3 text-sm text-ink-2">
          {demoActive ? "Beispieldaten sind aktiv. Löschen entfernt nur die Beispiele – deine eigenen Einträge bleiben erhalten." : "Es sind keine Beispieldaten aktiv."}
        </p>
        <div className="flex gap-2">
          {demoActive && (
            <ConfirmButton
              className="btn btn-danger"
              question="Beispieldaten wirklich löschen?"
              onConfirm={async () => {
                await api.del("/demo");
                toast("Beispieldaten gelöscht.", "success");
                onChanged();
              }}
            >
              Beispieldaten löschen
            </ConfirmButton>
          )}
          <ConfirmButton
            className="btn"
            question="Beispieldaten neu anlegen?"
            onConfirm={async () => {
              await api.post("/demo");
              toast("Beispieldaten neu erzeugt.", "success");
              onChanged();
            }}
          >
            Beispieldaten neu erzeugen
          </ConfirmButton>
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- Seite

export default function Einstellungen() {
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState(params.get("tab") || "verbindungen");
  const { data, error, loading, reload } = useApi("/settings");
  const toast = useToast();
  const { bump } = useRefresh();

  useEffect(() => {
    const g = params.get("google");
    if (g === "verbunden") toast("Google Kalender verbunden – Termine werden geladen.", "success");
    if (g === "abgebrochen") toast("Google-Verbindung abgebrochen.", "error");
    if (g) {
      params.delete("google");
      setParams(params, { replace: true });
    }
  }, [params, setParams, toast]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;

  async function save(values, msg = "Gespeichert.") {
    try {
      await api.put("/settings", values);
      toast(msg, "success");
      reload();
      bump();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  return (
    <div>
      <PageHeader title="Einstellungen" icon="⚙️" subtitle="Verbindungen, Ziele, Lernplan-Regeln, Habits, News-Feeds und Datenexport" />
      <div className="mb-5">
        <Segmented value={tab} onChange={setTab} options={TABS} />
      </div>
      {tab === "verbindungen" && (
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
          <GarminCard />
          <GoogleCard />
          <ClaudeCard />
          <IcsCard />
        </div>
      )}
      {tab === "ziele" && (
        <GoalsForm
          key={JSON.stringify(data)}
          settings={data}
          onSave={(s) =>
            save({
              profile_name: s.profile_name,
              sleep_goal_hours: Number(s.sleep_goal_hours),
              bedtime_target: s.bedtime_target,
              wake_target: s.wake_target,
              kcal_goal: Number(s.kcal_goal),
              protein_goal: Number(s.protein_goal),
              carbs_goal: Number(s.carbs_goal),
              fat_goal: Number(s.fat_goal),
              weekly_run_km_goal: Number(s.weekly_run_km_goal),
              weekly_training_hours_goal: Number(s.weekly_training_hours_goal),
              weekly_sessions_goal: Number(s.weekly_sessions_goal),
              max_hr: Number(s.max_hr),
              z2_reference_hr: Number(s.z2_reference_hr),
              hr_zone_limits: s.hr_zone_limits.map(Number),
              monthly_budget: Number(s.monthly_budget),
            })
          }
        />
      )}
      {tab === "lernplan" && <StudyForm key={JSON.stringify(data.study)} study={data.study} onSave={(study) => save({ study }, "Regeln gespeichert – Lernplan wurde neu berechnet.")} />}
      {tab === "habits" && <HabitsJournal settings={data} onSave={(v) => save(v)} />}
      {tab === "news" && <FeedsCard />}
      {tab === "daten" && (
        <DataCard
          demoActive={data.demo_active}
          onChanged={() => {
            reload();
            bump();
          }}
        />
      )}
    </div>
  );
}
