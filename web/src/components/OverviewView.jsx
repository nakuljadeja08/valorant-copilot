import { fmt, pct } from "../lib/data.js";
import BuyTypeBars from "./BuyTypeBars.jsx";
import MatchCard from "./MatchCard.jsx";
import Tile from "./Tile.jsx";
import TrendChart from "./TrendChart.jsx";

const BASE = import.meta.env.BASE_URL;
const RECENT = 4;

export default function OverviewView({ index }) {
  const { matches, season } = index;
  const perspective = season?.perspective === "hero" ? "your" : "Blue's";
  const sources = index.provenance?.sources?.join(" · ") ?? "simulated";

  return (
    <>
      <header className="hero">
        <img
          className="hero-art"
          src={`${BASE}assets/keyart-arrival.jpg`}
          alt=""
          aria-hidden="true"
        />
        <div className="hero-veil" aria-hidden="true" />
        <div className="hero-body">
          <div className="hero-eyebrow">
            Competitive · {sources} · {index.match_count} matches
            {season?.perspective !== "hero" && " · no focal player recorded, showing Blue"}
          </div>
          <h1 className="hero-title">
            Last {index.match_count}
            <br />
            matches
          </h1>
          <div className="hero-slash" aria-hidden="true" />
          <p className="hero-lede">
            Every number is {perspective === "your" ? "your" : "Blue's"} side, recomputed from the
            same rows the match views cite. Kill share stands in for trade efficiency — the
            simulator emits no death timestamps.
          </p>
        </div>
      </header>

      {season && (
        <div className="section">
          <div className="kpi-grid">
            <Tile
              label="Record"
              value={`${season.record.wins}–${season.record.losses}`}
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

          <p className="footnote">
            Every number above is {perspective} side, recomputed from the same rows the match
            views cite. Kill share stands in for trade efficiency — the simulator emits no
            death timestamps.
          </p>
        </div>
      )}

      {season && (
        <div className="section overview-charts">
          <TrendChart matches={matches} threshold={season.force_line} />
          <BuyTypeBars byBuyType={season.buy_type_win_rate} />
        </div>
      )}

      <div className="section">
        <div className="panel-head">
          <h2 className="section-title">Recent matches</h2>
          <a className="panel-meta" href="#/matches">
            All {matches.length} matches →
          </a>
        </div>
        <div className="match-grid">
          {matches.slice(0, RECENT).map((m) => (
            <MatchCard key={m.match_id} match={m} />
          ))}
        </div>
      </div>
    </>
  );
}
