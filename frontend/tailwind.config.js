/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#f3f1ec",
        paper: "#ffffff",
        info: "#2a6f8f",
        brand: {
          50: "#eef6f9",
          100: "#d7e9f0",
          200: "#b0d3e1",
          300: "#7fb6cc",
          400: "#4b93b1",
          500: "#2a7797",
          600: "#1f6180",
          700: "#1a4f69",
          800: "#163f53",
          900: "#10303f",
        },
        risk: {
          low: "#3f7d56",
          moderate: "#b08a1f",
          heavy: "#c8612a",
          extreme: "#b3342b",
        },
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        sm: "6px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(28, 25, 23, 0.04), 0 2px 8px -2px rgba(28, 25, 23, 0.06)",
        lift: "0 10px 30px -12px rgba(16, 48, 63, 0.35)",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.25s ease-out both",
      },
    },
  },
  plugins: [],
};
