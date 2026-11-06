import { useEffect, useMemo, useState } from "react";

import { useJson } from "../../lib/data.js";
import { STATE_VERSION, newState, weekList } from "../../lib/fantasy.js";
import FantasyHub from "./FantasyHub.jsx";
import FantasyLanding from "./FantasyLanding.jsx";
import FantasyPlayer from "./FantasyPlayer.jsx";
import FantasyRules from "./FantasyRules.jsx";
import FantasyWeek from "./FantasyWeek.jsx";
import SquadBuilder from "./SquadBuilder.jsx";

/* The fantasy game. Everything is static: season data comes from the bundles that
   src/fantasy/export.py writes, and a manager's season lives in localStorage, the
   same way the onboarding flag does. No account, no backend, nothing to send.

   Sub-routes:
     fantasy                 hub, or the landing page before a region is picked
     fantasy/squad           build and lock this match week's squad
     fantasy/week/<key>      one played week's points, each opening its trace
     fantasy/player/<id>     one player or coach
     fantasy/rules           scoring, squad rules and the assumed formats */

const STORE_KEY = "vcp-fantasy";

function readState() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(STORE_KEY));
    return raw?.version === STATE_VERSION ? raw : null;
  } catch {
    return null;
  }
}

function useSeasonState() {
  const [state, setState] = useState(null);
  useEffect(() => setState(readState()), []);
  const save = (next) => {
    setState(next);
    try {
      if (next) window.localStorage.setItem(STORE_KEY, JSON.stringify(next));
      else window.localStorage.removeItem(STORE_KEY);
    } catch {
      // Private mode throws on write; the season still plays for this visit.
    }
  };
  return [state, save];
}

/** Names and teams for every entity, so views never show a raw id. */
function directory(season) {
  const teams = Object.fromEntries(season.teams.map((t) => [t.team_id, t]));
  const people = {};
  for (const p of season.players) {
    people[p.puuid] = { id: p.puuid, handle: p.handle, kind: "player", role: p.base_role, region: p.region };
  }
  for (const c of season.coaches) {
    people[c.coach_id] = { id: c.coach_id, handle: c.handle, kind: "coach", team_id: c.team_id, role: null };
  }
  return { teams, people };
}

const SUBNAV = [
  ["fantasy", "Home"],
  ["fantasy/squad", "Squad"],
  ["fantasy/rules", "Rules"],
];

export default function FantasyView({ route }) {
  const { data: season, error } = useJson("fantasy/season.json");
  const { data: rivals } = useJson("fantasy/rivals.json");
  const [state, setState] = useSeasonState();

  const dir = useMemo(() => (season ? directory(season) : null), [season]);
  const weeks = useMemo(() => (season ? weekList(season) : []), [season]);

  if (error) {
    return (
      <p className="empty">
        Could not load the fantasy bundles ({String(error.message)}). Run{" "}
        <code>python -m src.fantasy.export</code> to generate them.
      </p>
    );
  }
  if (!season || !rivals) return <p className="empty">Loading…</p>;

  const sub = route.slice("fantasy".length).replace(/^\//, "");
  const ctx = { season, rivals, state, setState, dir, weeks };

  let body;
  if (sub === "rules") body = <FantasyRules {...ctx} />;
  else if (sub.startsWith("player/")) body = <FantasyPlayer {...ctx} entity={sub.slice(7)} />;
  else if (!state) body = <FantasyLanding {...ctx} onStart={(region) => setState(newState(region))} />;
  else if (sub === "squad") body = <SquadBuilder {...ctx} />;
  else if (sub.startsWith("week/")) body = <FantasyWeek {...ctx} weekKey={sub.slice(5)} />;
  else body = <FantasyHub {...ctx} />;

  const current = sub.startsWith("week/") || sub.startsWith("player/") ? null : `fantasy${sub ? `/${sub}` : ""}`;

  return (
    <div className="fx">
      <nav className="chip-row fx-subnav" aria-label="Fantasy">
        {SUBNAV.map(([r, label]) => (
          <a key={r} className="chip" href={`#/${r}`} aria-current={current === r ? "page" : undefined}>
            {label}
          </a>
        ))}
        <span className="fx-subnav-note">Simulated season · fictional teams and players</span>
      </nav>

      {body}

      <footer className="fx-legal">
        <p>
          Fantasy VALORANT is a fan-made concept built on a simulated season. Every team, player,
          coach and rival manager here is fictional, and no real pro data is used. It's free to play
          and has no prizes.
        </p>
        <p>
          Coaching Copilot was created under Riot Games' "Legal Jibber Jabber" policy using assets
          owned by Riot Games. Riot Games does not endorse or sponsor this project.
        </p>
      </footer>
    </div>
  );
}
