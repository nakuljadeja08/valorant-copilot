import { useEffect, useState } from "react";

import ThemeToggle from "./ThemeToggle.jsx";

/* The app chrome. Rendered by the shell on every route, like the provenance
   banner beneath it, so the SIM DATA pill is on screen wherever you are.

   The nav items are in-page anchors, not routes: the overview puts all three
   sections on one screen, and adding a router for three scroll targets would be
   a dependency in a project that deliberately hand-rolls hash routing. On a
   match route there is nothing to scroll to, so the nav is replaced by the back
   link — which is what the source design shows there too. */

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "agents", label: "Agents" },
  { id: "matches", label: "Matches" },
];

// Just below the sticky header: a section scrolled above this line is one you
// have already read past.
const SPY_LINE = 80;

/** Which section is currently in view, so the nav reflects where you are
 *  instead of always claiming "Overview".
 *
 *  A scroll position, not an IntersectionObserver: the sections are tall and
 *  unequal, so any observer band narrow enough to pick a single winner is also
 *  narrow enough to match nothing between two long sections. "The last heading
 *  you scrolled past" is what a reader means by where they are. */
function useActiveSection(enabled) {
  const [active, setActive] = useState(SECTIONS[0].id);

  useEffect(() => {
    if (!enabled) return;

    let frame = 0;
    const measure = () => {
      frame = 0;
      const tops = SECTIONS.map((s) => {
        const node = document.getElementById(s.id);
        return node ? { id: s.id, top: node.getBoundingClientRect().top } : null;
      }).filter(Boolean);
      if (!tops.length) return;

      // The bottom of the page can't scroll the final section up to the line,
      // so it would otherwise be unreachable.
      const atBottom =
        window.innerHeight + window.scrollY >= document.body.scrollHeight - 2;

      const passed = tops.filter((t) => t.top <= SPY_LINE);
      setActive(
        atBottom ? tops[tops.length - 1].id : (passed[passed.length - 1] ?? tops[0]).id,
      );
    };

    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };

    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [enabled]);

  return active;
}

export default function AppHeader({ provenance, onMatchRoute }) {
  const sources = provenance?.sources?.join(" · ");
  const active = useActiveSection(!onMatchRoute);

  return (
    <header className="app-header">
      <div className="app-header-inner">
        <span className="logo-mark" aria-hidden="true" />
        <a className="wordmark" href="#/">
          Coaching Copilot
        </a>

        {onMatchRoute ? (
          <a className="back-link" href="#/">
            ← All matches
          </a>
        ) : (
          <nav className="app-nav" aria-label="Sections">
            {SECTIONS.map((s) => (
              <a key={s.id} href={`#${s.id}`} aria-current={active === s.id ? "true" : undefined}>
                {s.label}
              </a>
            ))}
          </nav>
        )}

        <span className="header-spacer" />
        <ThemeToggle />
        <span className="sim-pill" title={sources ? `source: ${sources}` : undefined}>
          <span className="dot" aria-hidden="true" />
          SIM DATA
        </span>
      </div>
    </header>
  );
}
