import { C } from "../lib/colors";

/** Einheitlicher Tooltip für alle Diagramme. */
export function ChartTooltip({ active, payload, label, labelFormatter, valueFormatter, hideZero = false }) {
  if (!active || !payload || !payload.length) return null;
  const rows = payload.filter((p) => p.value !== null && p.value !== undefined && !(hideZero && !p.value));
  return (
    <div className="rounded-lg border border-accent/30 bg-[#0a121a]/95 px-3 py-2 text-xs shadow-xl backdrop-blur">
      <div className="mb-1 font-semibold text-ink">{labelFormatter ? labelFormatter(label, payload) : label}</div>
      {rows.map((p) => (
        <div key={p.dataKey} className="flex items-center justify-between gap-4 text-ink-2">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ background: p.color || p.fill || p.stroke }} />
            {p.name}
          </span>
          <span className="font-semibold text-ink">{valueFormatter ? valueFormatter(p.value, p) : p.value}</span>
        </div>
      ))}
    </div>
  );
}

export const axisProps = {
  stroke: C.grid,
  tick: { fill: C.axis, fontSize: 11 },
  tickLine: false,
  axisLine: { stroke: C.grid },
};

export const gridProps = { strokeDasharray: "3 4", vertical: false, stroke: C.grid };

export const barRadius = [4, 4, 0, 0];

export function Legend({ items }) {
  return (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      {items.map((i) => (
        <span key={i.label} className="flex items-center gap-1.5">
          <span
            className="inline-block"
            style={{
              width: i.line ? 14 : 10,
              height: i.line ? 2 : 10,
              borderRadius: i.line ? 1 : 2,
              background: i.color,
              borderTop: i.dashed ? `2px dashed ${i.color}` : undefined,
              backgroundColor: i.dashed ? "transparent" : i.color,
            }}
          />
          {i.label}
        </span>
      ))}
    </div>
  );
}
