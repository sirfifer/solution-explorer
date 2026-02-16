# AI Assist Resources

## ai_enhance Schema Reference

### Component.ai_enhance

```typescript
interface ComponentAIEnhance {
  help_text?: string;              // 3-5 sentence explanation for ? tooltip
  architectural_role?: string;     // from vocabulary below, or null
  data_handled?: string;           // what data flows through this component
  criticality?: "critical" | "important" | "supporting";
}
```

### Relationship.ai_enhance

```typescript
interface RelationshipAIEnhance {
  data_flow_description?: string;  // what flows across this connection
  importance?: "primary" | "secondary" | "internal";
  ai_discovered?: boolean;         // true only for AI-added relationships
}
```

### Architecture.ai_enhance (root level)

```typescript
interface ArchitectureAIEnhance {
  summary?: string;                // 3-5 sentence executive summary
  data_flow_narrative?: string;    // how a typical request flows through the system
  component_groups?: Array<{
    name: string;
    component_ids: string[];       // component IDs belonging to this group
  }>;
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

## Importance Guidelines (for relationships)

- **primary**: Core data path. This is how the main user-facing features communicate. Examples: client-to-API calls, API-to-database queries.
- **secondary**: Used regularly but not on the critical path. Examples: cache lookups, async notification delivery, analytics events.
- **internal**: Implementation detail, not architecturally significant. Examples: utility imports, shared type definitions, internal module dependencies.

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
    "criticality": "critical"
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
  "ai_enhance": {
    "data_flow_description": "iOS app sends authenticated REST requests for user data, content, and collaboration actions.",
    "importance": "primary"
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
    ]
  }
}
```
