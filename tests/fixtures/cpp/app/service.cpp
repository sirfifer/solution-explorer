#include "../core/logger.hpp"

namespace app {

// A small service that reports its status through the core logger.
class Service {
public:
    void start() {
        core::Logger::instance().info("service started");
    }

    void stop() {
        core::Logger::instance().warn("service stopped");
    }

private:
    bool running_;
};

}  // namespace app
