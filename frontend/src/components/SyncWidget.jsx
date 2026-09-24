import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, useRefresh } from "../lib/api";
import { dateTimeText } from "../lib/format";
import { Modal, useToast } from "./ui";

/** Garmin-Sync in der Seitenleiste: Status, „Jetzt synchronisieren“, Zwei-Faktor-Code. */
export default function SyncWidget() {
  const [status, setStatus] = useState(null);
  const [mfaOpen, setMfaOpen] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const { bump } = useRefresh();
  const toast = useToast();
  const wasRunning = useRef(false);

  const load = useCallback(async () => {
    try {
      const s = await api.get("/garmin/status");
      setStatus(s);
      if (wasRunning.current && !s.sync.running) {
        if (s.sync.last_error) toast(s.sync.last_error, "error");
        else toast(`Garmin-Sync fertig: ${s.sync.last_message || "Daten aktualisiert"}`, "success");
        bump();
      }
      wasRunning.current = s.sync.running;
      if (s.needs_mfa) setMfaOpen(true);
    } catch {
      /* Backend evtl. noch nicht bereit */
    }
  }, [bump, toast]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const interval = setInterval(load, status?.sync?.running ? 1500 : 30000);
    return () => clearInterval(interval);
  }, [load, status?.sync?.running]);

  async function sync() {
    setBusy(true);
    try {
      const r = await api.post("/garmin/sync");
      setStatus(r.status);
      wasRunning.current = true;
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function sendCode(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/garmin/mfa", { code });
      setMfaOpen(false);
      setCode("");
      toast("Code akzeptiert – Synchronisation läuft.", "success");
      wasRunning.current = true;
      load();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  const running = status?.sync?.running;
  const connected = status && (status.has_tokens || status.credentials_in_env);
  return (
    <div className="rounded-xl border border-accent/20 bg-[#0b131a] p-3">
      <div className="flex items-center justify-between">
        <span className="font-display text-[0.6rem] font-bold text-ink-2">⌚ Garmin</span>
        <span
          className="h-2 w-2 rounded-full"
          title={connected ? "Verbunden" : "Nicht verbunden"}
          style={{ background: connected ? "#22c55e" : "#66788a", boxShadow: connected ? "0 0 6px #22c55e" : "none" }}
        />
      </div>
      <div className="mt-1 text-[0.7rem] leading-snug text-ink-3">
        {running
          ? `${status.sync.phase || "Synchronisiere"} (${status.sync.progress}/${status.sync.total || "?"})`
          : status?.last_sync
            ? `Zuletzt: ${dateTimeText(status.last_sync)}`
            : connected
              ? "Noch nicht synchronisiert"
              : "Nicht verbunden – Beispieldaten"}
      </div>
      {running && (
        <div className="mt-2 h-1 overflow-hidden rounded bg-[#15202a]">
          <div className="h-full bg-accent shadow-[0_0_6px_#22d3ee] transition-all" style={{ width: `${status.sync.total ? (status.sync.progress / status.sync.total) * 100 : 10}%` }} />
        </div>
      )}
      {connected ? (
        <button className="btn btn-primary btn-sm mt-2 w-full" onClick={sync} disabled={busy || running}>
          {running ? <span className="spin inline-block h-3 w-3 rounded-full border-2 border-accent border-t-transparent" /> : "⟳"} Jetzt synchronisieren
        </button>
      ) : (
        <Link to="/einstellungen" className="btn btn-sm mt-2 w-full">
          Garmin verbinden
        </Link>
      )}
      <Modal open={mfaOpen} title="Garmin: Zwei-Faktor-Code" onClose={() => setMfaOpen(false)}>
        <form onSubmit={sendCode} className="space-y-3">
          <p className="text-sm text-ink-2">
            Garmin hat dir einen Bestätigungscode geschickt (E-Mail oder SMS). Gib ihn hier ein, um die Anmeldung abzuschließen.
          </p>
          <input className="input text-center text-lg tracking-[0.4em]" value={code} onChange={(e) => setCode(e.target.value)} placeholder="123456" autoFocus inputMode="numeric" />
          <button className="btn btn-primary w-full" disabled={busy || !code.trim()}>
            Code senden
          </button>
        </form>
      </Modal>
    </div>
  );
}
