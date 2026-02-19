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
