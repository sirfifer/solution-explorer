/** Tech reference database: description and link to official docs for known technologies */

export interface TechRef {
  description: string;
  url: string;
}

export const TECH_DOCS: Record<string, TechRef> = {
  // JavaScript / TypeScript
  "React": { description: "JavaScript library for building user interfaces with a component model", url: "https://react.dev" },
  "react": { description: "JavaScript library for building user interfaces with a component model", url: "https://react.dev" },
  "Next.js": { description: "Full-stack React framework with server rendering and routing", url: "https://nextjs.org" },
  "next.js": { description: "Full-stack React framework with server rendering and routing", url: "https://nextjs.org" },
  "Vue": { description: "Progressive JavaScript framework for building user interfaces", url: "https://vuejs.org" },
  "vue": { description: "Progressive JavaScript framework for building user interfaces", url: "https://vuejs.org" },
  "Angular": { description: "TypeScript-based web application framework by Google", url: "https://angular.dev" },
  "angular": { description: "TypeScript-based web application framework by Google", url: "https://angular.dev" },
  "Svelte": { description: "Compile-time JavaScript framework that writes minimal runtime code", url: "https://svelte.dev" },
  "svelte": { description: "Compile-time JavaScript framework that writes minimal runtime code", url: "https://svelte.dev" },
  "Express": { description: "Minimal and flexible Node.js web application framework", url: "https://expressjs.com" },
  "express": { description: "Minimal and flexible Node.js web application framework", url: "https://expressjs.com" },
  "Node.js": { description: "Server-side JavaScript runtime built on V8", url: "https://nodejs.org" },
  "node": { description: "Server-side JavaScript runtime built on V8", url: "https://nodejs.org" },
  "TypeScript": { description: "Typed superset of JavaScript that compiles to plain JS", url: "https://www.typescriptlang.org" },
  "typescript": { description: "Typed superset of JavaScript that compiles to plain JS", url: "https://www.typescriptlang.org" },
  "Vite": { description: "Next-generation frontend build tool with instant HMR", url: "https://vite.dev" },
  "vite": { description: "Next-generation frontend build tool with instant HMR", url: "https://vite.dev" },
  "Webpack": { description: "Module bundler for JavaScript applications", url: "https://webpack.js.org" },
  "webpack": { description: "Module bundler for JavaScript applications", url: "https://webpack.js.org" },
  "Tailwind CSS": { description: "Utility-first CSS framework for rapid UI development", url: "https://tailwindcss.com" },
  "tailwind": { description: "Utility-first CSS framework for rapid UI development", url: "https://tailwindcss.com" },
  "Zustand": { description: "Lightweight state management for React using hooks", url: "https://zustand-demo.pmnd.rs" },
  "zustand": { description: "Lightweight state management for React using hooks", url: "https://zustand-demo.pmnd.rs" },
  "Redux": { description: "Predictable state container for JavaScript apps", url: "https://redux.js.org" },
  "redux": { description: "Predictable state container for JavaScript apps", url: "https://redux.js.org" },
  "Jest": { description: "JavaScript testing framework with zero configuration", url: "https://jestjs.io" },
  "jest": { description: "JavaScript testing framework with zero configuration", url: "https://jestjs.io" },
  "Vitest": { description: "Blazing-fast unit test framework powered by Vite", url: "https://vitest.dev" },
  "vitest": { description: "Blazing-fast unit test framework powered by Vite", url: "https://vitest.dev" },
  "Prisma": { description: "Type-safe ORM for Node.js and TypeScript", url: "https://www.prisma.io" },
  "prisma": { description: "Type-safe ORM for Node.js and TypeScript", url: "https://www.prisma.io" },
  "GraphQL": { description: "Query language for APIs with a type system for data", url: "https://graphql.org" },
  "graphql": { description: "Query language for APIs with a type system for data", url: "https://graphql.org" },
  "Socket.IO": { description: "Real-time bidirectional event-based communication library", url: "https://socket.io" },
  "Electron": { description: "Framework for building cross-platform desktop apps with web tech", url: "https://www.electronjs.org" },
  "electron": { description: "Framework for building cross-platform desktop apps with web tech", url: "https://www.electronjs.org" },
  "Fastify": { description: "Fast and low-overhead web framework for Node.js", url: "https://fastify.dev" },
  "fastify": { description: "Fast and low-overhead web framework for Node.js", url: "https://fastify.dev" },
  "NestJS": { description: "Progressive Node.js framework for scalable server-side applications", url: "https://nestjs.com" },

  // Python
  "Python": { description: "General-purpose programming language emphasizing readability", url: "https://www.python.org" },
  "python": { description: "General-purpose programming language emphasizing readability", url: "https://www.python.org" },
  "Django": { description: "High-level Python web framework for rapid development", url: "https://www.djangoproject.com" },
  "django": { description: "High-level Python web framework for rapid development", url: "https://www.djangoproject.com" },
  "Flask": { description: "Lightweight Python WSGI web application framework", url: "https://flask.palletsprojects.com" },
  "flask": { description: "Lightweight Python WSGI web application framework", url: "https://flask.palletsprojects.com" },
  "FastAPI": { description: "Modern, high-performance Python web framework for building APIs", url: "https://fastapi.tiangolo.com" },
  "fastapi": { description: "Modern, high-performance Python web framework for building APIs", url: "https://fastapi.tiangolo.com" },
  "PyTorch": { description: "Open-source machine learning framework for deep learning", url: "https://pytorch.org" },
  "pytorch": { description: "Open-source machine learning framework for deep learning", url: "https://pytorch.org" },
  "TensorFlow": { description: "End-to-end open-source platform for machine learning", url: "https://www.tensorflow.org" },
  "tensorflow": { description: "End-to-end open-source platform for machine learning", url: "https://www.tensorflow.org" },
  "SQLAlchemy": { description: "Python SQL toolkit and Object-Relational Mapper", url: "https://www.sqlalchemy.org" },
  "sqlalchemy": { description: "Python SQL toolkit and Object-Relational Mapper", url: "https://www.sqlalchemy.org" },
  "Celery": { description: "Distributed task queue for Python", url: "https://docs.celeryq.dev" },
  "celery": { description: "Distributed task queue for Python", url: "https://docs.celeryq.dev" },
  "Pandas": { description: "Data analysis and manipulation library for Python", url: "https://pandas.pydata.org" },
  "pandas": { description: "Data analysis and manipulation library for Python", url: "https://pandas.pydata.org" },
  "NumPy": { description: "Fundamental package for numerical computing in Python", url: "https://numpy.org" },
  "numpy": { description: "Fundamental package for numerical computing in Python", url: "https://numpy.org" },

  // Ruby
  "Rails": { description: "Full-stack Ruby web framework following MVC conventions", url: "https://rubyonrails.org" },
  "rails": { description: "Full-stack Ruby web framework following MVC conventions", url: "https://rubyonrails.org" },
  "Ruby on Rails": { description: "Full-stack Ruby web framework following MVC conventions", url: "https://rubyonrails.org" },
  "Sinatra": { description: "Lightweight Ruby web framework for building web apps", url: "https://sinatrarb.com" },
  "sinatra": { description: "Lightweight Ruby web framework for building web apps", url: "https://sinatrarb.com" },
  "Ruby": { description: "Dynamic, interpreted programming language focused on simplicity", url: "https://www.ruby-lang.org" },
  "ruby": { description: "Dynamic, interpreted programming language focused on simplicity", url: "https://www.ruby-lang.org" },
  "Grape": { description: "REST-like API framework for Ruby", url: "https://github.com/ruby-grape/grape" },
  "RSpec": { description: "Behavior-driven development testing framework for Ruby", url: "https://rspec.info" },

  // Swift / Apple
  "SwiftUI": { description: "Apple's declarative UI framework for all Apple platforms", url: "https://developer.apple.com/xcode/swiftui/" },
  "swiftui": { description: "Apple's declarative UI framework for all Apple platforms", url: "https://developer.apple.com/xcode/swiftui/" },
  "UIKit": { description: "Apple's imperative UI framework for iOS and iPadOS", url: "https://developer.apple.com/documentation/uikit" },
  "uikit": { description: "Apple's imperative UI framework for iOS and iPadOS", url: "https://developer.apple.com/documentation/uikit" },
  "Swift": { description: "Modern compiled language by Apple for safe, fast development", url: "https://www.swift.org" },
  "swift": { description: "Modern compiled language by Apple for safe, fast development", url: "https://www.swift.org" },
  "Core Data": { description: "Apple's framework for managing object graphs and persistence", url: "https://developer.apple.com/documentation/coredata" },
  "CoreML": { description: "Apple's framework for integrating machine learning models", url: "https://developer.apple.com/documentation/coreml" },
  "Combine": { description: "Apple's reactive programming framework for processing values over time", url: "https://developer.apple.com/documentation/combine" },
  "WatchKit": { description: "Apple framework for building watchOS apps", url: "https://developer.apple.com/documentation/watchkit" },
  "WidgetKit": { description: "Apple framework for building Home Screen widgets", url: "https://developer.apple.com/documentation/widgetkit" },
  "AVFoundation": { description: "Apple framework for working with audiovisual media", url: "https://developer.apple.com/av-foundation/" },

  // Rust
  "Rust": { description: "Systems programming language focused on safety and performance", url: "https://www.rust-lang.org" },
  "rust": { description: "Systems programming language focused on safety and performance", url: "https://www.rust-lang.org" },
  "Actix": { description: "Powerful, pragmatic Rust web framework", url: "https://actix.rs" },
  "actix": { description: "Powerful, pragmatic Rust web framework", url: "https://actix.rs" },
  "Tokio": { description: "Asynchronous runtime for Rust", url: "https://tokio.rs" },
  "tokio": { description: "Asynchronous runtime for Rust", url: "https://tokio.rs" },
  "Axum": { description: "Ergonomic, modular web framework built on Tokio", url: "https://github.com/tokio-rs/axum" },
  "axum": { description: "Ergonomic, modular web framework built on Tokio", url: "https://github.com/tokio-rs/axum" },
  "Warp": { description: "Super-easy, composable web server framework for Rust", url: "https://github.com/seanmonstar/warp" },

  // Go
  "Go": { description: "Compiled, statically typed language by Google for systems programming", url: "https://go.dev" },
  "go": { description: "Compiled, statically typed language by Google for systems programming", url: "https://go.dev" },
  "Gin": { description: "High-performance HTTP web framework for Go", url: "https://gin-gonic.com" },
  "gin": { description: "High-performance HTTP web framework for Go", url: "https://gin-gonic.com" },
  "Echo": { description: "High-performance, minimalist Go web framework", url: "https://echo.labstack.com" },
  "Fiber": { description: "Express-inspired web framework built on Fasthttp for Go", url: "https://gofiber.io" },

  // Java / JVM
  "Java": { description: "Object-oriented language running on the JVM", url: "https://dev.java" },
  "java": { description: "Object-oriented language running on the JVM", url: "https://dev.java" },
  "Spring Boot": { description: "Convention-over-configuration framework for Java microservices", url: "https://spring.io/projects/spring-boot" },
  "spring": { description: "Comprehensive programming and configuration model for Java", url: "https://spring.io" },
  "Kotlin": { description: "Modern, concise JVM language with full Java interop", url: "https://kotlinlang.org" },
  "kotlin": { description: "Modern, concise JVM language with full Java interop", url: "https://kotlinlang.org" },
  "Gradle": { description: "Build automation tool for JVM projects", url: "https://gradle.org" },
  "gradle": { description: "Build automation tool for JVM projects", url: "https://gradle.org" },
  "Maven": { description: "Build automation and dependency management for Java", url: "https://maven.apache.org" },

  // Mobile
  "React Native": { description: "Cross-platform mobile framework using React", url: "https://reactnative.dev" },
  "react-native": { description: "Cross-platform mobile framework using React", url: "https://reactnative.dev" },
  "Flutter": { description: "Google's UI toolkit for cross-platform apps from a single codebase", url: "https://flutter.dev" },
  "flutter": { description: "Google's UI toolkit for cross-platform apps from a single codebase", url: "https://flutter.dev" },
  "Dart": { description: "Client-optimized language by Google for fast apps on any platform", url: "https://dart.dev" },
  "dart": { description: "Client-optimized language by Google for fast apps on any platform", url: "https://dart.dev" },
  "Jetpack Compose": { description: "Android's modern toolkit for building native UI", url: "https://developer.android.com/compose" },

  // Infrastructure / DevOps
  "Docker": { description: "Platform for building, sharing, and running containerized applications", url: "https://www.docker.com" },
  "docker": { description: "Platform for building, sharing, and running containerized applications", url: "https://www.docker.com" },
  "Kubernetes": { description: "Container orchestration system for automating deployment and scaling", url: "https://kubernetes.io" },
  "kubernetes": { description: "Container orchestration system for automating deployment and scaling", url: "https://kubernetes.io" },
  "Terraform": { description: "Infrastructure as Code tool for building cloud resources", url: "https://www.terraform.io" },
  "terraform": { description: "Infrastructure as Code tool for building cloud resources", url: "https://www.terraform.io" },
  "AWS": { description: "Amazon Web Services cloud computing platform", url: "https://aws.amazon.com" },
  "GCP": { description: "Google Cloud Platform for cloud computing services", url: "https://cloud.google.com" },
  "Azure": { description: "Microsoft's cloud computing platform", url: "https://azure.microsoft.com" },
  "Nginx": { description: "High-performance HTTP server and reverse proxy", url: "https://nginx.org" },
  "nginx": { description: "High-performance HTTP server and reverse proxy", url: "https://nginx.org" },
  "Redis": { description: "In-memory data structure store used as cache and message broker", url: "https://redis.io" },
  "redis": { description: "In-memory data structure store used as cache and message broker", url: "https://redis.io" },
  "PostgreSQL": { description: "Advanced open-source relational database", url: "https://www.postgresql.org" },
  "postgresql": { description: "Advanced open-source relational database", url: "https://www.postgresql.org" },
  "MySQL": { description: "Popular open-source relational database management system", url: "https://www.mysql.com" },
  "MongoDB": { description: "Document-oriented NoSQL database", url: "https://www.mongodb.com" },
  "mongodb": { description: "Document-oriented NoSQL database", url: "https://www.mongodb.com" },
  "SQLite": { description: "Self-contained, serverless SQL database engine", url: "https://www.sqlite.org" },
  "sqlite": { description: "Self-contained, serverless SQL database engine", url: "https://www.sqlite.org" },
  "RabbitMQ": { description: "Open-source message broker for distributed systems", url: "https://www.rabbitmq.com" },
  "Kafka": { description: "Distributed event streaming platform for high-throughput pipelines", url: "https://kafka.apache.org" },
  "Elasticsearch": { description: "Distributed search and analytics engine", url: "https://www.elastic.co/elasticsearch" },
  "GitHub Actions": { description: "CI/CD platform for automating build, test, and deploy pipelines", url: "https://docs.github.com/actions" },
  "Cloudflare": { description: "CDN, security, and edge computing platform", url: "https://www.cloudflare.com" },

  // C / C++
  "C": { description: "Low-level systems programming language", url: "https://en.cppreference.com/w/c" },
  "C++": { description: "General-purpose language with object-oriented and generic features", url: "https://isocpp.org" },
  "CMake": { description: "Cross-platform build system generator", url: "https://cmake.org" },
  "cmake": { description: "Cross-platform build system generator", url: "https://cmake.org" },
  "Qt": { description: "Cross-platform C++ framework for GUIs and applications", url: "https://www.qt.io" },

  // .NET
  "C#": { description: "Modern, object-oriented language for .NET", url: "https://learn.microsoft.com/en-us/dotnet/csharp/" },
  ".NET": { description: "Free, cross-platform developer platform by Microsoft", url: "https://dotnet.microsoft.com" },
  "ASP.NET": { description: "Framework for building web apps and APIs with .NET", url: "https://dotnet.microsoft.com/apps/aspnet" },
  "Blazor": { description: "Framework for building interactive web UIs with C#", url: "https://dotnet.microsoft.com/apps/aspnet/web-apps/blazor" },

  // Other
  "gRPC": { description: "High-performance RPC framework using Protocol Buffers", url: "https://grpc.io" },
  "protobuf": { description: "Language-neutral data serialization format by Google", url: "https://protobuf.dev" },
  "OpenAPI": { description: "Specification for describing REST APIs", url: "https://www.openapis.org" },
  "Storybook": { description: "Frontend workshop for building UI components in isolation", url: "https://storybook.js.org" },
  "Cypress": { description: "JavaScript end-to-end testing framework", url: "https://www.cypress.io" },
  "Playwright": { description: "Cross-browser end-to-end testing framework", url: "https://playwright.dev" },
};

/** Case-insensitive lookup for a tech reference */
export function getTechRef(name: string): TechRef | null {
  // Try exact match first
  if (TECH_DOCS[name]) return TECH_DOCS[name];
  // Try lowercase
  const lower = name.toLowerCase();
  if (TECH_DOCS[lower]) return TECH_DOCS[lower];
  // Try normalized (strip common suffixes/prefixes)
  const normalized = lower.replace(/\.js$/, "").replace(/^@\w+\//, "");
  if (TECH_DOCS[normalized]) return TECH_DOCS[normalized];
  return null;
}

/** Component type descriptions for tooltips */
export const TYPE_DESCRIPTIONS: Record<string, string> = {
  "mobile-client": "A native mobile application that runs on iOS or Android devices. Typically built with Swift/SwiftUI, Kotlin/Jetpack Compose, React Native, or Flutter.",
  "ios-client": "A native iOS application that runs on iPhone and iPad. Typically built with Swift and SwiftUI or UIKit, distributed through the App Store.",
  "android-client": "A native Android application that runs on Android devices. Typically built with Kotlin and Jetpack Compose or Java with XML layouts, distributed through Google Play.",
  "web-client": "A browser-based frontend application. Usually built with JavaScript/TypeScript frameworks like React, Vue, Angular, or Svelte.",
  "api-server": "A backend service that exposes HTTP, gRPC, or other API endpoints for clients to consume. Handles business logic, data access, and authentication.",
  "watch-app": "An application designed for smartwatch platforms like Apple Watch (watchOS) or Wear OS.",
  "desktop-app": "A native desktop application for macOS, Windows, or Linux. Built with frameworks like Electron, Qt, SwiftUI, or WPF.",
  "cli-tool": "A command-line interface tool that runs in a terminal. Accepts arguments and flags to perform specific tasks.",
  "service": "A background service or microservice that processes data, handles events, or provides functionality to other parts of the system.",
  "application": "A standalone application that serves as a primary entry point for users or other systems.",
  "library": "A reusable code library or SDK that provides functionality to other components. Not directly runnable on its own.",
  "package": "A distributable code package, often published to a package registry (npm, PyPI, crates.io, etc.).",
  "module": "An internal module or logical grouping of related code within a larger component.",
  "infrastructure": "Infrastructure configuration, deployment scripts, CI/CD pipelines, or cloud resource definitions.",
  "repository": "A code repository that may contain multiple components.",
  "project": "A project root that organizes the overall codebase structure.",
  "content": "Non-code content such as documentation, wiki pages, curriculum materials, or static assets.",
};

/** Symbol kind descriptions for tooltips */
export const SYMBOL_KIND_DESCRIPTIONS: Record<string, string> = {
  class: "A class defines a blueprint for creating objects with properties and methods.",
  struct: "A struct is a value type that groups related data together.",
  enum: "An enumeration defines a type with a fixed set of named values.",
  protocol: "A protocol (or interface) defines a contract that types must implement.",
  trait: "A trait defines shared behavior that types can implement (similar to interface).",
  interface: "An interface defines a contract of methods and properties that implementing types must provide.",
  function: "A standalone function that performs a specific task.",
  type: "A type alias or type definition.",
  component: "A UI component (React, Vue, etc.) that renders a section of the interface.",
  impl: "An implementation block that adds methods to a type.",
  extension: "An extension adds new functionality to an existing type.",
  module: "A module namespace that groups related declarations.",
  constant: "A constant value that cannot be changed after initialization.",
  variable: "A module-level variable or exported binding.",
};

/** Metric label descriptions */
export const METRIC_DESCRIPTIONS: Record<string, string> = {
  files: "Total number of source files in this component.",
  lines: "Total lines of code across all files (including comments and blank lines).",
  loc: "Lines of code, a measure of the component's size.",
  symbols: "Number of exported or public code symbols (classes, functions, types, etc.).",
  size: "Total file size on disk for all source files.",
  conn: "Number of connections (relationships) to other components in the architecture.",
  tests: "Total number of test cases (unit + integration + e2e) detected in this component.",
  coverage: "Percentage of source code lines covered by tests, parsed from coverage report files (LCOV, Istanbul, Cobertura).",
};

/** Design pattern references with descriptions and links */
export const PATTERN_DOCS: Record<string, TechRef> = {
  "MVC": { description: "Model-View-Controller separates data, UI, and control logic into three interconnected components", url: "https://developer.mozilla.org/en-US/docs/Glossary/MVC" },
  "MVVM": { description: "Model-View-ViewModel binds UI elements to data through a view model that exposes observable state", url: "https://learn.microsoft.com/en-us/dotnet/architecture/maui/mvvm" },
  "MVP": { description: "Model-View-Presenter where the presenter handles UI logic and mediates between model and view", url: "https://en.wikipedia.org/wiki/Model%E2%80%93view%E2%80%93presenter" },
  "Repository Pattern": { description: "Abstracts data access behind a collection-like interface, decoupling business logic from storage", url: "https://martinfowler.com/eaaCatalog/repository.html" },
  "Service Layer": { description: "Defines an application boundary with a set of available operations and coordinates responses", url: "https://martinfowler.com/eaaCatalog/serviceLayer.html" },
  "API Layer": { description: "A dedicated layer that exposes application functionality through well-defined endpoints", url: "https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design" },
  "Observer Pattern": { description: "Objects subscribe to events and are notified when state changes occur", url: "https://refactoring.guru/design-patterns/observer" },
  "Singleton": { description: "Ensures a class has only one instance and provides a global point of access", url: "https://refactoring.guru/design-patterns/singleton" },
  "Factory Pattern": { description: "Creates objects without exposing instantiation logic, using a common interface", url: "https://refactoring.guru/design-patterns/factory-method" },
  "Strategy Pattern": { description: "Defines a family of algorithms, encapsulates each one, and makes them interchangeable", url: "https://refactoring.guru/design-patterns/strategy" },
  "Dependency Injection": { description: "Components receive their dependencies from external sources rather than creating them", url: "https://en.wikipedia.org/wiki/Dependency_injection" },
  "Middleware": { description: "Functions that intercept and process requests in a pipeline before reaching the handler", url: "https://learn.microsoft.com/en-us/aspnet/core/fundamentals/middleware" },
  "Event-Driven": { description: "Architecture where components communicate by producing and consuming events asynchronously", url: "https://learn.microsoft.com/en-us/azure/architecture/guide/architecture-styles/event-driven" },
  "CQRS": { description: "Command Query Responsibility Segregation separates read and write operations into distinct models", url: "https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs" },
  "Pub/Sub": { description: "Publishers send messages to topics without knowing subscribers, enabling loose coupling", url: "https://cloud.google.com/pubsub/docs/overview" },
  "REST": { description: "Representational State Transfer, an architectural style for networked APIs using HTTP methods", url: "https://restfulapi.net" },
  "RESTful API": { description: "An API conforming to REST constraints, using HTTP methods and resource-based URLs", url: "https://restfulapi.net" },
  "GraphQL API": { description: "A query language for APIs that lets clients request exactly the data they need", url: "https://graphql.org/learn/" },
  "Microservices": { description: "Architecture where an application is composed of small, independently deployable services", url: "https://microservices.io" },
  "Monolith": { description: "A single deployable unit containing all application functionality", url: "https://en.wikipedia.org/wiki/Monolithic_application" },
  "Clean Architecture": { description: "Organizes code in concentric layers with dependencies pointing inward toward domain logic", url: "https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html" },
  "Hexagonal Architecture": { description: "Ports and adapters pattern that isolates core logic from external concerns", url: "https://alistair.cockburn.us/hexagonal-architecture/" },
  "Domain-Driven Design": { description: "Software design approach focused on modeling the core business domain and its logic", url: "https://martinfowler.com/bliki/DomainDrivenDesign.html" },
  "Actor Model": { description: "Concurrency model where actors are independent units that communicate via message passing", url: "https://en.wikipedia.org/wiki/Actor_model" },
  "State Machine": { description: "A model of computation with a finite number of states and transitions between them", url: "https://statecharts.dev" },
  "Command Pattern": { description: "Encapsulates a request as an object, allowing parameterization and queuing of operations", url: "https://refactoring.guru/design-patterns/command" },
  "Decorator Pattern": { description: "Dynamically adds behavior to objects by wrapping them in decorator objects", url: "https://refactoring.guru/design-patterns/decorator" },
  "Adapter Pattern": { description: "Converts the interface of a class into another interface that clients expect", url: "https://refactoring.guru/design-patterns/adapter" },
  "Facade Pattern": { description: "Provides a simplified interface to a complex subsystem of classes", url: "https://refactoring.guru/design-patterns/facade" },
  "Proxy Pattern": { description: "Provides a surrogate or placeholder for another object to control access to it", url: "https://refactoring.guru/design-patterns/proxy" },
  "Builder Pattern": { description: "Constructs complex objects step by step, separating construction from representation", url: "https://refactoring.guru/design-patterns/builder" },
  "Coordinator Pattern": { description: "Manages navigation flow between view controllers, keeping them decoupled from each other", url: "https://www.hackingwithswift.com/articles/71/how-to-use-the-coordinator-pattern-in-ios-apps" },
  "Combine": { description: "Apple's declarative framework for processing asynchronous events over time using publishers and subscribers", url: "https://developer.apple.com/documentation/combine" },
  "SwiftUI": { description: "Apple's declarative UI framework for building interfaces across all Apple platforms", url: "https://developer.apple.com/xcode/swiftui/" },
  "UIKit": { description: "Apple's imperative UI framework for building iOS and tvOS applications", url: "https://developer.apple.com/documentation/uikit" },
  "Core Data": { description: "Apple's framework for managing object graphs and persisting data locally", url: "https://developer.apple.com/documentation/coredata" },
  "VIPER": { description: "View-Interactor-Presenter-Entity-Router, a clean architecture pattern for iOS apps", url: "https://www.objc.io/issues/13-architecture/viper/" },
  "TCA": { description: "The Composable Architecture, a library for building apps in a consistent and testable way", url: "https://github.com/pointfreeco/swift-composable-architecture" },
};

/** Case-insensitive lookup for a pattern reference */
export function getPatternRef(name: string): TechRef | null {
  if (PATTERN_DOCS[name]) return PATTERN_DOCS[name];
  // Try case-insensitive match
  const lower = name.toLowerCase();
  for (const [key, ref] of Object.entries(PATTERN_DOCS)) {
    if (key.toLowerCase() === lower) return ref;
  }
  // Fall back to tech docs (some patterns overlap with tech names)
  return getTechRef(name);
}

/** Protocol/communication references */
export const PROTOCOL_DOCS: Record<string, TechRef> = {
  "HTTP": { description: "Hypertext Transfer Protocol, the foundation of data communication on the web", url: "https://developer.mozilla.org/en-US/docs/Web/HTTP" },
  "HTTPS": { description: "HTTP Secure, encrypted communication using TLS", url: "https://developer.mozilla.org/en-US/docs/Web/HTTP" },
  "WebSocket": { description: "Full-duplex communication protocol over a single TCP connection", url: "https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API" },
  "gRPC": { description: "High-performance RPC framework using HTTP/2 and Protocol Buffers", url: "https://grpc.io" },
  "REST": { description: "Representational State Transfer, an architectural style for networked APIs", url: "https://restfulapi.net" },
  "GraphQL": { description: "Query language for APIs that lets clients request specific data", url: "https://graphql.org" },
  "TCP": { description: "Transmission Control Protocol, reliable ordered delivery of data streams", url: "https://en.wikipedia.org/wiki/Transmission_Control_Protocol" },
  "UDP": { description: "User Datagram Protocol, low-latency connectionless communication", url: "https://en.wikipedia.org/wiki/User_Datagram_Protocol" },
  "MQTT": { description: "Lightweight messaging protocol for IoT and machine-to-machine communication", url: "https://mqtt.org" },
  "AMQP": { description: "Advanced Message Queuing Protocol for message-oriented middleware", url: "https://www.amqp.org" },
  "Redis": { description: "In-memory data store used as database, cache, and message broker", url: "https://redis.io" },
  "PostgreSQL": { description: "Advanced open-source relational database", url: "https://www.postgresql.org" },
  "SQL": { description: "Structured Query Language for managing relational databases", url: "https://en.wikipedia.org/wiki/SQL" },
  "FFI": { description: "Foreign Function Interface, calling code written in one language from another", url: "https://en.wikipedia.org/wiki/Foreign_function_interface" },
  "WatchConnectivity": { description: "Apple framework for communication between iPhone and Apple Watch apps", url: "https://developer.apple.com/documentation/watchconnectivity" },
  "Kafka": { description: "Distributed event streaming platform for high-throughput data pipelines", url: "https://kafka.apache.org" },
  "RabbitMQ": { description: "Open-source message broker supporting AMQP, MQTT, and STOMP", url: "https://www.rabbitmq.com" },
  "SQS": { description: "Amazon Simple Queue Service, fully managed message queuing", url: "https://aws.amazon.com/sqs/" },
  "NATS": { description: "Cloud-native messaging system for microservices and IoT", url: "https://nats.io" },
  "Protobuf": { description: "Language-neutral binary data serialization format by Google", url: "https://protobuf.dev" },
  "MongoDB": { description: "Document-oriented NoSQL database for flexible schema storage", url: "https://www.mongodb.com" },
  "MySQL": { description: "Open-source relational database management system", url: "https://www.mysql.com" },
  "Elasticsearch": { description: "Distributed search and analytics engine", url: "https://www.elastic.co/elasticsearch" },
  "Memcached": { description: "High-performance distributed memory caching system", url: "https://memcached.org" },
  "Celery": { description: "Distributed task queue for Python applications", url: "https://docs.celeryq.dev" },
  "SQLite": { description: "Self-contained embedded SQL database engine", url: "https://www.sqlite.org" },
};

/** Case-insensitive lookup for a protocol reference */
export function getProtocolRef(name: string): TechRef | null {
  if (PROTOCOL_DOCS[name]) return PROTOCOL_DOCS[name];
  const upper = name.toUpperCase();
  for (const [key, ref] of Object.entries(PROTOCOL_DOCS)) {
    if (key.toUpperCase() === upper) return ref;
  }
  return getTechRef(name);
}
