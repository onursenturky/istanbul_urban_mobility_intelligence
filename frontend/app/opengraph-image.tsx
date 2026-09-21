import { ImageResponse } from "next/og";

export const alt = "Istanbul Urban Mobility Intelligence — O3 Sustainability";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Built entirely from JSX/CSS (no stock imagery, no unsupported statistics) -- a grid-cell
// motif standing in for the analytical map, same technique already used on the landing page
// hero (app/(editorial)/page.tsx), reusing the exact O3 palette rather than introducing new colors.
export default function OpengraphImage() {
  const GRID_COLS = 8;
  const GRID_ROWS = 8;
  const colors = ["#6BAF82", "#B2F093", "#194B0A", "transparent", "transparent"];
  let seed = 7;
  const rand = () => {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    return seed / 2147483648;
  };
  const cells = Array.from({ length: GRID_COLS * GRID_ROWS }, () => colors[Math.floor(rand() * colors.length)]);

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          position: "relative",
          background: "#113306",
          padding: "0 80px",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: 0,
            right: 0,
            width: 420,
            height: 420,
            display: "flex",
            flexWrap: "wrap",
            opacity: 0.55,
          }}
        >
          {cells.map((color, i) => (
            <div key={i} style={{ width: `${100 / GRID_COLS}%`, height: `${100 / GRID_ROWS}%`, display: "flex" }}>
              <div style={{ width: "88%", height: "88%", margin: "auto", borderRadius: 3, background: color }} />
            </div>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 28 }}>
          <div style={{ width: 16, height: 16, borderRadius: 4, background: "#B2F093" }} />
          <span style={{ color: "#C5DFC9", fontSize: 26, letterSpacing: 4, textTransform: "uppercase" }}>Istanbul</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", color: "#F1FFE0", fontSize: 68, fontWeight: 700, lineHeight: 1.08 }}>
          <span>Urban Mobility</span>
          <span>Intelligence</span>
        </div>
        <div style={{ display: "flex", marginTop: 36, color: "#B2F093", fontSize: 28, fontWeight: 500 }}>
          O3 Sustainability spatial intelligence project
        </div>
      </div>
    ),
    { ...size }
  );
}
