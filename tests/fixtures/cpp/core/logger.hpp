// Logging facility for the sample C++ project.
#ifndef CORE_LOGGER_HPP
#define CORE_LOGGER_HPP

#include <string>

namespace core {

// A minimal logger exposing a shared instance.
class Logger {
public:
    static Logger& instance();
    void info(const std::string& message);
    void warn(const std::string& message);

private:
    Logger();
    int count_;
};

struct LogRecord {
    std::string level;
    std::string message;
};

}  // namespace core

#endif  // CORE_LOGGER_HPP
