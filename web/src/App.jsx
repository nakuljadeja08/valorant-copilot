import { useEffect, useState } from "react";

import { useJson, useRoute } from "./lib/data.js";
import SideRail from "./components/SideRail.jsx";
import TopBar from "./components/TopBar.jsx";
import Onboarding from "./components/Onboarding.jsx";
import ProvenanceBanner from "./components/ProvenanceBanner.jsx";
import OverviewView from "./components/OverviewView.jsx";
import AgentsView from "./components/AgentsView.jsx";
import MatchesView from "./components/MatchesView.jsx";
import MatchView from "./components/MatchView.jsx";
import RoleLensView from "./components/RoleLensView.jsx";

const ONBOARD_KEY = "vcp-onboarded";

export default function App() {
  const route = useRoute();
  const { data: index, error } = useJson("index.json");

  const matchId = route.startsWith("match/") ? route.slice("match/".length) : null;

  // First-run overlay. Default closed so a returning visitor never sees a flash;
  // the effect opens it once, unless a prior dismissal was stored.
  const [onboard, setOnboard] = useState(false);
  useEffect(() => {
    try {
      if (localStorage.getItem(ONBOARD_KEY) !== "1") setOnboard(true);
    } catch {
      setOnboard(true);
    }
  }, []);

  const closeOnboard = () => {
    try {
      localStorage.setItem(ONBOARD_KEY, "1");
    } catch {
      // Private mode throws on write; the overlay still closes for this view.
    }
    setOnboard(false);
  };

  return (
    <div className="app">
      {onboard && <Onboarding onClose={closeOnboard} />}

      {/* The rail and top bar are the shell, so provenance and the SIM DATA
          marker are on every route by construction. */}
      <SideRail
        route={route}
        provenance={index?.provenance}
        onReplayIntro={() => setOnboard(true)}
      />

      <div className="main-col">
        <TopBar
          route={route}
          matchId={matchId}
          season={index?.season}
          matches={index?.matches}
        />
        <ProvenanceBanner provenance={index?.provenance} />

        <main className="content">
          {error && (
            <p className="empty">
              Could not load the match bundles ({String(error.message)}). Run{" "}
              <code>python -m src.export.bundle</code> to generate them.
            </p>
          )}
          {!index && !error && <p className="empty">Loading…</p>}
          {index && <Route route={route} matchId={matchId} index={index} />}
        </main>
      </div>
    </div>
  );
}

function Route({ route, matchId, index }) {
  if (matchId) return <MatchView matchId={matchId} />;
  if (route === "agents") return <AgentsView season={index.season} />;
  if (route === "matches") return <MatchesView index={index} />;
  if (route === "role") return <RoleLensView index={index} />;
  return <OverviewView index={index} />;
}
