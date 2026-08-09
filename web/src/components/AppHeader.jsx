import ThemeToggle from "./ThemeToggle.jsx";

/* The app chrome. Rendered by the shell on every route, like the provenance
   banner beneath it, so the SIM DATA pill is on screen wherever you are. */

const NAV = [
  { route: "", label: "Overview" },
  { route: "agents", label: "Agents" },
  { route: "matches", label: "Matches" },
];

export default function AppHeader({ provenance, route }) {
  const sources = provenance?.sources?.join(" · ");
  // A match belongs to the Matches section, so the nav stays lit while you are
  // reading one -- and the back link points there rather than at the overview.
  const onMatch = route.startsWith("match/");
  const active = onMatch ? "matches" : route;

  return (
    <header className="app-header">
      <div className="app-header-inner">
        <span className="logo-mark" aria-hidden="true" />
        <a className="wordmark" href="#/">
          Coaching Copilot
        </a>

        <nav className="app-nav" aria-label="Sections">
          {NAV.map((n) => (
            <a
              key={n.route}
              href={`#/${n.route}`}
              aria-current={active === n.route ? "page" : undefined}
            >
              {n.label}
            </a>
          ))}
        </nav>

        {onMatch && (
          <a className="back-link" href="#/matches">
            ← All matches
          </a>
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
