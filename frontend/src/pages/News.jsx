import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Card, Empty, ErrorBox, Loading, PageHeader, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { dateTimeText } from "../lib/format";

const CAT_ICON = { Wirtschaft: "📊", Recht: "⚖️", Steuern: "🧾", Sport: "⚽", Allgemein: "📰", Politik: "🏛️", Technik: "💻" };

export default function News() {
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const { data, error, loading, reload } = useApi(`/news?category=${encodeURIComponent(category)}&q=${encodeURIComponent(query)}`);
  const toast = useToast();

  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    if (!data?.status?.running) return undefined;
    const t = setTimeout(reload, 3000);
    return () => clearTimeout(t);
  }, [data, reload]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;

  async function refresh() {
    await api.post("/news/refresh");
    toast("Feeds werden abgerufen …");
    setTimeout(reload, 4000);
  }

  const failing = data.feeds.filter((f) => f.active && f.last_error);
  const total = Object.values(data.counts).reduce((a, b) => a + b, 0);

  return (
    <div>
      <PageHeader
        title="News"
        icon="📰"
        subtitle={data.status.running ? "Feeds werden abgerufen …" : data.status.last_run ? `Zuletzt aktualisiert: ${dateTimeText(data.status.last_run)}` : "Nachrichten aus deinen RSS-Feeds"}
        actions={
          <>
            <Link to="/einstellungen" className="btn">
              ⚙ Feeds verwalten
            </Link>
            <button className="btn btn-primary" onClick={refresh} disabled={data.status.running}>
              ⟳ Aktualisieren
            </button>
          </>
        }
      />

      {data.demo && (
        <div className="mb-4 rounded-lg border border-accent/25 bg-accent/5 px-4 py-2.5 text-sm text-ink-2">
          Das sind Beispielmeldungen. Sobald deine Feeds erreichbar sind, erscheinen hier echte Nachrichten.
        </div>
      )}
      {failing.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-xs text-amber-100">
          ⚠ Nicht erreichbar: {failing.map((f) => f.name).join(", ")} – URL in den Einstellungen prüfen.
        </div>
      )}

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <button className={`chip ${!category ? "!border-accent/70 !bg-accent/15 !text-accent" : ""}`} onClick={() => setCategory("")}>
          Alle ({total})
        </button>
        {data.categories.map((c) => (
          <button key={c} className={`chip ${category === c ? "!border-accent/70 !bg-accent/15 !text-accent" : ""}`} onClick={() => setCategory(c)}>
            {CAT_ICON[c] || "📰"} {c} ({data.counts[c] || 0})
          </button>
        ))}
        <input className="input ml-auto w-64 py-1.5" placeholder="Suchen …" value={q} onChange={(e) => setQ(e.target.value)} aria-label="News durchsuchen" />
      </div>

      {data.items.length ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {data.items.map((it) => (
            <a key={it.id} href={it.link} target="_blank" rel="noreferrer" className="card group flex flex-col transition hover:border-accent/50 hover:shadow-[0_0_16px_rgba(34,211,238,0.15)]">
              <div className="mb-2 flex items-center justify-between text-[0.7rem] text-ink-3">
                <span className="chip">
                  {CAT_ICON[it.category] || "📰"} {it.category}
                </span>
                <span>{it.published ? dateTimeText(it.published) : ""}</span>
              </div>
              <h3 className="font-semibold leading-snug group-hover:text-accent">{it.title}</h3>
              {it.summary && <p className="mt-2 line-clamp-3 text-sm text-ink-2">{it.summary}</p>}
              <div className="mt-auto pt-3 text-xs text-ink-3">{it.feed} ↗</div>
            </a>
          ))}
        </div>
      ) : (
        <Card>
          <Empty icon="📰">{query ? "Keine Treffer." : "Noch keine Nachrichten – füge Feeds in den Einstellungen hinzu."}</Empty>
        </Card>
      )}
    </div>
  );
}
