import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "o3-bg-primary": "#194B0A",
        "o3-bg-deep": "#113306",
        "o3-accent": "#B2F093",
        "o3-green": "#6BAF82",
        "o3-text-primary": "#F1FFE0",
        "o3-text-secondary": "#C5DFC9",
        "o3-highlight": "#F1FFE0",
      },
      fontFamily: {
        outfit: ["var(--font-outfit)", "sans-serif"],
      },
      borderColor: {
        "o3-card": "rgba(197,223,201,0.15)",
        "o3-card-strong": "rgba(197,223,201,0.20)",
      },
      backgroundColor: {
        "o3-card": "rgba(255,255,255,0.06)",
        "o3-card-hover": "rgba(255,255,255,0.08)",
      },
    },
  },
  plugins: [],
};
export default config;
