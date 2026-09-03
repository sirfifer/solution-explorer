import { useMemo, useRef, useState } from "react";
import { useArchStore } from "../store";
import type { Architecture, OrientationProjection, OrientationTarget } from "../types";
import { buildOrientationFallback } from "../utils/orientation";
import { formatNumber } from "../utils/layout";
import { IdentityCard } from "./IdentityCard";
import { ThemeSwitcher } from "./ThemeSwitcher";
import { ExperienceSwitcher } from "./ExperienceSwitcher";
import { TrustDrawer, TrustLedger } from "./TrustLedger";
import { ViewerPreferences } from "./ViewerPreferences";
import { SearchOverlay } from "./SearchOverlay";
import { FindingsSurface } from "./FindingsSurface";
import { TourPlayer } from "./TourPlayer";
import { PublicationBanner } from "./PublicationBanner";
import { PublicationFooter } from "./PublicationFooter";
import { OrientationInvite } from "./OrientationInvite";
import { OrientationWalk } from "./OrientationWalk";

export function SystemOverview({ displayName }: { displayName: string }) {
  const architecture = useArchStore((state) => state.architecture)!;
  const direction = useArchStore((state) => state.overviewDirection);
  const setDirection = useArchStore((state) => state.setOverviewDirection);
  const darkMode = useArchStore((state) => state.darkMode);
  const setSearchOpen = useArchStore((state) => state.setSearchOpen);
  const setTrustOpen = useArchStore((state) => state.setTrustOpen);
  const setPreferencesOpen = useArchStore((state) => state.setPreferencesOpen);
  const orientation = architecture.orientation ?? buildOrientationFallback(architecture);
  const initialQuestion = orientation.question_routes.find((row) => row.available)?.id ?? "organization";
  const [questionId, setQuestionId] = useState(initialQuestion);

  const openTarget = (target: OrientationTarget, question?: string) => {
    const store = useArchStore.getState();
    store.setExperienceMode("workbench");
    if (target.semantic_level) store.setSemanticLevel(target.semantic_level);
    if (target.lens) store.setLens(target.lens);
    if (target.tour_id) store.startTour(target.tour_id);
    if (target.surface === "findings") store.openFindingsSurface({ elementFilter: null });
    if (target.surface === "search") store.setSearchOpen(true);
    if (question === "flow" && !target.tour_id && architecture.tours?.[0]) {
      store.startTour(architecture.tours[0].id);
    }
  };

  const openComponent = (id: string | undefined) => {
    if (!id) return;
    const store = useArchStore.getState();
    store.setExperienceMode("workbench");
    // A portrait area is a structural handoff. Never carry a stale specialist
    // lens (for example Support) into this route: that can replace the bounded
    // area with a large, unrelated graph even though the selected identity is
    // correct.
    store.setLens("structure");
    store.navigateToComponent(id);
  };

  return (
    <div
      data-testid="system-overview"
      data-direction={direction}
      className="flex min-h-screen flex-col bg-[var(--se-page)]"
    >
      <PublicationBanner />
      <header className={`sticky top-0 z-40 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 border-b px-3 py-2 backdrop-blur-xl sm:flex sm:justify-between sm:gap-3 sm:px-5 ${darkMode ? "border-zinc-800 bg-zinc-950/90" : "border-zinc-200 bg-white/90"}`}>
        <div className="min-w-0"><p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-cyan-500">System under study</p><h1 data-testid="overview-title" className={`truncate text-sm font-bold ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>{displayName}</h1></div>
        <ExperienceSwitcher className="order-3 col-span-2 w-full sm:order-none sm:w-auto" />
        <div data-testid="header-tools" className="flex items-center gap-0.5 sm:gap-1.5">
          <button data-testid="search-button" aria-label="Search everything" onClick={() => setSearchOpen(true)} className={`min-h-11 min-w-11 rounded-lg px-2.5 py-2 text-xs sm:min-h-0 sm:min-w-0 ${darkMode ? "bg-zinc-900 text-zinc-300 hover:bg-zinc-800" : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"}`}><span aria-hidden>⌕</span><span className="hidden sm:inline"> Search everything</span></button>
          <button data-testid="overview-trust-button" onClick={() => setTrustOpen(true)} className={`hidden rounded-lg px-2.5 py-2 text-xs md:block ${darkMode ? "bg-zinc-900 text-zinc-300" : "bg-zinc-100 text-zinc-700"}`}>{orientation.trust.source_coverage.analyzed != null && orientation.trust.source_coverage.inventory_total ? `${orientation.trust.source_coverage.analyzed}/${orientation.trust.source_coverage.inventory_total} mapped` : orientation.trust.source_coverage.percent == null ? "Scope" : `${orientation.trust.source_coverage.percent}% parsed`}</button>
          <ThemeSwitcher />
          <button data-testid="preferences-button" onClick={() => setPreferencesOpen(true)} className={`min-h-11 min-w-11 rounded-lg p-2 text-sm sm:min-h-0 sm:min-w-0 ${darkMode ? "text-zinc-400 hover:bg-zinc-900" : "text-zinc-600 hover:bg-zinc-100"}`} aria-label="Viewer preferences">◒</button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-5 sm:px-6 lg:px-10">
        {/* The posture chooser asked a first-time reader to pick a posture before
            they knew what one was. It stays, and keeps every hook the crawl
            reads, but it is now a quiet control at the end of the row rather
            than the first thing on the page. */}
        <div className="flex flex-wrap items-center justify-end gap-2 border-b border-zinc-500/20 pb-3">
          <span className="text-[10px] font-semibold uppercase tracking-[0.2em] text-zinc-500">Other ways in</span>
          <div className={`grid grid-cols-3 rounded-lg border p-0.5 ${darkMode ? "border-zinc-800 bg-zinc-900/80" : "border-zinc-200 bg-zinc-100"}`}>
            {(["portrait", "questions", "atlas"] as const).map((item) => <button data-testid="overview-direction" data-direction={item} data-selected={direction === item} key={item} aria-label={item} onClick={() => setDirection(item)} className={`min-h-11 rounded-md px-2.5 py-1 text-xs font-semibold capitalize sm:min-h-0 sm:text-[11px] ${direction === item ? darkMode ? "bg-zinc-700 text-white" : "bg-white text-zinc-900 shadow" : "text-zinc-500"}`}>{item}</button>)}
          </div>
        </div>

        {direction === "portrait" && <Portrait orientation={orientation} darkMode={darkMode} onTarget={openTarget} onComponent={openComponent} onTrust={() => setTrustOpen(true)} />}
        {direction === "questions" && <Questions orientation={orientation} questionId={questionId} setQuestionId={setQuestionId} darkMode={darkMode} onTarget={openTarget} />}
        {direction === "atlas" && <Atlas orientation={orientation} darkMode={darkMode} onTarget={openTarget} onComponent={openComponent} />}
      </main>
      <PublicationFooter />
      <TrustDrawer />
      <ViewerPreferences />
      <SearchOverlay />
      <FindingsSurface />
      <TourPlayer />
      <OrientationInvite />
      <OrientationWalk />
    </div>
  );
}

function Portrait({ orientation, darkMode, onTarget, onComponent, onTrust }: { orientation: OrientationProjection; darkMode: boolean; onTarget: (target: OrientationTarget, question?: string) => void; onComponent: (id?: string) => void; onTrust: () => void }) {
  const architecture = useArchStore((state) => state.architecture)!;
  const primary = orientation.question_routes.filter((route) => route.available).slice(0, 3);
  const interpretedStatement = orientation.orientation.interpreted_statement;
  const interpreted = interpretedStatement?.provenance.stale ? undefined : interpretedStatement?.text;
  const identity = orientation.identity ?? null;
  const openingSource = interpreted || architecture.description || orientation.orientation.deterministic_statement;
  const openingStatement = conciseOverviewStatement(openingSource);
  const hasLongerDescription = Boolean(interpreted && interpreted.trim() !== openingStatement);
  const staleInterpretationWithheld = Boolean(interpretedStatement?.provenance.stale);
  return <div className="grid gap-8 py-8 xl:grid-cols-[minmax(0,0.88fr)_minmax(560px,1.12fr)] xl:items-start">
    <section>
      <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-500">{identity?.statement ? "At a glance" : `${orientation.subject.name} at a glance`}</p>
      <IdentityCard
        identity={identity}
        subjectName={orientation.subject.name}
        headline={openingStatement}
        interpreted={identity?.statement ? interpreted : (hasLongerDescription ? interpreted : undefined)}
        staleWithheld={staleInterpretationWithheld}
        commitShort={subjectCommitShort(architecture)}
        darkMode={darkMode}
        onComponent={onComponent}
        onTrust={onTrust}
      />
      {/* The counts sentence is the trust ledger's business. It stays for a
          bundle with no identity, where it is the only thing the page can say
          about scale, and goes when the identity statement leads. */}
      {!identity?.statement && <p className={`mt-4 max-w-2xl text-sm leading-7 ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>{orientation.orientation.deterministic_statement}</p>}
      {orientation.deployment_posture?.items.length ? <section className={`mt-5 max-w-2xl rounded-2xl border p-4 ${darkMode ? "border-violet-500/20 bg-violet-500/5" : "border-violet-200 bg-violet-50"}`}>
        <div className="flex items-center justify-between gap-3"><p className="text-xs font-semibold uppercase tracking-wider text-violet-500">Deployment posture</p><span className="text-[11px] text-zinc-500">evidence-tiered</span></div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">{orientation.deployment_posture.items.map((item) => <div key={item.id} className={`rounded-xl border p-3 ${darkMode ? "border-zinc-800 bg-zinc-950/50" : "border-violet-100 bg-white/80"}`}><strong className={`block text-sm ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>{item.label}</strong><span className="mt-1 block text-[11px] font-semibold uppercase tracking-wide text-violet-500">{item.posture.replaceAll("_", " ")}</span>{item.detail && <small className="mt-1 block text-xs leading-5 text-zinc-500">{item.detail}</small>}<span className="mt-2 block text-[11px] text-zinc-500">{item.statement_kind === "repository_claim" ? "Repository claim" : "Observed source reference"}</span></div>)}</div>
        <p className="mt-3 text-xs leading-5 text-zinc-500">{orientation.deployment_posture.method_caveat}</p>
      </section> : null}
      <div data-testid="question-routes" className="mt-7 grid gap-2 sm:grid-cols-3">{primary.map((route, index) => <button data-se="card" key={route.id} onClick={() => onTarget(route.target, route.id)} className={`group rounded-2xl border p-4 text-left transition hover:-translate-y-0.5 ${index === 0 ? darkMode ? "border-cyan-400/40 bg-cyan-400/10" : "border-cyan-300 bg-cyan-50" : darkMode ? "border-zinc-800 bg-zinc-900/70" : "border-zinc-200 bg-white"}`}><span className="text-[9px] font-semibold uppercase tracking-wider text-cyan-500">{index === 0 ? "Best first step" : "Explore"}</span><strong className={`mt-2 block text-sm ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>{route.label}</strong><span className="mt-4 block text-cyan-500 transition group-hover:translate-x-1">→</span></button>)}</div>
      {/* The counts are the trust ledger's business, not the first thing a
          newcomer should read. One line, and the full ledger is one click. */}
      <button data-testid="scale-summary" onClick={onTrust} className={`mt-7 min-h-11 text-left text-xs sm:min-h-0 ${darkMode ? "text-zinc-500 hover:text-zinc-300" : "text-zinc-500 hover:text-zinc-700"}`}>{formatNumber(architecture.stats.total_components)} components · {formatNumber(architecture.stats.total_files)} files · {formatNumber(architecture.stats.total_relationships)} relationships · full ledger →</button>
    </section>
    <section data-se="panel" className={`relative min-h-[460px] overflow-hidden rounded-[2rem] border p-5 sm:p-8 ${darkMode ? "border-zinc-800 bg-zinc-950/75" : "border-zinc-200 bg-white"}`}>
      <div className="flex items-start justify-between gap-3"><div><p className="text-[10px] uppercase tracking-wider text-zinc-500">System portrait</p><h3 className={`mt-1 text-xl font-bold ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>{orientation.portrait.nodes.length} areas of the system</h3></div><button data-testid="open-workbench" onClick={() => onTarget({ lens: "structure", semantic_level: "system" })} className="min-h-11 shrink-0 text-xs font-semibold text-cyan-500 sm:min-h-0">Full map →</button></div>
      <div className="relative mt-8 grid min-h-[320px] grid-cols-2 content-center gap-4 sm:grid-cols-3">
        <div className="pointer-events-none absolute inset-8 rounded-full border border-cyan-500/20 bg-cyan-500/5 blur-[1px]" />
        {orientation.portrait.nodes.map((node, index) => <button data-se="card" data-testid="portrait-card" data-node-id={node.id} data-target={node.stable_targets[0] ?? ""} key={node.id} onClick={() => onComponent(node.stable_targets[0])} className={`relative z-10 rounded-2xl border p-4 text-left transition hover:scale-[1.02] ${index === 0 ? "sm:col-start-2" : ""} ${darkMode ? "border-zinc-700 bg-zinc-900/95 hover:border-cyan-500/50" : "border-zinc-200 bg-white hover:border-cyan-400"}`}><strong data-se="name" className={`block text-sm ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>{node.label}</strong>{node.representative ? <><span data-testid="portrait-representative" className={`mt-2 block text-xs font-bold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>{node.representative.name}</span>{node.representative.description && <small className={`mt-1 line-clamp-2 block leading-relaxed ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>{node.representative.description}</small>}{node.representative.description_kind === "interpreted" && <span className="mt-1 block text-[9px] uppercase tracking-wider text-zinc-500">interpreted</span>}</> : <small className={`mt-1 block leading-relaxed ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>{node.role}</small>}<span className="mt-2 block text-[10px] text-zinc-500">{node.member_count} components{node.share == null ? "" : ` · ${node.share < 0.01 ? "under 1%" : `${Math.round(node.share * 100)}%`}`}</span></button>)}
      </div>
      <button onClick={onTrust} className={`mt-2 min-h-11 text-xs sm:min-h-0 sm:text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>Derived by {orientation.portrait.method}. How do we know? →</button>
    </section>
  </div>;
}

function Questions({ orientation, questionId, setQuestionId, darkMode, onTarget }: { orientation: OrientationProjection; questionId: string; setQuestionId: (id: string) => void; darkMode: boolean; onTarget: (target: OrientationTarget, question?: string) => void }) {
  const architecture = useArchStore((state) => state.architecture)!;
  const answerRef = useRef<HTMLElement>(null);
  const route = orientation.question_routes.find((row) => row.id === questionId) ?? orientation.question_routes[0];
  const answer = useMemo(() => answerFor(route.id, architecture, orientation), [route.id, architecture, orientation]);
  const chooseQuestion = (id: string) => {
    setQuestionId(id);
    if (typeof window.matchMedia !== "function" || !window.matchMedia("(max-width: 1023px)").matches) return;
    window.requestAnimationFrame(() => answerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };
  return <div className="grid gap-6 py-8 lg:grid-cols-[0.72fr_1.28fr]">
    <section data-testid="question-routes"><p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-500">Start from intent</p><h2 className={`mt-3 text-4xl font-black ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>What are you trying to understand?</h2><p className={`mt-3 max-w-xl text-sm leading-7 ${darkMode ? "text-zinc-500" : "text-zinc-600"}`}>You do not need to know a component name, language, or which lens contains the answer.</p><div className="mt-6 space-y-2">{orientation.question_routes.map((item) => <button data-se="row" data-testid="question-route" data-route-id={item.id} data-available={item.available} key={item.id} disabled={!item.available} onClick={() => chooseQuestion(item.id)} className={`min-h-11 w-full rounded-xl border p-3 text-left transition ${item.id === route.id ? darkMode ? "border-cyan-400/40 bg-cyan-400/10" : "border-cyan-300 bg-cyan-50" : darkMode ? "border-zinc-800 bg-zinc-900/60" : "border-zinc-200 bg-white"} ${!item.available ? "opacity-40" : ""}`}><strong className={`text-sm ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>{item.label}</strong><small className="ml-2 text-zinc-500">{item.available ? "→" : "not observed"}</small></button>)}</div></section>
    <article ref={answerRef} data-se="panel" className={`scroll-mt-32 rounded-[2rem] border p-6 sm:p-10 ${darkMode ? "border-zinc-800 bg-zinc-950/75" : "border-zinc-200 bg-white"}`}><p className="text-[10px] font-semibold uppercase tracking-wider text-cyan-500">Answer assembled from mapped evidence</p><h3 className={`mt-5 text-3xl font-black ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>{answer.title}</h3><p className={`mt-4 text-base leading-8 ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>{answer.body}</p><div className="mt-7 grid gap-3 sm:grid-cols-3">{answer.facts.map(([value, label]) => <Scale key={label} value={value} label={label} dark={darkMode} />)}</div><div className={`mt-8 rounded-2xl border p-5 ${darkMode ? "border-zinc-800 bg-zinc-900/70" : "border-zinc-200 bg-zinc-50"}`}><p className="text-[10px] uppercase tracking-wider text-zinc-500">Open the detailed workspace</p><p className={`mt-2 text-sm ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>{route.target.lens ? `${route.target.lens} lens` : route.target.surface ?? "Detailed workspace"}{route.target.tour_id ? " · guided path available" : ""}</p></div><button data-testid="question-route-continue" data-route-id={route.id} onClick={() => onTarget(route.target, route.id)} className="mt-8 min-h-11 rounded-xl bg-cyan-500 px-5 py-3 text-sm font-bold text-zinc-950 hover:bg-cyan-400">Continue with this question →</button></article>
  </div>;
}

function Atlas({ orientation, darkMode, onTarget, onComponent }: { orientation: OrientationProjection; darkMode: boolean; onTarget: (target: OrientationTarget) => void; onComponent: (id?: string) => void }) {
  return <div data-se="panel" className={`mt-8 grid min-h-[650px] overflow-hidden rounded-[2rem] border lg:grid-cols-[260px_1fr] ${darkMode ? "border-zinc-800 bg-zinc-950/75" : "border-zinc-200 bg-white"}`}>
    <aside className={`border-b p-5 lg:border-b-0 lg:border-r ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}><p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-500">Direct entry</p><h2 className={`mt-3 text-2xl font-black ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>Begin with the system map.</h2><p className={`mt-3 text-xs leading-6 ${darkMode ? "text-zinc-500" : "text-zinc-600"}`}>The analytical shell starts at a bounded system model, not the complete component graph.</p><nav className="mt-6 space-y-1">{orientation.question_routes.filter((row, index, rows) => row.target.lens && row.available && rows.findIndex((other) => other.target.lens === row.target.lens) === index).map((row) => <button key={row.id} onClick={() => onTarget(row.target)} className={`min-h-11 w-full rounded-lg px-3 py-2 text-left text-xs ${darkMode ? "text-zinc-300 hover:bg-zinc-900" : "text-zinc-700 hover:bg-zinc-100"}`}>{row.target.lens} <span className="float-right text-zinc-500">→</span></button>)}</nav><button data-testid="open-workbench" onClick={() => onTarget({ lens: "structure", semantic_level: "system" })} className="mt-6 min-h-11 w-full rounded-xl bg-cyan-500 px-4 py-3 text-xs font-bold text-zinc-950">Open detailed workspace →</button></aside>
    <section className="flex min-w-0 flex-col"><div className={`flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}><span className={`text-xs font-semibold ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>{orientation.subject.name} › system map</span></div><div className="relative grid flex-1 content-center gap-5 p-6 sm:grid-cols-2 xl:grid-cols-3">{orientation.portrait.nodes.map((node) => <button data-testid="portrait-card" data-node-id={node.id} data-target={node.stable_targets[0] ?? ""} key={node.id} onClick={() => onComponent(node.stable_targets[0])} className={`min-h-36 rounded-2xl border p-5 text-left transition hover:-translate-y-1 ${darkMode ? "border-zinc-700 bg-zinc-900/90 hover:border-cyan-500/50" : "border-zinc-200 bg-white shadow-sm hover:border-cyan-400"}`}><span className="text-[9px] uppercase tracking-wider text-cyan-500">{node.member_count} components</span><strong className={`mt-2 block text-base ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>{node.label}</strong><small className={`mt-2 block leading-relaxed ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>{node.role}</small></button>)}</div><div className={`border-t px-5 py-2 text-[10px] ${darkMode ? "border-zinc-800 text-zinc-500" : "border-zinc-200 text-zinc-500"}`}><TrustLedger compact /></div></section>
  </div>;
}

/**
 * The subject's commit, short, for stamping a repository claim.
 *
 * Read from the activity provenance because that is where a real projection
 * records the head it analysed; absent on datasets with no git history, and the
 * caption then simply names the file without a commit rather than inventing one.
 */
export function subjectCommitShort(architecture: Architecture): string | null {
  const activity = architecture.activity as { provenance?: { head?: string | null } } | undefined;
  const head = activity?.provenance?.head;
  return typeof head === "string" && head.length >= 7 ? head.slice(0, 7) : null;
}

function Scale({ value, label, dark }: { value: number | string; label: string; dark: boolean }) {
  return <div data-se="stat" className={`rounded-xl border p-3 ${dark ? "border-zinc-800 bg-zinc-900/60" : "border-zinc-200 bg-white"}`}><strong className={`block text-lg ${dark ? "text-zinc-100" : "text-zinc-900"}`}>{typeof value === "number" ? formatNumber(value) : value}</strong><span data-se="stat-key" className="text-xs text-zinc-500">{label}</span></div>;
}

export function conciseOverviewStatement(value: string, limit = 180): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  const firstSentence = normalized.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim();
  const candidate = firstSentence && firstSentence.length >= 24 ? firstSentence : normalized;
  if (candidate.length <= limit) return candidate;
  const bounded = candidate.slice(0, limit + 1);
  const lastSpace = bounded.lastIndexOf(" ");
  return `${bounded.slice(0, lastSpace > limit * 0.65 ? lastSpace : limit).replace(/[,:;.!?]+$/, "")}…`;
}

function answerFor(id: string, architecture: Architecture, orientation: OrientationProjection): { title: string; body: string; facts: Array<[number | string, string]> } {
  const support = architecture.support;
  const security = architecture.security;
  const answers: Record<string, { title: string; body: string; facts: Array<[number | string, string]> }> = {
    organization: { title: `The system resolves into ${orientation.portrait.nodes.length} bounded areas before individual components.`, body: orientation.orientation.deterministic_statement, facts: [[architecture.stats.total_components, "components"], [orientation.portrait.nodes.length, "system areas"], [architecture.stats.total_relationships, "relationships"]] },
    flow: { title: architecture.tours?.length ? "The core experience has an evidence-linked path you can walk." : "Observed relationships provide the starting shape of the core experience.", body: architecture.tours?.[0]?.description ?? "Continue into the Flow lens to follow observable edges without treating the static graph as runtime truth.", facts: [[architecture.tours?.length ?? 0, "guided paths"], [architecture.relationships.length, "observed relationships"], [orientation.portrait.edges.length, "area connections"]] },
    capabilities: { title: `${architecture.capabilities?.length ?? 0} observed capabilities connect product behavior to implementation.`, body: "Capabilities keep their confidence and evidence, so the route from what the system does to where it is implemented remains inspectable.", facts: [[architecture.capabilities?.length ?? 0, "capabilities"], [architecture.capabilities?.filter((item) => item.confidence === "certain").length ?? 0, "certain"], [architecture.capabilities?.filter((item) => item.detail.tests?.length).length ?? 0, "test-linked"]] },
    data: { title: `${architecture.data_entities?.length ?? 0} data entities are connected to ownership and access.`, body: "The Data lens links entities to the components that own, read, and write them; inferred entities remain marked.", facts: [[architecture.data_entities?.length ?? 0, "entities"], [architecture.entity_access?.length ?? 0, "access edges"], [architecture.data_entities?.filter((item) => item.inferred).length ?? 0, "inferred"]] },
    attention: { title: "Start with evidenced leads, not an undifferentiated warning wall.", body: "Findings and producer gaps preserve verification and provenance. A finding remains a lead until its evidence survives review.", facts: [[architecture.findings?.length ?? 0, "findings"], [orientation.trust.findings.unverified, "unverified"], [architecture.gaps?.length ?? 0, "producer gaps"]] },
    support: { title: `${support?.attention.length ?? 0} components have observed operational attention signals.`, body: support?.method_caveat ?? "This dataset has no generated Support view.", facts: [[support?.configuration.length ?? 0, "configuration inputs"], [support?.external_dependencies.length ?? 0, "external services"], [support?.entry_points.length ?? 0, "entry points"]] },
    security: { title: `${security?.mechanisms.length ?? 0} security mechanisms are directly observable in repository evidence.`, body: security?.method_caveat ?? "This dataset has no generated Security view.", facts: [[security?.mechanisms.length ?? 0, "mechanisms"], [security?.communication_boundaries.length ?? 0, "boundaries"], [security?.not_observable.length ?? 0, "explicit unknowns"]] },
  };
  return answers[id] ?? answers.organization;
}
