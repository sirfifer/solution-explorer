# Ruby helper library for the polyglot fixture.

module RubyLib
  # Parses simple key=value strings.
  class Parser
    def initialize(separator = "=")
      @separator = separator
    end

    # Parse a single line into a pair.
    def parse(line)
      key, value = line.split(@separator, 2)
      { key: key, value: value }
    end
  end

  def self.version
    "0.1.0"
  end
end
