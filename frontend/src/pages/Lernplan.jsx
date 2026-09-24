import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, ConfirmButton, Empty, ErrorBox, Field, Loading, Modal, PageHeader, ProgressBar, Ring, Stat, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { dateLong, dayLabel, isoDate, minutesText, num, relativeDay, timeText } from "../lib/format";

const KIND_LABEL = { lernen: "Lernen", wiederholung: "Wiederholung", puffer: "Prüfungsvorbereitung" };
const KIND_ICON = { lernen: "📚", wiederholung: "🔁", puffer: "🎯" };
const STATUS_LABEL = { offen: "offen", in_arbeit: "in Arbeit", fertig: "fertig" };
const DIFF = { 1: "leicht", 2: "mittel", 3: "schwer" };

function SubjectCard({ s, active, onClick }) {
  const urgent = s.days_left !== null && s.days_left <= 7;
  return (
    <button
      onClick={onClick}
      className={`card w-full text-left transition hover:border-accent/50 ${active ? "!border-accent/70 shadow-[0_0_16px_rgba(34,211,238,0.2)]" : ""}`}
    >
      <div className="flex items-start gap-3">
        <Ring value={s.progress} size={64} stroke={6} color={s.color}>
          <span className="text-sm font-bold">{s.progress}%</span>
        </Ring>
        <div className="min-w-0 flex-1">
          <div className="truncate font-semibold">{s.name}</div>
          {s.exam_date ? (
            <div className={`mt-0.5 text-xs ${urgent ? "font-semibold text-amber-400" : "text-ink-2"}`}>
              📝 {dateLong(s.exam_date)}
              {s.exam_time ? `, ${s.exam_time}` : ""}
            </div>
          ) : (
            <div className="mt-0.5 text-xs text-ink-3">kein Prüfungstermin</div>
          )}
          <div className="mt-1 text-xs text-ink-3">
            {s.topics_done}/{s.topics_total} Themen · {minutesText(s.done_minutes)} von {minutesText(s.required_minutes)}
          </div>
        </div>
        {s.days_left !== null && s.days_left >= 0 && (
          <div className="text-center">
            <div className="font-display text-2xl font-extrabold" style={{ color: s.color, textShadow: `0 0 10px ${s.color}88` }}>
              {s.days_left}
            </div>
            <div className="text-[0.6rem] uppercase text-ink-3">Tage</div>
          </div>
        )}
      </div>
    </button>
  );
}

function SubjectForm({ initial, onSave, onCancel }) {
  const [f, setF] = useState(initial);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <form
      className="grid grid-cols-2 gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({
          name: f.name,
          short: f.short,
          color: f.color,
          exam_date: f.exam_date || null,
          exam_time: f.exam_time || null,
          exam_location: f.exam_location || "",
          study_start: f.study_start || null,
          notes: f.notes || "",
        });
      }}
    >
      <Field label="Fach" className="col-span-2">
        <input className="input" value={f.name} onChange={set("name")} required placeholder="z. B. Schuldrecht AT" />
      </Field>
      <Field label="Kürzel">
        <input className="input" value={f.short} onChange={set("short")} placeholder="SchR AT" />
      </Field>
      <Field label="Farbe">
        <input type="color" className="input h-[38px] p-1" value={f.color || "#38bdf8"} onChange={set("color")} />
      </Field>
      <Field label="Prüfungsdatum">
        <input type="date" className="input" value={f.exam_date || ""} onChange={set("exam_date")} />
      </Field>
      <Field label="Uhrzeit">
        <input type="time" className="input" value={f.exam_time || ""} onChange={set("exam_time")} />
      </Field>
      <Field label="Ort">
        <input className="input" value={f.exam_location || ""} onChange={set("exam_location")} placeholder="Audimax" />
      </Field>
      <Field label="Lernbeginn (optional)">
        <input type="date" className="input" value={f.study_start || ""} onChange={set("study_start")} />
      </Field>
      <Field label="Notizen" className="col-span-2">
        <textarea className="input" rows={2} value={f.notes || ""} onChange={set("notes")} />
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

function SubjectDetail({ subjectId, onChanged, claudeAvailable }) {
  const { data, error, loading, reload } = useApi(`/study/subjects/${subjectId}`, [subjectId]);
  const [editOpen, setEditOpen] = useState(false);
  const [text, setText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [proposal, setProposal] = useState(null);
  const fileRef = useRef(null);
  const toast = useToast();

  useEffect(() => setProposal(null), [subjectId]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  const s = data.subject;
  const topics = data.topics;

  const refresh = () => {
    reload();
    onChanged();
  };

  async function upload(files) {
    if (!files?.length) return;
    const form = new FormData();
    [...files].forEach((f) => form.append("files", f));
    setUploading(true);
    try {
      const r = await api(`/study/subjects/${subjectId}/documents`, { method: "POST", body: form });
      if (r.saved.length) toast(`${r.saved.length} Datei(en) hochgeladen.`, "success");
      r.errors.forEach((e) => toast(e, "error"));
      reload();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function extract() {
    setExtracting(true);
    try {
      const r = await api.post(`/study/subjects/${subjectId}/extract`, {});
      setProposal({ ...r, topics: r.topics.map((t) => ({ ...t, use: true })), replace: topics.every((t) => t.status === "offen") });
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setExtracting(false);
    }
  }

  async function acceptProposal() {
    const chosen = proposal.topics.filter((t) => t.use);
    if (!chosen.length) return;
    try {
      await api.post(`/study/subjects/${subjectId}/topics`, {
        topics: chosen.map((t) => ({ title: t.title, effort_hours: Number(t.effort_hours), difficulty: Number(t.difficulty) })),
        replace: proposal.replace,
        source: "ki",
      });
      toast(`${chosen.length} Themen übernommen – Lernplan aktualisiert.`, "success");
      setProposal(null);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function addManual(e) {
    e.preventDefault();
    try {
      const r = await api.post(`/study/subjects/${subjectId}/topics`, { text });
      toast(`${r.added} Thema/Themen hinzugefügt.`, "success");
      setText("");
      refresh();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  async function patchTopic(t, body) {
    try {
      await api.patch(`/study/topics/${t.id}`, body);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function move(index, dir) {
    const ids = topics.map((t) => t.id);
    const j = index + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[index], ids[j]] = [ids[j], ids[index]];
    await api.post(`/study/subjects/${subjectId}/reorder`, { topic_ids: ids });
    refresh();
  }

  async function saveSubject(payload) {
    try {
      await api.patch(`/study/subjects/${subjectId}`, payload);
      setEditOpen(false);
      refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function deleteSubject() {
    await api.del(`/study/subjects/${subjectId}`);
    onChanged(true);
  }

  return (
    <Card
      title={`${s.name}`}
      actions={
        <>
          <button className="btn btn-sm" onClick={() => setEditOpen(true)}>
            ✎ Fach bearbeiten
          </button>
          <ConfirmButton onConfirm={deleteSubject} question="Fach samt Themen löschen?">
            Löschen
          </ConfirmButton>
        </>
      }
    >
      <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Countdown" value={s.days_left !== null ? `${s.days_left} Tage` : "–"} sub={s.exam_date ? `${dateLong(s.exam_date)}${s.exam_location ? ` · ${s.exam_location}` : ""}` : "Prüfungstermin eintragen"} />
        <Stat label="Fortschritt" value={`${s.progress} %`} sub={`${minutesText(s.done_minutes)} von ${minutesText(s.required_minutes)}`} />
        <Stat label="Eingeplant" value={minutesText(s.planned_minutes)} sub={s.next_block ? `nächster Block: ${relativeDay(s.next_block)} ${timeText(s.next_block)}` : "keine Blöcke"} />
        <Stat label="Blöcke" value={`${s.blocks_done} erledigt`} sub={s.blocks_missed ? `${s.blocks_missed} verpasst (neu eingeplant)` : "nichts verpasst"} />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
        <div className="xl:col-span-3">
          <h3 className="card-title mb-2">Themen</h3>
          {topics.length ? (
            <ul className="space-y-1.5">
              {topics.map((t, i) => {
                const pctDone = Math.min(100, (t.done_minutes / (t.effort_hours * 60)) * 100);
                return (
                  <li key={t.id} className="rounded-lg border border-line/70 bg-[#0a1118] px-3 py-2">
                    <div className="flex items-start gap-2">
                      <div className="flex flex-col pt-0.5">
                        <button className="text-[0.6rem] leading-none text-ink-3 hover:text-accent" onClick={() => move(i, -1)} aria-label="nach oben">
                          ▲
                        </button>
                        <button className="text-[0.6rem] leading-none text-ink-3 hover:text-accent" onClick={() => move(i, 1)} aria-label="nach unten">
                          ▼
                        </button>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className={`text-sm font-medium ${t.status === "fertig" ? "text-ink-3 line-through" : ""}`}>
                          {t.source === "ki" && <span title="von Claude vorgeschlagen">✨ </span>}
                          {t.title}
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-3">
                          <span>
                            {DIFF[t.difficulty]} · erledigt {minutesText(t.done_minutes)}
                            {t.reviews_done ? ` · ${t.reviews_done}× wiederholt` : ""}
                            {t.planned_minutes ? ` · geplant ${minutesText(t.planned_minutes)}` : ""}
                          </span>
                          <span className="ml-auto flex items-center gap-1.5">
                            <input
                              type="number"
                              step="0.5"
                              min="0.5"
                              className="input w-16 px-2 py-0.5 text-xs"
                              defaultValue={t.effort_hours}
                              title="Aufwand in Stunden"
                              aria-label="Aufwand in Stunden"
                              onBlur={(e) => Number(e.target.value) !== t.effort_hours && patchTopic(t, { effort_hours: Number(e.target.value) })}
                            />
                            <span>h</span>
                            <select className="input w-[6.5rem] px-2 py-0.5 text-xs" value={t.status} onChange={(e) => patchTopic(t, { status: e.target.value })} aria-label="Status">
                              {Object.entries(STATUS_LABEL).map(([k, v]) => (
                                <option key={k} value={k}>
                                  {v}
                                </option>
                              ))}
                            </select>
                            <ConfirmButton onConfirm={() => api.del(`/study/topics/${t.id}`).then(refresh)} question="Löschen?">
                              ✕
                            </ConfirmButton>
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="mt-1.5">
                      <ProgressBar value={t.status === "fertig" ? 100 : pctDone} color={s.color} height={4} glow={false} label={t.title} />
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <Empty icon="📖">Noch keine Themen. Lade Unterlagen hoch und lass Claude Themen vorschlagen – oder trage sie unten selbst ein.</Empty>
          )}

          <form onSubmit={addManual} className="mt-4">
            <Field label="Themen manuell hinzufügen (eine Zeile pro Thema, optional „Titel | Stunden | Schwierigkeit 1–3“)">
              <textarea className="input font-mono text-xs" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={"Anfechtung | 6 | 3\nStellvertretung | 7\nVerjährung"} />
            </Field>
            <button className="btn btn-primary mt-2" disabled={!text.trim()}>
              + Themen hinzufügen
            </button>
          </form>
        </div>

        <div className="xl:col-span-2">
          <h3 className="card-title mb-2">Unterlagen</h3>
          <div
            className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-accent/40 bg-accent/[0.03] px-4 py-6 text-center text-sm text-ink-2 hover:bg-accent/[0.06]"
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              upload(e.dataTransfer.files);
            }}
          >
            <span className="text-2xl">📄</span>
            {uploading ? "Lade hoch …" : "PDF, Folien (PPTX) oder Text hierher ziehen oder klicken"}
            <input ref={fileRef} type="file" multiple accept=".pdf,.pptx,.txt,.md" className="hidden" onChange={(e) => upload(e.target.files)} />
          </div>
          {data.documents.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {data.documents.map((d) => (
                <li key={d.id} className="flex items-center gap-2 rounded-lg border border-line/70 px-2.5 py-1.5 text-sm">
                  <span>{d.filename.toLowerCase().endsWith(".pdf") ? "📕" : d.filename.toLowerCase().endsWith(".pptx") ? "📙" : "📄"}</span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate">{d.filename}</div>
                    <div className="text-xs text-ink-3">
                      {num(d.size / 1024 / 1024, 1)} MB · {num(d.text_chars)} Zeichen Text{d.topics_extracted ? " · ✨ ausgewertet" : ""}
                    </div>
                  </div>
                  <ConfirmButton onConfirm={() => api.del(`/study/documents/${d.id}`).then(reload)} question="?">
                    ✕
                  </ConfirmButton>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3">
            <button className="btn btn-primary w-full" onClick={extract} disabled={!claudeAvailable || !data.documents.length || extracting}>
              {extracting ? (
                <>
                  <span className="spin inline-block h-3 w-3 rounded-full border-2 border-accent border-t-transparent" /> Claude liest die Unterlagen …
                </>
              ) : (
                "✨ Themen mit Claude extrahieren"
              )}
            </button>
            {!claudeAvailable && (
              <p className="mt-2 text-xs text-ink-3">
                Für die automatische Themen-Erkennung wird ein Claude-API-Schlüssel benötigt (siehe <Link to="/einstellungen" className="text-accent underline">Einstellungen</Link>). Themen kannst du jederzeit manuell eintragen.
              </p>
            )}
          </div>
        </div>
      </div>

      <Modal open={editOpen} title="Fach bearbeiten" onClose={() => setEditOpen(false)}>
        <SubjectForm initial={{ ...s }} onSave={saveSubject} onCancel={() => setEditOpen(false)} />
      </Modal>

      <Modal open={Boolean(proposal)} title="Themenvorschläge von Claude" onClose={() => setProposal(null)} wide>
        {proposal && (
          <div>
            {proposal.note && <p className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">{proposal.note}</p>}
            <p className="mb-3 text-sm text-ink-2">Prüfe die Vorschläge, passe den Aufwand an und übernimm die gewünschten Themen.</p>
            <div className="max-h-[50vh] space-y-1.5 overflow-y-auto pr-1">
              {proposal.topics.map((t, i) => (
                <div key={i} className={`flex items-center gap-2 rounded-lg border border-line/70 px-2 py-1.5 ${t.use ? "" : "opacity-50"}`}>
                  <input
                    type="checkbox"
                    checked={t.use}
                    onChange={(e) => setProposal({ ...proposal, topics: proposal.topics.map((x, j) => (j === i ? { ...x, use: e.target.checked } : x)) })}
                  />
                  <div className="min-w-0 flex-1">
                    <input
                      className="input px-2 py-1 text-sm"
                      value={t.title}
                      onChange={(e) => setProposal({ ...proposal, topics: proposal.topics.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)) })}
                    />
                    <div className="mt-0.5 truncate text-xs text-ink-3" title={t.summary}>
                      {t.summary}
                    </div>
                  </div>
                  <input
                    type="number"
                    step="0.5"
                    className="input w-16 px-2 py-1 text-xs"
                    value={t.effort_hours}
                    onChange={(e) => setProposal({ ...proposal, topics: proposal.topics.map((x, j) => (j === i ? { ...x, effort_hours: e.target.value } : x)) })}
                  />
                  <span className="w-12 text-xs text-ink-3">{DIFF[t.difficulty]}</span>
                </div>
              ))}
            </div>
            <label className="mt-3 flex items-center gap-2 text-sm text-ink-2">
              <input type="checkbox" checked={proposal.replace} onChange={(e) => setProposal({ ...proposal, replace: e.target.checked })} />
              Bisherige offene Themen ohne Fortschritt ersetzen
            </label>
            <div className="mt-4 flex justify-end gap-2">
              <button className="btn" onClick={() => setProposal(null)}>
                Verwerfen
              </button>
              <button className="btn btn-primary" onClick={acceptProposal}>
                {proposal.topics.filter((t) => t.use).length} Themen übernehmen
              </button>
            </div>
          </div>
        )}
      </Modal>
    </Card>
  );
}

function BlockList({ blocks, onStatus }) {
  const [showPast, setShowPast] = useState(false);
  const now = new Date();
  const todayKey = isoDate(now);
  const groups = {};
  blocks.forEach((b) => {
    const key = isoDate(b.start);
    if (!showPast && key < todayKey) return;
    (groups[key] ||= []).push(b);
  });
  const days = Object.keys(groups).sort();
  const hasPast = blocks.some((b) => isoDate(b.start) < todayKey);
  return (
    <div>
      {hasPast && (
        <button className="btn btn-sm mb-3 w-full" onClick={() => setShowPast(!showPast)}>
          {showPast ? "Vergangene ausblenden" : "Letzte 7 Tage anzeigen"}
        </button>
      )}
      {!days.length && <Empty icon="📚">Keine Lernblöcke geplant.</Empty>}
    <div className="max-h-[640px] space-y-4 overflow-y-auto pr-1">
      {days.map((d) => (
        <div key={d}>
          <div className={`font-display mb-1.5 text-[0.65rem] font-bold ${d === todayKey ? "text-accent" : "text-ink-3"}`}>
            {["Heute", "Morgen", "Gestern"].includes(relativeDay(d)) ? `${relativeDay(d)} · ` : ""}
            {dayLabel(d)} · {minutesText(groups[d].filter((b) => b.status !== "verpasst").reduce((a, b) => a + b.minutes, 0))}
          </div>
          <ul className="space-y-1.5">
            {groups[d].map((b) => {
              const past = new Date(b.end) < now;
              return (
                <li
                  key={b.id}
                  className={`flex items-center gap-2.5 rounded-lg border border-line/70 bg-[#0a1118] px-2.5 py-1.5 ${b.status === "verpasst" ? "opacity-50" : ""} ${b.status === "erledigt" ? "opacity-70" : ""}`}
                >
                  <span className="h-8 w-1 rounded-full" style={{ background: b.color, boxShadow: `0 0 6px ${b.color}` }} />
                  <div className="w-11 shrink-0 text-xs leading-tight tabular-nums text-ink-2">
                    {timeText(b.start)}
                    <br />
                    <span className="text-ink-3">{timeText(b.end)}</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className={`line-clamp-2 text-sm leading-snug ${b.status === "verpasst" ? "line-through" : ""}`}>
                      {KIND_ICON[b.kind]} {b.title}
                    </div>
                    <div className="text-xs text-ink-3">
                      {b.subject} · {KIND_LABEL[b.kind]}
                      {b.synced ? " · 📅 Google" : ""}
                    </div>
                  </div>
                  {b.status === "erledigt" ? (
                    <Badge color="#22c55e">✓</Badge>
                  ) : b.status === "verpasst" ? (
                    <Badge color="#ef4444">✗</Badge>
                  ) : (
                    <div className="flex gap-1">
                      <button className="btn btn-sm" onClick={() => onStatus(b, "erledigt")} title="Erledigt">
                        ✓
                      </button>
                      {past && (
                        <button className="btn btn-sm" onClick={() => onStatus(b, "verpasst")} title="Verpasst – neu einplanen">
                          ✗
                        </button>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
    </div>
  );
}

export default function Lernplan() {
  const { data, error, loading, reload } = useApi("/study/overview");
  const [selected, setSelected] = useState(null);
  const [newOpen, setNewOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  useEffect(() => {
    if (data && (selected === null || !data.subjects.some((s) => s.id === selected)) && data.subjects.length) {
      setSelected(data.subjects[0].id);
    }
  }, [data, selected]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;

  async function replan() {
    setBusy(true);
    try {
      const r = await api.post("/study/replan");
      toast(`Neu geplant: ${r.created} Lernblöcke${r.missed ? `, ${r.missed} verpasste neu verteilt` : ""}.`, "success");
      reload();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function googleSync() {
    try {
      await api.post("/google/sync");
      toast("Lernplan wird in den Google-Kalender „Life OS – Lernplan“ geschrieben …");
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function setStatus(b, status) {
    try {
      await api.post(`/study/blocks/${b.id}/status`, { status });
      toast(status === "erledigt" ? "Stark! Block erledigt ✓" : "Block als verpasst markiert und neu eingeplant.", "success");
      reload();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function createSubject(payload) {
    try {
      const s = await api.post("/study/subjects", payload);
      setNewOpen(false);
      setSelected(s.id);
      reload();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  const st = data.settings;
  const warnings = data.last_plan?.warnings || [];

  return (
    <div>
      <PageHeader
        title="Lernplan"
        icon="📚"
        subtitle={`Lernfenster ${st.day_start}–${st.day_end} · max. ${minutesText(st.max_minutes_per_day)}/Tag · Blöcke à ${st.block_minutes} min · ${st.buffer_days} Puffertage · Wiederholung nach ${st.review_intervals.join("/")} Tagen`}
        actions={
          <>
            <Link to="/einstellungen" className="btn">
              ⚙ Regeln
            </Link>
            {data.google_connected && (
              <button className="btn" onClick={googleSync}>
                📅 In Google speichern
              </button>
            )}
            <button className="btn" onClick={replan} disabled={busy}>
              ⟳ Neu planen
            </button>
            <button className="btn btn-primary" onClick={() => setNewOpen(true)}>
              + Fach
            </button>
          </>
        }
      />

      {warnings.length > 0 && (
        <div className="mb-5 space-y-1 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          {warnings.map((w) => (
            <div key={w}>⚠ {w}</div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-12 gap-5">
        <Card className="col-span-12">
          <div className="grid grid-cols-2 gap-5 md:grid-cols-4">
            <Stat label="Diese Woche geplant" value={minutesText(data.week.planned_minutes)} />
            <Stat label="Davon erledigt" value={minutesText(data.week.done_minutes)} sub={data.week.planned_minutes ? `${Math.round((data.week.done_minutes / data.week.planned_minutes) * 100)} %` : null} />
            <Stat label="Verpasst (neu eingeplant)" value={data.week.missed} />
            <Stat label="Fokuszeit (Pomodoro)" value={minutesText(data.week.focus_minutes)} sub={<Link to="/habits" className="text-accent">Timer starten →</Link>} />
          </div>
        </Card>

        <div className="col-span-12 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.subjects.map((s) => (
            <SubjectCard key={s.id} s={s} active={s.id === selected} onClick={() => setSelected(s.id)} />
          ))}
          {!data.subjects.length && (
            <Card className="md:col-span-2 xl:col-span-3">
              <Empty icon="📚">Lege dein erstes Fach mit Prüfungstermin an.</Empty>
            </Card>
          )}
        </div>

        <div className="col-span-12 xl:col-span-8">
          {selected && (
            <SubjectDetail
              key={selected}
              subjectId={selected}
              claudeAvailable={data.claude_available}
              onChanged={(deleted) => {
                if (deleted) setSelected(null);
                reload();
              }}
            />
          )}
        </div>

        <Card title="Lernblöcke (nächste 3 Wochen)" className="col-span-12 xl:col-span-4">
          <BlockList blocks={data.blocks} onStatus={setStatus} />
        </Card>
      </div>

      <Modal open={newOpen} title="Neues Fach" onClose={() => setNewOpen(false)}>
        <SubjectForm initial={{ name: "", short: "", color: "#38bdf8", exam_date: "", exam_time: "", exam_location: "", study_start: "", notes: "" }} onSave={createSubject} onCancel={() => setNewOpen(false)} />
      </Modal>
    </div>
  );
}
