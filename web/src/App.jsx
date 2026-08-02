import { useJson, useRoute } from "./lib/data.js";
import ProvenanceBanner from "./components/ProvenanceBanner.jsx";
import MatchList from "./components/MatchList.jsx";
import MatchView from "./components/MatchView.jsx";

export default function App() {
  const route = useRoute();
  const { data: index, error } = useJson("index.json");

  const matchId = route.startsWith("match/") ? route.slice("match/".length) : null;

  return (
    <>
      {/* Rendered by the shell, so provenance is on every route by construction. */}
      <ProvenanceBanner provenance={index?.provenance} />
      <main className="shell">
        {error && (
          <p className="empty">
            Could not load the match bundles ({String(error.message)}). Run{" "}
            <code>python -m src.export.bundle</code> to generate them.
          </p>
        )}
        {!index && !error && <p className="empty">Loading…</p>}
        {index && (matchId ? <MatchView matchId={matchId} /> : <MatchList index={index} />)}
      </main>
    </>
  );
}
