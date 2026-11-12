import { CHIP_LABEL } from "../../lib/fantasy.js";

/* The rules, read straight from the rules block that scored the season, so this page
   can't disagree with the points. */

const PLAYER_RULES = [
  ["kill", "Kill"],
  ["death", "Death"],
  ["first_kill", "First kill of a round"],
  ["first_death", "First death of a round"],
  ["map_win", "On the winning side of a map"],
];

const n = (v) => (v > 0 ? `+${v}` : String(v));

export default function FantasyRules({ season }) {
  const { player, coach, squad, transfers, chips } = season.rules;

  return (
    <>
      <header className="page-head">
        <div className="accent-rule">
          <div className="eyebrow">Rules version {season.rules_version}</div>
          <h1 className="page-title">How it works</h1>
        </div>
      </header>

      <div className="section fx-two">
        <div className="panel">
          <div className="section-title">Player points, per map</div>
          <table className="fx-table">
            <tbody>
              {PLAYER_RULES.map(([k, label]) => (
                <tr key={k}>
                  <td>{label}</td>
                  <td>{n(player[k])}</td>
                </tr>
              ))}
              {Object.entries(player.assist).map(([role, v]) => (
                <tr key={role}>
                  <td>Assist, playing {role}</td>
                  <td>{n(v)}</td>
                </tr>
              ))}
              {Object.entries(player.multikill).map(([k, v]) => (
                <tr key={k}>
                  <td>{k === "5" ? "Ace" : `${k} kills in a round`}</td>
                  <td>{n(v)}</td>
                </tr>
              ))}
              {Object.entries(player.clutch).map(([k, v]) => (
                <tr key={k}>
                  <td>Clutch 1v{k}</td>
                  <td>{n(v)}</td>
                </tr>
              ))}
              <tr>
                <td>Best in their role on the map</td>
                <td>{n(player.role_bonus[0])}</td>
              </tr>
            </tbody>
          </table>
          <p className="footnote">
            Role means the agent played on that map, so a flexing duelist competes with the
            sentinels when they play one.
          </p>
        </div>

        <div className="panel">
          <div className="section-title">Coach points, per series</div>
          <table className="fx-table">
            <tbody>
              <tr>
                <td>Map won</td>
                <td>{n(coach.map_win)}</td>
              </tr>
              <tr>
                <td>Series won</td>
                <td>{n(coach.series_win)}</td>
              </tr>
              <tr>
                <td>Upset: beat a team with a pricier roster</td>
                <td>{n(coach.upset)}</td>
              </tr>
              <tr>
                <td>Round difference across the series</td>
                <td>+1 per {coach.round_diff_divisor}</td>
              </tr>
            </tbody>
          </table>

          <div className="section-title fx-group">Squad</div>
          <ul className="fx-list">
            <li>
              {squad.starters} starters with at least one of each role, {squad.subs} subs in auto-sub
              order, {squad.coaches} coaches who both score.
            </li>
            <li>
              Budget {squad.budget.regional} credits at regional events, {squad.budget.international} at
              international ones, where the field is stronger.
            </li>
            <li>
              At most {squad.max_players_per_team} players and {squad.max_coaches_per_team} coach from
              one team.
            </li>
            <li>
              The captain scores ×{squad.captain_multiplier}. If they play no map, the vice-captain
              does instead.
            </li>
            <li>A starter who plays no map that week is replaced by the first sub who did.</li>
          </ul>

          <div className="section-title fx-group">Transfers and chips</div>
          <ul className="fx-list">
            <li>Each event opens with a free rebuild.</li>
            <li>
              After that, {transfers.free_per_week} free transfer a week, banking up to{" "}
              {transfers.max_banked}. Each extra costs {transfers.hit} points.
            </li>
            <li>
              {CHIP_LABEL.triple_captain}: the captain scores ×
              {chips.triple_captain.captain_multiplier} for a week. {CHIP_LABEL.bench_boost}: both subs
              score too. Each once before{" "}
              {season.events.find((e) => e.event_id === chips.second_half_from)?.name} and once from it
              on.
            </li>
          </ul>
        </div>
      </div>

      <div className="section panel">
        <div className="section-title">The season</div>
        <div className="table-scroll">
          <table className="fx-table">
            <thead>
              <tr>
                <th className="tl">Event</th>
                <th className="tl">Dates</th>
                <th className="tl">Pick from</th>
                <th className="tl">Format</th>
              </tr>
            </thead>
            <tbody>
              {season.events.map((e) => (
                <tr key={e.event_id}>
                  <td className="tl">{e.name}</td>
                  <td className="tl">
                    {e.starts_on} to {e.ends_on}
                  </td>
                  <td className="tl">{e.kind === "international" ? "Any qualified team" : "Home region"}</td>
                  <td className="tl">{e.assumed ? <span className="tone-warn">Assumed</span> : "Announced"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="footnote">
          Dates and cities follow Riot's announced 2027 calendar. Where Riot hasn't published a format
          or field, the simulator assumes one, and it's marked here.
        </p>
      </div>

      <div className="section panel">
        <div className="section-title">About the data</div>
        <p className="lede">{season.provenance.detail}</p>
      </div>
    </>
  );
}
