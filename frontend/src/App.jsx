import { Suspense, lazy, useCallback, useMemo, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { RefreshContext } from "./lib/api";
import SyncWidget from "./components/SyncWidget";
import { Loading, ToastProvider } from "./components/ui";

const Heute = lazy(() => import("./pages/Heute"));
const Fitness = lazy(() => import("./pages/Fitness"));
const Schlaf = lazy(() => import("./pages/Schlaf"));
const Recovery = lazy(() => import("./pages/Recovery"));
const Kalender = lazy(() => import("./pages/Kalender"));
const Naehrwerte = lazy(() => import("./pages/Naehrwerte"));
const Habits = lazy(() => import("./pages/Habits"));
const Todos = lazy(() => import("./pages/Todos"));
const Stundenplan = lazy(() => import("./pages/Stundenplan"));
const Lernplan = lazy(() => import("./pages/Lernplan"));
const Finanzen = lazy(() => import("./pages/Finanzen"));
const Aktien = lazy(() => import("./pages/Aktien"));
const News = lazy(() => import("./pages/News"));
const Journal = lazy(() => import("./pages/Journal"));
const Rueckblick = lazy(() => import("./pages/Rueckblick"));
const KI = lazy(() => import("./pages/KI"));
const Einstellungen = lazy(() => import("./pages/Einstellungen"));

export const NAV = [
  { path: "/heute", label: "Heute", icon: "☀️", element: Heute },
  { path: "/fitness", label: "Fitness", icon: "🏃", element: Fitness },
  { path: "/schlaf", label: "Schlaf", icon: "🌙", element: Schlaf },
  { path: "/recovery", label: "Recovery", icon: "🔋", element: Recovery },
  { path: "/kalender", label: "Kalender", icon: "📅", element: Kalender },
  { path: "/naehrwerte", label: "Nährwerte", icon: "🥗", element: Naehrwerte },
  { path: "/habits", label: "Habits", icon: "✅", element: Habits },
  { path: "/todos", label: "To-dos", icon: "📝", element: Todos },
  { path: "/stundenplan", label: "Stundenplan", icon: "🎓", element: Stundenplan },
  { path: "/lernplan", label: "Lernplan", icon: "📚", element: Lernplan },
  { path: "/finanzen", label: "Finanzen", icon: "💶", element: Finanzen },
  { path: "/aktien", label: "Aktien", icon: "📈", element: Aktien },
  { path: "/news", label: "News", icon: "📰", element: News },
  { path: "/journal", label: "Journal", icon: "📓", element: Journal },
  { path: "/rueckblick", label: "Rückblick", icon: "🔭", element: Rueckblick },
  { path: "/ki", label: "KI", icon: "🤖", element: KI },
  { path: "/einstellungen", label: "Einstellungen", icon: "⚙️", element: Einstellungen },
];

function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r border-line bg-panel/95 backdrop-blur">
      <div className="px-5 pb-3 pt-5">
        <div className="font-display glow-text text-xl font-extrabold text-accent">Life OS</div>
        <div className="mt-0.5 text-[0.68rem] uppercase tracking-[0.2em] text-ink-3">Chris · Recht & Wirtschaft</div>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto pr-3" aria-label="Hauptnavigation">
        {NAV.map((item) => (
          <NavLink key={item.path} to={item.path} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
            <span className="w-5 text-center text-base [text-shadow:none]" aria-hidden>
              {item.icon}
            </span>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="p-3 pt-2">
        <SyncWidget />
      </div>
    </aside>
  );
}

export default function App() {
  const [version, setVersion] = useState(0);
  const bump = useCallback(() => setVersion((v) => v + 1), []);
  const ctx = useMemo(() => ({ version, bump }), [version, bump]);

  return (
    <RefreshContext.Provider value={ctx}>
      <ToastProvider>
        <Sidebar />
        <main className="ml-60 min-h-full px-8 py-7">
          <div className="mx-auto max-w-[1400px]">
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route path="/" element={<Navigate to="/heute" replace />} />
                {NAV.map(({ path, element: Page }) => (
                  <Route key={path} path={path} element={<Page />} />
                ))}
                <Route path="*" element={<Navigate to="/heute" replace />} />
              </Routes>
            </Suspense>
          </div>
        </main>
      </ToastProvider>
    </RefreshContext.Provider>
  );
}
