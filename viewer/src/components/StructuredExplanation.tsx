import type {
  ComponentExplanation,
  ComponentExplanationKey,
  ExplanationClaim,
  HonestGap,
} from "../types";

const SECTIONS: Array<{ key: ComponentExplanationKey; label: string }> = [
  { key: "purpose", label: "Purpose" },
  { key: "mechanism", label: "How it works" },
  { key: "place", label: "Place in the system" },
  { key: "why_matters", label: "Why it matters" },
  { key: "data_handled", label: "Data handled" },
  { key: "next_step", label: "Where to go next" },
];

function evidenceLabel(evidence: Record<string, unknown>): string {
  const path = typeof evidence.path === "string"
    ? evidence.path
    : typeof evidence.file === "string"
      ? evidence.file
      : null;
  const symbol = typeof evidence.symbol === "string" ? evidence.symbol : null;
  const line = typeof evidence.line === "number" ? evidence.line : null;
  if (path) {
    return `${path}${line != null ? `:${line}` : ""}${symbol ? ` · ${symbol}` : ""}`;
  }
  if (typeof evidence.component === "string" && typeof evidence.field === "string") {
    return `${evidence.component} · ${evidence.field}`;
  }
  if (typeof evidence.source === "string" && typeof evidence.target === "string") {
    const kind = typeof evidence.edge_type === "string" ? ` (${evidence.edge_type})` : "";
    return `${evidence.source} → ${evidence.target}${kind}`;
  }
  if (Array.isArray(evidence.raw_citation)) {
    return evidence.raw_citation.map(String).join(" · ");
  }
  return Object.entries(evidence)
    .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value))
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(" · ") || "Recorded evidence";
}

function EvidenceDisclosure({ claim }: { claim: ExplanationClaim }) {
  if (!claim.evidence?.length) return null;
  const rejected = claim.evidence.filter((entry) => entry.kind === "compact-invalid");
  const supporting = claim.evidence.filter((entry) => entry.kind !== "compact-invalid");
  return (
    <details className="se-info-evidence">
      <summary>{supporting.length > 0 ? `Evidence (${supporting.length})` : "References"}{rejected.length > 0 ? ` · ${rejected.length} rejected` : ""}</summary>
      {supporting.length > 0 && <ul>
        {supporting.map((evidence, index) => (
          <li key={index}>{evidenceLabel(evidence)}</li>
        ))}
      </ul>}
      {rejected.length > 0 && <div className="se-info-gaps mt-2">
        <p className="se-info-heading">Rejected references</p>
        <p>These references were not accepted as supporting evidence.</p>
        <ul>{rejected.map((evidence, index) => <li key={index}>
          <strong>{evidenceLabel(evidence)}</strong>
          <span>{typeof evidence.reason === "string" ? evidence.reason : "The reference could not be validated."}</span>
        </li>)}</ul>
      </div>}
    </details>
  );
}

/** Preserve authored paragraphs; never infer a list by splitting sentences. */
export function NarrativeText({ text }: { text: string }) {
  return <div className="space-y-2">{text.split(/\n\s*\n/).filter((part) => part.trim()).map((paragraph, index) => (
    <p key={index} className="se-info-body whitespace-pre-line">{paragraph}</p>
  ))}</div>;
}

export function StructuredExplanation({
  explanation,
  fallback,
  honestGaps = [],
  showEvidence = false,
  compact = false,
  stale = false,
}: {
  explanation?: ComponentExplanation;
  fallback?: string | null;
  honestGaps?: HonestGap[];
  showEvidence?: boolean;
  compact?: boolean;
  stale?: boolean;
}) {
  const sections = SECTIONS.flatMap(({ key, label }) => {
    const claim = explanation?.[key];
    return claim?.text?.trim() ? [{ key, label, claim }] : [];
  });

  if (sections.length === 0 && !fallback && honestGaps.length === 0) return null;

  return (
    <div
      data-testid="structured-explanation"
      data-structured={sections.length > 0 ? "true" : "false"}
      className={compact ? "se-info-stack se-info-stack-compact" : "se-info-stack"}
    >
      {stale && <p className="se-info-gaps">This interpretation predates the current component files. Verify it against the source.</p>}
      {sections.length > 0 ? sections.map(({ key, label, claim }) => (
        <section key={key} data-explanation-section={key}>
          <h4 className="se-info-heading">{label}</h4>
          {claim.status && claim.status !== "answered" && <p className="se-info-gaps">
            {claim.status === "uncertain" ? "Not established" : `Answer status: ${claim.status}`}
            {claim.reason ? `: ${claim.reason}` : ""}
          </p>}
          <NarrativeText text={claim.text} />
          {showEvidence && <EvidenceDisclosure claim={claim} />}
        </section>
      )) : fallback ? (
        <section data-explanation-section="legacy">
          <h4 className="se-info-heading">Overview</h4>
          <NarrativeText text={fallback} />
        </section>
      ) : null}

      {sections.length > 0 && fallback && showEvidence && <details className="se-info-evidence">
        <summary>Full description</summary>
        <div className="mt-2"><NarrativeText text={fallback} /></div>
      </details>}

      {honestGaps.length > 0 && (
        <section className="se-info-gaps" aria-label="Not established">
          <h4 className="se-info-heading">Not established</h4>
          <ul>
            {honestGaps.map((gap, index) => (
              <li key={`${gap.question}:${index}`}>
                <strong>{SECTIONS.find(({ key }) => key === gap.question)?.label ?? gap.question}</strong>
                <span>{gap.why}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
