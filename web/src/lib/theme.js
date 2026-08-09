/* Theme state. Kept out of data.js, which is documented as the only I/O in the
   app -- localStorage would quietly make that comment false.

   Dark is the default and the CSS base. A first-time visitor gets dark
   regardless of prefers-color-scheme: this is a dark-native product surface,
   and the toggle in the header is a one-click, persistent fix either way. To
   make it system-first instead, change the inline script in index.html to read
   `stored || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")`
   -- the rest of this module already handles both values. */

import { useCallback, useState } from "react";

export const THEME_KEY = "vcp-theme";
export const DEFAULT_THEME = "dark";

function read() {
  if (typeof document === "undefined") return DEFAULT_THEME;
  return document.documentElement.dataset.theme || DEFAULT_THEME;
}

export function useTheme() {
  // Seeded from the DOM, which the pre-paint script in index.html has already
  // set, so React never renders a label that disagrees with the painted page.
  const [theme, setThemeState] = useState(read);

  const setTheme = useCallback((next) => {
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem(THEME_KEY, next);
    } catch {
      // Safari private mode throws on write. The theme still applies for this
      // page view; only the persistence is lost.
    }
    setThemeState(next);
  }, []);

  return [theme, setTheme];
}
