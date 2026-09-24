import { createContext, useCallback, useContext, useEffect, useState } from "react";

export function PageHeader({ title, subtitle, icon, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display glow-text flex items-center gap-3 text-2xl font-extrabold text-accent">
          {icon && <span className="text-2xl [text-shadow:none]">{icon}</span>}
          {title}
        </h1>
        {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, actions, children, className = "", bodyClass = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          {title && <h2 className="card-title">{title}</h2>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, unit, sub, color, big = false }) {
  return (
    <div>
      <div className="text-[0.68rem] font-semibold uppercase tracking-wider text-ink-3">{label}</div>
      <div className={`mt-1 flex items-baseline gap-1 font-semibold ${big ? "text-3xl" : "text-xl"}`} style={color ? { color } : undefined}>
        <span>{value ?? "–"}</span>
        {unit && <span className="text-xs font-medium text-ink-3">{unit}</span>}
      </div>
      {sub && <div className="mt-0.5 text-xs text-ink-2">{sub}</div>}
    </div>
  );
}

export function ProgressBar({ value, max = 100, color = "var(--color-accent)", height = 8, glow = true, label }) {
  const pctValue = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div>
      <div className="w-full overflow-hidden rounded-full bg-[#15202a]" style={{ height }} role="progressbar" aria-valuenow={Math.round(pctValue)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pctValue}%`, background: color, boxShadow: glow ? `0 0 8px ${color}` : undefined }}
        />
      </div>
    </div>
  );
}

export function Ring({ value, max = 100, size = 96, stroke = 8, color = "var(--color-accent)", children }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const p = max > 0 ? Math.max(0, Math.min(1, (value ?? 0) / max)) : 0;
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#15202a" strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${c * p} ${c}`}
          style={{ filter: `drop-shadow(0 0 4px ${color})`, transition: "stroke-dasharray 0.6s" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">{children}</div>
    </div>
  );
}

export function Loading({ text = "Lade …" }) {
  return (
    <div className="flex items-center gap-3 py-10 text-ink-2">
      <span className="spin inline-block h-4 w-4 rounded-full border-2 border-accent border-t-transparent" />
      {text}
    </div>
  );
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
      <b>Fehler:</b> {error}
      {onRetry && (
        <button className="btn btn-sm ml-3" onClick={onRetry}>
          Erneut versuchen
        </button>
      )}
    </div>
  );
}

export function Empty({ children, icon = "✨" }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-8 text-center text-sm text-ink-3">
      <span className="text-2xl opacity-70">{icon}</span>
      <div>{children}</div>
    </div>
  );
}

export function Field({ label, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      {label && <span className="label">{label}</span>}
      {children}
    </label>
  );
}

export function Segmented({ options, value, onChange, size = "md" }) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-[#081017] p-0.5">
      {options.map((o) => {
        const val = typeof o === "string" ? o : o.value;
        const label = typeof o === "string" ? o : o.label;
        const active = val === value;
        return (
          <button
            key={val}
            type="button"
            onClick={() => onChange(val)}
            className={`rounded-md ${size === "sm" ? "px-2 py-0.5 text-[0.7rem]" : "px-3 py-1 text-xs"} font-semibold transition ${
              active ? "bg-accent/15 text-accent shadow-[0_0_8px_rgba(34,211,238,0.3)]" : "text-ink-2 hover:text-ink"
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

export function Modal({ open, title, onClose, children, wide = false }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-6 pt-[8vh] backdrop-blur-sm" onMouseDown={onClose}>
      <div className={`card w-full ${wide ? "max-w-3xl" : "max-w-lg"}`} onMouseDown={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="card-title text-sm">{title}</h2>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Schließen">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Badge({ children, color = "#9fb0bf" }) {
  return (
    <span className="chip" style={{ borderColor: `${color}55`, color, background: `${color}14` }}>
      {children}
    </span>
  );
}

export function PriorityBadge({ priority }) {
  const map = { hoch: ["#f87171", "Hoch"], mittel: ["#eab308", "Mittel"], niedrig: ["#9fb0bf", "Niedrig"] };
  const [color, label] = map[priority] || map.mittel;
  return <Badge color={color}>{label}</Badge>;
}

export function ConfirmButton({ onConfirm, children = "Löschen", question = "Wirklich löschen?", className = "btn btn-sm btn-danger" }) {
  const [ask, setAsk] = useState(false);
  useEffect(() => {
    if (!ask) return undefined;
    const t = setTimeout(() => setAsk(false), 3500);
    return () => clearTimeout(t);
  }, [ask]);
  return ask ? (
    <button className={`${className} !border-red-500/60 !text-red-300`} onClick={() => { setAsk(false); onConfirm(); }}>
      {question}
    </button>
  ) : (
    <button className={className} onClick={() => setAsk(true)}>
      {children}
    </button>
  );
}

// ---------------------------------------------------------------- Toasts

const ToastContext = createContext(() => {});

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((text, type = "info") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, text, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), type === "error" ? 7000 : 3500);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-[60] flex w-96 flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto rounded-lg border px-4 py-3 text-sm shadow-lg backdrop-blur ${
              t.type === "error"
                ? "border-red-500/50 bg-red-950/80 text-red-100"
                : t.type === "success"
                  ? "border-emerald-500/50 bg-emerald-950/80 text-emerald-100"
                  : "border-accent/40 bg-[#0b1620]/90 text-ink"
            }`}
          >
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
