import type { Config } from "tailwindcss";

/** Canonical semantic palette (UI/UX §3.2 + MedChain design tokens). */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#f2f5f6",
        ink: "#14263b",
        "ink-soft": "#4a5b6e",
        "ink-faint": "#7c8b99",
        line: "#d3dde2",
        teal: "#0e7c7b",
        "teal-deep": "#0a5e5d",
        "teal-wash": "#e1f0ef",
        amber: "#b7791f",
        "amber-deep": "#8a5a13",
        "amber-wash": "#f6ecda",
        alarm: "#c2413b",
        "alarm-wash": "#f8e3e1",
      },
      fontFamily: {
        sans: ["Schibsted Grotesk", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(20,38,59,.06)",
      },
    },
  },
  plugins: [],
};
export default config;
