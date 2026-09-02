import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { JSDOM } from "../../viewer/node_modules/jsdom/lib/api.js";

const base = new URL("./", import.meta.url);
const html = await readFile(new URL("index.html", base), "utf8");
const script = await readFile(new URL("app.js", base), "utf8");

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  url: "http://127.0.0.1:4173/docs/front-door-prototype/",
  pretendToBeVisual: true,
});

dom.window.eval(script);

const { document } = dom.window;
const click = (selector) => {
  const element = document.querySelector(selector);
  assert.ok(element, `Expected element: ${selector}`);
  element.click();
  return element;
};

assert.ok(document.querySelector("#overviewView").classList.contains("is-visible"));
assert.ok(document.querySelector('[data-concept-panel="portrait"]').classList.contains("is-visible"));

click('[data-concept="questions"]');
click('[data-question="data"]');
assert.match(document.querySelector("#answerTitle").textContent, /Data becomes legible/);

click('[data-action="open-trust"]');
assert.ok(document.querySelector("#trustDrawer").classList.contains("is-open"));
click('[data-action="close-drawers"]');
assert.equal(document.querySelector("#drawerScrim").hidden, true);

click('[data-journey="flow"]');
assert.ok(document.querySelector("#journeyOverlay").classList.contains("is-open"));
click("#journeyNext");
assert.equal(document.querySelector("#journeyProgress").textContent, "Step 2 of 6");

click('[data-action="open-workbench"]');
assert.ok(document.querySelector("#workbenchView").classList.contains("is-visible"));
assert.match(document.querySelector("#carriedContext").textContent, /Core learning loop/);

click('[data-workbench-lens="flow"]');
assert.match(document.querySelector("#workbenchLensTitle").textContent, /learner input/);

click('.workbench-canvas [data-node="providers"]');
assert.equal(document.querySelector("#inspectorTitle").textContent, "Voice & intelligence");
assert.equal(document.querySelector("#metricConnections").textContent, "31");

click('[data-action="open-preferences"]');
const form = document.querySelector("#preferencesForm");
form.querySelector('[name="startView"][value="workbench"]').checked = true;
form.querySelector('[name="density"][value="dense"]').checked = true;
form.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
const saved = JSON.parse(dom.window.localStorage.getItem("syscorpus-front-door-prototype-preferences-v1"));
assert.equal(saved.startView, "workbench");
assert.equal(saved.density, "dense");
assert.ok(document.body.classList.contains("dense-workbench"));

console.log("Front-door prototype DOM checks passed.");

dom.window.close();
