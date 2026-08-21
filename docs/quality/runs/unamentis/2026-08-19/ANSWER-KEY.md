# Answer key: UnaMentis

Charter `comprehension-review/v1`. Built 2026-08-19, before any sitting ran.
Built once per subject and reused on every rerun.

**Sourcing.** Built under charter source priority: the subject's own
architecture documentation first, then an independent reading of the subject's
actual source. It was built with **no access to our projection**. The agent that
established the ground truth was instructed not to read anything under this
repository, and not to read any `architecture.json`, `ai.json` or analysis
output produced by this tool, because grading the tool against its own output
would make the key circular and worthless. The one exception permitted was the
`unamentis` skill file, read solely to learn which four repositories constitute
the subject.

**Who wrote it.** The orchestrator, who ran no sitting for this subject.

## The subject, for the orchestrator's reference only

Four repositories, all on the Mac Studio:

| Repo | Purpose | Language | HEAD |
|---|---|---|---|
| `unamentis` | Monorepo: server, curriculum tooling, USM Core, an in-tree iOS/watchOS app, canonical docs | Swift 132K, Python 125K, TS/TSX 62K, Rust 4.7K | `7422da1`, 2026-07-22 |
| `unamentis-ios` | Swift 6 / SwiftUI iOS and watchOS client | Swift, 474 files, 156,876 lines | `a5717bf`, 2026-08-15 |
| `unamentis-android` | Kotlin / Compose port, feature parity with iOS | Kotlin, 423 files, 130,620 lines | `c90ba1a`, 2026-04-12 |
| `unamentis.org` | Static marketing site, no backend | HTML/CSS/JS, 65 files | `17457cd`, 2026-06-20 |

## How to use this key

Per question: the expected answer, the facts that **must** appear for it to
count as correct, the facts that would be **wrong**, and the source.

Three verdicts are available per battery question: `correct`, `partial`,
`wrong`. A fourth, `unscoreable`, is used where the subject's own source does
not settle the matter. **Never grade an unscoreable question.** A wrong key is
worse than a missing one, because it turns a correct answer into a recorded
failure.

### The two self-contradictions, and why they are the sharpest instrument here

The subject's own source disagrees with itself in two places. Both were found by
reading the subject, not by reading our output.

1. **USM Core's port.** The Rust CLI's own default flag is `8767`
   (`server/usm-core/crates/usm-cli/src/main.rs:33`). A Swift client hard-codes
   `8787` with the comment "USM Core runs on 8787 (distinctly different from
   legacy USM on 8767)" (`server/server-manager/USMXcode-FFI/USMFFI/Core/USMCoreManager.swift:54`).
   The prose architecture docs say 8787.
2. **Which iOS tree is authoritative.** The `unamentis` monorepo's README calls
   itself "an iOS application" and maintains a full, actively committed
   iOS/watchOS tree. The separate `unamentis-ios` repo's README describes
   `unamentis` as server, docs and curriculum only.

**Both are `unscoreable` for the persona.** Neither can be held against a
reviewer.

They are, however, load bearing for the orchestrator in a different way. If the
tool states either fact with confidence and no hedge, that is a **trust
incident**, because the tool would be asserting as settled something its subject
does not settle. If the tool surfaces the contradiction, or marks the fact
inferred or low confidence, that is a **notable strength** and should be
recorded as such. Check both explicitly during verification whether or not a
persona raises them.

---

## P1: the senior engineer who does not know the language

### Q1. What is this product, for whom, and what are its moving parts?

**Expected.** A voice-based AI tutoring platform for long conversational
learning sessions, targeting sub-500ms end-to-end latency, delivering curriculum
content through a custom format and teaching by "teachback" rather than by
giving answers.

**Must appear.** Voice or conversational tutoring as the purpose; learners or
students as the audience; and at least four of these moving parts, by role if
not by name: a mobile client (iOS and/or Android), a Management API backend, USM
Core as the service manager, a web client, an operations console, curriculum
importers, the curriculum format itself.

**Wrong.** Describing it as a text chatbot, as a general-purpose assistant, as a
content management system, or as a single monolithic application. Naming a
company, product or domain that is not this one.

**Source.** `unamentis/README.md:1-15`;
`unamentis/docs/architecture/PROJECT_OVERVIEW.md:1-9` and its own Component
Summary table at `:53-66`.

### Q2. How does the primary client talk to its backend, over what protocols and ports?

**Expected.** REST over plain HTTP under an `/api/*` prefix, plus WebSocket, to
the Management API on **port 8766**. A dedicated audio WebSocket at
`/ws/audio`, and a general WebSocket at `/ws`. Server discovery on the local
network by Bonjour/mDNS, service type `_unamentis._tcp`.

**Must appear.** Port 8766; both REST and WebSocket; and that audio rides a
WebSocket rather than the REST API.

**Partial.** Gets REST and WebSocket but no port, or the port but only one
protocol.

**Wrong.** Naming GraphQL or gRPC as the client-to-backend style. Claiming the
audio path is REST or plain HTTP polling. Claiming HTTPS or TLS on the
client-to-Management-API hop; the clients use plain `http://` and `ws://`.

**Unscoreable.** USM Core's port. See the contradiction above. `8767` and `8787`
are both defensible from the source, so accept either, or none, without penalty.

**Source.** `unamentis/server/management/server.py:4994-5088` (route table),
`:5192` (`/ws`), `:5492` (startup banner); `audio_ws.py:435` and `:414`;
`unamentis-ios/UnaMentis/Core/Config/ServerConfigManager.swift:972-977`;
`unamentis-android/.../data/remote/ApiClient.kt:40` and `WebSocketClient.kt:215`;
`unamentis-ios/.../Core/Discovery/Tiers/BonjourDiscovery.swift:43`;
`unamentis/server/usm-core/config/services.toml:15`.

### Q3. The symptom: mid-session the product stops talking back, no error is shown, session appears live, worse on hotel wifi

**Expected.** The reviewer should reach, in roughly this order: the audio
WebSocket path (`/ws/audio` on the Management API), because a silently dropped
or stalled WebSocket matches "appears to still be running with no error"; then
the TTS and STT provider chain, because the product is explicitly designed to
fall back rather than error; then the Management API process itself as the
single hop everything traverses.

**Must appear.** The audio WebSocket, or the Management API that hosts it, named
as the first or second place to look, **and** an explicit link between "no error
is shown" and the product's deliberate fallback design. That link is the
insight the question is testing: the silence is not an absent error path, it is
a designed one.

**Partial.** Names plausible components but never connects the missing error to
the fallback architecture.

**Wrong.** Sending the reviewer first to the curriculum importers, the
operations console, the marketing site, or the database, none of which sit on
the live audio path.

**Source.** `unamentis/server/management/audio_ws.py:414,435`;
`unamentis/docs/architecture/FALLBACK_ARCHITECTURE.md:1-11` ("never show an
error when a fallback exists") and its chains at `:17-136`.

### Q4. Where does data live, and what does it depend on externally?

**Expected, data.** PostgreSQL 15 with `pg_trgm` for curriculum and production
data; Core Data on iOS; Room/SQLite on Android; local model files on device. A
file-based storage backend exists as a development alternative.

**Expected, external.** Model providers the project does not control: Anthropic,
OpenAI and Google for LLM; Deepgram, AssemblyAI and Groq for speech to text;
ElevenLabs and Deepgram Aura for text to speech. Ollama as the self-hosted
option. Unleash for feature flags. LiveKit optionally for real-time transport.

**Must appear.** PostgreSQL; on-device storage on at least one client; and at
least two named third-party model or speech providers.

**Wrong.** Naming a cloud database the subject does not use, such as DynamoDB,
Firebase or MongoDB. Claiming a third-party authentication provider: **auth is
self-implemented JWT**, and no third-party auth vendor exists in the source.
Claiming a payment provider: **none exists in the source at all.**

**Unscoreable.** Object or blob storage beyond Postgres and on-device files. AWS
Lambda handlers exist but no S3 or GCS configuration was located, so neither
"it uses object storage" nor "it does not" can be graded. Also unscoreable: how
much of the documented AWS and Cloudflare hosting is live rather than planned,
since the document is explicitly a target-state assessment.

**Source.** `unamentis/server/database/schema.sql:1-16`;
`server/database/docker-compose.yml`; `UnaMentis/Core/Persistence/PersistenceController.swift:1-33`;
`unamentis-android/.../data/local/AppDatabase.kt:37-51`; `unamentis/.env.example`;
`unamentis/server/management/auth/auth_middleware.py`;
`server/usm-core/config/services.toml:63-76`.

### Q5. Could you sketch this architecture on a whiteboard?

**Not graded against facts.** Scored for whether the sketch's *shape* is right:
clients on one side, a Management API as the hub, USM Core managing services
beneath it, Postgres behind, external providers off to the side. Credit honesty
about blanks; the question explicitly asks for it. A confident sketch full of
invented detail scores below an accurate sketch with stated gaps.

---

## P2: the non-coding executive

### Q1. What does this system do, in board language?

**Expected.** Software that teaches people by talking with them, using AI, in
long sessions, with the technical bet being that it responds fast enough to feel
like a conversation.

**Must appear.** Teaching or tutoring; voice or conversation; AI. No jargon
required, and jargon is not a bonus.

**Wrong.** Any description that would leave a board with the wrong business.

**Source.** As P1 Q1.

### Q2. What is critical, and what happens if it fails?

**Expected.** The Management API on 8766 is the single hop that carries
curriculum delivery, session persistence and the live audio channel, and it is
the one component with no documented fallback. The speech and language providers
each have documented fallback chains ending in Apple's on-device services, and a
minimum viable configuration runs with no network and no API keys at all, so
provider failure degrades quality rather than stopping the product.

**Must appear.** That provider failure degrades rather than kills, **and** that
something central has no such protection.

**Partial.** Identifies the fallback design but not the unprotected centre, or
the reverse.

**Wrong.** Claiming the product dies if one model vendor goes down. That is
precisely what the fallback architecture is built to prevent.

**Source.** `docs/architecture/FALLBACK_ARCHITECTURE.md:1-11,17-136,138-146`;
absence of any fallback for the Management API in that document.

### Q3. What does it depend on that we do not control?

**Expected.** As P1 Q4's external list. Board framing: multiple interchangeable
AI vendors, deliberately interchangeable.

**Must appear.** At least two named third-party providers, and the observation
that they are substitutable.

**Wrong.** Naming a payment or third-party auth dependency; neither exists.

### Q4. Where is the risk concentrated?

**Expected.** The entire backend runs on one laptop. The subject's own
infrastructure document names its production host as a MacBook Pro M4 Max and
lists among that host's disadvantages, verbatim, "Not always-on (laptop)" and
"Single point of failure". Every backend service is co-located there. Secondarily,
USM Core starts, stops and health-checks every other service and has no
documented redundant instance.

**Must appear.** Concentration on a single machine, or the equivalent
observation that the backend has no redundancy.

**Wrong.** Describing the backend as distributed, redundant, load balanced or
cloud hosted as its current state.

**Source.** `unamentis/docs/architecture/SERVER_INFRASTRUCTURE.md:22-28,33-49`;
`server/usm-core/README.md:15-40`.

**Note for verification.** This is the single highest-value fact in the subject
for an executive, and the most commercially interesting thing the tool could
surface. Check specifically whether the projection carries it at all. If the map
cannot lead a reviewer to "it all runs on one laptop", record that as a finding
regardless of the persona's score.

### Q5. Could you brief someone in five minutes?

**Not graded against facts.** Graded on whether the written five-minute brief
would leave a listener with a correct picture, and on the honesty of the
self-assessment that follows it.

---

## P3: the staff engineer and AI power user

P3's battery is largely about **our tool**, not about the subject, so most of it
is verified rather than keyed. That asymmetry is itself an instrument-retro
item: P3's questions cannot be scored against subject ground truth the way P1's
and P2's can.

### Q1. Do all pathways to the same fact agree?

**Key.** They must. For any component, the facts shown in the UI detail panel,
returned by search, published in `/ai.json` and `/architecture/ai.json`, and
stored in that component's `architecture/data/detail-<safe_id>.json` shard must
be identical. Any disagreement is a defect in our tool, at severity high if it
concerns a component's identity, dependencies or file paths.

**Verification.** The orchestrator checks every claimed agreement or
disagreement directly against the mirror's JSON. A persona claiming agreement is
not evidence of agreement.

### Q2. Could an agent answer a real question from the machine front door alone, and at what token cost?

**Key, the comparison basis.** The published machine-readable surface is 280
files and 20,402,031 bytes total, of which the front door proper is `/ai.json`,
`/llms.txt`, `/architecture/manifest.json` and a search index of 8 shards, with
254 per-component detail shards behind them. The raw subject is roughly 466K
lines in `unamentis`, 168K in `unamentis-ios`, 146K in `unamentis-android` and
13K in `unamentis.org`.

Any order-of-magnitude estimate resting on those figures is acceptable. A
specific token count is not required and should not be demanded.

**Wrong.** Claiming the front door is larger than the raw source.

### Q3. What does the tool claim that it cannot support?

**Verified, not keyed.** Every instance the persona raises is checked against
the dataset and the source. The two subject self-contradictions above are
checked explicitly whether or not the persona finds them.

### Q4. Fastest route from question to citable answer

**Verified.** The orchestrator reproduces the claimed route and times it.

### Q5. Would you trust its output in a code review?

**Not graded against facts.** The reasoning and the stated conditions are the
content.

---

## Unscoreable, collected

| Question | Why |
|---|---|
| P1 Q2, USM Core's port | Source contradicts itself: 8767 in the CLI default, 8787 in a client and in prose docs |
| P1 Q4, object storage | Lambda handlers exist, no S3 or GCS configuration located |
| P1 Q4, live versus planned cloud hosting | The hosting document is explicitly target state |
| Any question turning on which iOS tree is authoritative | The two repositories' READMEs contradict each other |
| Monetization or payment | Absent from all four repos; cannot distinguish "not built" from "handled outside the four-repo scope" |
| Observability wiring | An OpenTelemetry spec exists, no SDK import located |
