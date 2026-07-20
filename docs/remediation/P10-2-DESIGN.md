# P10-2 Security view: design pass

## 1. The honest scope line

A static, deterministic, no-scanner tool can truthfully show security-relevant **surfaces** (where authentication happens, what crosses the network boundary and to where, what parses external input), **postures** (http versus https scheme on outbound calls, presence of mTLS or session config, dependency pin status), **hygiene** (SECURITY.md present or absent, secret-shaped files and whether git tracks them, signed-commit presence), and **evidence** (every claim drills to file:line). It must NEVER claim vulnerability status, CVE presence, taint reachability, exploitability, a secure-versus-insecure verdict, or compliance or certification. It has no vulnerability feed, no dataflow taint, no runtime. It reports what is present and where, not whether it is safe. That boundary is the whole product ethic (VISION No theater): "authentication happens here via JWT" is defensible; "this auth is broken" is theater the tool cannot back.

## 2. The question list (stakeholder to signal source)

1. Where does authentication happen, and of what kind? -> `AUTH_PATTERNS` (constants.py: oauth2, api_key, mtls, session, basic, jwt), today derived only onto edges in derive/relationships.py `_detect_auth` with no line evidence and no string mask. NEW `auth_site` Tier-1 signal (extractor A).
2. What crosses the network boundary, to where, plaintext or TLS? -> existing `url_reference` (carries scheme, so http versus https is already there), `http_client`, `endpoint`, `port` signals. No new extractor.
3. Which files are secret-shaped, and are any tracked in git? -> inventory `secrets` category (already flags .pem/.key/.env/id_rsa with `security_sensitive`) plus NEW git-tracked check (extractor E).
4. Are any secrets hardcoded in source? -> NEW `secret_literal` extractor (C).
5. Which env vars look like credentials? -> existing `env_var` signals filtered by a secret-ish name set (SECRET, TOKEN, PASSWORD, API_KEY, KEY). Classifier only, no new scan.
6. What crypto primitives appear, and where? -> NEW `crypto_primitive` extractor (B).
7. What parses or deserializes external input? -> NEW `input_sink` extractor (D).
8. Which data entities carry sensitive-looking fields? -> existing `data_entity` field lists plus a name classifier (ssn, password, dob, card, token, email).
9. Which dependencies are unpinned, and how large is the dependency surface? -> P10-1 SBOM pin status (bridge, not a new extractor).
10. Does the repo carry security hygiene artifacts? -> NEW project-level checks (E): SECURITY.md, security.txt, dependabot/renovate config, signed-commit sample.
11. Where do authorization decisions live? -> existing Rules lens `policy` type rules.
12. Where is the auth concern, and is it implemented consistently? -> existing correlations auth concern (imports plus access-control keywords plus policy rules).

## 3. New extractors needed

All are Tier 1 per-file (single content read, StringMask, line evidence, deterministic order per I4) except E.

**A. `auth_site`.** Rule: apply `AUTH_PATTERNS` per file through `StringMask.in_string`; emit one signal per auth_type per file with the matched evidence and line. FP risk: the D3 self-scan class, the tool's own `AUTH_PATTERNS` definitions in constants.py match themselves. Mitigation: the string mask (a pattern literal is in-string, skipped), plus a self-scan regression test as with `_http_clients`. Evidence: auth_type, matched text, file:line.

**B. `crypto_primitive`.** Rule: a per-language table of crypto API call shapes (hashlib.md5/sha256, crypto.createHash, CryptoKit/CommonCrypto symbols, bcrypt/argon2, AES/RSA constructors, SecureRandom versus Math.random). FP: names in comments/docstrings and pattern strings. Mitigation: StringMask, call-shaped patterns (a trailing `(`), not bare words. Evidence: primitive name and file:line. It emits the primitive only, never a strong-versus-weak verdict (that would be a judgment the tool cannot defend).

**C. `secret_literal`.** Rule: assignment of a secret-named identifier to a string literal, `(password|passwd|secret|api_?key|token|priv(ate)?_?key)\s*[:=]\s*["'][^"']{8,}["']`. FP risk: the highest in the whole view (the tool's own secret patterns, test fixtures, placeholders). Mitigation, all required: StringMask confirms the RHS is a real literal; exclude env reads (os.environ, process.env, interpolations, format strings); exclude a placeholder allowlist (changeme, xxxx, example, your_key_here); the D3 self-scan test must prove extractor C does not flag constants.py's own patterns. Evidence: the key name and file:line only. The literal value is NEVER copied into the projection.

**D. `input_sink`.** Rule: a conservative per-language table of deserialization and exec sinks (pickle.loads, yaml.load without SafeLoader, eval/exec, subprocess with shell=True, child_process.exec). FP: eval in benign contexts. Mitigation: keep the list short and call-shaped, mask strings/comments. Evidence: sink name and file:line.

**E. Project-level checks (Tier 3/4 reader, like inventory).** Git-tracked status via `git ls-files` membership for each secret-shaped inventory path; existence of SECURITY.md, security.txt, .github/dependabot.yml or renovate config; a signed-commit sample via `git log --format=%G?`. FP low. Evidence: the path, or the git command output.

**F. `sensitive_field`.** Not a scan: a name classifier over existing `data_entity` fields. Label "sensitive-looking," never "PII violation." Evidence: entity, field, file:line.

## 4. The view itself

**L9 Security, a lens, not a bolted-on tab.** It satisfies the lens invariants, which is the test for lens-hood. I11 (rank, do not render): the landing is a set of ranked factual panels, "look here first," not a graph. Panel order by defensible severity of fact: (1) secret-shaped files tracked in git, (2) hardcoded secret literals, (3) plaintext-http outbound calls, (4) auth surfaces, (5) crypto primitives, (6) input sinks, (7) sensitive-looking fields, (8) hygiene checklist, (9) dependency surface from SBOM. I12 (same element, one identity): every auth site, crypto call, and sink is a symbol reachable in Structure and Flow; selecting one keeps breadcrumbs and URL state. I13: the rationale strip rides every element. I14: each panel row is a gesture (drill to line). I15: security findings (tracked secret, hardcoded secret, plaintext boundary) join the existing FindingsSurface with evidence, confidence, and an action.

Renders dense and factual: counts and drill lists, no scores, no letter grades. Color encodes only a defensible binary fact: a git-tracked secret file and a plaintext-http outbound call render amber because the fact (tracked=yes, scheme=http) is certain. Auth types and crypto primitives render neutral, because "weak" is a judgment. Drill-to-line everywhere. Mobile-safe per the global rule: panels restack to one column at 390px, drill lists are finger-sized tap targets, no hover-gated affordance, no horizontal scroll (long file paths truncate with a tap-to-expand).

## 5. Value test verdict

- Network boundary panel: a security engineer sees every outbound destination and which are plaintext, in one place, in seconds. KEEP.
- Auth surfaces: reviewer locates every auth mechanism and its sites without grepping an unknown codebase. KEEP.
- Secret-shaped plus git-tracked: turns "a .env exists" into "a .env is committed to history," the single highest-value fact here. KEEP.
- Hardcoded secret literals (2b): finds credentials in source with drill-to-line. KEEP, gated on the self-scan test passing.
- Env-var credential names: cheap orientation to the secret surface. KEEP.
- Crypto primitives: shows what crypto is in use and where, no verdict. KEEP.
- Input sinks (2b): locates deserialization/exec surface. KEEP, conservative list.
- Sensitive fields: points a pre-audit tech lead at data worth classifying. KEEP.
- Hygiene checklist: instant pre-audit gap list, feeds P10-4. KEEP.
- Dependency surface: KEEP as a bridge panel, owned by P10-1.
- KILLED: any "security score," risk rating, or red-green posture gauge. It fails the value test (a named stakeholder can do nothing new with a number the tool cannot defend) and is exactly the theater the owner rejected.

## 6. Phasing

**P10-2a (one executor session, existing signals plus inventory plus the cheap project checks).** Extractor A (small upgrade of existing AUTH_PATTERNS to a masked Tier-1 signal with evidence), extractor E (git-tracked and hygiene checks), the env-var and sensitive-field classifiers (F), the network boundary panel over existing `url_reference`/`http_client`/`endpoint`/`port`, the SBOM pin-status bridge if P10-1 has landed, and security findings into FindingsSurface. Buildable from this document alone.

**P10-2b (new content-scan extractors).** Extractors B (crypto_primitive), C (secret_literal), D (input_sink). Each ships with its StringMask usage and a D3 self-scan regression test before its panel lands. C does not ship until its self-scan test is green.

## 7. AI overlay boundary

Per I1 (deterministic skeleton) and I9 (provenance-stamped overlay), enrichment may add plain-language explanation of a surface ("this endpoint authenticates with JWT; here is what that gates"), prioritization hints ("review the tracked .env before the crypto sites"), and concern narration, each sentence citing file:line or marked as inference. Enrichment may NEVER assert a vulnerability, a CVE, exploitability, or a secure-versus-insecure verdict; those stay out entirely because neither the deterministic tier nor the model can back them, and an unverifiable security claim is the exact DeepWiki failure this project exists to avoid.

---
