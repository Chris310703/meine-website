import { STATUS } from "../lib/colors";

/** Ampel mit drei Lichtern – das aktive leuchtet; Beschriftung macht den Zustand auch ohne Farbe klar. */
export default function TrafficLight({ color = "grau", size = 34 }) {
  const lights = ["rot", "gelb", "gruen"];
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-line bg-[#070c11] p-2.5" role="img" aria-label={`Ampel: ${STATUS[color]?.label}`}>
      {lights.map((l) => {
        const on = l === color;
        const s = STATUS[l];
        return (
          <span
            key={l}
            className={`block rounded-full transition-all ${on ? "pulse-glow" : ""}`}
            style={{
              width: size,
              height: size,
              background: on ? `radial-gradient(circle at 35% 35%, #fff8, ${s.color} 45%)` : "#141d26",
              "--glow": s.glow,
              boxShadow: on ? `0 0 18px ${s.glow}` : "inset 0 0 6px #000",
              opacity: on ? 1 : 0.55,
            }}
          />
        );
      })}
    </div>
  );
}
