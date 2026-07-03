/** Tailwind standalone CLI config (D55) — build via scripts/build_css.ps1 */
module.exports = {
  content: ["./templates/**/*.html", "./*/templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        ink: "#1c2733",
        paper: "#f6f7f9",
        accent: { DEFAULT: "#0f6e5d", dark: "#0b5347" },
        danger: "#b3372d",
      },
    },
  },
  plugins: [],
};
