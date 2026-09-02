const STORAGE_KEY = "syscorpus-front-door-prototype-preferences-v1";

const answers = {
  flow: {
    eyebrow: "Core experience",
    title: "A real-time learning loop crosses six replaceable stages.",
    body: "A learner speaks; the voice layer detects and transcribes; curriculum context is assembled; a language model responds; and speech services play the answer back.",
    facts: [["6", "stages"], ["11", "protocol boundaries"], ["3", "guided paths"]],
  },
  capabilities: {
    eyebrow: "Capabilities",
    title: "UnaMentis teaches, practices, and evaluates through conversation.",
    body: "Its capability map includes curriculum delivery, free-form teaching, Knowledge Bowl training, reading assistance, session history, provider management, and administrative operations—each linked back to implementation and available proof.",
    facts: [["7", "major domains"], ["3", "client experiences"], ["100%", "source traceable"]],
  },
  organization: {
    eyebrow: "System organization",
    title: "The product is larger than its repository tree.",
    body: "The useful top level is architectural: learning experiences, the learning core, voice and intelligence providers, and the data and operations foundation. Repository membership remains available as supporting metadata.",
    facts: [["5", "system areas"], ["168", "components"], ["3", "semantic levels"]],
  },
  attention: {
    eyebrow: "Ranked attention",
    title: "Start with evidenced leads, not an undifferentiated warning wall.",
    body: "SysCorpus ranks findings, analysis gaps, hotspots, and dependency boundaries while preserving confidence and verification state. A finding remains a lead until its evidence survives review.",
    facts: [["85", "findings"], ["42", "producer gaps"], ["7", "direct dependencies"]],
  },
  data: {
    eyebrow: "Data model",
    title: "Data becomes legible through entities, stores, and access paths.",
    body: "The Data lens connects models and persistence to the components that read and write them, so a visitor can move from a business concept to storage and then to exact source evidence.",
    facts: [["1", "shared model"], ["2", "persistence contexts"], ["4", "consuming areas"]],
  },
  dependencies: {
    eyebrow: "External reliance",
    title: "Provider boundaries are visible without pretending detection is exhaustive.",
    body: "Voice, model, search, package, runtime, and service dependencies are brought together from relationships and the SBOM. Detection method, directness, version, and pin state remain visible.",
    facts: [["7", "direct dependencies"], ["11", "protocol boundaries"], ["1", "SBOM"]],
  },
  change: {
    eyebrow: "Activity and knowledge",
    title: "Recent change is ranked by where it matters, not shown as a feed.",
    body: "Hotspots combine activity with structural importance; ownership and change coupling explain who knows an area and what tends to move with it.",
    facts: [["30d", "activity window"], ["8", "hotspots"], ["3", "knowledge islands"]],
  },
};

const nodes = {
  unamentis: {
    icon: "U",
    title: "UnaMentis",
    role: "Primary learning system",
    description: "Coordinates voice-driven learning experiences across clients, curriculum, providers, and persistent data.",
    files: "16",
    connections: "11",
    coverage: "100%",
  },
  experience: {
    icon: "E",
    title: "Learning experiences",
    role: "Client-facing products",
    description: "Presents voice-first learning across iOS, watchOS, and web experiences, with navigable flows down to individual screens.",
    files: "214",
    connections: "37",
    coverage: "100%",
  },
  learning: {
    icon: "L",
    title: "Learning core",
    role: "Curriculum and session domain",
    description: "Assembles curricula, session context, teaching rules, and Knowledge Bowl training into coherent learning behavior.",
    files: "186",
    connections: "46",
    coverage: "100%",
  },
  providers: {
    icon: "P",
    title: "Voice & intelligence",
    role: "Replaceable provider boundary",
    description: "Abstracts speech recognition, language models, text-to-speech, search, and on-device intelligence behind explicit protocols.",
    files: "94",
    connections: "31",
    coverage: "100%",
  },
  operations: {
    icon: "O",
    title: "Data & operations",
    role: "Persistence and service foundation",
    description: "Owns shared data, persistence, management services, process lifecycle, observability, and administrative surfaces.",
    files: "257",
    connections: "59",
    coverage: "100%",
  },
};

const lensContent = {
  structure: {
    eyebrow: "Architecture · system level",
    title: "How the system is composed",
    rankedTitle: "System boundaries",
    summary: "The primary learning experience depends on four major system areas.",
  },
  capability: {
    eyebrow: "Capabilities · ranked by user value",
    title: "What the system can do—and where the proof lives",
    rankedTitle: "Primary capabilities",
    summary: "Start with the product behavior, then descend to components, tests, and source.",
  },
  flow: {
    eyebrow: "Flow · core learning loop",
    title: "What happens from learner input to spoken response",
    rankedTitle: "Walkable scenarios",
    summary: "Follow a bounded scenario instead of manually hopping through a call graph.",
  },
  data: {
    eyebrow: "Data · entities and access",
    title: "What the system knows and who reads or writes it",
    rankedTitle: "Important data paths",
    summary: "Entities and persistence stay connected to their owning and consuming components.",
  },
  activity: {
    eyebrow: "Activity · last 30 days",
    title: "Where the code is changing and who knows it",
    rankedTitle: "Hotspots",
    summary: "Change frequency is combined with structural importance, then linked to ownership.",
  },
  rules: {
    eyebrow: "Rules · evidence-linked",
    title: "Where the system makes decisions",
    rankedTitle: "Decision-bearing areas",
    summary: "Mechanical rules remain distinct from business-language interpretation.",
  },
  findings: {
    eyebrow: "Findings · verification visible",
    title: "What the system noticed and why it may matter",
    rankedTitle: "Look here first",
    summary: "Ranked leads carry evidence, confidence, verification, and an action.",
  },
  supply: {
    eyebrow: "Supply chain · SBOM backed",
    title: "What was not written here and how it is pinned",
    rankedTitle: "External reliance",
    summary: "Packages, SDK targets, providers, and versions are shown without claiming exhaustiveness.",
  },
  review: {
    eyebrow: "Review · human-to-AI loop",
    title: "Turn what you learn into an evidenced directive",
    rankedTitle: "Review targets",
    summary: "Annotate one element or a cross-cutting set, then export a structured work order.",
  },
};

const journeySteps = [
  ["Learner input", "Experience", "The learner speaks naturally.", "The client captures speech while voice activity detection decides when an utterance begins and ends.", "3 components and 8 symbols"],
  ["Voice layer", "Provider boundary", "Speech becomes a stable transcript.", "A replaceable speech-to-text provider turns audio into text while the protocol boundary keeps provider details out of the learning core.", "5 relationships and 4 protocol declarations"],
  ["Learning context", "Domain", "The system decides what the conversation is about.", "Curriculum, topic, progress, and session history are assembled into the context the model needs to teach rather than merely chat.", "14 components and 2 data entities"],
  ["Response model", "Provider boundary", "A language model creates the next teaching turn.", "The model receives grounded context through an abstraction that supports cloud, local, and test implementations.", "7 providers and 11 conforming symbols"],
  ["Speech output", "Experience", "The answer becomes speech.", "Text-to-speech selection, buffering, and playback return the response without coupling the session engine to one voice service.", "4 components and 6 relationships"],
  ["Evidence", "Verification", "Every stage can be opened down to source.", "The workbench carries this path into the Flow lens, keeps the current stage selected, and exposes files, symbols, tests, provenance, and review actions.", "100% mapped source with explicit gaps"],
];

const state = {
  mode: "overview",
  concept: "portrait",
  question: "flow",
  selectedNode: "unamentis",
  lens: "structure",
  journeyIndex: 0,
  carriedContext: "System overview",
};

let toastTimer;

function getPreferences() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}

function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 2400);
}

function setMode(mode, { remember = true } = {}) {
  state.mode = mode;
  document.querySelector("#overviewView").classList.toggle("is-visible", mode === "overview");
  document.querySelector("#workbenchView").classList.toggle("is-visible", mode === "workbench");
  document.querySelectorAll("[data-mode]").forEach((button) => button.classList.toggle("is-active", button.dataset.mode === mode));
  location.hash = mode;
  if (remember && getPreferences().remember !== false) {
    sessionStorage.setItem("syscorpus-last-mode", mode);
  }
}

function setConcept(concept) {
  state.concept = concept;
  document.querySelectorAll("[data-concept]").forEach((button) => {
    const active = button.dataset.concept === concept;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-concept-panel]").forEach((panel) => panel.classList.toggle("is-visible", panel.dataset.conceptPanel === concept));
  const select = document.querySelector("#conceptSelect");
  if (select) select.value = concept;
}

function setQuestion(question) {
  const answer = answers[question] || answers.flow;
  state.question = question;
  state.carriedContext = answer.eyebrow;
  document.querySelectorAll("[data-question]").forEach((button) => button.classList.toggle("is-active", button.dataset.question === question));
  document.querySelector("#answerEyebrow").textContent = answer.eyebrow;
  document.querySelector("#answerTitle").textContent = answer.title;
  document.querySelector("#answerBody").textContent = answer.body;
  document.querySelector("#answerFacts").innerHTML = answer.facts.map(([value, label]) => `<span><strong>${value}</strong> ${label}</span>`).join("");
  document.querySelector("#carriedContext").textContent = answer.eyebrow;
  if (state.concept !== "questions") setConcept("questions");
}

function selectNode(id) {
  const node = nodes[id] || nodes.unamentis;
  state.selectedNode = id;
  document.querySelectorAll("[data-node]").forEach((button) => button.classList.toggle("is-selected", button.dataset.node === id));
  document.querySelector("#inspectorIcon").textContent = node.icon;
  document.querySelector("#inspectorTitle").textContent = node.title;
  document.querySelector("#inspectorRole").textContent = node.role;
  document.querySelector("#inspectorDescription").textContent = node.description;
  document.querySelector("#metricFiles").textContent = node.files;
  document.querySelector("#metricConnections").textContent = node.connections;
  document.querySelector("#metricCoverage").textContent = node.coverage;
  document.querySelectorAll(".ranked-list [data-node]").forEach((button) => button.classList.toggle("is-active", button.dataset.node === id));
}

function setLens(lens) {
  const content = lensContent[lens] || lensContent.structure;
  state.lens = lens;
  document.querySelectorAll("[data-workbench-lens]").forEach((button) => button.classList.toggle("is-active", button.dataset.workbenchLens === lens));
  document.querySelector("#workbenchLensEyebrow").textContent = content.eyebrow;
  document.querySelector("#workbenchLensTitle").textContent = content.title;
  document.querySelector("#rankedTitle").textContent = content.rankedTitle;
  document.querySelector("#rankedSummary").textContent = content.summary;
}

function openDrawer(id) {
  closeDrawers();
  document.querySelector("#drawerScrim").hidden = false;
  const drawer = document.querySelector(id);
  drawer.classList.add("is-open");
  drawer.setAttribute("aria-hidden", "false");
}

function closeDrawers() {
  document.querySelector("#drawerScrim").hidden = true;
  document.querySelectorAll(".side-drawer").forEach((drawer) => {
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
  });
}

function openSearch() {
  const overlay = document.querySelector("#searchOverlay");
  overlay.classList.add("is-open");
  overlay.setAttribute("aria-hidden", "false");
  setTimeout(() => document.querySelector("#searchInput").focus(), 0);
}

function closeSearch() {
  const overlay = document.querySelector("#searchOverlay");
  overlay.classList.remove("is-open");
  overlay.setAttribute("aria-hidden", "true");
}

function renderJourney() {
  const [label, kind, title, body, evidence] = journeySteps[state.journeyIndex];
  document.querySelector("#journeyEyebrow").textContent = `Guided path · ${state.journeyIndex + 1} of ${journeySteps.length}`;
  document.querySelector("#journeyTitle").textContent = title;
  document.querySelector("#journeyStepKind").textContent = kind;
  document.querySelector("#journeyStepTitle").textContent = title;
  document.querySelector("#journeyStepBody").textContent = body;
  document.querySelector("#journeyEvidenceTitle").textContent = `Mapped to ${evidence}`;
  document.querySelector("#journeyVisual strong").textContent = String(state.journeyIndex + 1).padStart(2, "0");
  document.querySelector("#journeyVisual small").textContent = label;
  document.querySelector("#journeyProgress").textContent = `Step ${state.journeyIndex + 1} of ${journeySteps.length}`;
  document.querySelector("#journeyBack").disabled = state.journeyIndex === 0;
  document.querySelector("#journeyNext").textContent = state.journeyIndex === journeySteps.length - 1 ? "Continue in workbench →" : `Next: ${journeySteps[state.journeyIndex + 1][0].toLowerCase()} →`;
  document.querySelector("#journeySteps").innerHTML = journeySteps.map((step, index) => `
    <button class="${index === state.journeyIndex ? "is-active" : ""}" data-journey-step="${index}">
      <span>${String(index + 1).padStart(2, "0")}</span>
      <div><strong>${step[0]}</strong><small>${step[1]}</small></div>
    </button>`).join("");
}

function openJourney(kind = "flow") {
  state.journeyIndex = 0;
  state.carriedContext = kind === "flow" ? "Core learning loop · step 1" : (answers[kind]?.eyebrow || "Guided path");
  document.querySelector("#carriedContext").textContent = state.carriedContext;
  renderJourney();
  const overlay = document.querySelector("#journeyOverlay");
  overlay.classList.add("is-open");
  overlay.setAttribute("aria-hidden", "false");
}

function closeJourney() {
  const overlay = document.querySelector("#journeyOverlay");
  overlay.classList.remove("is-open");
  overlay.setAttribute("aria-hidden", "true");
}

function openWorkbench() {
  closeJourney();
  closeSearch();
  document.querySelector("#carriedContext").textContent = state.carriedContext;
  setMode("workbench");
  selectNode(state.selectedNode);
}

function loadPreferencesIntoForm(preferences) {
  const form = document.querySelector("#preferencesForm");
  const start = form.querySelector(`[name="startView"][value="${preferences.startView || "overview"}"]`);
  if (start) start.checked = true;
  form.elements.concept.value = preferences.concept || state.concept;
  const density = form.querySelector(`[name="density"][value="${preferences.density || "focused"}"]`);
  if (density) density.checked = true;
  form.elements.remember.checked = preferences.remember !== false;
  form.elements.evidence.checked = preferences.evidence !== false;
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("button, a");
  if (!target) return;

  if (target.dataset.mode) setMode(target.dataset.mode);
  if (target.dataset.concept) setConcept(target.dataset.concept);
  if (target.dataset.question) setQuestion(target.dataset.question);
  if (target.dataset.node) selectNode(target.dataset.node);
  if (target.dataset.workbenchLens) setLens(target.dataset.workbenchLens);
  if (target.dataset.journey) openJourney(target.dataset.journey);
  if (target.dataset.journeyStep !== undefined) {
    state.journeyIndex = Number(target.dataset.journeyStep);
    renderJourney();
  }
  if (target.dataset.searchResult) {
    closeSearch();
    state.carriedContext = target.querySelector("strong")?.textContent || "Search result";
    openWorkbench();
    showToast("Search context carried into the workbench");
  }

  switch (target.dataset.action) {
    case "show-overview": setMode("overview"); break;
    case "open-workbench": openWorkbench(); break;
    case "open-search": openSearch(); break;
    case "open-trust": openDrawer("#trustDrawer"); break;
    case "open-preferences":
      loadPreferencesIntoForm(getPreferences());
      openDrawer("#preferencesDrawer");
      break;
    case "close-drawers": closeDrawers(); break;
    case "close-journey": closeJourney(); break;
    case "reset-preferences":
      localStorage.removeItem(STORAGE_KEY);
      loadPreferencesIntoForm({ startView: "overview", concept: "portrait", density: "focused", remember: true, evidence: true });
      setConcept("portrait");
      showToast("First-visit defaults restored");
      break;
  }
});

document.querySelector("#drawerScrim").addEventListener("click", closeDrawers);
document.querySelector("#searchOverlay").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) closeSearch();
});
document.querySelector("#journeyOverlay").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) closeJourney();
});

document.querySelector("#journeyBack").addEventListener("click", () => {
  if (state.journeyIndex > 0) state.journeyIndex -= 1;
  renderJourney();
});

document.querySelector("#journeyNext").addEventListener("click", () => {
  if (state.journeyIndex < journeySteps.length - 1) {
    state.journeyIndex += 1;
    state.carriedContext = `Core learning loop · step ${state.journeyIndex + 1}`;
    document.querySelector("#carriedContext").textContent = state.carriedContext;
    renderJourney();
  } else {
    state.lens = "flow";
    setLens("flow");
    openWorkbench();
  }
});

document.querySelector("#preferencesForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  const preferences = {
    startView: data.get("startView"),
    concept: data.get("concept"),
    density: data.get("density"),
    remember: data.get("remember") === "on",
    evidence: data.get("evidence") === "on",
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  setConcept(preferences.concept);
  document.body.classList.toggle("dense-workbench", preferences.density === "dense");
  closeDrawers();
  showToast("Preferences saved for return visits");
});

document.querySelector("#conceptSelect").addEventListener("change", (event) => setConcept(event.target.value));

document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    openSearch();
  }
  if (event.key === "Escape") {
    closeDrawers();
    closeSearch();
    closeJourney();
  }
});

function initialize() {
  const preferences = getPreferences();
  setConcept(preferences.concept || "portrait");
  document.body.classList.toggle("dense-workbench", preferences.density === "dense");
  let initialMode = "overview";
  if (preferences.startView === "workbench") initialMode = "workbench";
  if (preferences.startView === "last") initialMode = sessionStorage.getItem("syscorpus-last-mode") || "overview";
  if (location.hash === "#workbench") initialMode = "workbench";
  setMode(initialMode, { remember: false });
  setQuestion("flow");
  setConcept(preferences.concept || "portrait");
  selectNode("unamentis");
  setLens("structure");
}

initialize();
