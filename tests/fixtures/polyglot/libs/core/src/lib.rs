//! Core library for the polyglot fixture.

/// A parsed identifier shared across services.
pub struct Identifier {
    pub value: u64,
}

impl Identifier {
    /// Create a new identifier.
    pub fn new(value: u64) -> Self {
        Identifier { value }
    }

    /// Render the identifier as a string.
    pub fn render(&self) -> String {
        format!("id:{}", self.value)
    }
}

/// Double an input value.
pub fn double(x: u64) -> u64 {
    x * 2
}
