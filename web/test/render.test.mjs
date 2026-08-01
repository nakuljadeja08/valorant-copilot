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

  it("match list renders every exported match", async () => {
    const { container } = await mount("#/");
    const index = JSON.parse(await readFile(path.join(dataRoot, "index.json"), "utf-8"));

    const links = [...container.querySelectorAll("a.match-card")];
    assert.equal(links.length, index.match_count);
    assert.match(container.textContent, /Verified claims/);
  });

  it("provenance banner is present on both routes", async () => {
    for (const hash of ["#/", `#/match/${firstMatch}`]) {
      const { container } = await mount(hash);
      assert.match(
        container.textContent,
        /production key application pending/,
        `banner missing on ${hash}`,
      );
    }
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

  it("charts have a table-view twin", async () => {
    const { container } = await mount(`#/match/${firstMatch}`);
    const toggles = [...container.querySelectorAll("button.table-toggle")];
    assert.equal(toggles.length, 2, "expected a table toggle on the timeline and the chart");

    for (const toggle of toggles) {
      await React.act(async () => {
        toggle.dispatchEvent(new global.window.MouseEvent("click", { bubbles: true }));
      });
    }
    assert.ok(
      container.querySelectorAll("table").length >= 3,
      "table views did not replace the charts",
    );
  });

  it("ships no API key and no network calls beyond the static bundles", async () => {
    const sources = await Promise.all(
      ["src/App.jsx", "src/lib/data.js", "vite.config.js"].map((f) =>
        readFile(path.join(webRoot, f), "utf-8"),
      ),
    );
    for (const src of sources) {
      assert.doesNotMatch(src, /api[_-]?key|Bearer\s|X-Riot-Token/i);
      assert.doesNotMatch(src, /https?:\/\/(?!localhost)/);
    }
  });
});
