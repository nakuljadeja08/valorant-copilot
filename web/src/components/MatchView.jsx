import { fmt, heroTeam, otherTeam, pct, useJson } from "../lib/data.js";
import DebriefPanel from "./DebriefPanel.jsx";
import EconomyChart from "./EconomyChart.jsx";
import MomentumChart from "./MomentumChart.jsx";
import RoundTimeline from "./RoundTimeline.jsx";
import Scoreboard from "./Scoreboard.jsx";

export default function MatchView({ matchId }) {
  const { data, error } = useJson(`match/${encodeURIComponent(matchId)}.json`);

  if (error) return <p className="empty">No bundle for match {matchId}.</p>;
  if (!data) return <p className="empty">Loading match…</p>;

  const { match, rounds, players, match_features: mf, debrief, trace, excluded } = data;
  const pivotalRound = mf.pivotal_round ?? null;
  const team = heroTeam(match);
  const foe = otherTeam(team);

  const won = match.winner === team;
  const outcome = !match.winner ? "draw" : won ? "win" : "loss";

  const stats = matchStats(rounds, team);
  const foeStats = matchStats(rounds, foe);
  const postPlant = mf[`win_after_plant:${team}`];

  return (
    <>
      <div className="section">
        <p className="eyebrow" style={{ marginBottom: 8 }}>
          {match.map_name} · {match.queue_id} · {match.rounds} rounds
          {match.hero_team ? "" : " · no focal player recorded, showing Blue"}
        </p>

        <div className="match-hero">
          <span className={`result-badge ${outcome}`}>
            {outcome === "draw" ? "Draw" : won ? "Win" : "Loss"}
          </span>
          <h1 className="match-hero-title">
            {match.map_name}{" "}
            <span className="score">
              {match.score[team]}–{match.score[foe]}
            </span>
          </h1>

          <div className="hero-stats">
            <div>
              <div className="eyebrow">Pivotal</div>
              <div className="hero-stat-value">
                {pivotalRound === null ? "—" : `R${pivotalRound}`}
                {mf.pivotal_round_swing !== undefined && (
                  <span className="tone-muted"> · {pct(mf.pivotal_round_swing)}</span>
                )}
              </div>
            </div>
            <div>
              <div className="eyebrow">Force rate</div>
              <div
                className={`hero-stat-value ${stats.forceRate > 0.3 ? "tone-bad" : ""}`}
              >
                {pct(stats.forceRate)}
              </div>
            </div>
            <div>
              <div className="eyebrow">Broken buys</div>
              <div className={`hero-stat-value ${stats.broken > 0 ? "tone-bad" : ""}`}>
                {stats.broken}
              </div>
            </div>
            <div>
              <div className="eyebrow">Post-plant</div>
              <div
                className={`hero-stat-value ${postPlant >= 0.5 ? "tone-good" : postPlant === undefined ? "" : "tone-bad"}`}
              >
                {pct(postPlant)}
              </div>
            </div>
          </div>
        </div>

        <p className="match-summary">
          {summarize({ team, outcome, stats, postPlant, pivotalRound, swing: mf.pivotal_round_swing })}
        </p>
      </div>

      <MomentumChart
        rounds={rounds}
        pivotalRound={pivotalRound}
        team={team}
        proxyNote={data.provenance?.proxy_note}
      />

      <div className="section two-col">
        <div className="verdict-card good">
          <div className="verdict-head tone-good">
            <span className="diamond" style={{ background: "var(--good)" }} aria-hidden="true" />
            What went right
          </div>
          <div className="verdict-row">
            <span>Full buys converted</span>
            <span className="mono tone-good">
              {stats.byBuy.full.won}/{stats.byBuy.full.rounds}
            </span>
          </div>
          <div className="verdict-row">
            <span>Eco rounds stolen</span>
            <span className="mono tone-good">
              {stats.byBuy.eco.won}/{stats.byBuy.eco.rounds}
            </span>
          </div>
          <div className="verdict-row">
            <span>Post-plant conversion</span>
            <span className="mono tone-good">{pct(postPlant)}</span>
          </div>
        </div>

        <div className="verdict-card bad">
          <div className="verdict-head tone-bad">
            <span className="diamond" style={{ background: "var(--bad)" }} aria-hidden="true" />
            What went wrong
          </div>
          <div className="verdict-row">
            <span>
              Broken buys
              {stats.brokenRounds.length > 0 &&
                ` (${stats.brokenRounds.map((r) => `R${r}`).join(", ")})`}
            </span>
            <span className="mono tone-bad">{stats.broken}</span>
          </div>
          <div className="verdict-row">
            <span>Force-buy rate</span>
            <span className="mono tone-bad">{pct(stats.forceRate)}</span>
          </div>
          <div className="verdict-row">
            <span>Kill share (sim-approx)</span>
            <span className={`mono ${stats.killShare < 0.5 ? "tone-bad" : "tone-good"}`}>
              {pct(stats.killShare)}
            </span>
          </div>
        </div>
      </div>

      <DebriefPanel debrief={debrief} trace={trace} excluded={excluded} />
      <RoundTimeline rounds={rounds} pivotalRound={pivotalRound} />
      <EconomyChart rounds={rounds} pivotalRound={pivotalRound} />
      <Scoreboard players={players} heroTeam={match.hero_team} />

      <p className="footnote">
        {match.match_id} · source: {match.source}
        {foeStats.broken > 0 && ` · ${foe} broke ${foeStats.broken} of its own buys`}
      </p>
    </>
  );
}

/** Per-match aggregates for one side, from the round list already in the bundle
 *  — the same derivation `_force_rate` and `_season` use server-side. */
function matchStats(rounds, team) {
  const byBuy = {
    full: { rounds: 0, won: 0 },
    half: { rounds: 0, won: 0 },
    force: { rounds: 0, won: 0 },
    eco: { rounds: 0, won: 0 },
  };
  const brokenRounds = [];
  const shares = [];

  for (const r of rounds) {
    const econ = r.economy?.[team] ?? {};
    if (econ.buy_type && byBuy[econ.buy_type]) {
      byBuy[econ.buy_type].rounds += 1;
      if (r.winning_team === team) byBuy[econ.buy_type].won += 1;
    }
    if (econ.broken_buy === 1) brokenRounds.push(r.round_num);
    if (econ.kill_share_sim_approx !== null && econ.kill_share_sim_approx !== undefined) {
      shares.push(econ.kill_share_sim_approx);
    }
  }

  const played = Object.values(byBuy).reduce((s, b) => s + b.rounds, 0);
  return {
    byBuy,
    brokenRounds,
    broken: brokenRounds.length,
    forceRate: played ? byBuy.force.rounds / played : null,
    killShare: shares.length ? shares.reduce((a, b) => a + b, 0) / shares.length : null,
  };
}

/** One sentence, assembled only from values present in the bundle. */
function summarize({ team, outcome, stats, postPlant, pivotalRound, swing }) {
  const parts = [];
  if (stats.byBuy.full.rounds) {
    parts.push(
      `${team} converted ${stats.byBuy.full.won} of ${stats.byBuy.full.rounds} full buys`,
    );
  }
  if (stats.broken) {
    // "broke N more" would read as N more *full* buys, which is not what a
    // broken buy is.
    parts.push(`broke ${stats.broken} ${stats.broken === 1 ? "buy" : "buys"}`);
  }
  if (pivotalRound !== null && swing !== undefined) {
    parts.push(`and the match turned on R${pivotalRound}`);
  }
  const lead =
    outcome === "win" ? "Won it" : outcome === "loss" ? "Lost it" : "Drew it";
  return `${lead}: ${parts.join(", ")}.`;
}
