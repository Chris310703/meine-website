import { TYPE_STYLE } from "../lib/colors";
import { timeText } from "../lib/format";
import { Empty } from "./ui";

export default function AgendaList({ items, emptyText = "Keine Termine." }) {
  if (!items?.length) return <Empty icon="🗓️">{emptyText}</Empty>;
  const now = new Date();
  return (
    <ul className="space-y-1.5">
      {items.map((it) => {
        const style = TYPE_STYLE[it.type] || TYPE_STYLE.google;
        const past = new Date(it.end) < now;
        const missed = it.status === "verpasst";
        return (
          <li
            key={it.id}
            className={`flex items-start gap-3 rounded-lg border border-transparent px-2 py-1.5 hover:border-line ${past ? "opacity-55" : ""}`}
          >
            <div className="w-12 shrink-0 pt-0.5 text-right text-xs tabular-nums text-ink-2">
              {it.all_day ? "ganztägig" : timeText(it.start)}
            </div>
            <span className="mt-1 h-8 w-1 shrink-0 rounded-full" style={{ background: style.color, boxShadow: `0 0 6px ${style.color}` }} />
            <div className="min-w-0 flex-1">
              <div className={`truncate text-sm font-medium ${missed ? "line-through" : ""}`}>
                <span className="mr-1.5" aria-hidden>
                  {style.icon}
                </span>
                {it.title}
              </div>
              <div className="truncate text-xs text-ink-3">
                {style.label}
                {!it.all_day && ` · bis ${timeText(it.end)}`}
                {it.subtitle ? ` · ${it.subtitle}` : ""}
                {missed ? " · verpasst" : ""}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
