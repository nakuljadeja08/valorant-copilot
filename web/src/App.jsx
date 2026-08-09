import { useJson, useRoute } from "./lib/data.js";
import AppHeader from "./components/AppHeader.jsx";
import ProvenanceBanner from "./components/ProvenanceBanner.jsx";
import OverviewView from "./components/OverviewView.jsx";
import AgentsView from "./components/AgentsView.jsx";
import MatchesView from "./components/MatchesView.jsx";
import MatchView from "./components/MatchView.jsx";

export default function App() {
  const route = useRoute();
  const { data: index, error } = useJson("index.json");

  const matchId = route.startsWith("match/") ? route.slice("match/".length) : null;

  return (
    <>
      {/* Both are rendered by the shell, so provenance and the data-source pill
          are on every route by construction. */}
      <AppHeader provenance={index?.provenance} route={route} />
      <ProvenanceBanner provenance={index?.provenance} />
      <main className="shell">
        {error && (
          <p className="empty">
            Could not load the match bundles ({String(error.message)}). Run{" "}
            <code>python -m src.export.bundle</code> to generate them.
          </p>
        )}
        {!index && !error && <p className="empty">Loading…</p>}
        {index && <Route route={route} matchId={matchId} index={index} />}
      </main>
    </>
  );
}

function Route({ route, matchId, index }) {
  if (matchId) return <MatchView matchId={matchId} />;
  if (route === "agents") return <AgentsView season={index.season} />;
  if (route === "matches") return <MatchesView index={index} />;
  return <OverviewView index={index} />;
}
