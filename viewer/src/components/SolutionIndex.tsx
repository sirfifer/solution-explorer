// Multi-repo solution member index (MULTI-REPO-DESIGN.md, M1).
//
// When the viewer loads a root manifest whose kind is SOLUTION_MANIFEST_KIND, it
// renders THIS page instead of the component graph: a list of member repos with
// their per-member coverage badge and stats. Tapping a member opens the EXISTING
// viewer experience over that member's dataset via the `?data=` param
// (see utils/dataSource.memberDataUrl). Full graph-of-members visualization is
// M2+; this M1 view is a member index only, deliberately minimal.
//
// Mobile-first: single-column stacked cards at phone width, a responsive grid at
// wider widths, finger-sized tap targets, no hover-gated affordances, no
// horizontal page scroll.

import { formatNumber } from "../utils/layout";
import { memberDataUrl } from "../utils/dataSource";
import type { SolutionManifest, SolutionMember } from "../types";

interface SolutionIndexProps {
  solution: SolutionManifest;
  solutionBase: string;
  darkMode: boolean;
}

function CoveragePill({ member, darkMode }: { member: SolutionMember; darkMode: boolean }) {
  const cov = member.coverage;
  if (!cov) return null;
  const gapped = cov.has_gaps;
  const cls = gapped
    ? darkMode
      ? "bg-amber-950 text-amber-300 border border-amber-800"
      : "bg-amber-50 text-amber-700 border border-amber-300"
    : darkMode
      ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
      : "bg-emerald-50 text-emerald-700 border border-emerald-300";
  return (
    <span className={`inline-flex items-center px-2 py-1 rounded-md text-xs font-medium ${cls}`}>
      {cov.source_percent}% of source analyzed
      {gapped ? ` · ${formatNumber(cov.families.gap)} gap${cov.families.gap === 1 ? "" : "s"}` : ""}
    </span>
  );
}

function MemberCard({
  member,
  solutionBase,
  darkMode,
}: {
  member: SolutionMember;
  solutionBase: string;
  darkMode: boolean;
}) {
  const cardBase = darkMode
    ? "bg-zinc-900 border-zinc-800"
    : "bg-white border-zinc-200";
  const title = darkMode ? "text-zinc-100" : "text-zinc-900";
  const sub = darkMode ? "text-zinc-400" : "text-zinc-500";

  if (!member.resolved) {
    // A git URL member: recorded in the index, not analyzed in M1.
    return (
      <div className={`rounded-xl border p-4 ${cardBase} opacity-80`}>
        <div className="flex items-start justify-between gap-2">
          <h3 className={`text-base font-semibold ${title}`}>{member.label}</h3>
          <span
            className={`shrink-0 inline-flex items-center px-2 py-1 rounded-md text-xs font-medium ${
              darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-500"
            }`}
          >
            not analyzed
          </span>
        </div>
        {member.url ? (
          <p className={`mt-2 text-xs break-all ${sub}`}>
            {member.url}
            {member.ref ? ` @ ${member.ref}` : ""}
          </p>
        ) : null}
        <p className={`mt-2 text-xs ${sub}`}>
          {member.error || member.unresolved_reason || "Not available in this composition."}
        </p>
      </div>
    );
  }

  const stats = member.stats;
  const href = member.projection ? memberDataUrl(member.projection, solutionBase) : "#";
  return (
    <a
      href={href}
      className={`group block rounded-xl border p-4 transition-colors ${cardBase} ${
        darkMode ? "hover:border-blue-700 active:border-blue-600" : "hover:border-blue-400 active:border-blue-500"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className={`text-base font-semibold ${title}`}>{member.label}</h3>
        <span
          className={`shrink-0 text-lg leading-none ${darkMode ? "text-zinc-600 group-hover:text-blue-400" : "text-zinc-400 group-hover:text-blue-500"}`}
          aria-hidden="true"
        >
          &rarr;
        </span>
      </div>
      {member.path ? <p className={`mt-1 text-xs font-mono ${sub}`}>{member.path}</p> : null}
      <div className="mt-3">
        <CoveragePill member={member} darkMode={darkMode} />
      </div>
      {stats ? (
        <dl className={`mt-3 grid grid-cols-3 gap-2 text-xs ${sub}`}>
          <div>
            <dt className="uppercase tracking-wide opacity-70">Components</dt>
            <dd className={`text-sm font-semibold ${title}`}>{formatNumber(stats.total_components)}</dd>
          </div>
          <div>
            <dt className="uppercase tracking-wide opacity-70">Files</dt>
            <dd className={`text-sm font-semibold ${title}`}>{formatNumber(stats.total_files)}</dd>
          </div>
          <div>
            <dt className="uppercase tracking-wide opacity-70">Lines</dt>
            <dd className={`text-sm font-semibold ${title}`}>{formatNumber(stats.total_lines)}</dd>
          </div>
        </dl>
      ) : null}
    </a>
  );
}

export function SolutionIndex({ solution, solutionBase, darkMode }: SolutionIndexProps) {
  const summary = solution.summary;
  const page = darkMode ? "bg-zinc-950 text-zinc-100" : "bg-white text-zinc-900";
  const sub = darkMode ? "text-zinc-400" : "text-zinc-500";
  const gapped = summary.members_with_gaps || [];
  // An empty `members_with_gaps` is ambiguous on its own: it is also what a
  // solution with NO member coverage data at all looks like (every member's
  // `coverage` key absent). Without this check, "No source gaps in any
  // member" reads as a verified clean bill of health when nothing was
  // actually measured (O4 principle: never imply coverage exists when it
  // does not).
  const membersWithCoverage = solution.members.filter((m) => m.coverage).length;

  return (
    <div className={`min-h-screen w-full overflow-x-hidden ${page}`}>
      <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 sm:py-10">
        <header className="mb-6">
          <p className={`text-xs uppercase tracking-widest ${sub}`}>Solution</p>
          <h1 className="mt-1 text-2xl font-bold sm:text-3xl">{solution.name}</h1>
          <p className={`mt-2 text-sm ${sub}`}>
            {summary.composed_count} of {summary.member_count} member
            {summary.member_count === 1 ? "" : "s"} composed
            {" · "}
            {formatNumber(summary.total_source_files)} source files
            {" · "}
            {formatNumber(summary.total_nonsource_files)} non-source accounted for
          </p>
          {gapped.length > 0 ? (
            <p className={`mt-2 text-sm ${darkMode ? "text-amber-400" : "text-amber-600"}`}>
              Source gaps in: {gapped.join(", ")}
            </p>
          ) : membersWithCoverage > 0 ? (
            <p className={`mt-2 text-sm ${darkMode ? "text-emerald-400" : "text-emerald-600"}`}>
              No source gaps in any member. Coverage is reported per member and never blended.
            </p>
          ) : (
            <p className={`mt-2 text-sm ${sub}`}>
              Coverage data is not available for these members.
            </p>
          )}
        </header>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {solution.members.map((member) => (
            <MemberCard
              key={member.slug}
              member={member}
              solutionBase={solutionBase}
              darkMode={darkMode}
            />
          ))}
        </div>

        <footer className={`mt-8 text-xs ${sub}`}>
          Tap a member to open its full architecture. Generated {solution.generated_at} by
          solution-explorer {solution.analyzer_version}.
        </footer>
      </div>
    </div>
  );
}
