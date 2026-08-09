import { useTheme } from "../lib/theme.js";

/* A plain button, not role="switch". A switch announces "on/off", which does
   not map onto two named themes -- "theme, switch, on" tells a screen-reader
   user nothing. The accessible name says what the press will do, and the live
   region reports what it did. */

export default function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const next = theme === "light" ? "dark" : "light";

  return (
    <>
      <button
        type="button"
        className="theme-toggle"
        aria-label={`Switch to ${next} theme`}
        onClick={() => setTheme(next)}
      >
        <span aria-hidden="true">{theme === "light" ? "◑" : "◐"}</span>
        <span>{theme === "light" ? "LIGHT" : "DARK"}</span>
      </button>
      <span className="visually-hidden" aria-live="polite">
        {theme === "light" ? "Light theme" : "Dark theme"}
      </span>
    </>
  );
}
