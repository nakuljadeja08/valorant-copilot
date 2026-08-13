/* Renders the real app against the real exported bundles, in jsdom.
 *
 * This is not a substitute for looking at the page -- it checks that both routes
 * mount without throwing and that the load-bearing content (provenance banner,
 * debrief, an expandable trace) is actually in the DOM. A regression that blanks
 * a panel fails here rather than on the deployed URL.
 *
 * Run: npm test  (from web/)
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { after, before, describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { JSDOM } from "jsdom";

const here = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(here, "..");
const dataRoot = path.join(webRoot, "public", "data");

let vite;
let React;
let ReactDOM;
let App;

function installDom(hash = "") {
  // The hash goes in the URL at construction: assigning location.hash after the
  // fact queues a hashchange that lands outside act() and trips React's warning.
  const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>", {
    url: `http://localhost/${hash}`,
    pretendToBeVisual: true,
  });

  global.window = dom.window;
  global.document = dom.window.document;
  // node >=21 defines globalThis.navigator as a getter, so plain assignment throws
  Object.defineProperty(global, "navigator", {
    value: dom.window.navigator,
    configurable: true,
    writable: true,
  });
  global.HTMLElement = dom.window.HTMLElement;
  global.Element = dom.window.Element;
  global.Node = dom.window.Node;
  global.getComputedStyle = dom.window.getComputedStyle;
  global.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  global.cancelAnimationFrame = clearTimeout;
  global.IS_REACT_ACT_ENVIRONMENT = true;

  dom.window.scrollTo = () => {}; // jsdom logs "not implemented" otherwise

  // jsdom ships neither of these; the chart only uses them for sizing.
  dom.window.ResizeObserver = class {
    observe() {}
    disconnect() {}
  };
  global.ResizeObserver = dom.window.ResizeObserver;

  // The app's only I/O: static JSON under public/data.
  global.fetch = async (url) => {
    const rel = String(url).replace(/^https?:\/\/[^/]+\//, "").replace(/^\.?\//, "");
    const file = path.join(webRoot, "public", rel);
    try {
      const text = await readFile(file, "utf-8");
      return { ok: true, status: 200, json: async () => JSON.parse(text) };
    } catch {
      return { ok: false, status: 404, json: async () => ({}) };
    }
  };

  return dom;
}

/** Mount App at a hash route and let effects (fetch -> setState) settle. */
async function mount(hash) {
  const dom = installDom(hash);

  const container = dom.window.document.getElementById("root");
  const root = ReactDOM.createRoot(container);

  // Two fetches settle in sequence -- the index, then the match bundle that only
  // starts once the route has data -- and each lands whenever the filesystem gets
  // to it. A fixed tick count is a race: too few and a late resolution fires
  // outside act() (React's "not wrapped in act(...)" warning), too many and the
  // test is slow for nothing. So: pump act() until the DOM says it has settled.
  // Each act() call must be its own scope, because queued updates are only
  // flushed when the scope exits -- polling inside one long scope never sees them.
  await React.act(async () => {
    root.render(React.createElement(App));
  });

  const pending = () => !container.textContent || /Loading/.test(container.textContent);
  for (let i = 0; i < 100 && pending(); i++) {
    await React.act(async () => {
      await new Promise((r) => setTimeout(r, 2));
    });
  }

  assert.doesNotMatch(container.textContent, /Loading/, `${hash} never finished loading`);

  return { dom, container, root };
}

function findButton(container, textMatch) {
  return [...container.querySelectorAll("button")].find((b) =>
    textMatch.test(b.textContent || ""),
  );
}

describe("dashboard", () => {
  let firstMatch;

  before(async () => {
    installDom();
    const { createServer } = await import("vite");
    vite = await createServer({
      root: webRoot,
      logLevel: "error",
      server: { middlewareMode: true },
      appType: "custom",
    });
    React = await import("react");
    ReactDOM = await import("react-dom/client");
    App = (await vite.ssrLoadModule("/src/App.jsx")).default;

    const index = JSON.parse(await readFile(path.join(dataRoot, "index.json"), "utf-8"));
    firstMatch = index.matches[0].match_id;
  });

  after(async () => {
    await vite?.close();
  });

  it("matches route renders every exported match", async () => {
    const { container } = await mount("#/matches");
    const index = JSON.parse(await readFile(path.join(dataRoot, "index.json"), "utf-8"));

    const links = [...container.querySelectorAll("a.match-card")];
    assert.equal(links.length, index.match_count);
  });

  it("overview shows the season KPI grid with a record", async () => {
    const { container } = await mount("#/");
    const index = JSON.parse(await readFile(path.join(dataRoot, "index.json"), "utf-8"));
    const { wins, losses } = index.season.record;

    assert.equal(container.querySelectorAll(".kpi-grid .tile").length, 6);
    assert.match(container.textContent, new RegExp(`${wins}–${losses}`));
    assert.match(container.textContent, /verified claims/i);
  });

  it("every match card leads with its verdict", async () => {
    const { container } = await mount("#/matches");
    const index = JSON.parse(await readFile(path.join(dataRoot, "index.json"), "utf-8"));
    const verdicts = new Map(index.matches.map((m) => [m.match_id, m.verdict]));

    for (const card of container.querySelectorAll("a.match-card")) {
      const id = card.getAttribute("href").replace("#/match/", "");
      assert.match(card.textContent, /\S/);
      assert.ok(
        card.textContent.includes(verdicts.get(id)),
        `card for ${id} does not show its verdict`,
      );
    }
  });

  it("filter chips actually filter the match grid", async () => {
    const { container } = await mount("#/matches");
    const index = JSON.parse(await readFile(path.join(dataRoot, "index.json"), "utf-8"));
    const losses = index.matches.filter((m) => m.winner && m.winner !== m.hero_team).length;

    const chip = [...container.querySelectorAll("button.chip")].find(
      (b) => b.textContent === "Losses",
    );
    assert.ok(chip, "no Losses filter chip");
    await React.act(async () => {
      chip.dispatchEvent(new global.window.MouseEvent("click", { bubbles: true }));
    });

    const shown = container.querySelectorAll("a.match-card").length;
    assert.equal(shown, losses);
    assert.ok(shown < index.match_count, "filter did not narrow the grid");
  });

  it("agents route lists every verified finding from its own bundle", async () => {
    const { container } = await mount("#/agents");
    const agents = JSON.parse(await readFile(path.join(dataRoot, "agents.json"), "utf-8"));
    const index = JSON.parse(await readFile(path.join(dataRoot, "index.json"), "utf-8"));

    assert.equal(agents.findings.length, index.season.verified_claims);
    assert.ok(container.querySelector(".pipeline"), "no pipeline diagram");
    // Unfiltered, so the heading is a bare total with no "of N" suffix.
    assert.match(container.textContent, new RegExp(`Findings — ${agents.findings.length}`));

    // Paged, so the DOM stays reasonable; the count in the heading is the truth.
    const rows = container.querySelectorAll(".feed-row").length;
    assert.ok(rows > 0 && rows <= agents.findings.length);

    const more = [...container.querySelectorAll("button.table-toggle")].find((b) =>
      /Show \d+ more/.test(b.textContent),
    );
    assert.ok(more, "no pagination control for 93 findings");
    await React.act(async () => {
      more.dispatchEvent(new global.window.MouseEvent("click", { bubbles: true }));
    });
    assert.ok(
      container.querySelectorAll(".feed-row").length > rows,
      "pagination revealed nothing",
    );
  });

  it("agents route filters findings by agent", async () => {
    const { container } = await mount("#/agents");
    const agents = JSON.parse(await readFile(path.join(dataRoot, "agents.json"), "utf-8"));
    const economist = agents.findings.filter((f) => f.agent === "Economist").length;

    const chip = [...container.querySelectorAll("button.chip")].find(
      (b) => b.textContent === "Economist",
    );
    assert.ok(chip, "no Economist filter chip");
    await React.act(async () => {
      chip.dispatchEvent(new global.window.MouseEvent("click", { bubbles: true }));
    });
    assert.match(container.textContent, new RegExp(`Findings — ${economist} of`));
  });

  it("provenance banner and app header are present on both routes", async () => {
    for (const hash of ["#/", `#/match/${firstMatch}`]) {
      const { container } = await mount(hash);
      assert.match(
        container.textContent,
        /production key application pending/,
        `banner missing on ${hash}`,
      );
      assert.ok(
        container.querySelector("header.app-header"),
        `app header missing on ${hash}`,
      );
      assert.match(container.textContent, /SIM DATA/, `data-source pill missing on ${hash}`);
    }
  });

  it("each nav item is its own route, and marks itself current", async () => {
    const expected = [
      ["#/", "Overview", ".kpi-grid"],
      ["#/agents", "Agents", ".pipeline"],
      ["#/matches", "Matches", "a.match-card"],
    ];

    for (const [hash, label, marker] of expected) {
      const { container } = await mount(hash);

      assert.deepEqual(
        [...container.querySelectorAll(".app-nav a")].map((a) => a.getAttribute("href")),
        ["#/", "#/agents", "#/matches"],
      );
      assert.ok(container.querySelector(marker), `${hash} did not render ${marker}`);

      const current = container.querySelector('.app-nav a[aria-current="page"]');
      assert.equal(current?.textContent, label, `wrong nav item current on ${hash}`);
    }
  });

  it("a match keeps Matches lit and offers a way back to it", async () => {
    const { container } = await mount(`#/match/${firstMatch}`);

    const current = container.querySelector('.app-nav a[aria-current="page"]');
    assert.equal(current?.textContent, "Matches");
    assert.equal(
      container.querySelector("a.back-link")?.getAttribute("href"),
      "#/matches",
    );
  });

  /* A bare fragment is not a route. Browsers leave a lone "#" behind on some
     interactions, and it must resolve to the overview, not a blank view. */
  it("a bare fragment falls back to the overview", async () => {
    const { container } = await mount("#");
    assert.ok(container.querySelector(".kpi-grid"), "bare # lost the overview");
  });

  it("theme toggle flips the document theme and persists it", async () => {
    const { container, dom } = await mount("#/");
    const root = dom.window.document.documentElement;
    assert.ok(!root.dataset.theme || root.dataset.theme === "dark", "dark is the default");

    const toggle = container.querySelector("button.theme-toggle");
    assert.ok(toggle, "no theme toggle in the header");

    await React.act(async () => {
      toggle.dispatchEvent(new global.window.MouseEvent("click", { bubbles: true }));
    });
    assert.equal(root.dataset.theme, "light");
    assert.equal(dom.window.localStorage.getItem("vcp-theme"), "light");

    await React.act(async () => {
      toggle.dispatchEvent(new global.window.MouseEvent("click", { bubbles: true }));
    });
    assert.equal(root.dataset.theme, "dark");
    assert.equal(dom.window.localStorage.getItem("vcp-theme"), "dark");
  });

  it("match view renders timeline, chart, debrief and scoreboard", async () => {
    const { container } = await mount(`#/match/${firstMatch}`);
    const text = container.textContent;

    assert.match(text, /Round timeline/);
    assert.match(text, /Round spend/);
    assert.match(text, /Debrief/);
    assert.match(text, /Scoreboard/);
    assert.ok(container.querySelector("svg path"), "economy chart drew no line");
    assert.ok(container.querySelectorAll(".round-col").length > 0, "timeline drew no rounds");
  });

  it("every claim can expand into a decision trace citing raw rows", async () => {
    const { container } = await mount(`#/match/${firstMatch}`);
    const bundle = JSON.parse(
      await readFile(path.join(dataRoot, "match", `${firstMatch}.json`), "utf-8"),
    );
    const verified = bundle.trace.conclusions.filter((c) => c.verified === true);

    const claims = [...container.querySelectorAll("article.claim")];
    assert.equal(claims.length, verified.length);
    assert.ok(claims.length > 0, "no claims rendered");

    for (const claim of claims) {
      const toggle = findButton(claim, /Show decision trace/);
      assert.ok(toggle, "claim has no trace disclosure");
      await React.act(async () => {
        toggle.dispatchEvent(new global.window.MouseEvent("click", { bubbles: true }));
      });
      assert.ok(claim.querySelector(".evidence"), "expanded trace showed no evidence");
      assert.ok(claim.querySelector(".rows li"), "evidence cited no raw rows");
    }
  });

  it("the role lens toggles on, showing per-player percentile cards", async () => {
    const { container } = await mount(`#/match/${firstMatch}`);
    const bundle = JSON.parse(
      await readFile(path.join(dataRoot, "match", `${firstMatch}.json`), "utf-8"),
    );
    assert.ok(bundle.role, "fixture bundle has no role block");

    const toggle = findButton(container, /How each player performed for their role/);
    assert.ok(toggle, "no base<->role toggle");
    await React.act(async () => {
      toggle.dispatchEvent(new global.window.MouseEvent("click", { bubbles: true }));
    });

    // One card per player, each with a percentile bar per feature.
    const cards = container.querySelectorAll(".role-card");
    assert.equal(cards.length, bundle.role.players.length);
    assert.ok(container.querySelector(".bar-fill"), "no percentile bars rendered");

    // The synergy strip and its role-approx badge (the honesty signal) are present.
    assert.match(container.textContent, /Composition & synergy/);
    assert.ok(
      [...container.querySelectorAll(".role-approx-badge")].length > 0,
      "role-approx badge missing from an inferred metric",
    );
  });

  it("role claims carry the within-role percentile and its baseline into the trace", async () => {
    const { container } = await mount(`#/match/${firstMatch}`);
    await React.act(async () => {
      findButton(container, /How each player performed for their role/)
        .dispatchEvent(new global.window.MouseEvent("click", { bubbles: true }));
    });
    const bundle = JSON.parse(
      await readFile(path.join(dataRoot, "match", `${firstMatch}.json`), "utf-8"),
    );
    // At least one role claim is percentile-scored; the UI must surface the baseline.
    const scored = bundle.role.trace.conclusions.find(
      (c) => c.within_role_percentile !== undefined && c.verified === true,
    );
    assert.ok(scored, "no percentile-scored role claim in the fixture");
    assert.match(container.textContent, /percentile among\s+same-role peers/i);
    assert.match(container.textContent, new RegExp(scored.baseline_version));
  });

  /* Structural rather than counted: the property worth pinning is "every chart
     has a table twin", which stays true as charts are added. The old
     `toggles.length === 2` had to be edited every time one was. */
  it("every chart has a table-view twin", async () => {
    for (const hash of ["#/", `#/match/${firstMatch}`]) {
      const { container } = await mount(hash);
      const charts = [...container.querySelectorAll("[data-chart]")];
      assert.ok(charts.length > 0, `no charts on ${hash}`);

      for (const chart of charts) {
        const toggles = chart.querySelectorAll("button.table-toggle");
        assert.equal(
          toggles.length,
          1,
          `${chart.dataset.chart} on ${hash} has ${toggles.length} table toggles`,
        );

        assert.equal(chart.querySelectorAll("table").length, 0);
        await React.act(async () => {
          toggles[0].dispatchEvent(new global.window.MouseEvent("click", { bubbles: true }));
        });
        assert.equal(
          chart.querySelectorAll("table").length,
          1,
          `${chart.dataset.chart} on ${hash} showed no table`,
        );
      }
    }
  });

  /* The momentum series is explicitly not a calibrated probability -- see
     src/features/pivotal_round.py. These two lines are what stop the label
     drifting back to "win probability" in six months. */
  it("labels the momentum proxy honestly, never as a win probability", async () => {
    const { container } = await mount(`#/match/${firstMatch}`);
    const chart = container.querySelector('[data-chart="momentum"]');
    assert.ok(chart, "momentum chart did not render");

    // The heading and legend are where a reader takes the label from.
    assert.match(chart.querySelector(".section-title").textContent, /momentum index/i);
    assert.doesNotMatch(chart.querySelector(".section-title").textContent, /probability/i);
    assert.match(chart.querySelector(".legend").textContent, /proxy/i);

    // Axis ticks are index values. A percent sign is what makes a reader treat
    // a number as a probability, so there must not be one in the plot.
    const svgText = [...chart.querySelectorAll("svg text")].map((t) => t.textContent);
    assert.ok(svgText.includes("0.5"), "axis is not labelled on a 0-1 scale");
    assert.ok(!svgText.some((t) => t.includes("%")), `percent on the axis: ${svgText}`);

    // And the disclaimer that travels with the data is on the page.
    assert.match(chart.textContent, /not a calibrated win probability/i);
  });

  it("keeps the sim-approx caveat on kill share", async () => {
    for (const hash of ["#/", `#/match/${firstMatch}`]) {
      const { container } = await mount(hash);
      if (/kill share/i.test(container.textContent)) {
        assert.match(container.textContent, /sim-approx/i, `caveat dropped on ${hash}`);
      }
    }
  });

  it("ships no API key and no network calls beyond the static bundles", async () => {
    const files = [
      "index.html",
      "src/App.jsx",
      "src/lib/data.js",
      "src/lib/theme.js",
      "vite.config.js",
      "src/styles/index.css",
      "src/styles/tokens.css",
      "src/styles/fonts.css",
      "src/styles/base.css",
      "src/styles/chrome.css",
      "src/styles/charts.css",
      "src/styles/views.css",
    ];
    const sources = await Promise.all(
      files.map(async (f) => [f, await readFile(path.join(webRoot, f), "utf-8")]),
    );
    for (const [name, src] of sources) {
      assert.doesNotMatch(src, /api[_-]?key|Bearer\s|X-Riot-Token/i, name);
      // Bare hostnames too: the source mockup loaded Google Fonts, and fonts
      // must stay self-hosted for the build to make no third-party request.
      assert.doesNotMatch(src, /https?:\/\/(?!localhost)/, name);
      assert.doesNotMatch(src, /fonts\.(googleapis|gstatic)/, name);
    }
  });
});
