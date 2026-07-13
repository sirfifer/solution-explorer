import SwiftUI

/// The root view of the polyglot iOS app.
struct ContentView: View {
    @State private var count: Int = 0

    var body: some View {
        VStack {
            Text("count: \(count)")
            Button("Increment") {
                increment()
            }
        }
    }

    /// Increment the counter.
    func increment() {
        count += 1
    }
}

/// A small value type used by the app.
struct Counter {
    var value: Int

    func doubled() -> Int {
        value * 2
    }
}
