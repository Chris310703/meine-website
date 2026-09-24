import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import WeekGrid from "../components/WeekGrid";
import { Card, ErrorBox, Loading, Modal, PageHeader, Segmented, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { TYPE_STYLE } from "../lib/colors";
import { addDays, dateLong, isoDate, monthName, startOfWeek, timeText, todayIso, toDate, weekdayLong } from "../lib/format";

const WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

function hhmm(value) {
  const d = toDate(value);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function itemStyle(it) {
  const st = TYPE_STYLE[it.type] || TYPE_STYLE.google;
  const faded = it.status === "verpasst";
  return {
    background: `${st.color}${faded ? "14" : "26"}`,
    borderLeft: `3px solid ${st.color}`,
    color: "#e6edf3",
    opacity: faded ? 0.55 : 1,
    textDecoration: faded ? "line-through" : undefined,
    cursor: "pointer",
  };
}

export default function Kalender() {
  const [view, setView] = useState("woche");
  const [anchor, setAnchor] = useState(todayIso());
  const [hidden, setHidden] = useState(new Set());
  const [selected, setSelected] = useState(null);
  const toast = useToast();

  const range = useMemo(() => {
    if (view === "woche") {
      const s = startOfWeek(anchor);
      return { start: s, end: addDays(s, 6) };
    }
    const a = toDate(anchor);
    const first = new Date(a.getFullYear(), a.getMonth(), 1);
    const s = startOfWeek(first);
    return { start: s, end: addDays(s, 41), month: a.getMonth(), year: a.getFullYear() };
  }, [view, anchor]);

  const { data, error, loading, reload } = useApi(`/calendar?start=${isoDate(range.start)}&end=${isoDate(range.end)}`);

  function shift(dir) {
    const a = toDate(anchor);
    if (view === "woche") setAnchor(isoDate(addDays(a, dir * 7)));
    else setAnchor(isoDate(new Date(a.getFullYear(), a.getMonth() + dir, 1)));
  }

  function toggleType(t) {
    const next = new Set(hidden);
    if (next.has(t)) next.delete(t);
    else next.add(t);
    setHidden(next);
  }

  async function googleSync() {
    try {
      await api.post("/google/sync");
      toast("Google-Synchronisation gestartet …");
      setTimeout(reload, 4000);
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function setBlockStatus(it, status) {
    try {
      await api.post(`/study/blocks/${it.source_id}/status`, { status });
      toast(status === "erledigt" ? "Lernblock erledigt ✓" : "Als verpasst markiert – wird neu eingeplant.", "success");
      setSelected(null);
      reload();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function toggleWorkout(it) {
    await api.patch(`/fitness/planned/${it.source_id}`, { done: it.status !== "erledigt" });
    setSelected(null);
    reload();
  }

  const items = (data?.items || []).filter((it) => !hidden.has(it.type));
  const today = todayIso();

  const title =
    view === "woche"
      ? `KW ${isoWeek(range.start)} · ${dateLong(range.start).slice(0, 6)} – ${dateLong(range.end)}`
      : `${monthName(range.month)} ${range.year}`;

  return (
    <div>
      <PageHeader
        title="Kalender"
        icon="📅"
        subtitle="Google-Termine, Stundenplan, Lernblöcke, Trainings und Prüfungen"
        actions={
          <>
            <Segmented value={view} onChange={setView} options={[{ value: "woche", label: "Woche" }, { value: "monat", label: "Monat" }]} />
            {data?.google_connected ? (
              <button className="btn" onClick={googleSync}>
                ⟳ Google
              </button>
            ) : (
              <Link to="/einstellungen" className="btn">
                Google verbinden
              </Link>
            )}
          </>
        }
      />

      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <button className="btn btn-sm" onClick={() => shift(-1)} aria-label="Zurück">
              ‹
            </button>
            <button className="btn btn-sm" onClick={() => setAnchor(todayIso())}>
              Heute
            </button>
            <button className="btn btn-sm" onClick={() => shift(1)} aria-label="Weiter">
              ›
            </button>
            <span className="font-display ml-2 text-sm font-bold text-ink">{title}</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(TYPE_STYLE).map(([key, st]) => (
              <button
                key={key}
                onClick={() => toggleType(key)}
                className="chip transition"
                style={hidden.has(key) ? { opacity: 0.4 } : { borderColor: `${st.color}88`, color: "#e6edf3", background: `${st.color}1f` }}
                aria-pressed={!hidden.has(key)}
              >
                <span className="h-2 w-2 rounded-full" style={{ background: st.color }} />
                {st.icon} {st.label}
              </button>
            ))}
          </div>
        </div>

        {error && <ErrorBox error={error} onRetry={reload} />}
        {loading && !data ? (
          <Loading />
        ) : view === "woche" ? (
          <WeekGrid
            days={[0, 1, 2, 3, 4, 5, 6].map((i) => {
              const d = addDays(range.start, i);
              return { key: i, index: i, label: WD[i], sub: `${d.getDate()}.${d.getMonth() + 1}.`, isToday: isoDate(d) === today, date: isoDate(d) };
            })}
            items={items
              .filter((it) => !it.all_day)
              .flatMap((it) => {
                const d = Math.round((toDate(isoDate(it.start)) - range.start) / 86400000);
                if (d < 0 || d > 6) return [];
                const endSameDay = isoDate(it.end) === isoDate(it.start);
                return [{ ...it, day: d, start: hhmm(it.start), end: endSameDay ? hhmm(it.end) : "23:59", raw: it }];
              })}
            startHour={7}
            endHour={23}
            itemStyle={itemStyle}
            allDay={(d) =>
              items
                .filter((it) => it.all_day && isoDate(it.start) <= d.date && d.date < isoDate(it.end === it.start ? addDays(it.end, 1) : it.end))
                .map((it) => (
                  <div key={it.id} className="truncate rounded px-1 text-[0.65rem]" style={itemStyle(it)} onClick={() => setSelected(it)}>
                    {TYPE_STYLE[it.type]?.icon} {it.title}
                  </div>
                ))
            }
            renderItem={(it) => (
              <div onClick={() => setSelected(it.raw)} className="h-full">
                <div className="truncate font-semibold">
                  {TYPE_STYLE[it.type]?.icon} {it.title}
                </div>
                <div className="truncate text-[0.62rem] text-ink-2">
                  {it.start}–{it.end}
                  {it.raw.location ? ` · ${it.raw.location}` : ""}
                </div>
              </div>
            )}
          />
        ) : (
          <MonthView range={range} items={items} today={today} onSelect={setSelected} />
        )}
      </Card>

      <Modal open={Boolean(selected)} title={selected ? TYPE_STYLE[selected.type]?.label : ""} onClose={() => setSelected(null)}>
        {selected && (
          <div className="space-y-3 text-sm">
            <div className="text-lg font-semibold">
              {TYPE_STYLE[selected.type]?.icon} {selected.title}
            </div>
            <div className="text-ink-2">
              {weekdayLong(selected.start)}, {dateLong(selected.start)}
              {selected.all_day ? " · ganztägig" : ` · ${timeText(selected.start)}–${timeText(selected.end)}`}
            </div>
            {selected.subtitle && <div className="text-ink-2">{selected.subtitle}</div>}
            {selected.location && <div className="text-ink-2">📍 {selected.location}</div>}
            {selected.status && <div className="text-ink-3">Status: {selected.status}</div>}
            {selected.type === "lernblock" && (
              <div className="flex gap-2 pt-2">
                <button className="btn btn-primary" onClick={() => setBlockStatus(selected, "erledigt")}>
                  ✓ Erledigt
                </button>
                <button className="btn" onClick={() => setBlockStatus(selected, "verpasst")}>
                  ✗ Verpasst – neu einplanen
                </button>
                <Link className="btn" to="/lernplan">
                  Lernplan
                </Link>
              </div>
            )}
            {selected.type === "training" && selected.id.startsWith("pw-") && (
              <button className="btn btn-primary" onClick={() => toggleWorkout(selected)}>
                {selected.status === "erledigt" ? "Als offen markieren" : "✓ Training erledigt"}
              </button>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}

function isoWeek(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
}

function MonthView({ range, items, today, onSelect }) {
  const cells = [];
  for (let i = 0; i < 42; i++) cells.push(addDays(range.start, i));
  const byDay = {};
  items.forEach((it) => {
    const s = toDate(isoDate(it.start));
    const e = it.all_day ? addDays(toDate(isoDate(it.end)), -1) : s;
    for (let d = s; d <= e; d = addDays(d, 1)) {
      const k = isoDate(d);
      (byDay[k] ||= []).push(it);
    }
  });
  return (
    <div>
      <div className="grid grid-cols-7 gap-px text-center">
        {WD.map((w) => (
          <div key={w} className="font-display pb-2 text-[0.65rem] font-bold text-ink-2">
            {w}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1.5">
        {cells.map((d) => {
          const k = isoDate(d);
          const list = byDay[k] || [];
          const inMonth = d.getMonth() === range.month;
          const isToday = k === today;
          return (
            <div
              key={k}
              className={`min-h-[112px] rounded-lg border p-1.5 ${isToday ? "border-accent/70 shadow-[0_0_10px_rgba(34,211,238,0.25)]" : "border-line/70"} ${inMonth ? "bg-[#0a1118]" : "bg-transparent opacity-45"}`}
            >
              <div className={`mb-1 text-right text-xs ${isToday ? "font-bold text-accent" : "text-ink-3"}`}>{d.getDate()}</div>
              <div className="space-y-0.5">
                {list.slice(0, 4).map((it) => (
                  <button key={it.id} onClick={() => onSelect(it)} className="block w-full truncate rounded px-1 py-px text-left text-[0.65rem]" style={itemStyle(it)} title={it.title}>
                    {!it.all_day && <span className="text-ink-3">{timeText(it.start)} </span>}
                    {TYPE_STYLE[it.type]?.icon} {it.title}
                  </button>
                ))}
                {list.length > 4 && <div className="px-1 text-[0.62rem] text-ink-3">+{list.length - 4} weitere</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
