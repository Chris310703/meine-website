import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Markdown from "../components/Markdown";
import { Card, ConfirmButton, Loading, PageHeader, useToast } from "../components/ui";
import { api, useApi } from "../lib/api";
import { dateTimeText } from "../lib/format";

const QUICK = [
  "Wie war meine Woche?",
  "Soll ich heute hart trainieren?",
  "Wie komme ich im Lernplan voran – schaffe ich BGB AT?",
  "Wie war mein Schlaf in den letzten zwei Wochen?",
  "Wie sieht mein Budget diesen Monat aus?",
  "Plane mir einen sinnvollen Tag für morgen.",
];

const TOOL_LABEL = {
  heute_ueberblick: "Heute",
  recovery_daten: "Recovery",
  training_daten: "Training",
  schlaf_daten: "Schlaf",
  lernplan: "Lernplan",
  kalender: "Kalender",
  finanzen: "Finanzen",
  ernaehrung: "Ernährung",
  habits_und_todos: "Habits & To-dos",
  rueckblick: "Rückblick",
};

export default function KI() {
  const { data: status } = useApi("/ai/status");
  const { data: history, setData, reload } = useApi("/ai/history");
  const [text, setText] = useState("");
  const [pending, setPending] = useState(null);
  const [tools, setTools] = useState({});
  const endRef = useRef(null);
  const toast = useToast();

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history, pending]);

  async function send(message) {
    const msg = (message ?? text).trim();
    if (!msg || pending) return;
    setText("");
    setPending(msg);
    try {
      const r = await api.post("/ai/chat", { message: msg });
      setData([...(history || []), r.user, r.reply]);
      setTools({ ...tools, [r.reply.id]: r.tools });
    } catch (e) {
      toast(e.message, "error");
      setText(msg);
    } finally {
      setPending(null);
    }
  }

  async function clear() {
    await api.del("/ai/history");
    setTools({});
    reload();
  }

  if (!status || !history) return <Loading />;

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <PageHeader
        title="KI"
        icon="🤖"
        subtitle={status.configured ? `Chat mit Claude (${status.model}) – mit Zugriff auf deine Training-, Schlaf-, Recovery-, Lern- und Finanzdaten` : "Chat mit Claude"}
        actions={
          history.length > 0 && (
            <ConfirmButton className="btn" onConfirm={clear} question="Verlauf wirklich löschen?">
              ＋ Neuer Chat
            </ConfirmButton>
          )
        }
      />

      {!status.configured ? (
        <Card title="Claude einrichten">
          <ol className="list-decimal space-y-2 pl-5 text-sm text-ink-2">
            <li>
              Konto anlegen bzw. anmelden unter <b>console.anthropic.com</b> und unter „API Keys“ einen Schlüssel erstellen.
            </li>
            <li>
              Die Datei <code className="text-accent">.env</code> im Projektordner öffnen und eintragen: <code className="text-accent">ANTHROPIC_API_KEY=sk-ant-…</code>
            </li>
            <li>Die App neu starten (Terminal: Ctrl + C, dann ./start.sh).</li>
          </ol>
          <p className="mt-3 text-sm text-ink-3">
            Alle anderen Funktionen laufen auch ohne Schlüssel. Details stehen in der README und unter{" "}
            <Link to="/einstellungen" className="text-accent underline">
              Einstellungen
            </Link>
            .
          </p>
        </Card>
      ) : (
        <>
          <div className="card flex-1 overflow-y-auto">
            {history.length === 0 && !pending && (
              <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
                <div className="font-display glow-text text-lg text-accent">Frag mich etwas</div>
                <p className="max-w-lg text-sm text-ink-3">Ich schaue mir deine Daten an und gebe dir konkrete Empfehlungen – zum Training, Schlaf, Lernen oder Budget.</p>
                <div className="flex max-w-2xl flex-wrap justify-center gap-2">
                  {QUICK.map((q) => (
                    <button key={q} className="chip px-3 py-1.5 text-xs hover:border-accent/60 hover:text-accent" onClick={() => send(q)}>
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="space-y-4">
              {history.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[75%] rounded-2xl rounded-br-sm border border-accent/40 bg-accent/10 px-4 py-2.5 text-sm text-ink">
                      {m.content}
                      <div className="mt-1 text-right text-[0.65rem] text-ink-3">{dateTimeText(m.created_at)}</div>
                    </div>
                  </div>
                ) : (
                  <div key={m.id} className="flex gap-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-accent/40 bg-accent/10 text-sm shadow-[0_0_10px_rgba(34,211,238,0.3)]">🤖</div>
                    <div className="max-w-[85%] rounded-2xl rounded-tl-sm border border-line bg-[#0a1118] px-4 py-3">
                      <Markdown text={m.content} />
                      {tools[m.id]?.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {[...new Set(tools[m.id])].map((t) => (
                            <span key={t} className="chip text-[0.62rem]">
                              🔎 {TOOL_LABEL[t] || t}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ),
              )}
              {pending && (
                <>
                  <div className="flex justify-end">
                    <div className="max-w-[75%] rounded-2xl rounded-br-sm border border-accent/40 bg-accent/10 px-4 py-2.5 text-sm">{pending}</div>
                  </div>
                  <div className="flex items-center gap-3 text-sm text-ink-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full border border-accent/40 bg-accent/10">🤖</div>
                    <span className="spin inline-block h-3 w-3 rounded-full border-2 border-accent border-t-transparent" /> Claude schaut sich deine Daten an …
                  </div>
                </>
              )}
              <div ref={endRef} />
            </div>
          </div>
          <form
            className="mt-4 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <textarea
              className="input flex-1 resize-none"
              rows={2}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder="Frag Claude … (Enter = senden, Shift + Enter = neue Zeile)"
              aria-label="Nachricht an Claude"
            />
            <button className="btn btn-primary px-5" disabled={!text.trim() || Boolean(pending)}>
              Senden
            </button>
          </form>
          {history.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {QUICK.slice(0, 4).map((q) => (
                <button key={q} className="chip text-[0.68rem] hover:border-accent/60 hover:text-accent" onClick={() => send(q)} disabled={Boolean(pending)}>
                  {q}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
