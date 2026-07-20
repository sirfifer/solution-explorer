#include "../core/logger.hpp"
#include <string>

// Entry point that drives the shared logger from the core component.
int main() {
    core::Logger& log = core::Logger::instance();
    log.info("starting up");
    return 0;
}
