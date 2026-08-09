/* Extracted from MatchView, unchanged in substance. */

export default function Scoreboard({ players, heroTeam }) {
  return (
    <section className="panel section">
      <div className="panel-head">
        <h2 className="section-title">Scoreboard</h2>
        <span className="panel-meta">
          {heroTeam ? `${heroTeam} is your side` : "no focal player recorded"}
        </span>
      </div>
      <p className="footnote" style={{ marginTop: 0, marginBottom: 10 }}>
        Agents resolved from real val-content-v1 UUIDs. Player identifiers are simulator UUIDs —
        no real account is represented.
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
