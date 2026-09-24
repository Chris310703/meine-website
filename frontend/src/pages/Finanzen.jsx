import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTooltip, Legend, axisProps, barRadius, gridProps } from "../components/charts";
import { Card, ConfirmButton, Empty, ErrorBox, Field, Loading, Modal, PageHeader, ProgressBar, Segmented, Stat, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { C } from "../lib/colors";
import { dateShort, euro, num, todayIso } from "../lib/format";

function shiftMonth(month, dir) {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + dir, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function TxForm({ initial, expenseCats, incomeCats, onSave, onCancel }) {
  const [f, setF] = useState(initial);
  const cats = f.kind === "einnahme" ? incomeCats : expenseCats;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <form
      className="grid grid-cols-2 gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({ date: f.date, amount: Number(String(f.amount).replace(",", ".")), kind: f.kind, category: f.category || cats[0] || "Sonstiges", description: f.description });
      }}
    >
      <div className="col-span-2">
        <Segmented value={f.kind} onChange={(k) => setF({ ...f, kind: k, category: "" })} options={[{ value: "ausgabe", label: "− Ausgabe" }, { value: "einnahme", label: "+ Einnahme" }]} />
      </div>
      <Field label="Betrag (€)">
        <input className="input" inputMode="decimal" value={f.amount} onChange={set("amount")} required placeholder="0,00" />
      </Field>
      <Field label="Datum">
        <input type="date" className="input" value={f.date} onChange={set("date")} required />
      </Field>
      <Field label="Kategorie">
        <select className="input" value={f.category || cats[0]} onChange={set("category")}>
          {cats.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </Field>
      <Field label="Beschreibung">
        <input className="input" value={f.description} onChange={set("description")} placeholder="z. B. REWE" />
      </Field>
      <div className="col-span-2 flex justify-end gap-2">
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            Abbrechen
          </button>
        )}
        <button className="btn btn-primary">Speichern</button>
      </div>
    </form>
  );
}

export default function Finanzen() {
  const [month, setMonth] = useState(todayIso().slice(0, 7));
  const { data, error, loading, reload } = useApi(`/finance?month=${month}`);
  const [editing, setEditing] = useState(null);
  const [budgetOpen, setBudgetOpen] = useState(false);
  const [budgets, setBudgets] = useState(null);
  const toast = useToast();

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  const s = data.summary;
  const usedPct = data.budget ? (s.expense / data.budget) * 100 : 0;

  async function save(payload) {
    try {
      if (editing?.id) await api.patch(`/finance/transactions/${editing.id}`, payload);
      else await api.post("/finance/transactions", payload);
      toast("Buchung gespeichert.", "success");
      setEditing(null);
      reload();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function saveBudgets(e) {
    e.preventDefault();
    const cats = Object.fromEntries(budgets.rows.filter((r) => r.name.trim()).map((r) => [r.name.trim(), Number(r.amount) || 0]));
    await api.put("/settings", { monthly_budget: Number(budgets.total) || 0, budget_categories: cats });
    setBudgetOpen(false);
    reload();
  }

  const newTx = { date: todayIso(), amount: "", kind: "ausgabe", category: "", description: "" };

  return (
    <div>
      <PageHeader
        title="Finanzen"
        icon="💶"
        subtitle={data.month_label}
        actions={
          <>
            <button className="btn" onClick={() => setMonth(shiftMonth(month, -1))}>
              ‹
            </button>
            <button className="btn" onClick={() => setMonth(todayIso().slice(0, 7))}>
              Aktueller Monat
            </button>
            <button className="btn" onClick={() => setMonth(shiftMonth(month, 1))}>
              ›
            </button>
            <button
              className="btn"
              onClick={() => {
                setBudgets({ total: data.budget, rows: data.categories.filter((c) => c.budget !== null && c.budget !== undefined).map((c) => ({ name: c.category, amount: c.budget })) });
                setBudgetOpen(true);
              }}
            >
              ⚙ Budget
            </button>
            <button className="btn btn-primary" onClick={() => setEditing(newTx)}>
              + Buchung
            </button>
          </>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <Card className="col-span-12">
          <div className="grid grid-cols-2 gap-5 md:grid-cols-5">
            <Stat label="Einnahmen" value={euro(s.income)} color="#34d399" />
            <Stat label="Ausgaben" value={euro(s.expense)} color="#fb923c" />
            <Stat label="Saldo" value={euro(s.saldo)} color={s.saldo >= 0 ? "#22d3ee" : "#f87171"} />
            <Stat label="Budget übrig" value={euro(data.budget_left)} color={data.budget_left >= 0 ? undefined : "#f87171"} sub={`von ${euro(data.budget, 0)} Monatsbudget`} />
            <Stat label="Ø Saldo / Monat" value={data.avg_saldo === null ? "–" : euro(data.avg_saldo)} sub="letzte 12 Monate" />
          </div>
          <div className="mt-4">
            <ProgressBar value={s.expense} max={data.budget} color={usedPct > 100 ? "#ef4444" : usedPct > 85 ? "#eab308" : C.orange} label="Budget" />
            <div className="mt-1 text-xs text-ink-3">{num(usedPct)} % des Monatsbudgets ausgegeben</div>
          </div>
        </Card>

        <Card title="Ausgaben nach Kategorie vs. Budget" className="col-span-12 xl:col-span-6">
          {data.categories.length ? (
            <div className="space-y-3">
              {data.categories.map((c) => (
                <div key={c.category}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-ink-2">
                      {c.category}
                      {c.over && <span className="ml-1.5 text-xs font-semibold text-red-400">⚠ über Budget</span>}
                    </span>
                    <span>
                      <b>{euro(c.spent)}</b>
                      <span className="text-ink-3"> {c.budget ? `/ ${euro(c.budget, 0)}` : "· kein Budget"}</span>
                    </span>
                  </div>
                  <ProgressBar value={c.spent} max={c.budget || c.spent || 1} color={c.over ? "#ef4444" : C.orange} height={7} glow={false} label={c.category} />
                </div>
              ))}
            </div>
          ) : (
            <Empty icon="💶">Keine Ausgaben in diesem Monat.</Empty>
          )}
        </Card>

        <Card title="Ausgabenverlauf im Monat" className="col-span-12 xl:col-span-6">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={data.cumulative} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="day" {...axisProps} tickFormatter={(d) => `${d}.`} />
              <YAxis {...axisProps} tickFormatter={(v) => `${num(v)} €`} width={62} />
              <Tooltip content={<ChartTooltip labelFormatter={(d) => `${d}. ${data.month_label}`} valueFormatter={(v) => euro(v)} />} />
              <ReferenceLine y={data.budget} stroke="#ef444488" strokeDasharray="4 4" label={{ value: "Budget", fill: "#f87171", fontSize: 11, position: "insideTopLeft" }} />
              <Line dataKey="budget_pace" name="Gleichmäßiges Budget" stroke={C.accent} strokeDasharray="6 4" strokeWidth={1.5} dot={false} />
              <Line dataKey="spent" name="Ausgegeben (kumuliert)" stroke={C.orange} strokeWidth={2.5} dot={false} connectNulls={false} />
            </LineChart>
          </ResponsiveContainer>
          <Legend items={[{ label: "Ausgegeben (kumuliert)", color: C.orange, line: true }, { label: "Gleichmäßig verteiltes Budget", color: C.accent, dashed: true, line: true }]} />
        </Card>

        <Card title="Übersicht 12 Monate" className="col-span-12 xl:col-span-7">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={data.months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="label" {...axisProps} interval={0} tick={{ ...axisProps.tick, fontSize: 10 }} />
              <YAxis {...axisProps} tickFormatter={(v) => `${num(v)} €`} width={62} />
              <Tooltip content={<ChartTooltip valueFormatter={(v) => euro(v)} />} />
              <Bar dataKey="income" name="Einnahmen" fill={C.cyan} radius={barRadius} maxBarSize={18} />
              <Bar dataKey="expense" name="Ausgaben" fill={C.orange} radius={barRadius} maxBarSize={18} />
            </BarChart>
          </ResponsiveContainer>
          <Legend items={[{ label: "Einnahmen", color: C.cyan }, { label: "Ausgaben", color: C.orange }]} />
        </Card>

        <Card title="Einnahmen nach Quelle" className="col-span-12 xl:col-span-5">
          {data.income_by_category.length ? (
            <ul className="space-y-2">
              {data.income_by_category.map((i) => (
                <li key={i.category} className="flex justify-between border-b border-line/50 pb-2 text-sm">
                  <span className="text-ink-2">{i.category}</span>
                  <b className="text-emerald-400">{euro(i.amount)}</b>
                </li>
              ))}
            </ul>
          ) : (
            <Empty icon="💰">Keine Einnahmen in diesem Monat.</Empty>
          )}
        </Card>

        <Card title={`Buchungen (${data.transactions.length})`} className="col-span-12">
          {data.transactions.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Datum</th>
                  <th>Beschreibung</th>
                  <th>Kategorie</th>
                  <th className="text-right">Betrag</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.transactions.map((t) => (
                  <tr key={t.id}>
                    <td className="text-ink-2">{dateShort(t.date)}</td>
                    <td>{t.description || "–"}</td>
                    <td>
                      <span className="chip">{t.category}</span>
                    </td>
                    <td className={`text-right font-semibold tabular-nums ${t.kind === "einnahme" ? "text-emerald-400" : ""}`}>
                      {t.kind === "einnahme" ? "+" : "−"}
                      {euro(t.amount)}
                    </td>
                    <td className="text-right">
                      <button className="btn btn-sm mr-1" onClick={() => setEditing({ ...t })}>
                        ✎
                      </button>
                      <ConfirmButton onConfirm={() => api.del(`/finance/transactions/${t.id}`).then(reload)} question="?">
                        ✕
                      </ConfirmButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty icon="🧾">Noch keine Buchungen in diesem Monat.</Empty>
          )}
        </Card>
      </div>

      <Modal open={Boolean(editing)} title={editing?.id ? "Buchung bearbeiten" : "Neue Buchung"} onClose={() => setEditing(null)}>
        {editing && <TxForm initial={editing} expenseCats={data.expense_categories} incomeCats={data.income_categories} onSave={save} onCancel={() => setEditing(null)} />}
      </Modal>

      <Modal open={budgetOpen} title="Monatsbudget" onClose={() => setBudgetOpen(false)}>
        {budgets && (
          <form onSubmit={saveBudgets} className="space-y-3">
            <Field label="Gesamtbudget pro Monat (€)">
              <input type="number" className="input" value={budgets.total} onChange={(e) => setBudgets({ ...budgets, total: e.target.value })} />
            </Field>
            <div className="label">Budgets je Kategorie</div>
            {budgets.rows.map((r, i) => (
              <div key={i} className="flex gap-2">
                <input className="input flex-1" value={r.name} onChange={(e) => setBudgets({ ...budgets, rows: budgets.rows.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })} />
                <input type="number" className="input w-28" value={r.amount} onChange={(e) => setBudgets({ ...budgets, rows: budgets.rows.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)) })} />
                <button type="button" className="btn btn-sm" onClick={() => setBudgets({ ...budgets, rows: budgets.rows.filter((_, j) => j !== i) })}>
                  ✕
                </button>
              </div>
            ))}
            <button type="button" className="btn btn-sm" onClick={() => setBudgets({ ...budgets, rows: [...budgets.rows, { name: "", amount: 0 }] })}>
              + Kategorie
            </button>
            <div className="text-xs text-ink-3">Summe der Kategorien: {euro(budgets.rows.reduce((a, r) => a + (Number(r.amount) || 0), 0), 0)}</div>
            <div className="flex justify-end">
              <button className="btn btn-primary">Speichern</button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
