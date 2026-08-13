import { ordinal, pct } from "../lib/data.js";
import DebriefPanel from "./DebriefPanel.jsx";

/* The role layer (R4): each player scored *within their role*, never across
 * roles. Percentiles are oriented so higher always reads better; the inverted
 * metric (first death) is already flipped server-side. */

const ROLE_LABEL = {
  duelist: "Duelist",
  initiator: "Initiator",
  controller: "Controller",
  sentinel: "Sentinel",
};

const FEATURE_LABEL = {
  first_contact_rate: "First contact",
  entry_success_rate: "Entry success",
  first_death_rate: "First death",
  entry_trade_rate: "Entry traded",
  multikill_rate: "Multikills",
  assist_rate: "Assists",
  survival_rate: "Survival",
  utility_per_round: "Utility / round",
};

// A percentile's tone: strong / weak / middling within the role.
function tone(p) {
  if (p === null || p === undefined) return "var(--ink-faint)";
  if (p >= 60) return "var(--good)";
  if (p < 25) return "var(--bad)";
  return "var(--warn)";
}

function formatValue(f) {
  return f.name === "utility_per_round" ? f.value.toFixed(2) : pct(f.value);
}

function RoleCard({ player }) {
  return (
    <article className="panel section role-card">
      <div className="panel-head">
        <h3 className="section-title" style={{ marginBottom: 0 }}>
          {player.agent_name}
          {player.is_hero && <span className="tag" style={{ marginLeft: 8 }}>you</span>}
        </h3>
        <span className="badge neutral">{ROLE_LABEL[player.role] ?? player.role}</span>
      </div>

      <p className="match-summary" style={{ marginTop: 0 }}>{player.verdict}</p>

      <div className="bar-list">
        {player.features.map((f) => (
          <div key={f.name}>
            <div className="bar-head">
              <span>
                {FEATURE_LABEL[f.name] ?? f.name}
                {f.inverted && <span className="tone-muted"> · low is good</span>}
                {f.role_approx && <span className="badge neutral role-approx-badge">role-approx</span>}
              </span>
              <span className="bar-value">
                {formatValue(f)} · {f.percentile === null ? "—" : ordinal(f.percentile)}
              </span>
            </div>
            <div className="bar-track" role="img"
                 aria-label={`${FEATURE_LABEL[f.name] ?? f.name}: ${f.percentile === null ? "no peers" : `${Math.round(f.percentile)}th percentile among ${player.role}s`}`}>
              <div className="bar-fill"
                   style={{ width: `${f.percentile ?? 0}%`, background: tone(f.percentile) }} />
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

function SynergyStrip({ synergy }) {
  const teams = Object.keys(synergy).sort();
  return (
    <section className="panel section">
      <div className="panel-head">
        <h2 className="section-title">Composition &amp; synergy</h2>
        <span className="panel-meta">role-relative, never cross-role</span>
      </div>
      <div className="two-col">
        {teams.map((team) => {
          const s = synergy[team];
          const sbe = s.support_before_entry;
          return (
            <div className="verdict-card" key={team}>
              <div className="verdict-head">
                <span className={`key-dot ${team === "Blue" ? "blue" : "red"}`} aria-hidden="true" />
                {team}
              </div>
              <div className="verdict-row">
                <span>Role balance (distinct roles)</span>
                <span className="mono">{s.role_balance ?? "—"} / 4</span>
              </div>
              <div className="verdict-row">
                <span>
                  Support before entry
                  <span className="badge neutral role-approx-badge">role-approx</span>
                </span>
                <span className={`mono ${sbe && sbe.value < 0.5 ? "tone-bad" : "tone-good"}`}>
                  {sbe ? pct(sbe.value) : "—"}
                </span>
              </div>
            </div>
          );
        })}
      </div>
      <p className="footnote">
        Support-before-entry is inferred from utility cast counts, not cast timings — the API
        exposes counts, not when a smoke or flash went down. Flagged <em>role-approx</em>: it is a
        proxy, not an observed sequence.
      </p>
    </section>
  );
}

export default function RolePanel({ role }) {
  // Hero first, then Blue, then Red; agents are unique per match so name is a stable key.
  const players = [...role.players].sort((a, b) => {
    if (a.is_hero !== b.is_hero) return a.is_hero ? -1 : 1;
    if (a.team_id !== b.team_id) return a.team_id < b.team_id ? -1 : 1;
    return a.agent_name < b.agent_name ? -1 : 1;
  });

  return (
    <>
      <p className="footnote" style={{ marginTop: 0 }}>
        Every number below is a percentile <em>within the player's own role</em>, scored against{" "}
        {role.baseline_matches} peers in baseline <span className="mono">{role.baseline_version}</span>.
        A Sentinel is never ranked against a Duelist.
      </p>

      <SynergyStrip synergy={role.synergy} />

      <div className="role-grid">
        {players.map((p) => (
          <RoleCard key={p.puuid} player={p} />
        ))}
      </div>

      <DebriefPanel debrief={role.debrief} trace={role.trace} excluded={[]} />
    </>
  );
}
