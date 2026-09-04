// Publication-metadata sidecar (publication.json) parsing, validation, and text
// substitution. Design authority: docs/publication/PUBLICATION-METADATA.md and
// docs/publication/publication.schema.json.
//
// The sidecar is OPTIONAL and never influences analysis. When it is absent OR
// invalid the viewer must render exactly as today (design rule 2), so the parser
// returns null on anything it cannot validate rather than throwing or returning a
// partial object. A non-null Publication is therefore always structurally valid,
// and every render site can rely on its required fields.

import type { Publication } from "../types";

const AFFILIATIONS = new Set(["owner", "maintainer", "contributor", "none"]);
const PURPOSES = new Set(["demo", "documentation", "internal", "evaluation", "other"]);
const UPDATE_POLICIES = new Set(["snapshot", "periodic", "continuous"]);
const VISIBILITIES = new Set(["public", "private-preview", "internal"]);

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

/**
 * Validate an already-parsed JSON value against the publication schema's required
 * shape and return a typed Publication, or null when it is not a valid sidecar.
 *
 * This mirrors the load-bearing constraints of publication.schema.json (required
 * keys, enums, the footer.always min-1 rule). It is deliberately strict on the
 * required fields and lenient about ignoring unknown extras, so a newer file with
 * additive keys still renders rather than silently disappearing.
 */
export function parsePublication(raw: unknown): Publication | null {
  if (!isObject(raw)) return null;

  if (raw.publication_version !== 1) return null;

  const publisher = raw.publisher;
  if (!isObject(publisher)) return null;
  if (!isNonEmptyString(publisher.name) || !isNonEmptyString(publisher.contact)) return null;

  const subject = raw.subject;
  if (!isObject(subject)) return null;
  if (!isNonEmptyString(subject.name)) return null;
  if (typeof subject.commit !== "string" || subject.commit.length < 7) return null;
  if (typeof subject.snapshot_date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(subject.snapshot_date)) {
    return null;
  }
  if (typeof subject.affiliation !== "string" || !AFFILIATIONS.has(subject.affiliation)) return null;

  if (typeof raw.purpose !== "string" || !PURPOSES.has(raw.purpose)) return null;
  if (typeof raw.update_policy !== "string" || !UPDATE_POLICIES.has(raw.update_policy)) return null;

  const header = raw.header;
  if (!isObject(header) || !isNonEmptyString(header.banner)) return null;
  if (header.front_page !== undefined && !isStringArray(header.front_page)) return null;

  const footer = raw.footer;
  if (!isObject(footer) || !isStringArray(footer.always) || footer.always.length < 1) return null;
  if (footer.front_page !== undefined && !isStringArray(footer.front_page)) return null;

  if (raw.context !== undefined && !isStringArray(raw.context)) return null;
  if (raw.disclaimers !== undefined && !isStringArray(raw.disclaimers)) return null;

  const access = raw.access;
  if (!isObject(access)) return null;
  if (typeof access.visibility !== "string" || !VISIBILITIES.has(access.visibility)) return null;

  const generatedBy = raw.generated_by;
  if (!isObject(generatedBy)) return null;
  if (!isNonEmptyString(generatedBy.tool) || !isNonEmptyString(generatedBy.version)) return null;

  // Structurally valid: cast through the raw object so additive unknown keys are
  // preserved on the value while the typed view exposes only the known shape.
  return raw as unknown as Publication;
}

/** Prefer the subject's public home over its source repository. */
export function publicationSubjectUrl(
  publication: Publication | null,
  repository?: string | null,
): string | null {
  const candidate = publication?.subject.homepage_url
    ?? publication?.subject.repo_url
    ?? repository;
  return typeof candidate === "string" && /^https?:/i.test(candidate) ? candidate : null;
}

/**
 * Resolve a dotted path (e.g. "subject.name") against the publication object.
 * Returns the resolved scalar as a string, or undefined when any segment is
 * missing or the value is not a scalar. Arrays and objects do not resolve.
 */
function resolvePath(pub: Publication, path: string): string | undefined {
  const segments = path.split(".");
  let node: unknown = pub;
  for (const segment of segments) {
    if (!isObject(node)) return undefined;
    node = node[segment];
  }
  if (typeof node === "string") return node;
  if (typeof node === "number" || typeof node === "boolean") return String(node);
  return undefined;
}

/**
 * Apply {{path}} substitution against the publication file itself (design doc,
 * "Text values support {{path}} substitution against the same file").
 *
 * A path that resolves to nothing renders LOUDLY as `[missing: path]`, never as a
 * silent empty string (design doc, follow-up card requirements). An empty-string
 * value is treated as missing so a blank field is not indistinguishable from a
 * correctly filled one.
 */
export function resolvePublicationText(text: string, pub: Publication): string {
  return text.replace(/\{\{\s*([^}]+?)\s*\}\}/g, (_match, rawPath: string) => {
    const path = rawPath.trim();
    const value = resolvePath(pub, path);
    return value === undefined || value === "" ? `[missing: ${path}]` : value;
  });
}

/**
 * The name to DISPLAY in the header. When a valid publication is present its
 * editable subject.name wins; otherwise the folder-derived architecture.name (the
 * contextual default) is used. This is display only: the annotation identity key
 * stays on architecture.name (see utils/annotationStorage.ts), so an edited
 * display name never orphans annotations.
 */
export function publicationDisplayName(pub: Publication | null, fallbackName: string): string {
  if (pub && isNonEmptyString(pub.subject.name)) return pub.subject.name;
  return fallbackName;
}
