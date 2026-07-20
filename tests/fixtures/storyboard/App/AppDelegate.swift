import UIKit
import CoreData

// A source file so the store is not storyboard-only, and a custom-class match
// target: HomeViewController here shares its name with the storyboard scene.
@main
class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        return true
    }
}

class HomeViewController: UIViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        // Reads a Session managed object by name (an entity_access edge target).
        let session = Session(context: PersistenceController.shared.container.viewContext)
        session.startedAt = Date()
    }
}
