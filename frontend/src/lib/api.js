import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

function errorText(detail, status) {
  if (!detail) return `Fehler ${status}`;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (d.loc ? `${d.loc.slice(1).join(".")}: ${d.msg}` : d.msg || JSON.stringify(d)))
      .join("; ");
  }
  return JSON.stringify(detail);
}

export async function api(path, { method = "GET", body } = {}) {
  const isForm = body instanceof FormData;
  const res = await fetch(`/api${path}`, {
    method,
    headers: body !== undefined && !isForm ? { "Content-Type": "application/json" } : {},
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* keine JSON-Antwort */
    }
    throw new Error(errorText(detail, res.status));
  }
  if (res.status === 204) return null;
  const type = res.headers.get("content-type") || "";
  return type.includes("application/json") ? res.json() : res.text();
}

api.get = (p) => api(p);
api.post = (p, body) => api(p, { method: "POST", body: body ?? {} });
api.put = (p, body) => api(p, { method: "PUT", body: body ?? {} });
api.patch = (p, body) => api(p, { method: "PATCH", body: body ?? {} });
api.del = (p) => api(p, { method: "DELETE" });

/** Globaler Zähler: nach einem Sync laden alle Seiten ihre Daten neu. */
export const RefreshContext = createContext({ version: 0, bump: () => {} });

export function useRefresh() {
  return useContext(RefreshContext);
}

/** Lädt Daten von der API und lädt neu, wenn sich `path` oder die globale Version ändert. */
export function useApi(path, deps = []) {
  const { version } = useRefresh();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(Boolean(path));
  const seq = useRef(0);

  const load = useCallback(
    async (silent = false) => {
      if (!path) return;
      const id = ++seq.current;
      if (!silent) setLoading(true);
      try {
        const result = await api(path);
        if (id === seq.current) {
          setData(result);
          setError(null);
        }
      } catch (e) {
        if (id === seq.current) setError(e.message);
      } finally {
        if (id === seq.current) setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [path, ...deps],
  );

  useEffect(() => {
    load(data !== null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, version]);

  return { data, error, loading, reload: () => load(true), setData };
}
