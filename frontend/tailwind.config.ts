import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: "#0F172A",
          soft: "#1E293B",
          muted: "#475569",
        },
        brand: {
          DEFAULT: "#1E88E5",
          dark: "#1565C0",
        },
        accent: "#F5B700",
      },
      fontFamily: {
        // Arabic-capable stack first: the UI is Arabic by default.
        sans: [
          "var(--font-ui)",
          "Segoe UI",
          "Tahoma",
          "Noto Sans Arabic",
          "system-ui",
          "sans-serif",
        ],
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.25s ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
