import { useJson, useRoute } from "./lib/data.js";
import AppHeader from "./components/AppHeader.jsx";
import ProvenanceBanner from "./components/ProvenanceBanner.jsx";
import HomeView from "./components/HomeView.jsx";
import MatchView from "./components/MatchView.jsx";

export default function App() {
  const route = useRoute();
  const { data: index, error } = useJson("index.json");

  const matchId = route.startsWith("match/") ? route.slice("match/".length) : null;

  return (
    <>
      {/* Both are rendered by the shell, so provenance and the data-source pill
          are on every route by construction. */}
      <AppHeader provenance={index?.provenance} onMatchRoute={Boolean(matchId)} />
      <ProvenanceBanner provenance={index?.provenance} />
      <main className="shell">
        {error && (
          <p className="empty">
            Could not load the match bundles ({String(error.message)}). Run{" "}
            <code>python -m src.export.bundle</code> to generate them.
          </p>
        )}
        {!index && !error && <p className="empty">Loading…</p>}
        {index && (matchId ? <MatchView matchId={matchId} /> : <HomeView index={index} />)}
      </main>
    </>
  );
}
