import { useJson } from "../lib/data.js";
import RolePanel from "./RolePanel.jsx";

/* The standalone Role Lens route. The role layer is otherwise only reachable
   from inside a match; promoting it to its own destination gives the
   role-relative read a home. It is grounded in the most recent match's bundle
   -- the same rows that match's own role tab cites -- rather than a synthetic
   season aggregate, so every percentile here is real and traceable. */

export default function RoleLensView({ index }) {
  const latest = index.matches[0];
  const { data, error } = useJson(`match/${encodeURIComponent(latest.match_id)}.json`);

  return (
    <>
      <header className="page-head">
        <div className="accent-rule">
          <h1 className="page-title">Role lens</h1>
          <p className="lede" style={{ margin: "6px 0 0" }}>
            Role-relative, never cross-role. A Sentinel is not a weak Duelist because their
            first-blood rate is low. Every player is scored against role-appropriate expectations
            and a peer distribution of same-role players.
          </p>
        </div>
      </header>

      <p className="footnote" style={{ marginBottom: 14 }}>
        Reading the most recent match — {latest.map_name}. Open any match and switch to the role
        lens for that game's breakdown.
      </p>

      {error && <p className="empty">No bundle for {latest.map_name}.</p>}
      {!data && !error && <p className="empty">Loading role lens…</p>}
      {data && !data.role && (
        <p className="empty">This match has no role layer. Re-export the bundles to add it.</p>
      )}
      {data?.role && <RolePanel role={data.role} />}
    </>
  );
}
