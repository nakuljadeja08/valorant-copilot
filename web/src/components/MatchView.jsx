import { useJson } from "../lib/data.js";
import RoundTimeline from "./RoundTimeline.jsx";
import EconomyChart from "./EconomyChart.jsx";
import DebriefPanel from "./DebriefPanel.jsx";

const pct = (v) => (v === undefined || v === null ? "—" : `${Math.round(v * 100)}%`);

export default function MatchView({ matchId }) {
  const { data, error } = useJson(`match/${encodeURIComponent(matchId)}.json`);

  if (error) return <p className="empty">No bundle for match {matchId}.</p>;
  if (!data) return <p className="empty">Loading match…</p>;

  const { match, rounds, players, match_features: mf, debrief, trace, excluded } = data;
  const pivotalRound = mf.pivotal_round ?? null;

  return (
    <>
      <a className="back" href="#/">
        ← All matches
      </a>

      <header className="page-head">
        <p className="eyebrow">
          {match.map_name} · {match.queue_id} · {match.rounds} rounds
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <span className="key-dot blue" aria-hidden="true" />
          <span className="hero">{match.score.Blue}</span>
          <span className="hero" style={{ color: "var(--muted)" }}>
            –
          </span>
          <span className="hero">{match.score.Red}</span>
          <span className="key-dot red" aria-hidden="true" />
          <span style={{ color: "var(--ink-2)" }}>
            {match.winner ? `${match.winner} won` : "drawn"}
          </span>
        </div>
        <p className="match-id" style={{ marginTop: 10 }}>
          {match.match_id} · source: {match.source}
        </p>
      </header>

      <div className="kpi-row">
        <Stat label="Pivotal round" value={pivotalRound === null ? "—" : `R${pivotalRound}`} />
        <Stat label="Win swing at pivot" value={pct(mf.pivotal_round_swing)} />
        <Stat label="Blue post-plant conversion" value={pct(mf["win_after_plant:Blue"])} />
        <Stat label="Red post-plant conversion" value={pct(mf["win_after_plant:Red"])} />
      </div>

      <RoundTimeline rounds={rounds} pivotalRound={pivotalRound} />
      <EconomyChart rounds={rounds} pivotalRound={pivotalRound} />
      <DebriefPanel debrief={debrief} trace={trace} excluded={excluded} />
      <Scoreboard players={players} />
    </>
  );
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  );
}

function Scoreboard({ players }) {
  return (
    <section className="card">
      <div className="card-head">
        <h2 style={{ fontSize: 15 }}>Scoreboard</h2>
      </div>
      <p className="card-sub">
        Agents resolved from real val-content-v1 UUIDs. Player identifiers are simulator
        UUIDs — no real account is represented.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Team</th>
              <th scope="col" className="tl">
                Agent
              </th>
              <th scope="col">Score</th>
              <th scope="col">K</th>
              <th scope="col">D</th>
              <th scope="col">A</th>
            </tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={p.puuid}>
                <td>
                  <span className="key">
                    <span
                      className={`key-dot ${p.team_id === "Blue" ? "blue" : "red"}`}
                      aria-hidden="true"
                    />
                    {p.team_id}
                  </span>
                </td>
                <td className="tl">{p.agent_name}</td>
                <td>{p.score?.toLocaleString("en-US")}</td>
                <td>{p.kills}</td>
                <td>{p.deaths}</td>
                <td>{p.assists}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
