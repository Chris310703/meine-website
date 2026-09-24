/**
 * Wochenraster mit Stundenlinien. Einträge: { id, day (0–6), start "HH:MM", end "HH:MM", ... }.
 * `renderItem(item)` liefert den Inhalt, `itemStyle(item)` Farbe/Rahmen.
 */
const HOUR_PX = 46;

function toMin(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

/** Überlappende Einträge nebeneinander legen (einfache Spurzuteilung). */
function layout(items) {
  const sorted = [...items].sort((a, b) => toMin(a.start) - toMin(b.start) || toMin(b.end) - toMin(a.end));
  const lanes = [];
  const placed = [];
  let group = [];
  let groupEnd = -1;
  const flush = () => {
    const count = Math.max(1, ...group.map((g) => g.lane + 1));
    group.forEach((g) => placed.push({ ...g, lanes: count }));
    group = [];
    lanes.length = 0;
  };
  for (const it of sorted) {
    const s = toMin(it.start);
    const e = Math.max(toMin(it.end), s + 15);
    if (s >= groupEnd && group.length) flush();
    let lane = lanes.findIndex((end) => end <= s);
    if (lane === -1) {
      lane = lanes.length;
      lanes.push(e);
    } else lanes[lane] = e;
    group.push({ ...it, lane });
    groupEnd = Math.max(groupEnd, e);
  }
  if (group.length) flush();
  return placed;
}

export default function WeekGrid({ days, items, startHour = 7, endHour = 22, renderItem, itemStyle, background, onSlotClick, nowLine = true, allDay }) {
  const hours = [];
  for (let h = startHour; h < endHour; h++) hours.push(h);
  const height = (endHour - startHour) * HOUR_PX;
  const now = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes();

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[760px]">
        <div className="grid" style={{ gridTemplateColumns: `52px repeat(${days.length}, minmax(0, 1fr))` }}>
          <div />
          {days.map((d) => (
            <div key={d.key} className={`border-b border-line px-2 pb-2 text-center ${d.isToday ? "text-accent" : "text-ink-2"}`}>
              <div className="font-display text-[0.65rem] font-bold">{d.label}</div>
              {d.sub && <div className={`text-xs ${d.isToday ? "glow-text font-semibold" : "text-ink-3"}`}>{d.sub}</div>}
            </div>
          ))}
          {allDay && (
            <>
              <div className="pt-1 text-right text-[0.6rem] text-ink-3">ganzt.</div>
              {days.map((d) => (
                <div key={d.key} className="min-h-[26px] space-y-0.5 border-b border-l border-line/60 p-0.5">
                  {allDay(d)}
                </div>
              ))}
            </>
          )}
        </div>
        <div className="relative grid" style={{ gridTemplateColumns: `52px repeat(${days.length}, minmax(0, 1fr))`, height }}>
          <div className="relative">
            {hours.map((h) => (
              <div key={h} className="absolute right-2 -translate-y-1/2 text-[0.65rem] tabular-nums text-ink-3" style={{ top: (h - startHour) * HOUR_PX }}>
                {String(h).padStart(2, "0")}:00
              </div>
            ))}
          </div>
          {days.map((d) => {
            const dayItems = layout(items.filter((it) => it.day === d.index));
            return (
              <div
                key={d.key}
                className={`relative border-l border-line/60 ${d.isToday ? "bg-accent/[0.03]" : ""}`}
                onDoubleClick={(e) => {
                  if (!onSlotClick) return;
                  const rect = e.currentTarget.getBoundingClientRect();
                  const minutes = Math.floor(((e.clientY - rect.top) / HOUR_PX) * 4) * 15 + startHour * 60;
                  onSlotClick(d, `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`);
                }}
              >
                {hours.map((h) => (
                  <div key={h} className="absolute inset-x-0 border-t border-line/40" style={{ top: (h - startHour) * HOUR_PX }} />
                ))}
                {background?.(d, (hhmm) => ((toMin(hhmm) - startHour * 60) / 60) * HOUR_PX)}
                {dayItems.map((it) => {
                  const s = Math.max(toMin(it.start), startHour * 60);
                  const e = Math.min(Math.max(toMin(it.end), toMin(it.start) + 20), endHour * 60);
                  if (e <= startHour * 60 || s >= endHour * 60) return null;
                  const top = ((s - startHour * 60) / 60) * HOUR_PX;
                  const h = Math.max(((e - s) / 60) * HOUR_PX - 2, 18);
                  const width = 100 / it.lanes;
                  return (
                    <div
                      key={it.id}
                      className="absolute overflow-hidden rounded-md px-1.5 py-1 text-[0.7rem] leading-tight transition hover:z-10 hover:brightness-125"
                      style={{ top, height: h, left: `calc(${it.lane * width}% + 2px)`, width: `calc(${width}% - 4px)`, ...(itemStyle ? itemStyle(it) : {}) }}
                    >
                      {renderItem(it)}
                    </div>
                  );
                })}
                {nowLine && d.isToday && nowMin >= startHour * 60 && nowMin <= endHour * 60 && (
                  <div className="pointer-events-none absolute inset-x-0 z-20 h-0.5 bg-accent shadow-[0_0_8px_#22d3ee]" style={{ top: ((nowMin - startHour * 60) / 60) * HOUR_PX }}>
                    <span className="absolute -left-1 -top-[3px] h-2 w-2 rounded-full bg-accent" />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
