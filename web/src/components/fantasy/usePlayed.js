import { useEffect, useState } from "react";

import { loadJson } from "../../lib/data.js";

/** Points files for the weeks already played, keyed by week. Only played weeks are
 *  loaded, so nothing on screen gives away a result the replay hasn't reached. */
export function usePlayedWeeks(keys) {
  const [weeks, setWeeks] = useState({});
  const joined = keys.join(",");

  useEffect(() => {
    let live = true;
    Promise.all(keys.map((k) => loadJson(`fantasy/points/${k}.json`).then((d) => [k, d])))
      .then((pairs) => live && setWeeks(Object.fromEntries(pairs)))
      .catch(() => live && setWeeks({}));
    return () => {
      live = false;
    };
    // `joined` stands in for `keys`, which is a fresh array every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [joined]);

  return weeks;
}

/** Season-to-date points per entity, from the played weeks. */
export function totalsFrom(weeks) {
  const totals = {};
  for (const w of Object.values(weeks)) {
    for (const [e, v] of Object.entries(w.entities)) totals[e] = (totals[e] ?? 0) + v.total;
  }
  return totals;
}
