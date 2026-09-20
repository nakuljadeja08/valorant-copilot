import ThemeToggle from "./ThemeToggle.jsx";

/* The launcher rail. Rendered by the shell on every route, so the SIM DATA
   marker and the theme control are on screen wherever you are -- the honesty
   signal never scrolls away.

   A match belongs to the Matches section, so that item stays lit while you read
   one. Nav is a real <nav> of anchors: hash routes, so back/forward and
   open-in-new-tab work without JavaScript. */

const NAV = [
  {
    route: "",
    label: "Overview",
    icon: (
      <svg width="17" height="17" viewBox="0 0 17 17" fill="currentColor" aria-hidden="true">
        <rect x="0" y="0" width="7" height="7" />
        <rect x="10" y="0" width="7" height="7" />
        <rect x="0" y="10" width="7" height="7" />
        <rect x="10" y="10" width="7" height="7" />
      </svg>
    ),
  },
  {
    route: "matches",
    label: "Matches",
    icon: (
      <svg width="17" height="17" viewBox="0 0 17 17" fill="currentColor" aria-hidden="true">
        <rect x="0" y="2" width="17" height="3" />
        <rect x="0" y="7" width="12" height="3" />
        <rect x="0" y="12" width="15" height="3" />
      </svg>
    ),
  },
  {
    route: "agents",
    label: "Agent Pipeline",
    icon: (
      <svg width="17" height="17" viewBox="0 0 17 17" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        <circle cx="3.5" cy="8.5" r="2.4" />
        <circle cx="13.5" cy="3.5" r="2.4" />
        <circle cx="13.5" cy="13.5" r="2.4" />
        <path d="M5.6 7.2 L11.4 4.2 M5.6 9.8 L11.4 12.8" />
      </svg>
    ),
  },
  {
    route: "role",
    label: "Role Lens",
    icon: (
      <svg width="17" height="17" viewBox="0 0 17 17" fill="currentColor" aria-hidden="true">
        <path d="M8.5 0 L11 6 L8.5 8.5 L6 6 Z" />
        <path d="M17 8.5 L11 11 L8.5 8.5 L11 6 Z" />
        <path d="M8.5 17 L6 11 L8.5 8.5 L11 11 Z" />
        <path d="M0 8.5 L6 6 L8.5 8.5 L6 11 Z" />
      </svg>
    ),
  },
];

export default function SideRail({ route, provenance, onReplayIntro }) {
  const onMatch = route.startsWith("match/");
  const active = onMatch ? "matches" : route;
  const sources = provenance?.sources?.join(" · ");

  return (
    <aside className="rail">
      <div className="rail-edge" aria-hidden="true" />

      <a className="rail-logo" href="#/">
        <span className="rail-mark" aria-hidden="true" />
        <span className="rail-word">
          Coaching
          <br />
          <span className="wordmark-accent">Copilot</span>
        </span>
      </a>

      <div className="rail-sep" aria-hidden="true" />

      <nav className="rail-nav" aria-label="Sections">
        {NAV.map((n) => (
          <a
            key={n.route}
            href={`#/${n.route}`}
            aria-current={active === n.route ? "page" : undefined}
          >
            <span className="rail-nav-bar" aria-hidden="true" />
            <span className="rail-nav-icon">{n.icon}</span>
            <span className="rail-nav-label">{n.label}</span>
          </a>
        ))}
      </nav>

      <div className="rail-foot">
        <div className="rail-sim" title={sources ? `source: ${sources}` : undefined}>
          <span className="rail-sim-dot" aria-hidden="true" />
          <span>
            SIM DATA
            {sources && (
              <>
                <br />
                <span className="rail-sim-src">source: {sources}</span>
              </>
            )}
          </span>
        </div>
        <div className="rail-actions">
          <ThemeToggle />
          <button
            type="button"
            className="rail-help"
            title="Replay intro"
            aria-label="Replay the intro"
            onClick={onReplayIntro}
          >
            ?
          </button>
        </div>
      </div>
    </aside>
  );
}
