import { useMemo, useState } from "react";

import { fmt, pct } from "../lib/data.js";
import AgentFeed from "./AgentFeed.jsx";
import AgentPipeline from "./AgentPipeline.jsx";
import BuyTypeBars from "./BuyTypeBars.jsx";
import Tile from "./Tile.jsx";
import TrendChart from "./TrendChart.jsx";

const FILTERS = [
  { id: "all", label: "All", test: () => true },
  { id: "wins", label: "Wins", test: (m) => m.winner === m.hero_team },
  { id: "losses", label: "Losses", test: (m) => m.winner && m.winner !== m.hero_team },
  { id: "critical", label: "Has critical", test: (m) => (m.severities?.critical ?? 0) > 0 },
];

export default function HomeView({ index }) {
  const { matches, season } = index;
  const [filter, setFilter] = useState("all");
  const [map, setMap] = useState("all");

  const maps = useMemo(
    () => [...new Set(matches.map((m) => m.map_name))].sort(),
    [matches],
  );

  const shown = useMemo(() => {
    const test = FILTERS.find((f) => f.id === filter).test;
    return matches.filter((m) => test(m) && (map === "all" || m.map_name === map));
  }, [matches, filter, map]);

  const record = season?.record;
  const perspective = season?.perspective === "hero" ? "your" : "Blue's";

  return (
    <>
      <div className="section" id="overview">
        <header className="page-head">
          <h1 className="page-title">Last {index.match_count} matches</h1>
          <p className="lede" style={{ margin: 0 }}>
            Competitive · {index.provenance?.sources?.join(" · ") ?? "simulated"} val-match-v1
            {season?.perspective !== "hero" && " · no focal player recorded, showing Blue"}
          </p>
        </header>

        {season && (
          <div className="kpi-grid">
            <Tile
              label="Record"
              value={`${record.wins}–${record.losses}`}
              foot={`${pct(season.win_rate)} win rate`}
              tone={season.win_rate >= 0.5 ? "good" : "bad"}
            />
            <Tile
              label="Force-buy rate"
              value={pct(season.force_rate)}
              foot={
                season.force_rate > season.force_line
                  ? "past the habit line"
                  : "under the habit line"
              }
              tone={season.force_rate > season.force_line ? "warn" : "neutral"}
            />
            <Tile
              label="Broken buys"
              value={fmt(season.broken_buys)}
              foot="funded, never made"
              tone="bad"
              alert
            />
            <Tile
              label="Kill share"
              value={pct(season.kill_share_sim_approx)}
              foot="sim-approx"
              tone={season.kill_share_sim_approx >= 0.5 ? "good" : "neutral"}
            />
            <Tile
              label="Full-buy conversion"
              value={pct(season.buy_type_win_rate?.full?.rate)}
              foot={`${season.buy_type_win_rate?.full?.won} / ${season.buy_type_win_rate?.full?.rounds} rounds`}
              tone="good"
            />
            <Tile
              label="Critical findings"
              value={fmt(season.critical_findings)}
              foot={`${fmt(season.verified_claims)} verified claims`}
            />
          </div>
        )}

        <p className="footnote">
          Every number above is {perspective} side, recomputed from the same rows the match
          views cite. Kill share stands in for trade efficiency — the simulator emits no death
          timestamps.
        </p>
      </div>

      {season && (
        <div className="section overview-charts">
          <TrendChart matches={matches} threshold={season.force_line} />
          <BuyTypeBars byBuyType={season.buy_type_win_rate} />
        </div>
      )}

      <AgentPipeline season={season} findings={season?.findings} />
      <AgentFeed findings={season?.findings} />

      <div className="section" id="matches">
        <div className="panel-head">
          <h2 className="section-title">Matches — with the verdict up front</h2>
          <span className="panel-meta">
            {shown.length} of {matches.length}
          </span>
        </div>

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

function MatchCard({ match: m }) {
  const team = m.hero_team || "Blue";
  const other = team === "Red" ? "Blue" : "Red";
  const won = m.winner === team;
  const outcome = !m.winner ? "draw" : won ? "win" : "loss";
  const crit = m.severities?.critical ?? 0;
  const warn = m.severities?.warning ?? 0;

  return (
    <a className={`match-card ${outcome}`} href={`#/match/${m.match_id}`}>
      <span className="match-map">{m.map_name}</span>
      <span className={`match-score ${won ? "tone-good" : m.winner ? "tone-bad" : ""}`}>
        {outcome === "draw" ? "D" : won ? "W" : "L"} {m.score[team]}–{m.score[other]}
      </span>
      <span className="match-verdict">{m.verdict}</span>
      {crit > 0 ? (
        <span className="badge sev-critical">{crit} CRIT</span>
      ) : warn > 0 ? (
        <span className="badge sev-warning">{warn} WARN</span>
      ) : (
        <span className="badge neutral">{m.verified_claims} CLAIMS</span>
      )}
    </a>
  );
}
