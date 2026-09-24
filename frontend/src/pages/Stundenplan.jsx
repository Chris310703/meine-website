import { useState } from "react";
import WeekGrid from "../components/WeekGrid";
import { Card, ConfirmButton, Empty, ErrorBox, Field, Loading, Modal, PageHeader, Stat, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { dateLong, minutesText } from "../lib/format";

const WD = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];
const KINDS = ["Vorlesung", "Übung", "Tutorium", "Seminar", "AG", "Kolloquium"];

const EMPTY = {
  title: "",
  kind: "Vorlesung",
  weekday: 0,
  start_time: "10:00",
  end_time: "12:00",
  room: "",
  lecturer: "",
  subject_id: "",
  interval_weeks: 1,
  valid_from: "",
  valid_until: "",
};

function EntryForm({ initial, subjects, onSave, onCancel }) {
  const [f, setF] = useState(initial);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <form
      className="grid grid-cols-2 gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({
          ...f,
          weekday: Number(f.weekday),
          interval_weeks: Number(f.interval_weeks),
          subject_id: f.subject_id ? Number(f.subject_id) : null,
          valid_from: f.valid_from || null,
          valid_until: f.valid_until || null,
        });
      }}
    >
      <Field label="Titel" className="col-span-2">
        <input className="input" value={f.title} onChange={set("title")} required placeholder="z. B. BGB AT" />
      </Field>
      <Field label="Art">
        <select className="input" value={f.kind} onChange={set("kind")}>
          {KINDS.map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
      </Field>
      <Field label="Fach (für Lernplan & Farbe)">
        <select className="input" value={f.subject_id ?? ""} onChange={set("subject_id")}>
          <option value="">– keins –</option>
          {subjects.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Wochentag">
        <select className="input" value={f.weekday} onChange={set("weekday")}>
          {WD.map((w, i) => (
            <option key={w} value={i}>
              {w}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Rhythmus">
        <select className="input" value={f.interval_weeks} onChange={set("interval_weeks")}>
          <option value={1}>jede Woche</option>
          <option value={2}>alle 2 Wochen</option>
        </select>
      </Field>
      <Field label="Beginn">
        <input type="time" className="input" value={f.start_time} onChange={set("start_time")} required />
      </Field>
      <Field label="Ende">
        <input type="time" className="input" value={f.end_time} onChange={set("end_time")} required />
      </Field>
      <Field label="Raum">
        <input className="input" value={f.room} onChange={set("room")} placeholder="Hörsaal H1" />
      </Field>
      <Field label="Dozent/in">
        <input className="input" value={f.lecturer} onChange={set("lecturer")} placeholder="Prof. Dr. …" />
      </Field>
      <Field label="Gültig ab (optional)">
        <input type="date" className="input" value={f.valid_from || ""} onChange={set("valid_from")} />
      </Field>
      <Field label="Gültig bis (optional)">
        <input type="date" className="input" value={f.valid_until || ""} onChange={set("valid_until")} />
      </Field>
      <div className="col-span-2 flex justify-end gap-2 pt-2">
        <button type="button" className="btn" onClick={onCancel}>
          Abbrechen
        </button>
        <button className="btn btn-primary">Speichern</button>
      </div>
    </form>
  );
}

export default function Stundenplan() {
  const { data, error, loading, reload } = useApi("/timetable");
  const { data: subjects } = useApi("/study/subjects");
  const [editing, setEditing] = useState(null);
  const [semOpen, setSemOpen] = useState(false);
  const [sem, setSem] = useState(null);
  const toast = useToast();

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;

  const entries = data.entries;
  const showWeekend = entries.some((e) => e.weekday >= 5);
  const dayCount = showWeekend ? 7 : 5;
  const todayIdx = (new Date().getDay() + 6) % 7;
  const freeByDay = data.free_slots.filter((s) => s.weekday < dayCount);
  const freeMinutes = freeByDay.reduce((a, s) => a + s.minutes, 0);

  async function save(payload) {
    try {
      if (editing.id) await api.patch(`/timetable/entries/${editing.id}`, payload);
      else await api.post("/timetable/entries", payload);
      toast("Stundenplan gespeichert – Lernplan wurde angepasst.", "success");
      setEditing(null);
      reload();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function remove(entry) {
    await api.del(`/timetable/entries/${entry.id}`);
    setEditing(null);
    reload();
  }

  async function saveSemester(e) {
    e.preventDefault();
    try {
      await api.put("/timetable/semester", { name: sem.name, start: sem.start || null, end: sem.end || null });
      setSemOpen(false);
      reload();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  return (
    <div>
      <PageHeader
        title="Stundenplan"
        icon="🎓"
        subtitle={
          data.semester?.start
            ? `${data.semester.name}: ${dateLong(data.semester.start)} – ${dateLong(data.semester.end)}${data.semester_week > 0 ? ` · Semesterwoche ${data.semester_week}` : ""}`
            : "Lege den Semesterzeitraum fest, damit sich die Termine wöchentlich wiederholen."
        }
        actions={
          <>
            <button
              className="btn"
              onClick={() => {
                setSem({ name: data.semester?.name || "Wintersemester", start: data.semester?.start || "", end: data.semester?.end || "" });
                setSemOpen(true);
              }}
            >
              🗓️ Semester
            </button>
            <button className="btn btn-primary" onClick={() => setEditing({ ...EMPTY })}>
              + Veranstaltung
            </button>
          </>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <Card className="col-span-12">
          <div className="grid grid-cols-2 gap-5 md:grid-cols-4">
            <Stat label="Veranstaltungen" value={entries.length} />
            <Stat label="Präsenzzeit / Woche" value={`${String(data.hours_per_week).replace(".", ",")} h`} />
            <Stat label="Freie Lernfenster" value={minutesText(freeMinutes)} sub={`zwischen ${data.study_window.day_start} und ${data.study_window.day_end} (Mo–${showWeekend ? "So" : "Fr"})`} />
            <Stat label="Semesterwoche" value={data.semester_week > 0 ? data.semester_week : "–"} />
          </div>
        </Card>

        <Card title="Wochenansicht" className="col-span-12" actions={<span className="text-xs text-ink-3">Gestrichelt = freies Zeitfenster · Doppelklick = neue Veranstaltung</span>}>
          <WeekGrid
            days={Array.from({ length: dayCount }, (_, i) => ({ key: i, index: i, label: WD[i], isToday: i === todayIdx }))}
            items={entries.map((e) => ({ ...e, day: e.weekday, start: e.start_time, end: e.end_time }))}
            startHour={8}
            endHour={21}
            nowLine
            onSlotClick={(d, time) => {
              const [h, m] = time.split(":").map(Number);
              setEditing({ ...EMPTY, weekday: d.index, start_time: time, end_time: `${String(Math.min(h + 2, 23)).padStart(2, "0")}:${String(m).padStart(2, "0")}` });
            }}
            background={(d, toY) =>
              freeByDay
                .filter((s) => s.weekday === d.index)
                .map((s) => (
                  <div
                    key={`${s.start_time}`}
                    className="absolute inset-x-1 flex items-center justify-center rounded-md border border-dashed border-accent/25 text-[0.62rem] text-accent/60"
                    style={{ top: toY(s.start_time) + 2, height: toY(s.end_time) - toY(s.start_time) - 4 }}
                  >
                    frei · {minutesText(s.minutes)}
                  </div>
                ))
            }
            itemStyle={(e) => ({
              background: `${e.subject_color || "#22d3ee"}26`,
              borderLeft: `3px solid ${e.subject_color || "#22d3ee"}`,
              boxShadow: `0 0 10px ${e.subject_color || "#22d3ee"}22`,
              cursor: "pointer",
            })}
            renderItem={(e) => (
              <div className="h-full" onClick={() => setEditing({ ...e, subject_id: e.subject_id ?? "", valid_from: e.valid_from || "", valid_until: e.valid_until || "" })}>
                <div className="truncate font-semibold">{e.title}</div>
                <div className="truncate text-[0.62rem] text-ink-2">
                  {e.kind}
                  {e.interval_weeks > 1 ? " · 14-tägig" : ""}
                </div>
                <div className="truncate text-[0.62rem] text-ink-3">
                  {e.start_time}–{e.end_time} · {e.room}
                </div>
                <div className="truncate text-[0.62rem] text-ink-3">{e.lecturer}</div>
              </div>
            )}
          />
        </Card>

        <Card title="Alle Veranstaltungen" className="col-span-12">
          {entries.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Tag</th>
                  <th>Zeit</th>
                  <th>Veranstaltung</th>
                  <th>Art</th>
                  <th>Raum</th>
                  <th>Dozent/in</th>
                  <th>Rhythmus</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id}>
                    <td>{WD[e.weekday]}</td>
                    <td className="tabular-nums">
                      {e.start_time}–{e.end_time}
                    </td>
                    <td>
                      <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full" style={{ background: e.subject_color || "#22d3ee" }} />
                      {e.title}
                      {e.subject && e.subject !== e.title && <span className="text-xs text-ink-3"> · {e.subject}</span>}
                    </td>
                    <td>{e.kind}</td>
                    <td>{e.room || "–"}</td>
                    <td>{e.lecturer || "–"}</td>
                    <td>{e.interval_weeks > 1 ? "14-tägig" : "wöchentlich"}</td>
                    <td className="text-right">
                      <button className="btn btn-sm" onClick={() => setEditing({ ...e, subject_id: e.subject_id ?? "", valid_from: e.valid_from || "", valid_until: e.valid_until || "" })}>
                        Bearbeiten
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty icon="🎓">Noch keine Veranstaltungen. Füge deine Vorlesungen und Übungen hinzu.</Empty>
          )}
        </Card>
      </div>

      <Modal open={Boolean(editing)} title={editing?.id ? "Veranstaltung bearbeiten" : "Neue Veranstaltung"} onClose={() => setEditing(null)}>
        {editing && (
          <>
            <EntryForm initial={editing} subjects={subjects || []} onSave={save} onCancel={() => setEditing(null)} />
            {editing.id && (
              <div className="mt-3 border-t border-line pt-3">
                <ConfirmButton onConfirm={() => remove(editing)}>Veranstaltung löschen</ConfirmButton>
              </div>
            )}
          </>
        )}
      </Modal>

      <Modal open={semOpen} title="Semesterzeitraum" onClose={() => setSemOpen(false)}>
        {sem && (
          <form onSubmit={saveSemester} className="grid grid-cols-2 gap-3">
            <Field label="Bezeichnung" className="col-span-2">
              <input className="input" value={sem.name} onChange={(e) => setSem({ ...sem, name: e.target.value })} />
            </Field>
            <Field label="Vorlesungsbeginn">
              <input type="date" className="input" value={sem.start} onChange={(e) => setSem({ ...sem, start: e.target.value })} />
            </Field>
            <Field label="Vorlesungsende">
              <input type="date" className="input" value={sem.end} onChange={(e) => setSem({ ...sem, end: e.target.value })} />
            </Field>
            <p className="col-span-2 text-xs text-ink-3">Veranstaltungen wiederholen sich jede Woche (bzw. alle 2 Wochen) innerhalb dieses Zeitraums.</p>
            <div className="col-span-2 flex justify-end">
              <button className="btn btn-primary">Speichern</button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
