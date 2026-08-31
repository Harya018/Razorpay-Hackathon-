/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Register 1 — storefront ("Priya's shop"). See
        // src/styles/storefront-tokens.css for the full rationale.
        clay: { DEFAULT: "#8B6552", dark: "#6E4F3F", light: "#A98977" },
        putty: { DEFAULT: "#D9CBB8", dark: "#C2AD91", light: "#E5DAC9" },
        moss: { DEFAULT: "#5C6E52", dark: "#46543E", light: "#7C9270" },
        ink: { DEFAULT: "#2B2823", soft: "#5C574C" },
        ivory: { DEFAULT: "#F2EDE3", deep: "#EAE1D0" },
        // Register 2 — dashboard ("audit-grade instrument panel"). Only
        // the two backgrounds Tailwind's own defaults don't already cover
        // exactly — deterministic/LLM color-coding reuses slate/violet
        // directly (see dashboard-tokens.css's rationale).
        panel: { DEFAULT: "#1C2430", raised: "#253044" },
        content: { DEFAULT: "#F7F8FA" },
      },
      fontFamily: {
        // Global default sans (both registers) — Inter, quiet and out of
        // the way. Fraunces (display) is opt-in via font-display,
        // reserved for storefront headlines/product names. JetBrains
        // Mono (mono) is opt-in via font-mono, reserved for dashboard
        // numeric/log/audit data specifically.
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        display: ["Fraunces", "Georgia", "serif"],
        mono: ['"JetBrains Mono"', '"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
