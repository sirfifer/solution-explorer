import { useEffect, useState } from "react";
import type { FormFactor, OrientationIdentity } from "../types";

/**
 * What the system is, to a person, before any count.
 *
 * The headline used to be a sentence about the snapshot ("this snapshot
 * contains the source code at the recorded commit"), which tells a first-time
 * reader nothing they can use. Everything here is composed by the analyzer from
 * markers in the checkout, and every claim carries the file that proves it, so
 * the page can be read by someone who does not know what a repository is and
 * still be checked by someone who does.
 */

const PLATFORM_NAMES: Record<string, string> = {
  macos: "macOS",
  windows: "Windows",
  linux: "Linux",
  ios: "iOS",
  watchos: "watchOS",
  android: "Android",
  browser: "the browser",
};

function platformLabel(platforms: string[]): string {
  return platforms.map((platform) => PLATFORM_NAMES[platform] ?? platform).join(", ");
}

/** The small text under a chip: where it runs, or which one of several it is.
 *
 * A subject can have two command-line tools, and two chips reading only
 * "Command-line tool" tell a reader there are two of something without saying
 * what either one is. The last part of the component path is what the reader
 * would recognise, and the evidence panel carries the whole of it.
 */
function chipDetail(record: FormFactor): string | null {
  if (record.platforms.length) return platformLabel(record.platforms);
  if (record.name) return record.name;
  const id = record.component_id;
  if (!id || id === "root") return null;
  return id.split("/").slice(-2).join("/");
}

function evidenceLabel(file: string, line?: number): string {
  return line ? `${file}:${line}` : file;
}

/** Several records can share a kind (two command-line tools, say), so the key
 *  is the whole identity of the record, not its kind. */
function chipKey(record: FormFactor): string {
  return `${record.kind}:${record.component_id}:${record.name ?? ""}`;
}

function FormFactorChip({
  record,
  open,
  onToggle,
  darkMode,
}: {
  record: FormFactor;
  open: boolean;
  onToggle: () => void;
  darkMode: boolean;
}) {
  const detail = chipDetail(record);
  return (
    <button
      data-testid="form-factor"
      data-kind={record.kind}
      aria-expanded={open}
      onClick={onToggle}
      className={`flex min-h-11 flex-col items-start rounded-xl border px-3 py-2 text-left transition sm:min-h-0 ${
        open
          ? darkMode
            ? "border-cyan-400/50 bg-cyan-400/10"
            : "border-cyan-400 bg-cyan-50"
          : darkMode
            ? "border-zinc-800 bg-zinc-900/70 hover:border-zinc-700"
            : "border-zinc-200 bg-white hover:border-zinc-300"
      }`}
    >
      <strong className={`text-xs font-semibold ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
        {record.label}
      </strong>
      {detail && <span className="text-[10px] text-zinc-500">{detail}</span>}
      <span className="text-[10px] text-zinc-500">Observed source reference</span>
    </button>
  );
}

/**
 * The evidence behind one chip.
 *
 * Rendered under the chip row rather than floating beside the chip it belongs
 * to: an anchored popover 288 px wide next to the fourth chip runs off a 390 px
 * phone, and a front door that scrolls sideways is the first thing a reader
 * notices about it.
 */
function FormFactorEvidence({
  record,
  darkMode,
  onComponent,
}: {
  record: FormFactor;
  darkMode: boolean;
  onComponent: (id?: string) => void;
}) {
  const canOpen = Boolean(record.component_id) && record.component_id !== "root";
  return (
    <div
      data-testid="form-factor-evidence"
      className={`mt-2 max-w-2xl rounded-xl border p-3 ${
        darkMode ? "border-zinc-700 bg-zinc-950" : "border-zinc-200 bg-white"
      }`}
    >
      <p className="text-[10px] uppercase tracking-wider text-zinc-500">
        {record.label}: {record.how_met}
      </p>
      <ul className="mt-2 space-y-1">
        {record.evidence.map((item) => (
          <li
            key={`${item.file}:${item.line ?? ""}:${item.marker}`}
            className={`break-all text-[11px] ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}
          >
            <span className="font-mono">{evidenceLabel(item.file, item.line)}</span>{" "}
            <span className="text-zinc-500">{item.marker}</span>
          </li>
        ))}
      </ul>
      {record.platforms_assumed && (
        <p className="mt-2 text-[11px] text-amber-500">
          Platforms are the usual set for this toolkit, not named in the source.
        </p>
      )}
      {canOpen && (
        <button
          onClick={() => onComponent(record.component_id)}
          className="mt-3 min-h-11 text-[11px] font-semibold text-cyan-500 sm:min-h-0"
        >
          Open in workbench →
        </button>
      )}
    </div>
  );
}

export function IdentityCard({
  identity,
  subjectName,
  headline,
  interpreted,
  staleWithheld,
  commitShort,
  darkMode,
  onComponent,
  onTrust,
}: {
  identity: OrientationIdentity | null | undefined;
  subjectName: string;
  headline: string;
  interpreted?: string;
  staleWithheld: boolean;
  commitShort?: string | null;
  darkMode: boolean;
  onComponent: (id?: string) => void;
  onTrust: () => void;
}) {
  const [openKind, setOpenKind] = useState<string | null>(null);

  // Escape closes the evidence panel, as it closes every other overlay in the
  // viewer. Bound while one is open only, so the front door adds no listener to
  // a page that is not showing one.
  useEffect(() => {
    if (!openKind) return undefined;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenKind(null);
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [openKind]);

  // The title says WHICH system; the subtitle says WHAT it is. The analyzer
  // composes both, so the subtitle never repeats the name back at the reader.
  const statement = identity?.summary ?? identity?.statement ?? null;
  const formFactors = identity?.form_factors ?? [];
  const openRecord = formFactors.find((record) => chipKey(record) === openKind) ?? null;
  const claim = identity?.authors_claim ?? null;
  const claimCaption = claim
    ? `${claim.source}${commitShort ? ` at commit ${commitShort}` : ""}, Repository claim`
    : "";

  return (
    <>
      {statement ? (
        <>
          <h2
            className={`mt-2 text-3xl font-black leading-[1.1] sm:text-4xl ${
              darkMode ? "text-zinc-100" : "text-zinc-900"
            }`}
          >
            {subjectName}
          </h2>
          <p
            data-testid="identity-statement"
            className={`mt-3 max-w-2xl text-base leading-7 sm:text-lg sm:leading-8 ${
              darkMode ? "text-zinc-300" : "text-zinc-700"
            }`}
          >
            {statement}
          </p>
        </>
      ) : (
        <h2
          className={`mt-4 max-w-3xl text-3xl font-black leading-[1.08] sm:text-4xl xl:text-[3.25rem] ${
            darkMode ? "text-zinc-100" : "text-zinc-900"
          }`}
        >
          {headline}
        </h2>
      )}

      {formFactors.length > 0 && (
        <>
          <div className="mt-4 flex max-w-2xl flex-wrap gap-2">
            {formFactors.map((record) => (
              <FormFactorChip
                key={chipKey(record)}
                record={record}
                darkMode={darkMode}
                open={openKind === chipKey(record)}
                onToggle={() =>
                  setOpenKind((current) => (current === chipKey(record) ? null : chipKey(record)))
                }
              />
            ))}
          </div>
          {openRecord && (
            <FormFactorEvidence
              record={openRecord}
              darkMode={darkMode}
              onComponent={onComponent}
            />
          )}
        </>
      )}

      {claim && (
        <figure className="mt-5 max-w-2xl">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            In the maintainers&apos; words
          </p>
          <blockquote
            data-testid="authors-claim"
            className={`mt-2 border-l-2 pl-3 text-sm leading-6 ${
              darkMode ? "border-zinc-700 text-zinc-300" : "border-zinc-300 text-zinc-700"
            }`}
          >
            {claim.text}
          </blockquote>
          <figcaption className="mt-2 text-[11px] text-zinc-500">{claimCaption}</figcaption>
        </figure>
      )}

      {interpreted && (
        <details
          className={`mt-4 max-w-2xl text-xs leading-6 ${
            darkMode ? "text-zinc-500" : "text-zinc-600"
          }`}
        >
          <summary className="flex min-h-11 cursor-pointer items-center font-semibold text-cyan-500 sm:min-h-0">
            Interpreted summary
          </summary>
          <p className="mt-2">{interpreted}</p>
          <p className="mt-1 text-[11px] text-zinc-500">Interpreted, not observed</p>
        </details>
      )}

      {staleWithheld && (
        <button
          onClick={onTrust}
          className={`mt-3 flex min-h-11 items-center text-left text-xs font-semibold sm:min-h-0 ${
            darkMode ? "text-amber-300" : "text-amber-700"
          }`}
        >
          An older interpreted summary was withheld because its mapped evidence changed.
          Review provenance →
        </button>
      )}
    </>
  );
}
