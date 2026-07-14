import SwiftData

@Model
final class Item {
    var title: String
    var quantity: Int
    var createdAt: Date

    init(title: String, quantity: Int) {
        self.title = title
        self.quantity = quantity
        self.createdAt = Date()
    }
}
