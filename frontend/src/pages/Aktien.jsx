import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartTooltip, axisProps, gridProps } from "../components/charts";
import { Card, ConfirmButton, Empty, ErrorBox, Field, Loading, Modal, PageHeader, ProgressBar, Segmented, Stat, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { C } from "../lib/colors";
import { dateShort, dateTimeText, dayLabel, euro, money, num, pct } from "../lib/format";

function Spark({ values, up }) {
  if (!values?.length) return <span className="text-xs text-ink-3">–</span>;
  const data = values.map((v, i) => ({ i, v }));
  return (
    <div className="h-7 w-24">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Line dataKey="v" stroke={up ? "#34d399" : "#f87171"} strokeWidth={1.5} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function Change({ value }) {
  if (value === null || value === undefined) return <span className="text-ink-3">–</span>;
  return <span className={value >= 0 ? "text-emerald-400" : "text-red-400"}>{pct(value, 2, true)}</span>;
}

function StockChart({ position }) {
  const [period, setPeriod] = useState("6m");
  const { data } = useApi(`/stocks/history/${encodeURIComponent(position.symbol)}?period=${period}`, [position.symbol]);
  const pts = data?.points || [];
  const first = pts[0]?.close;
  const last = pts[pts.length - 1]?.close;
  const perf = first && last ? (last / first - 1) * 100 : null;
  return (
    <Card
      title={`${position.name} · ${position.symbol}`}
      actions={<Segmented size="sm" value={period} onChange={setPeriod} options={["1m", "3m", "6m", "1j"].map((p) => ({ value: p, label: p.toUpperCase() }))} />}
    >
      <div className="mb-2 flex items-baseline gap-4 text-sm">
        <span className="text-2xl font-semibold">{money(position.price, position.price_currency)}</span>
        <span>
          Zeitraum: <Change value={perf} />
        </span>
        {position.buy_price && <span className="text-ink-3">Kaufkurs {money(position.buy_price, position.currency)}</span>}
      </div>
      {pts.length ? (
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={pts} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="stockFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={C.accent} stopOpacity={0.25} />
                <stop offset="100%" stopColor={C.accent} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={36} />
            <YAxis {...axisProps} domain={["auto", "auto"]} tickFormatter={(v) => num(v, v < 10 ? 2 : 0)} width={52} />
            <Tooltip content={<ChartTooltip labelFormatter={dayLabel} valueFormatter={(v) => money(v, data.currency || position.price_currency)} />} />
            {position.buy_price && <ReferenceLine y={position.buy_price} stroke={C.orange} strokeDasharray="5 4" label={{ value: "Kaufkurs", fill: C.orange, fontSize: 11, position: "insideBottomLeft" }} />}
            <Area dataKey="close" name="Schlusskurs" stroke={C.accent} strokeWidth={2} fill="url(#stockFill)" />
          </AreaChart>
        </ResponsiveContainer>
      ) : (
        <Empty icon="📈">Noch kein Kursverlauf – „Kurse aktualisieren“ klicken.</Empty>
      )}
    </Card>
  );
}

const EMPTY = { symbol: "", name: "", kind: "depot", quantity: "", buy_price: "", buy_date: "", currency: "EUR", notes: "" };

export default function Aktien() {
  const { data, error, loading, reload } = useApi("/stocks");
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(null);
  const toast = useToast();

  useEffect(() => {
    if (data && !selected && data.positions.length) setSelected(data.positions[0].symbol);
  }, [data, selected]);

  useEffect(() => {
    if (!data?.status?.running) return undefined;
    const t = setTimeout(reload, 3000);
    return () => clearTimeout(t);
  }, [data, reload]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;

  const depot = data.positions.filter((p) => p.kind === "depot");
  const watch = data.positions.filter((p) => p.kind === "watchlist");
  const sel = data.positions.find((p) => p.symbol === selected);
  const t = data.totals;

  async function refresh() {
    await api.post("/stocks/refresh");
    toast("Kurse werden aktualisiert …");
    setTimeout(reload, 2500);
  }

  async function save(e) {
    e.preventDefault();
    const payload = {
      symbol: form.symbol,
      name: form.name,
      kind: form.kind,
      quantity: Number(String(form.quantity).replace(",", ".")) || 0,
      buy_price: form.buy_price === "" ? null : Number(String(form.buy_price).replace(",", ".")),
      buy_date: form.buy_date || null,
      currency: form.currency,
      notes: form.notes,
    };
    try {
      if (form.id) await api.patch(`/stocks/positions/${form.id}`, payload);
      else await api.post("/stocks/positions", payload);
      setForm(null);
      toast("Gespeichert – Kurse werden geladen.", "success");
      setTimeout(reload, 2500);
      reload();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const lastUpdate = data.positions.map((p) => p.updated_at).filter(Boolean).sort().pop();

  return (
    <div>
      <PageHeader
        title="Aktien"
        icon="📈"
        subtitle={
          data.status.running
            ? "Kurse werden geladen …"
            : data.demo_prices
              ? "Beispielkurse – klicke „Kurse aktualisieren“ für echte Daten (yfinance)"
              : lastUpdate
                ? `Kurse von ${dateTimeText(lastUpdate)} (Yahoo Finance, verzögert)`
                : "Depot und Watchlist"
        }
        actions={
          <>
            <button className="btn" onClick={refresh} disabled={data.status.running}>
              {data.status.running ? <span className="spin inline-block h-3 w-3 rounded-full border-2 border-accent border-t-transparent" /> : "⟳"} Kurse aktualisieren
            </button>
            <button className="btn btn-primary" onClick={() => setForm({ ...EMPTY })}>
              + Position
            </button>
          </>
        }
      />
      {data.status.last_error && <div className="mb-5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-100">⚠ {data.status.last_error}</div>}

      <div className="grid grid-cols-12 gap-5">
        <Card className="col-span-12">
          <div className="grid grid-cols-2 gap-5 md:grid-cols-5">
            <Stat label="Depotwert" value={euro(t.value)} big />
            <Stat label="Investiert" value={euro(t.invested)} />
            <Stat label="Gewinn / Verlust" value={euro(t.pl)} color={t.pl >= 0 ? "#34d399" : "#f87171"} sub={t.pl_pct !== null ? pct(t.pl_pct, 2, true) : null} />
            <Stat label="Heute" value={euro(t.day_change)} color={t.day_change >= 0 ? "#34d399" : "#f87171"} />
            <Stat label="Positionen" value={`${depot.length} Depot · ${watch.length} Watchlist`} />
          </div>
        </Card>

        <Card title="Depotwert · 12 Monate" className="col-span-12 xl:col-span-7">
          {data.value_history.length ? (
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={data.value_history} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="depotFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={C.accent} stopOpacity={0.25} />
                    <stop offset="100%" stopColor={C.accent} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="date" {...axisProps} tickFormatter={dateShort} minTickGap={40} />
                <YAxis {...axisProps} domain={["auto", "auto"]} tickFormatter={(v) => `${num(v / 1000, 1)}k`} width={44} />
                <Tooltip content={<ChartTooltip labelFormatter={dayLabel} valueFormatter={(v) => euro(v)} />} />
                {t.invested > 0 && <ReferenceLine y={t.invested} stroke={C.orange} strokeDasharray="5 4" label={{ value: "Investiert", fill: C.orange, fontSize: 11, position: "insideBottomRight" }} />}
                <Area dataKey="value" name="Depotwert" stroke={C.accent} strokeWidth={2} fill="url(#depotFill)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <Empty icon="📈">Noch kein Verlauf.</Empty>
          )}
          <p className="mt-1 text-xs text-ink-3">Mit heutigen Stückzahlen zurückgerechnet (ohne Käufe/Verkäufe im Zeitraum).</p>
        </Card>

        <Card title="Aufteilung" className="col-span-12 xl:col-span-5">
          {data.allocation.length ? (
            <div className="space-y-3">
              {data.allocation.map((a) => (
                <div key={a.symbol}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-ink-2">{a.name}</span>
                    <span>
                      {euro(a.value_eur, 0)} <span className="text-ink-3">· {num(a.share, 1)} %</span>
                    </span>
                  </div>
                  <ProgressBar value={a.share} color={C.orange} height={7} glow={false} label={a.name} />
                </div>
              ))}
            </div>
          ) : (
            <Empty icon="🥧">Noch keine Depotpositionen.</Empty>
          )}
        </Card>

        <Card title="Depot" className="col-span-12">
          {depot.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Wertpapier</th>
                  <th className="text-right">Stück</th>
                  <th className="text-right">Kaufkurs</th>
                  <th className="text-right">Kurs</th>
                  <th className="text-right">Heute</th>
                  <th className="text-right">Wert</th>
                  <th className="text-right">G/V</th>
                  <th>30 Tage</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {depot.map((p) => (
                  <tr key={p.id} className={`cursor-pointer ${selected === p.symbol ? "bg-accent/5" : ""}`} onClick={() => setSelected(p.symbol)}>
                    <td>
                      <div className="font-medium">{p.name}</div>
                      <div className="text-xs text-ink-3">{p.symbol}</div>
                    </td>
                    <td className="text-right tabular-nums">{num(p.quantity, p.quantity % 1 ? 2 : 0)}</td>
                    <td className="text-right tabular-nums">{money(p.buy_price, p.currency)}</td>
                    <td className="text-right tabular-nums">{money(p.price, p.price_currency)}</td>
                    <td className="text-right tabular-nums">
                      <Change value={p.change_pct} />
                    </td>
                    <td className="text-right tabular-nums">
                      {money(p.value, p.price_currency)}
                      {p.price_currency !== "EUR" && p.value_eur !== null && <div className="text-xs text-ink-3">{euro(p.value_eur)}</div>}
                    </td>
                    <td className="text-right tabular-nums">
                      <div className={p.pl >= 0 ? "text-emerald-400" : "text-red-400"}>{money(p.pl, p.price_currency)}</div>
                      <div className="text-xs">
                        <Change value={p.pl_pct} />
                      </div>
                    </td>
                    <td>
                      <Spark values={p.spark} up={p.spark.length > 1 && p.spark[p.spark.length - 1] >= p.spark[0]} />
                    </td>
                    <td className="text-right" onClick={(e) => e.stopPropagation()}>
                      <button className="btn btn-sm mr-1" onClick={() => setForm({ ...p, buy_price: p.buy_price ?? "", buy_date: p.buy_date || "" })}>
                        ✎
                      </button>
                      <ConfirmButton onConfirm={() => api.del(`/stocks/positions/${p.id}`).then(reload)} question="?">
                        ✕
                      </ConfirmButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty icon="💼">Noch keine Depotpositionen – füge deine erste hinzu.</Empty>
          )}
        </Card>

        <div className="col-span-12 xl:col-span-7">{sel && <StockChart key={sel.symbol} position={sel} />}</div>

        <Card title="Watchlist" className="col-span-12 xl:col-span-5">
          {watch.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Wertpapier</th>
                  <th className="text-right">Kurs</th>
                  <th className="text-right">Heute</th>
                  <th>30 Tage</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {watch.map((p) => (
                  <tr key={p.id} className={`cursor-pointer ${selected === p.symbol ? "bg-accent/5" : ""}`} onClick={() => setSelected(p.symbol)}>
                    <td>
                      <div className="font-medium">{p.name}</div>
                      <div className="text-xs text-ink-3">{p.symbol}</div>
                    </td>
                    <td className="text-right tabular-nums">{money(p.price, p.price_currency)}</td>
                    <td className="text-right">
                      <Change value={p.change_pct} />
                    </td>
                    <td>
                      <Spark values={p.spark} up={p.spark.length > 1 && p.spark[p.spark.length - 1] >= p.spark[0]} />
                    </td>
                    <td className="text-right" onClick={(e) => e.stopPropagation()}>
                      <ConfirmButton onConfirm={() => api.del(`/stocks/positions/${p.id}`).then(reload)} question="?">
                        ✕
                      </ConfirmButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty icon="👀">Watchlist ist leer.</Empty>
          )}
        </Card>
      </div>

      <Modal open={Boolean(form)} title={form?.id ? "Position bearbeiten" : "Neue Position"} onClose={() => setForm(null)}>
        {form && (
          <form onSubmit={save} className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Segmented value={form.kind} onChange={(k) => setForm({ ...form, kind: k })} options={[{ value: "depot", label: "Depot" }, { value: "watchlist", label: "Watchlist" }]} />
            </div>
            <Field label="Symbol (Yahoo)">
              <input className="input uppercase" value={form.symbol} onChange={set("symbol")} required disabled={Boolean(form.id)} placeholder="SAP.DE, AAPL, EUNL.DE" />
            </Field>
            <Field label="Name (optional)">
              <input className="input" value={form.name} onChange={set("name")} placeholder="wird sonst automatisch ermittelt" />
            </Field>
            {form.kind === "depot" && (
              <>
                <Field label="Stückzahl">
                  <input className="input" inputMode="decimal" value={form.quantity} onChange={set("quantity")} required />
                </Field>
                <Field label="Kaufkurs pro Stück">
                  <input className="input" inputMode="decimal" value={form.buy_price} onChange={set("buy_price")} />
                </Field>
                <Field label="Kaufdatum">
                  <input type="date" className="input" value={form.buy_date} onChange={set("buy_date")} />
                </Field>
              </>
            )}
            <Field label="Währung">
              <select className="input" value={form.currency} onChange={set("currency")}>
                {["EUR", "USD", "GBP", "CHF"].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </Field>
            <p className="col-span-2 text-xs text-ink-3">
              Tipp: Deutsche Börsenplätze mit Endung, z. B. <b>SAP.DE</b> (Xetra), ETFs wie <b>EUNL.DE</b>. US-Aktien ohne Endung, z. B. <b>AAPL</b>.
            </p>
            <div className="col-span-2 flex justify-end gap-2">
              <button type="button" className="btn" onClick={() => setForm(null)}>
                Abbrechen
              </button>
              <button className="btn btn-primary">Speichern</button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
