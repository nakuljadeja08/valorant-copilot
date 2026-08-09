import { useMemo, useState } from "react";

import MatchCard from "./MatchCard.jsx";

const FILTERS = [
  { id: "all", label: "All", test: () => true },
  { id: "wins", label: "Wins", test: (m) => m.winner === m.hero_team },
  { id: "losses", label: "Losses", test: (m) => m.winner && m.winner !== m.hero_team },
  { id: "critical", label: "Has critical", test: (m) => (m.severities?.critical ?? 0) > 0 },
];

export default function MatchesView({ index }) {
  const { matches } = index;
  const [filter, setFilter] = useState("all");
  const [map, setMap] = useState("all");

  const maps = useMemo(() => [...new Set(matches.map((m) => m.map_name))].sort(), [matches]);

  const shown = useMemo(() => {
    const test = FILTERS.find((f) => f.id === filter).test;
    return matches.filter((m) => test(m) && (map === "all" || m.map_name === map));
  }, [matches, filter, map]);

  return (
    <>
      <header className="page-head">
        <h1 className="page-title">Matches</h1>
        <p className="lede" style={{ margin: 0 }}>
          The verdict up front, the trace one click in.
        </p>
      </header>

      <div className="section">
        <div className="chip-row" style={{ marginBottom: 14 }}>
          <span className="chip-label" id="filter-label">
            Filter
          </span>
          <span role="radiogroup" aria-labelledby="filter-label" className="chip-row">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                role="radio"
                className="chip"
                aria-checked={filter === f.id}
                onClick={() => setFilter(f.id)}
              >
                {f.label}
              </button>
            ))}
          </span>
          {/* A native select, restyled as a chip: keyboard and screen-reader
              behaviour for free, no custom listbox to get wrong. */}
          <select
            className="chip"
            value={map}
            aria-label="Filter by map"
            onChange={(e) => setMap(e.target.value)}
          >
            <option value="all">All maps</option>
            {maps.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <span className="panel-meta" style={{ marginLeft: "auto" }}>
            {shown.length} of {matches.length}
          </span>
        </div>

        <div className="match-grid">
          {shown.map((m) => (
            <MatchCard key={m.match_id} match={m} />
          ))}
        </div>
        {!shown.length && <p className="empty">No matches match that filter.</p>}
      </div>
    </>
  );
}
