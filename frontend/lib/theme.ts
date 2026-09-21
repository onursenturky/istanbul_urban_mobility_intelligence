/**
 * Central O3 Sustainability design-token registry (TypeScript mirror of
 * app/globals.css custom properties). Components should import these
 * constants instead of hardcoding hex values.
 */
export const o3Colors = {
  bgPrimary: "#194B0A",
  bgDeep: "#113306",
  accent: "#B2F093",
  green: "#6BAF82",
  textPrimary: "#F1FFE0",
  textSecondary: "#C5DFC9",
  card: "rgba(255,255,255,0.06)",
  cardHover: "rgba(255,255,255,0.08)",
  cardBorder: "rgba(197,223,201,0.15)",
  cardBorderStrong: "rgba(197,223,201,0.20)",
  highlight: "#F1FFE0",
  highlightText: "#113306",
} as const;

/**
 * Analytical semantic palette. Deliberately NOT five shades of green --
 * data readability takes priority over brand-color purity for analytical
 * map layers (per Phase 13 spec Section 3, "Analytical Color System").
 */
export const semanticColors = {
  positive: "#6BAF82", // complete / already-sufficient accessibility
  gain: "#B2F093", // cycling closes the gap (flagship positive signal)
  partial: "#E0C168", // partial gain
  gap: "#E0785A", // remaining accessibility gap
  uncertain: "#8C9A91", // evidence uncertain / quality-limited
  transitLimit: "#7D8BB0", // transit-data limitation
  knownLimit: "#A98CC7", // known network limitation (e.g. Adalar)
} as const;

export type SemanticColorKey = keyof typeof semanticColors;
