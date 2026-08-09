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
  { id: "matches", label: "Matches" },
  { id: "agents", label: "Agents" },
];

export default function AppHeader({ provenance, onMatchRoute }) {
  const sources = provenance?.sources?.join(" · ");

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
            {SECTIONS.map((s, i) => (
              <a key={s.id} href={`#${s.id}`} aria-current={i === 0 ? "true" : undefined}>
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
