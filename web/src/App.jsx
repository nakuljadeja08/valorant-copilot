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
import FantasyView from "./components/fantasy/FantasyView.jsx";

const ONBOARD_KEY = "vcp-onboarded";

export default function App() {
  const route = useRoute();
  const { data: index, error } = useJson("index.json");

  const matchId = route.startsWith("match/") ? route.slice("match/".length) : null;
  const fantasy = route === "fantasy" || route.startsWith("fantasy/");
  // The game carries its own provenance: a different simulated season, described
  // by the bundle it ships in.
  const { data: fantasySeason } = useJson(fantasy ? "fantasy/season.json" : null);
  const provenance = fantasy ? fantasySeason?.provenance : index?.provenance;

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
      {/* The coaching intro would talk over the fantasy pitch, so the game skips it. */}
      {onboard && !fantasy && <Onboarding onClose={closeOnboard} />}

      {/* The rail and top bar are the shell, so provenance and the SIM DATA
          marker are on every route by construction. */}
      <SideRail
        route={route}
        provenance={provenance}
        onReplayIntro={() => setOnboard(true)}
      />

      <div className="main-col">
        <TopBar
          route={route}
          matchId={matchId}
          season={fantasy ? null : index?.season}
          matches={index?.matches}
        />
        <ProvenanceBanner provenance={provenance} />

        <main className="content">
          {fantasy && <FantasyView route={route} />}
          {!fantasy && error && (
            <p className="empty">
              Could not load the match bundles ({String(error.message)}). Run{" "}
              <code>python -m src.export.bundle</code> to generate them.
            </p>
          )}
          {!fantasy && !index && !error && <p className="empty">Loading…</p>}
          {!fantasy && index && <Route route={route} matchId={matchId} index={index} />}
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
