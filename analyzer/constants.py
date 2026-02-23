"""Constants and configuration for the architecture analyzer."""

# Directories to always skip
SKIP_DIRS = {
    ".git", "node_modules", ".build", "build", "dist", "DerivedData",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "target", ".next", ".nuxt", ".output", ".vercel", ".turbo",
    "vendor", "Pods", ".swiftpm", ".sass-cache", "coverage",
    ".gradle", ".idea", ".vscode", "venv", ".venv", "env",
    ".tox", "egg-info", ".eggs", ".cache",
    "htmlcov",  # Python coverage HTML output
}

# Suffix patterns for directory names that indicate prebuilt binary frameworks
# (not source code to analyze). These are matched by suffix.
SKIP_DIR_SUFFIXES = {".xcframework", ".framework", ".dSYM"}

# File extensions to skip
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".avif",
    ".mp3", ".mp4", ".wav", ".ogg", ".webm", ".mov",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".lock", ".sum", ".resolved",
    ".DS_Store", ".pyc", ".pyo", ".class", ".o", ".a", ".so", ".dylib",
    ".bin", ".dat", ".db", ".sqlite", ".sqlite3",
    ".gguf", ".mlmodel", ".mlmodelc", ".mlpackage",
    ".xcworkspace",  # directory-like
}

LANGUAGE_MAP = {
    ".swift": "swift",
    ".py": "python",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".dart": "dart",
    ".vue": "vue",
    ".svelte": "svelte",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".mdx": "markdown",
}

# Marker files that indicate a component boundary
COMPONENT_MARKERS = {
    "Package.swift": ("swift", "package"),
    "Cargo.toml": ("rust", "package"),
    "package.json": ("typescript", "package"),
    "pyproject.toml": ("python", "package"),
    "setup.py": ("python", "package"),
    "setup.cfg": ("python", "package"),
    "go.mod": ("go", "module"),
    "Gemfile": ("ruby", "package"),
    "build.gradle": ("java", "package"),
    "build.gradle.kts": ("kotlin", "package"),
    "pom.xml": ("java", "package"),
    "pubspec.yaml": ("dart", "package"),
    "Makefile": (None, "module"),
    "Dockerfile": (None, "service"),
    "docker-compose.yml": (None, "infrastructure"),
    "docker-compose.yaml": (None, "infrastructure"),
    "template.yaml": (None, "infrastructure"),   # AWS SAM
    "template.yml": (None, "infrastructure"),     # AWS SAM
    "serverless.yml": (None, "infrastructure"),   # Serverless Framework
    "serverless.yaml": (None, "infrastructure"),  # Serverless Framework
    "Info.plist": ("swift", "application"),
}

# Directory names that suggest content-only (non-architectural) directories
CONTENT_DIR_NAMES = {
    "wiki", "wiki-content", "docs", "doc", "documentation",
    "curriculum", "prompts", "prompt-templates",
    "assets", "resources", "fixtures", "samples", "examples",
    "models", "data", "migrations", "output", "baselines",
}

# File extensions considered "content" (not code)
CONTENT_EXTENSIONS = {
    ".md", ".mdx", ".txt", ".rst", ".json", ".yaml", ".yml",
    ".csv", ".tsv", ".xml",
}

# Languages considered actual code (for port detection and relationship scanning).
# Excludes markup, config, and content languages that can contain port-like numbers.
CODE_LANGUAGES = {
    "swift", "python", "rust", "typescript", "javascript",
    "go", "java", "kotlin", "ruby", "cpp", "c", "csharp", "dart",
    "vue", "svelte", "shell",
}

# HTTP client patterns by language - used to detect when a component makes HTTP calls
# Each pattern group helps identify outbound HTTP connections
HTTP_CLIENT_PATTERNS = {
    # Swift/iOS patterns - URLSession, Alamofire, etc.
    "swift": [
        r'URLSession\s*\.\s*shared',
        r'URLSession\s*\(',
        r'URLRequest\s*\(',
        r'dataTask\s*\(\s*with:',
        r'\.data\s*\(\s*from:',
        r'AF\s*\.\s*request',  # Alamofire
        r'Moya\s*\.\s*request',
    ],
    # TypeScript/JavaScript patterns
    "typescript": [
        r'\bfetch\s*\(',
        r'axios\s*\.\s*(?:get|post|put|delete|patch|request)',
        r'\.ajax\s*\(',
        r'http\.(?:get|post|put|delete)',
        r'request\s*\(',
    ],
    "javascript": [
        r'\bfetch\s*\(',
        r'axios\s*\.\s*(?:get|post|put|delete|patch|request)',
        r'\.ajax\s*\(',
        r'http\.(?:get|post|put|delete)',
        r'request\s*\(',
    ],
    # Python patterns
    "python": [
        r'requests\s*\.\s*(?:get|post|put|delete|patch)',
        r'httpx\s*\.\s*(?:get|post|put|delete|patch)',
        r'aiohttp\.ClientSession',
        r'urllib\.request',
        r'http\.client',
    ],
    # Go patterns
    "go": [
        r'http\.(?:Get|Post|NewRequest)',
        r'client\.(?:Get|Post|Do)',
    ],
    # Kotlin/Android patterns
    "kotlin": [
        r'OkHttpClient',
        r'Retrofit',
        r'HttpClient',
        r'\.execute\s*\(\s*\)',
    ],
    # Rust patterns
    "rust": [
        r'reqwest::(?:get|Client)',
        r'hyper::Client',
        r'surf::(?:get|post)',
    ],
}

# URL patterns to extract from code - helps identify target services
URL_EXTRACTION_PATTERNS = [
    # Full URLs with scheme
    r'["\'](?P<url>https?://[a-zA-Z0-9][-a-zA-Z0-9.]*(?::\d+)?(?:/[^"\']*)?)["\']',
    # Environment variable references for URLs
    r'(?:API_URL|SERVER_URL|BASE_URL|ENDPOINT|_HOST|_SERVER)\s*[=:]\s*["\'](?P<url>[^"\']+)["\']',
    # Service names in docker-compose style (service:port)
    r'["\'](?P<service>[a-zA-Z][-a-zA-Z0-9_]*):\d+["\']',
]

# Logging/observability framework patterns - helps detect logging services
LOGGING_SERVICE_PATTERNS = {
    "sentry": ["sentry-sdk", "sentry", "@sentry/node", "@sentry/browser"],
    "datadog": ["ddtrace", "datadog", "@datadog/browser-logs"],
    "newrelic": ["newrelic", "@newrelic/browser-agent"],
    "grafana": ["grafana", "loki-client"],
    "prometheus": ["prometheus", "prometheus-client", "prom-client"],
    "elasticsearch": ["elasticsearch", "@elastic/elasticsearch"],
    "fluentd": ["fluent-logger", "fluentd"],
}

# Well-known external cloud APIs - detected to show external dependencies
# Maps domain patterns to (service_name, service_category) tuples
EXTERNAL_CLOUD_APIS = {
    # LLM/AI APIs
    "api.openai.com": ("OpenAI", "ai"),
    "api.anthropic.com": ("Anthropic", "ai"),
    "api.groq.com": ("Groq", "ai"),
    "api.cohere.ai": ("Cohere", "ai"),
    "api.mistral.ai": ("Mistral", "ai"),
    "generativelanguage.googleapis.com": ("Google AI", "ai"),
    # Speech APIs
    "api.deepgram.com": ("Deepgram", "speech"),
    "api.assemblyai.com": ("AssemblyAI", "speech"),
    "api.elevenlabs.io": ("ElevenLabs", "speech"),
    "api.speechmatics.com": ("Speechmatics", "speech"),
    # Other cloud services
    "api.stripe.com": ("Stripe", "payments"),
    "api.twilio.com": ("Twilio", "communications"),
    "api.sendgrid.com": ("SendGrid", "email"),
    "api.github.com": ("GitHub", "devtools"),
    "api.gitlab.com": ("GitLab", "devtools"),
    "api.slack.com": ("Slack", "communications"),
    "api.firebase.google.com": ("Firebase", "backend"),
    "firestore.googleapis.com": ("Firestore", "database"),
}

# iOS/watchOS framework imports that indicate companion app communication
WATCH_CONNECTIVITY_IMPORTS = [
    "WatchConnectivity",
    "WCSession",
    "WCSessionDelegate",
]

# Framework specificity ranking: more specific frameworks override generic ones
# at the component level. E.g., if one file uses SwiftUI and another uses AppKit,
# the component framework should be AppKit (macOS-only). Similarly, Next.js
# overrides React since Next.js is built on React.
FRAMEWORK_PRIORITY = {
    # Swift
    "SwiftUI": 1,      # Cross-platform (iOS, macOS, watchOS, tvOS)
    "UIKit": 2,         # iOS-specific
    "AppKit": 2,        # macOS-specific
    "WatchKit": 2,      # watchOS-specific
    "Vapor": 3,         # Server-side Swift
    # JavaScript / TypeScript
    "React": 1,         # Generic UI library
    "Vue": 1,           # Generic UI framework
    "Svelte": 1,        # Generic UI framework
    "Next.js": 2,       # React meta-framework (includes React)
    "Angular": 2,       # Full framework
    "Express": 2,       # Server-side Node
    # Python
    "Flask": 1,         # Lightweight server
    "Starlette": 1,     # Lightweight async server
    "Click": 1,         # CLI framework
    "FastAPI": 2,       # Built on Starlette, more specific
    "Django": 2,        # Full framework
    "aiohttp": 2,       # Full async framework
    "Tornado": 2,       # Full async framework
    "pytest": 1,        # Test framework
    # Rust
    "Tokio": 1,         # Async runtime (generic)
    "Warp": 2,          # HTTP framework built on Tokio
    "Axum": 2,          # HTTP framework built on Tokio
    "Actix": 2,         # HTTP framework
    "Rocket": 2,        # HTTP framework
    # Go
    "net/http": 1,      # Standard library
    "Gorilla": 2,       # Router built on net/http
    "Chi": 2,           # Router built on net/http
    "Gin": 3,           # Full framework
    "Echo": 3,          # Full framework
    "Fiber": 3,         # Full framework
    "Beego": 3,         # Full framework
    # Ruby
    "Sinatra": 1,       # Lightweight
    "Grape": 1,         # API-only
    "Hanami": 2,        # Full framework
    "Rails": 3,         # Full framework
}

# UI Flow Detection constants

# Directories whose names suggest they contain UI/view code.
UI_DIR_NAMES = {
    "ui", "views", "screens", "pages", "features",
    "modules", "tabs", "navigation", "scenes",
}

# View struct name suffixes that suggest a full screen (not a tiny helper).
SCREEN_SUFFIXES = ("View", "Screen", "Page", "Tab", "Panel", "Dashboard")

# View name patterns that indicate helper/subviews, not navigable screens.
# These are small reusable UI pieces, not full navigable pages.
HELPER_SUFFIXES = ("Sheet", "HelpSheet", "Row", "Cell", "Card", "Button",
                   "Badge", "Indicator", "Overlay", "Popover", "Toolbar",
                   "Header", "Footer", "Banner", "Toast", "Chip", "Style",
                   "Frame", "Ring", "Level", "Meter", "Placeholder",
                   "Buttons", "Controls", "Animation", "Chart", "Image",
                   "Error", "Content", "Status", "Preview",
                   "Renderer", "Asset", "Math", "Logo", "Icon", "Picker",
                   "Wrapper", "Container", "Progress", "Calendar")

# View name substrings that indicate the view is a helper, not a screen.
# Checked with 'in' rather than 'endswith'.
HELPER_CONTAINS = ("Fallback", "Inline", "Fullscreen", "SidePanel",
                   "Empty", "Mini", "Static", "Scanning", "Idle",
                   "Placeholder", "Thumbnail", "Compact", "Snippet")


# ---------------------------------------------------------------------------
# Test Coverage Detection
# ---------------------------------------------------------------------------

# Directory names that contain test files
TEST_DIR_NAMES = {
    "tests", "test", "spec", "specs", "__tests__",
    "testing", "test_suite", "e2e", "integration",
}

# E2E test directory indicators
E2E_DIR_NAMES = {"e2e", "cypress", "playwright", "end-to-end", "e2e-tests"}

# Integration test directory indicators
INTEGRATION_DIR_NAMES = {"integration", "functional", "integration-tests"}

# Regex patterns to count individual test functions/methods per language
TEST_FUNCTION_PATTERNS = {
    "python": [
        r"^\s*def\s+test_\w+",
        r"^\s*async\s+def\s+test_\w+",
    ],
    "typescript": [
        r"""(?:it|test)\s*\(\s*['"]""",
        r"""(?:it|test)\s*\.\s*(?:only|skip)\s*\(""",
    ],
    "javascript": [
        r"""(?:it|test)\s*\(\s*['"]""",
        r"""(?:it|test)\s*\.\s*(?:only|skip)\s*\(""",
    ],
    "swift": [
        r"^\s*func\s+test\w+\s*\(",
    ],
    "go": [
        r"^\s*func\s+Test\w+\s*\(\s*t\s+\*testing\.T",
    ],
    "rust": [
        r"#\[test\]",
        r"#\[tokio::test\]",
    ],
    "ruby": [
        r"""(?:it|specify)\s+['"]""",
        r"^\s*def\s+test_\w+",
    ],
    "java": [
        r"@Test\b",
        r"@ParameterizedTest\b",
    ],
    "kotlin": [
        r"@Test\b",
    ],
}

# Config files that indicate a test framework
TEST_FRAMEWORK_INDICATORS = {
    "jest.config.js": "Jest",
    "jest.config.ts": "Jest",
    "jest.config.mjs": "Jest",
    "vitest.config.ts": "Vitest",
    "vitest.config.js": "Vitest",
    "vitest.config.mts": "Vitest",
    "pytest.ini": "pytest",
    "conftest.py": "pytest",
    "setup.cfg": "pytest",  # often contains [tool:pytest]
    ".rspec": "RSpec",
    "cypress.config.js": "Cypress",
    "cypress.config.ts": "Cypress",
    "playwright.config.ts": "Playwright",
    "playwright.config.js": "Playwright",
}

# Package dependency names that map to test frameworks
PACKAGE_TEST_DEPS = {
    "jest": "Jest",
    "vitest": "Vitest",
    "@testing-library/react": "Testing Library",
    "@testing-library/vue": "Testing Library",
    "pytest": "pytest",
    "pytest-cov": "pytest",
    "rspec": "RSpec",
    "minitest": "Minitest",
    "mocha": "Mocha",
    "cypress": "Cypress",
    "playwright": "Playwright",
    "@playwright/test": "Playwright",
    "xctest": "XCTest",
}

# Coverage report files to search for (path relative to component, format name)
COVERAGE_REPORT_FILES = [
    ("lcov.info", "lcov"),
    ("coverage/lcov.info", "lcov"),
    ("coverage/lcov-report/lcov.info", "lcov"),
    ("coverage.xml", "cobertura"),
    ("coverage/coverage.xml", "cobertura"),
    ("coverage/cobertura-coverage.xml", "cobertura"),
    ("coverage-summary.json", "istanbul"),
    ("coverage/coverage-summary.json", "istanbul"),
]

# CI config file globs and test command patterns
CI_CONFIG_FILES = [
    ".github/workflows",
    ".gitlab-ci.yml",
    "Jenkinsfile",
    ".circleci/config.yml",
    "bitbucket-pipelines.yml",
    "azure-pipelines.yml",
]

CI_TEST_PATTERNS = [
    r"pytest\b",
    r"npm\s+(?:run\s+)?test\b",
    r"yarn\s+test\b",
    r"vitest\b",
    r"jest\b",
    r"go\s+test\b",
    r"cargo\s+test\b",
    r"swift\s+test\b",
    r"xcodebuild.*test\b",
    r"rspec\b",
    r"bundle\s+exec\s+rspec\b",
    r"gradle.*test\b",
    r"mvn.*test\b",
]

# ---------------------------------------------------------------------------
# Relationship Enrichment Detection
# ---------------------------------------------------------------------------

# WebSocket patterns by language
WEBSOCKET_PATTERNS = {
    "typescript": [
        r"\bnew\s+WebSocket\s*\(",
        r"\bsocket\.io\b",
        r"io\s*\(\s*['\"]",
        r"\bws://|wss://",
        r"\.on\s*\(\s*['\"]connect",
    ],
    "javascript": [
        r"\bnew\s+WebSocket\s*\(",
        r"\bsocket\.io\b",
        r"io\s*\(\s*['\"]",
        r"\bws://|wss://",
    ],
    "python": [
        r"\bwebsockets?\.",
        r"\bsocketio\.",
        r"\bSocketIO\s*\(",
        r"\bchannels\.",
        r"\bws://|wss://",
    ],
    "go": [
        r"gorilla/websocket",
        r"websocket\.Upgrader",
        r"nhooyr\.io/websocket",
    ],
    "swift": [
        r"URLSessionWebSocketTask",
        r"NWConnection.*\.ws",
        r"\bStarscream\b",
    ],
    "rust": [
        r"tokio.tungstenite",
        r"ws::WebSocket",
        r"warp::ws",
        r"actix.web.*ws",
    ],
}

# gRPC patterns by language
GRPC_PATTERNS = {
    "typescript": [
        r"@grpc/grpc-js",
        r"grpc\.load\b",
        r"grpc-web",
    ],
    "python": [
        r"\bgrpc\.",
        r"\bgrpcio\b",
        r"_pb2_grpc\b",
    ],
    "go": [
        r"google\.golang\.org/grpc",
        r"pb\.\w+Server\b",
        r"pb\.\w+Client\b",
    ],
    "rust": [
        r"\btonic::",
        r"\bprost::",
    ],
    "java": [
        r"io\.grpc\.",
        r"\bStreamObserver\b",
    ],
    "kotlin": [
        r"io\.grpc\.",
    ],
}

# Message queue / event streaming patterns: (regex, system_name)
MESSAGE_QUEUE_PATTERNS = {
    "typescript": [
        (r"\bkafkajs\b|@confluentinc/kafka", "kafka"),
        (r"\bamqplib\b|amqp-connection-manager", "rabbitmq"),
        (r"\bbullmq\b|\bbull\b", "redis_queue"),
        (r"@aws-sdk/client-sqs|aws-sdk.*SQS", "sqs"),
        (r"@google-cloud/pubsub", "google_pubsub"),
        (r"\bnats\b|nats\.connect", "nats"),
    ],
    "javascript": [
        (r"\bkafkajs\b|@confluentinc/kafka", "kafka"),
        (r"\bamqplib\b|amqp-connection-manager", "rabbitmq"),
        (r"\bbullmq\b|\bbull\b", "redis_queue"),
        (r"@aws-sdk/client-sqs|aws-sdk.*SQS", "sqs"),
        (r"@google-cloud/pubsub", "google_pubsub"),
        (r"\bnats\b|nats\.connect", "nats"),
    ],
    "python": [
        (r"\bkafka\b|confluent_kafka|aiokafka", "kafka"),
        (r"\bpika\b|aio_pika|kombu\b", "rabbitmq"),
        (r"\bcelery\b", "celery"),
        (r"boto3.*sqs|SQS", "sqs"),
        (r"google\.cloud\.pubsub", "google_pubsub"),
        (r"\brq\b|redis.*Queue", "redis_queue"),
        (r"\bnats\b", "nats"),
    ],
    "go": [
        (r"segmentio/kafka-go|confluent-kafka-go|sarama", "kafka"),
        (r"amqp091-go|streadway/amqp", "rabbitmq"),
        (r"aws-sdk-go.*sqs", "sqs"),
        (r"cloud\.google\.com/go/pubsub", "google_pubsub"),
        (r"nats\.go", "nats"),
    ],
    "java": [
        (r"org\.apache\.kafka", "kafka"),
        (r"spring-cloud-stream|spring-amqp|spring-rabbit", "rabbitmq"),
        (r"com\.amazonaws.*sqs", "sqs"),
    ],
    "rust": [
        (r"\brdkafka\b", "kafka"),
        (r"\blapin\b", "rabbitmq"),
        (r"\bnats\b", "nats"),
    ],
    "ruby": [
        (r"\bbunny\b|\bhutch\b", "rabbitmq"),
        (r"ruby-kafka|rdkafka", "kafka"),
        (r"\bsidekiq\b|\bresque\b", "redis_queue"),
    ],
}

# Database connection patterns: (regex, library_name, db_engine)
DATABASE_PATTERNS = {
    "typescript": [
        (r"\bprisma\b|@prisma/client", "prisma", "postgresql"),
        (r"\btypeorm\b", "typeorm", "sql"),
        (r"\bsequelize\b", "sequelize", "sql"),
        (r"\bknex\b", "knex", "sql"),
        (r"\bmongoose\b", "mongoose", "mongodb"),
        (r"\bpg\b|node-postgres", "pg", "postgresql"),
        (r"\bmysql2?\b", "mysql", "mysql"),
        (r"better-sqlite3|sql\.js", "sqlite", "sqlite"),
        (r"\bioredis\b|\bredis\b", "redis_client", "redis"),
        (r"\bMongoClient\b|mongodb\b", "mongodb_driver", "mongodb"),
    ],
    "javascript": [
        (r"\bmongoose\b", "mongoose", "mongodb"),
        (r"\bpg\b|node-postgres", "pg", "postgresql"),
        (r"\bmysql2?\b", "mysql", "mysql"),
        (r"\bioredis\b|\bredis\b", "redis_client", "redis"),
        (r"\bMongoClient\b|mongodb\b", "mongodb_driver", "mongodb"),
    ],
    "python": [
        (r"\bsqlalchemy\b|SQLAlchemy", "sqlalchemy", "sql"),
        (r"django\.db\b", "django_orm", "sql"),
        (r"\bpsycopg[23]?\b", "psycopg", "postgresql"),
        (r"\bpymysql\b|mysqlclient", "pymysql", "mysql"),
        (r"\bpymongo\b|\bmotor\b", "pymongo", "mongodb"),
        (r"\bredis\b|\baioredis\b", "redis_client", "redis"),
        (r"\bsqlite3\b", "sqlite3", "sqlite"),
        (r"\bpeewee\b", "peewee", "sql"),
        (r"\btortoise\b", "tortoise", "sql"),
    ],
    "go": [
        (r"database/sql\b", "stdlib_sql", "sql"),
        (r"gorm\.io\b", "gorm", "sql"),
        (r"go-pg\b|pgx\b", "pg", "postgresql"),
        (r"go-sql-driver/mysql", "mysql_driver", "mysql"),
        (r"go\.mongodb\.org/mongo-driver", "mongo_driver", "mongodb"),
        (r"go-redis\b|redigo\b", "redis_client", "redis"),
    ],
    "rust": [
        (r"\bdiesel\b", "diesel", "sql"),
        (r"\bsqlx\b", "sqlx", "sql"),
        (r"sea.orm\b|sea_orm\b", "sea_orm", "sql"),
        (r"\bredis\b", "redis_client", "redis"),
        (r"\bmongodb\b", "mongo_driver", "mongodb"),
    ],
    "ruby": [
        (r"\bActiveRecord\b", "active_record", "sql"),
        (r"\bSequel\b", "sequel", "sql"),
        (r"\bMongoid\b", "mongoid", "mongodb"),
        (r"\bRedis\b", "redis_client", "redis"),
    ],
    "java": [
        (r"javax\.persistence\b|jakarta\.persistence\b", "jpa", "sql"),
        (r"org\.hibernate\b", "hibernate", "sql"),
        (r"org\.springframework\.data\b", "spring_data", "sql"),
        (r"com\.mongodb\b", "mongo_driver", "mongodb"),
        (r"\bjedis\b|\blettuce\b", "redis_client", "redis"),
    ],
    "swift": [
        (r"\bCoreData\b|NSManagedObject", "core_data", "sqlite"),
        (r"\bGRDB\b", "grdb", "sqlite"),
        (r"\bRealmSwift\b|\bRealm\b", "realm", "realm"),
        (r"\bSwiftData\b", "swift_data", "sqlite"),
    ],
    "kotlin": [
        (r"\bRoom\b|@Entity\b|@Dao\b", "room", "sqlite"),
        (r"org\.jetbrains\.exposed\b", "exposed", "sql"),
    ],
}

# Authentication patterns: maps auth type to detection regexes
AUTH_PATTERNS = {
    "jwt": [
        r"\bjsonwebtoken\b",
        r"\bPyJWT\b",
        r"\bjose\b.*jwt",
        r"\bgolang-jwt\b",
        r"\bBearer\b",
        r"\baccess_token\b",
        r"\brefresh_token\b",
    ],
    "oauth2": [
        r"\bOAuth2?\b",
        r"\bpassport\b",
        r"\bOAuthSwift\b",
        r"\bauthlib\b",
        r"\bclient_credentials\b",
        r"\bauthorization_code\b",
        r"\bAppAuth\b",
    ],
    "api_key": [
        r"[Aa]pi[-_]?[Kk]ey",
        r"X-API-Key",
        r"\bAPI_KEY\b",
    ],
    "mtls": [
        r"client.certificate",
        r"mutual.tls",
        r"\bmTLS\b",
        r"tls\.Config",
        r"SSLContext.*verify",
    ],
    "session": [
        r"\bexpress-session\b",
        r"\bcookie-session\b",
        r"\bsession_id\b",
        r"\bFlask-Login\b",
    ],
    "basic": [
        r"Basic\s+auth",
        r"\bbasicAuth\b",
        r"\bHTTPBasicAuth\b",
    ],
}

# Data format detection patterns: maps format to detection regexes
DATA_FORMAT_PATTERNS = {
    "json": [
        r"application/json",
        r"Content-Type.*json",
        r"\.json\(\)",
        r"\bJSON\.parse\b",
        r"\bJSON\.stringify\b",
        r"\bjson\.loads\b",
        r"\bjson\.dumps\b",
        r"\bserde_json\b",
        r"\bencoding/json\b",
        r"\bJSONDecoder\b",
        r"\bJSONEncoder\b",
    ],
    "protobuf": [
        r"\.proto\b",
        r"\bprotobuf\b",
        r"\bprost\b",
        r"_pb2\b",
        r"\bprotoc\b",
    ],
    "graphql": [
        r"\bgraphql\b",
        r"\bGraphQL\b",
        r"\bgql\s*`",
        r"\bapollographql\b",
    ],
    "xml": [
        r"application/xml",
        r"text/xml",
        r"\bXMLParser\b",
        r"\blxml\b",
        r"\betree\b",
    ],
    "msgpack": [
        r"\bmsgpack\b",
        r"\bMessagePack\b",
    ],
}

# Middleware detection patterns: maps middleware type to detection regexes
MIDDLEWARE_PATTERNS = {
    "rate_limit": [
        r"rate.limit",
        r"\bRateLimit\b",
        r"\bthrottle\b",
        r"express-rate-limit",
        r"\bslowapi\b",
    ],
    "cors": [
        r"\bcors\b",
        r"\bCORS\b",
        r"Access-Control-Allow",
    ],
    "auth": [
        r"\bauthenticate\b",
        r"\brequireAuth\b",
        r"\bisAuthenticated\b",
        r"\bauth_required\b",
        r"@login_required",
        r"\.protect\b",
    ],
    "logging": [
        r"\bmorgan\b",
        r"logging\.middleware",
        r"\brequest_logger\b",
    ],
    "compression": [
        r"\bcompression\b",
        r"\bgzip\b",
        r"\bbrotli\b",
    ],
}

# Queue/topic name extraction patterns
QUEUE_NAME_PATTERNS = [
    r"""(?:topic|queue|channel|exchange)\s*[=:]\s*['"]([^'"]+)['"]""",
    r"""(?:TOPIC|QUEUE|CHANNEL)\s*[=:]\s*['"]([^'"]+)['"]""",
    r"""\.subscribe\s*\(\s*['"]([^'"]+)['"]""",
    r"""\.publish\s*\(\s*['"]([^'"]+)['"]""",
]

# Docker service image names to relationship type mapping:
# (relationship_type, protocol/engine, default_port)
DOCKER_SERVICE_TYPES = {
    "postgres": ("database", "postgresql", 5432),
    "mysql": ("database", "mysql", 3306),
    "mariadb": ("database", "mysql", 3306),
    "mongo": ("database", "mongodb", 27017),
    "redis": ("cache", "redis", 6379),
    "rabbitmq": ("message_queue", "rabbitmq", 5672),
    "kafka": ("message_queue", "kafka", 9092),
    "nats": ("message_queue", "nats", 4222),
    "elasticsearch": ("database", "elasticsearch", 9200),
    "memcached": ("cache", "memcached", 11211),
    "cockroachdb": ("database", "postgresql", 26257),
    "cassandra": ("database", "cassandra", 9042),
}
