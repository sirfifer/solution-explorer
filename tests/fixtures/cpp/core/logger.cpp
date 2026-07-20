#include "logger.hpp"
#include <iostream>

namespace core {

Logger::Logger() : count_(0) {}

Logger& Logger::instance() {
    static Logger shared;
    return shared;
}

void Logger::info(const std::string& message) {
    count_++;
    std::cout << "[info] " << message << std::endl;
}

void Logger::warn(const std::string& message) {
    count_++;
    std::cout << "[warn] " << message << std::endl;
}

}  // namespace core
