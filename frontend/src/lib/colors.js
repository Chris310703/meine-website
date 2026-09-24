// Datenfarben – mit dem Paletten-Validator für den dunklen Hintergrund geprüft.
export const C = {
  orange: "#e0620f",
  cyan: "#0ea5b7",
  violet: "#8b5cf6",
  green: "#1f9d55",
  pink: "#d9328a",
  accent: "#22d3ee",
  grid: "#1a2631",
  axis: "#66788a",
  ink2: "#9fb0bf",
};

// Schlafphasen (gestapelt): Tief, Leicht, REM, Wach
export const SLEEP_COLORS = {
  deep: C.violet,
  light: C.orange,
  rem: C.cyan,
  awake: C.pink,
};

// Kalender-Typen – zusätzlich immer mit Icon und Text beschriftet
export const TYPE_STYLE = {
  google: { color: C.violet, icon: "📅", label: "Termin" },
  stundenplan: { color: C.cyan, icon: "🎓", label: "Stundenplan" },
  lernblock: { color: C.orange, icon: "📚", label: "Lernblock" },
  training: { color: C.green, icon: "🏃", label: "Training" },
  pruefung: { color: C.pink, icon: "📝", label: "Prüfung" },
};

export const STATUS = {
  gruen: { color: "#22c55e", glow: "rgba(34,197,94,0.55)", icon: "▲", label: "Grün" },
  gelb: { color: "#eab308", glow: "rgba(234,179,8,0.5)", icon: "■", label: "Gelb" },
  rot: { color: "#ef4444", glow: "rgba(239,68,68,0.55)", icon: "●", label: "Rot" },
  grau: { color: "#66788a", glow: "rgba(102,120,138,0.3)", icon: "○", label: "Keine Daten" },
};
