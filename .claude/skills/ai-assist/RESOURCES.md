# AI Assist Resources

## ai_enhance Schema Reference

### Component.ai_enhance

```typescript
interface ComponentAIEnhance {
  // Core fields
  help_text?: string;              // 3-5 sentence explanation for ? tooltip
  architectural_role?: string;     // from vocabulary below, or null
  data_handled?: string;           // what data flows through this component
  criticality?: "critical" | "important" | "supporting";
  testing_assessment?: string;     // 1-2 sentence evaluation of test quality

  // UI actions analysis (populate when component has `actions` array)
  actions_summary?: string;        // 1-2 sentence summary of UI actions by type
  key_user_flows?: string[];       // 2-5 key user flows as user-facing descriptions

  // Deeper testing insight (populate when component has `testing` data)
  testing_gaps?: string[];         // 1-3 specific gaps in test coverage
  testing_maturity?: "comprehensive" | "adequate" | "minimal" | "untested";

  // External services context (populate when `external_services` exists)
  external_services_assessment?: string;  // dependencies and critical path analysis

  // Infrastructure context (populate when `port` is set)
  port_assessment?: string;        // what this port is used for architecturally

  // Codebase health (populate for large components: >5K lines or >20 files)
  complexity_assessment?: string;  // size/complexity observations

  // Technology context (populate when `language`/`framework` are set)
  tech_context?: string;           // how tech choices fit the broader architecture

  // Enhancement metadata (always set)
  ai_enhanced_at?: string;         // ISO timestamp of when enhancement was performed
  ai_enhance_version?: number;     // schema version, currently 2
}
```

### Relationship.ai_enhance

```typescript
interface RelationshipAIEnhance {
  data_flow_description?: string;  // what flows across this connection
  importance?: "primary" | "secondary" | "internal";
  ai_discovered?: boolean;         // true only for AI-added relationships
  authentication_detail?: string;  // prose explanation of the auth flow
  payload_examples?: string[];     // 2-3 example payload descriptions
  error_handling?: string;         // how errors are handled on this connection
  sla_notes?: string;              // latency expectations, rate limits, timeouts
  security_notes?: string;         // encryption, certificate pinning, network policies

  // Infrastructure context (populate when relationship has a `port`)
  port_context?: string;           // what service listens on this port and how

  // Enhancement metadata (always set)
  ai_enhanced_at?: string;         // ISO timestamp
}
```

### Relationship base fields (fill if empty/null)

The static analyzer may populate these. AI should fill any that remain empty:
- `authentication`: "jwt" | "oauth2" | "api_key" | "mtls" | "basic" | "session"
- `data_format`: "json" | "protobuf" | "graphql" | "xml" | "binary" | "msgpack"
- `api_style`: "rest" | "graphql" | "grpc" | "websocket" | "soap" | "rpc"
- `endpoints`: `[{"method": "GET", "path": "/users"}]`
- `middleware`: `["rate_limit", "cors", "auth", "logging", "compression"]`
- `transport`: "http/2" | "tcp" | "udp" | "amqp" | "mqtt"
- `queue_name`: topic or queue name for message queue relationships
- `connection_pattern`: "connection_pool" | "orm" | "per_request" | "singleton"

### Architecture.ai_enhance (root level)

```typescript
interface ArchitectureAIEnhance {
  // Core fields
  summary?: string;                // 3-5 sentence executive summary
  data_flow_narrative?: string;    // how a typical request flows through the system
  component_groups?: Array<{
    name: string;
    component_ids: string[];       // component IDs belonging to this group
  }>;

  // Changelog interpretation (populate when `changelog` array exists)
  recent_changes_summary?: string; // 2-3 sentence summary of recent architectural evolution

  // Analyzer improvement observations
  observations?: AnalyzerObservation[];

  // Cross-cutting summaries
  tech_diversity?: string;         // 1-2 sentence summary of technology mix
  test_health_summary?: string;    // 1-2 sentence overview of testing health

  // Enhancement metadata (always set)
  ai_enhanced_at?: string;         // ISO timestamp
  ai_enhance_version?: number;     // schema version, currently 2
}

interface AnalyzerObservation {
  category: "missing_relationship" | "misclassified_component" | "naming_issue"
          | "structural_suggestion" | "detection_gap" | "data_quality";
  component_id?: string;           // which component this relates to, if any
  description: string;             // what was observed
  suggestion?: string;             // what could be improved
  confidence: "high" | "medium" | "low";
  sources?: string[];              // Phase 4 assembly only: partition IDs that reported this
}
```

## Architectural Role Vocabulary

Use exactly one of these values for `architectural_role`, or null if none apply:

| Role | Description |
|------|-------------|
| `api-gateway` | Entry point that routes external requests to internal services |
| `auth-service` | Handles authentication, authorization, tokens, sessions |
| `data-store` | Primary database or persistent storage (SQL, NoSQL, file-based) |
| `cache-layer` | In-memory cache (Redis, Memcached) for performance |
| `queue-processor` | Consumes messages from a queue (SQS, RabbitMQ, Kafka consumer) |
| `event-bus` | Publishes/subscribes events across services |
| `orchestrator` | Coordinates workflows across multiple services |
| `worker` | Background job processor (cron, task queue worker) |
| `proxy` | Reverse proxy, load balancer, or API proxy |
| `monitoring` | Health checks, metrics collection, alerting |
| `logging` | Centralized logging, log aggregation |
| `scheduler` | Time-based task scheduling (cron, scheduled jobs) |
| `notification-service` | Push notifications, email, SMS delivery |
| `file-storage` | File upload/download, asset management, CDN origin |
| `search-engine` | Full-text search (Elasticsearch, Algolia, Meilisearch) |
| `ml-pipeline` | Machine learning model serving or training pipeline |
| `presentation-layer` | UI rendering, view layer, template engine |
| `business-logic` | Core domain logic, business rules |
| `data-access` | ORM, repository pattern, data access layer |

## Criticality Guidelines

- **critical**: The system cannot function without this component. If it goes down, users see errors or the app is unusable. Examples: main API server, primary database, auth service.
- **important**: The system works without it but with degraded functionality. Examples: cache layer, search, notification service.
- **supporting**: Developer tooling, utilities, infrastructure helpers. Examples: logging, monitoring, CI/CD config, test utilities.

## Testing Maturity Guidelines

- **comprehensive**: >80% coverage, multiple test types (unit + integration or e2e), CI integration. Testing is thorough and well-maintained.
- **adequate**: >50% coverage or reasonable test count proportional to component size. Core paths are tested.
- **minimal**: Some tests exist but coverage is thin, only one test type, or tests don't cover critical paths.
- **untested**: Zero test files detected. Use null if no `testing` data exists at all.

## Observation Categories

- **missing_relationship**: A connection between components that the analyzer did not detect but is visible in source code (e.g., HTTP calls, database connections, message queue usage).
- **misclassified_component**: A component whose `type` or `architectural_role` doesn't match what the code actually does.
- **naming_issue**: A component `name` that is misleading, too generic, or doesn't reflect the component's purpose.
- **structural_suggestion**: The component hierarchy could be reorganized for clarity (e.g., a large component should be split, or related components should be grouped).
- **detection_gap**: A pattern or framework feature the analyzer doesn't detect but should (e.g., a navigation pattern, a service registration mechanism).
- **data_quality**: Existing analyzer data is incorrect or incomplete (e.g., wrong port, missing framework detection, incorrect language attribution).

## Importance Guidelines (for relationships)

- **primary**: Core data path. This is how the main user-facing features communicate. Examples: client-to-API calls, API-to-database queries.
- **secondary**: Used regularly but not on the critical path. Examples: cache lookups, async notification delivery, analytics events.
- **internal**: Implementation detail, not architecturally significant. Examples: utility imports, shared type definitions, internal module dependencies.

## DPEA Pipeline Templates

### Terminology Glossary Template (Phase 1 Digest)

The digest agent produces a terminology glossary that all downstream subagents
must follow. This prevents terminology drift across partitions.

```markdown
## Terminology Glossary
| Term | Canonical Name | Do NOT use |
|------|---------------|------------|
| The primary database | PostgreSQL database | DB, Postgres, data store, persistence layer |
| User authentication | JWT authentication | auth, login system, token auth |
| The iOS client | iOS app | mobile app, iPhone app, client |
| REST API calls | HTTP requests | API calls, network calls, server calls |
```

**Rules for glossary construction:**
- Include every domain-specific entity (services, protocols, data models)
- Include technology names with their canonical form
- List 2-4 synonyms to avoid for each term
- Downstream agents MUST use the exact canonical name
- Phase 4 normalization checks for violations

### Criticality Calibration Template (Phase 1 Digest)

The digest agent produces calibration guidance so subagents rate criticality
consistently across partitions.

```markdown
## Criticality Calibration

In this codebase:
- "critical" means: Components on the primary user-facing request path.
  Without these, users cannot use the application at all.
  Examples: backend/api (sole API entry point, 45 inbound relationships),
  postgres (primary data store, all state lives here).
  Guideline: typically 10-15% of components in a well-architected system.

- "important" means: Components that provide significant functionality but
  whose absence degrades rather than breaks the system.
  Examples: redis-cache (performance degrades without caching),
  notification-worker (emails stop but core features work).
  Guideline: typically 25-35% of components.

- "supporting" means: Developer tooling, utilities, monitoring, logging,
  CI/CD configuration, test utilities, and leaf-node UI screens that are
  not on the critical path.
  Guideline: typically 50-65% of components.

Structural signals for criticality assessment:
- >10 inbound relationships: likely critical or important
- Articulation point in dependency graph: likely critical
- 0 inbound relationships (leaf node): likely supporting
- Component on the primary data flow path: likely critical
```

### Quality Rubric (Phase 3 Subagent Context)

Include these calibration examples in every subagent prompt to ensure
consistent quality. Each example shows the expected level of detail.

**Good help_text (4 sentences, specific, references neighbors):**
> "The UserService handles all user lifecycle operations including registration,
> profile updates, and account deletion. It is called by the API Gateway for
> every authenticated request to validate user sessions. It writes to the
> PostgreSQL database via the UserRepository and publishes user events to the
> event bus for downstream consumers. Without this service, no authenticated
> operations can proceed."

**Bad help_text (too vague, no context):**
> "This service manages users. It handles CRUD operations."

**Good data_handled (specific data types):**
> "User profile objects, authentication tokens, session metadata, password hashes, email verification codes"

**Bad data_handled (too generic):**
> "User data"

**Good criticality justification:**
> Criticality: "critical" because this is the sole API entry point with 32 inbound
> relationships and is an articulation point in the dependency graph. Per the digest
> calibration, components on the primary request path are critical.

**Bad criticality justification:**
> Criticality: "critical" because it seems important.

### Partition Result Format (Phase 3 Output)

Each subagent writes its output as `enhancement/result-{n}.json`:

```json
{
  "partition_id": 0,
  "components": {
    "backend/api": {
      "help_text": "...",
      "architectural_role": "api-gateway",
      "data_handled": "...",
      "criticality": "critical",
      "testing_assessment": "...",
      "testing_maturity": "comprehensive",
      "testing_gaps": ["..."],
      "port_assessment": "...",
      "tech_context": "...",
      "ai_enhanced_at": "2026-03-01T12:00:00Z",
      "ai_enhance_version": 2
    }
  },
  "component_fields": {
    "backend/api": {
      "description": "REST API server handling all client requests.",
      "docs": {
        "purpose": "Central API mediating between clients and data.",
        "key_decisions": ["JWT auth with refresh tokens"],
        "patterns": ["Service Layer", "Repository Pattern"]
      }
    }
  },
  "relationships": {
    "ios-app|backend/api|http": {
      "data_flow_description": "iOS app sends authenticated REST requests.",
      "importance": "primary",
      "authentication_detail": "JWT tokens with refresh rotation.",
      "ai_enhanced_at": "2026-03-01T12:00:00Z"
    }
  },
  "relationship_fields": {
    "ios-app|backend/api|http": {
      "label": "REST API calls",
      "authentication": "jwt",
      "data_format": "json",
      "api_style": "rest"
    }
  },
  "discovered_relationships": [],
  "local_observations": [
    {
      "category": "missing_relationship",
      "component_id": "backend/api",
      "description": "API server imports ioredis but no Redis relationship exists.",
      "suggestion": "Add Redis connection detection for ioredis imports.",
      "confidence": "high"
    }
  ]
}
```

### Phase 4 Adjustments Format

The assembly agent writes `enhancement/adjustments.json`:

```json
{
  "terminology_replacements": [
    {
      "component_id": "backend/workers",
      "field": "help_text",
      "old": "Postgres database",
      "new": "PostgreSQL database"
    }
  ],
  "criticality_overrides": [
    {
      "component_id": "shared/utils",
      "old": "critical",
      "new": "supporting",
      "reason": "Leaf node with 0 inbound relationships, no evidence of critical path involvement."
    }
  ],
  "aggregated_observations": [
    {
      "category": "missing_relationship",
      "component_id": "backend/api",
      "description": "Multiple subagents flagged Redis connection not detected.",
      "suggestion": "Add Redis connection detection for ioredis/node-redis.",
      "confidence": "high",
      "sources": ["partition-0", "partition-2"]
    }
  ],
  "quality_flags": [
    "Partition 3 has unusually short help_text (avg 2.1 sentences vs 3.8 overall)",
    "No data-access roles assigned across 256 components, likely a gap"
  ]
}
```

## Example: Enhanced Component

```json
{
  "id": "backend/api",
  "name": "API Server",
  "type": "api-server",
  "description": "REST API server that handles all client requests for user management, content delivery, and real-time collaboration features.",
  "docs": {
    "purpose": "Central API that mediates between client apps and the data layer.",
    "key_decisions": [
      "Uses Express.js with TypeScript for type safety",
      "JWT-based auth with refresh token rotation",
      "Rate limiting via Redis sliding window"
    ],
    "patterns": ["API Layer", "Service Layer", "Repository Pattern"]
  },
  "ai_enhance": {
    "help_text": "This is the main API server that all client applications communicate with. It receives HTTP requests from the iOS, Android, and web clients, processes them through a service layer, and queries the PostgreSQL database via a repository pattern. It also manages WebSocket connections for real-time collaboration features.",
    "architectural_role": "api-gateway",
    "data_handled": "User authentication tokens, content CRUD operations, real-time collaboration events, file upload metadata",
    "criticality": "critical",
    "testing_assessment": "Good coverage with 85% line coverage via Jest. Integration tests cover all major endpoints.",
    "testing_maturity": "comprehensive",
    "testing_gaps": ["No load testing for WebSocket connections"],
    "port_assessment": "Listens on port 8080 as the sole HTTP entry point for all client traffic.",
    "tech_context": "Express.js with TypeScript, following the service-repository pattern common in Node.js backends.",
    "external_services_assessment": "Depends on Stripe for payments (critical path) and SendGrid for email (degraded without it).",
    "ai_enhanced_at": "2026-03-01T12:00:00Z",
    "ai_enhance_version": 2
  }
}
```

## Example: Enhanced Relationship

```json
{
  "source": "ios-app",
  "target": "backend/api",
  "type": "http",
  "label": "REST API",
  "protocol": "HTTP",
  "port": 8080,
  "authentication": "jwt",
  "data_format": "json",
  "api_style": "rest",
  "middleware": ["rate_limit", "cors", "auth"],
  "ai_enhance": {
    "data_flow_description": "iOS app sends authenticated REST requests for user data, content, and collaboration actions.",
    "importance": "primary",
    "authentication_detail": "JWT tokens issued during login, refreshed via /auth/refresh endpoint. Tokens include user ID and role claims.",
    "payload_examples": ["User profile JSON with preferences", "Content list with pagination metadata"],
    "security_notes": "All traffic over HTTPS with certificate pinning on iOS client."
  }
}
```

## Example: AI-Discovered Relationship

```json
{
  "source": "backend/api",
  "target": "redis-cache",
  "type": "database",
  "label": "Session cache",
  "protocol": "Redis",
  "port": 6379,
  "bidirectional": true,
  "ai_enhance": {
    "ai_discovered": true,
    "data_flow_description": "API server reads/writes user sessions and rate-limit counters to Redis.",
    "importance": "secondary"
  }
}
```

## Example: Architecture-Level Enhancement

```json
{
  "name": "MyProject",
  "ai_enhance": {
    "summary": "MyProject is a real-time collaboration platform with native iOS and web clients backed by an Express.js API server. The architecture follows a client-server pattern with PostgreSQL for persistence and Redis for caching and real-time event distribution. Authentication uses JWT with refresh token rotation.",
    "data_flow_narrative": "A typical request starts when a user action in the iOS or web client triggers an HTTP request to the API server. The server validates the JWT token, processes the request through the service layer, queries PostgreSQL via the repository pattern, and returns a JSON response. For real-time features, the server publishes events to Redis pub/sub, which are forwarded to connected WebSocket clients.",
    "component_groups": [
      { "name": "Client Layer", "component_ids": ["ios-app", "web-app"] },
      { "name": "API Layer", "component_ids": ["backend/api"] },
      { "name": "Data Layer", "component_ids": ["postgres", "redis-cache"] }
    ],
    "recent_changes_summary": "Over the last 3 updates, a NotificationWorker was added for async email delivery and the API server gained WebSocket support. The architecture is evolving toward event-driven patterns.",
    "tech_diversity": "Primarily TypeScript (72%) with Swift (28%) for the iOS client. Backend and web share TypeScript for maximum code reuse.",
    "test_health_summary": "4 of 5 components have tests. API server has comprehensive coverage (85%), but the iOS client has minimal testing (12% coverage, unit tests only).",
    "observations": [
      {
        "category": "missing_relationship",
        "component_id": "backend/api",
        "description": "API server references Redis for session storage but no cache relationship was detected by the analyzer.",
        "suggestion": "Add Redis connection pattern detection for ioredis/node-redis imports.",
        "confidence": "high"
      },
      {
        "category": "detection_gap",
        "component_id": "ios-app",
        "description": "SwiftUI sheet presentations in SettingsView are not detected as navigation relationships.",
        "suggestion": "Extend SwiftUIFlowDetector to handle .sheet(item:) with dynamic destinations.",
        "confidence": "medium"
      }
    ],
    "ai_enhanced_at": "2026-03-01T12:00:00Z",
    "ai_enhance_version": 2
  }
}
```
