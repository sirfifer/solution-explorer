// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "SwiftFixture",
    dependencies: [
        .package(url: "https://github.com/apple/swift-nio.git", from: "2.0.0"),
        .package(url: "https://github.com/apple/swift-log.git", exact: "1.5.3"),
    ]
)
