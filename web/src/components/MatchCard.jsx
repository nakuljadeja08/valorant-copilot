/* Shared by the overview's recent strip and the Matches route. */

export default function MatchCard({ match: m }) {
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
