/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        added: "#22c55e",
        modified: "#3b82f6",
        deleted: "#ef4444",
        affected: "#a855f7",
        contextual: "#f59e0b",
      },
    },
  },
  plugins: [],
};
