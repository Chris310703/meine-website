import { useMemo, useState } from "react";
import { Card, ConfirmButton, Empty, ErrorBox, Field, Loading, Modal, PageHeader, PriorityBadge, Segmented, Stat, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { addDays, dateLong, isoDate, relativeDay, todayIso } from "../lib/format";

function groupOf(t, today, weekEnd) {
  if (t.done) return "Erledigt";
  if (!t.due_date) return "Ohne Datum";
  if (t.due_date < today) return "Überfällig";
  if (t.due_date === today) return "Heute";
  if (t.due_date <= weekEnd) return "Diese Woche";
  return "Später";
}
const GROUP_ORDER = ["Überfällig", "Heute", "Diese Woche", "Später", "Ohne Datum", "Erledigt"];

function TodoForm({ initial, categories, subjects, onSave, onCancel, compact = false }) {
  const [f, setF] = useState(initial);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  function submit(e) {
    e.preventDefault();
    onSave({
      title: f.title,
      notes: f.notes || "",
      priority: f.priority,
      due_date: f.due_date || null,
      category: f.category || "",
      subject_id: f.subject_id ? Number(f.subject_id) : null,
    });
    if (compact) setF({ ...initial });
  }
  return (
    <form onSubmit={submit} className={compact ? "grid grid-cols-12 items-end gap-2" : "grid grid-cols-2 gap-3"}>
      <Field label="Aufgabe" className={compact ? "col-span-12 lg:col-span-4" : "col-span-2"}>
        <input className="input" value={f.title} onChange={set("title")} required placeholder="Was ist zu tun?" />
      </Field>
      <Field label="Priorität" className={compact ? "col-span-4 lg:col-span-2" : ""}>
        <select className="input" value={f.priority} onChange={set("priority")}>
          <option value="hoch">Hoch</option>
          <option value="mittel">Mittel</option>
          <option value="niedrig">Niedrig</option>
        </select>
      </Field>
      <Field label="Fällig" className={compact ? "col-span-4 lg:col-span-2" : ""}>
        <input type="date" className="input" value={f.due_date || ""} onChange={set("due_date")} />
      </Field>
      <Field label="Kategorie" className={compact ? "col-span-4 lg:col-span-1" : ""}>
        <select className="input" value={f.category} onChange={set("category")}>
          <option value="">–</option>
          {categories.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </Field>
      <Field label="Fach" className={compact ? "col-span-8 lg:col-span-2" : ""}>
        <select className="input" value={f.subject_id ?? ""} onChange={set("subject_id")}>
          <option value="">–</option>
          {subjects.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </Field>
      {!compact && (
        <Field label="Notizen" className="col-span-2">
          <textarea className="input" rows={3} value={f.notes || ""} onChange={set("notes")} />
        </Field>
      )}
      <div className={compact ? "col-span-4 lg:col-span-1" : "col-span-2 flex justify-end gap-2"}>
        {!compact && (
          <button type="button" className="btn" onClick={onCancel}>
            Abbrechen
          </button>
        )}
        <button className="btn btn-primary w-full">{compact ? "+" : "Speichern"}</button>
      </div>
    </form>
  );
}

export default function Todos() {
  const [status, setStatus] = useState("offen");
  const { data, error, loading, reload } = useApi(`/todos?status=${status}`);
  const [filter, setFilter] = useState("alle");
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState(null);
  const toast = useToast();

  const today = todayIso();
  const weekEnd = isoDate(addDays(today, 7 - ((new Date().getDay() + 6) % 7) - 1));

  const grouped = useMemo(() => {
    if (!data) return {};
    const g = {};
    data.todos
      .filter((t) => filter === "alle" || t.category === filter || String(t.subject_id) === filter)
      .filter((t) => !search.trim() || `${t.title} ${t.notes}`.toLowerCase().includes(search.toLowerCase()))
      .forEach((t) => {
        (g[groupOf(t, today, weekEnd)] ||= []).push(t);
      });
    return g;
  }, [data, filter, search, today, weekEnd]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;

  async function create(payload) {
    try {
      await api.post("/todos", payload);
      toast("Aufgabe angelegt.", "success");
      reload();
    } catch (e) {
      toast(e.message, "error");
    }
  }
  async function update(payload) {
    await api.patch(`/todos/${editing.id}`, payload);
    setEditing(null);
    reload();
  }
  async function toggle(t) {
    await api.patch(`/todos/${t.id}`, { done: !t.done });
    if (!t.done) toast(`✓ „${t.title}“ erledigt`, "success");
    reload();
  }

  const c = data.counts;
  const emptyForm = { title: "", notes: "", priority: "mittel", due_date: "", category: "", subject_id: "" };

  return (
    <div>
      <PageHeader
        title="To-dos"
        icon="📝"
        subtitle="Aufgaben mit Priorität, Fälligkeit und Fach bzw. Kategorie"
        actions={<Segmented value={status} onChange={setStatus} options={[{ value: "offen", label: "Offen" }, { value: "erledigt", label: "Erledigt" }, { value: "alle", label: "Alle" }]} />}
      />
      <div className="grid grid-cols-12 gap-5">
        <Card className="col-span-12">
          <div className="grid grid-cols-2 gap-5 md:grid-cols-5">
            <Stat label="Offen" value={c.offen} />
            <Stat label="Überfällig" value={c.ueberfaellig} color={c.ueberfaellig ? "#f87171" : undefined} />
            <Stat label="Heute fällig" value={c.heute} />
            <Stat label="Hohe Priorität" value={c.hoch} />
            <Stat label="Erledigt" value={c.erledigt} />
          </div>
        </Card>

        <Card title="Neue Aufgabe" className="col-span-12">
          <TodoForm initial={emptyForm} categories={data.categories} subjects={data.subjects} onSave={create} compact />
        </Card>

        <Card
          className="col-span-12"
          title="Aufgaben"
          actions={
            <input className="input w-56 py-1 text-sm" placeholder="Suchen …" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Aufgaben durchsuchen" />
          }
        >
          <div className="mb-4 flex flex-wrap gap-1.5">
            {[{ value: "alle", label: "Alle" }, ...data.categories.map((x) => ({ value: x, label: x })), ...data.subjects.map((s) => ({ value: String(s.id), label: `📚 ${s.short || s.name}` }))].map((o) => (
              <button
                key={o.value}
                className={`chip ${filter === o.value ? "!border-accent/70 !bg-accent/15 !text-accent" : "hover:text-ink"}`}
                onClick={() => setFilter(o.value)}
              >
                {o.label}
              </button>
            ))}
          </div>
          {GROUP_ORDER.filter((g) => grouped[g]?.length).map((g) => (
            <div key={g} className="mb-5">
              <div className={`font-display mb-2 text-[0.68rem] font-bold ${g === "Überfällig" ? "text-red-400" : g === "Heute" ? "text-accent" : "text-ink-3"}`}>
                {g} ({grouped[g].length})
              </div>
              <ul className="divide-y divide-line/60 rounded-lg border border-line/60">
                {grouped[g].map((t) => (
                  <li key={t.id} className="flex items-start gap-3 px-3 py-2.5">
                    <button
                      className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border text-xs ${t.done ? "border-accent bg-accent/20 text-accent" : "border-ink-3 hover:border-accent"}`}
                      onClick={() => toggle(t)}
                      aria-label={t.done ? "Wieder öffnen" : "Erledigen"}
                    >
                      {t.done ? "✓" : ""}
                    </button>
                    <div className="min-w-0 flex-1">
                      <div className={`text-sm font-medium ${t.done ? "text-ink-3 line-through" : ""}`}>{t.title}</div>
                      {t.notes && <div className="mt-0.5 text-xs text-ink-3">{t.notes}</div>}
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
                        {t.category && <span className="chip">{t.category}</span>}
                        {t.subject && (
                          <span className="chip" style={{ borderColor: `${t.subject_color}66`, color: t.subject_color }}>
                            📚 {t.subject_short || t.subject}
                          </span>
                        )}
                        {t.done && t.done_at && <span>erledigt {relativeDay(t.done_at)}</span>}
                      </div>
                    </div>
                    <PriorityBadge priority={t.priority} />
                    {t.due_date && (
                      <span className={`w-24 text-right text-xs ${t.overdue ? "font-semibold text-red-400" : "text-ink-2"}`} title={dateLong(t.due_date)}>
                        {relativeDay(t.due_date)}
                      </span>
                    )}
                    <button className="btn btn-sm" onClick={() => setEditing({ ...t, subject_id: t.subject_id ?? "", due_date: t.due_date || "" })} aria-label="Bearbeiten">
                      ✎
                    </button>
                    <ConfirmButton onConfirm={() => api.del(`/todos/${t.id}`).then(reload)} question="?">
                      ✕
                    </ConfirmButton>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {!Object.keys(grouped).length && <Empty icon="🎉">{status === "offen" ? "Keine offenen Aufgaben – stark!" : "Keine Aufgaben gefunden."}</Empty>}
        </Card>
      </div>

      <Modal open={Boolean(editing)} title="Aufgabe bearbeiten" onClose={() => setEditing(null)}>
        {editing && <TodoForm initial={editing} categories={data.categories} subjects={data.subjects} onSave={update} onCancel={() => setEditing(null)} />}
      </Modal>
    </div>
  );
}
