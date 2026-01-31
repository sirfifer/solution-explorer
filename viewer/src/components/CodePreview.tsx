import { useArchStore } from "../store";

interface CodePreviewProps {
  code: string;
  language: string;
}

// Simple syntax highlighting without dependencies
function highlightCode(code: string, language: string): string {
  // Escape HTML
  let html = code
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Keywords by language
  const keywords: Record<string, string[]> = {
    swift: [
      "import", "class", "struct", "enum", "protocol", "extension", "func",
      "var", "let", "if", "else", "guard", "switch", "case", "return",
      "self", "super", "init", "deinit", "public", "private", "internal",
      "fileprivate", "open", "static", "final", "override", "mutating",
      "async", "await", "throws", "try", "catch", "throw", "actor",
      "some", "any", "where", "typealias", "associatedtype", "true", "false", "nil",
    ],
    python: [
      "import", "from", "class", "def", "if", "elif", "else", "return",
      "self", "async", "await", "with", "as", "try", "except", "finally",
      "raise", "for", "in", "while", "break", "continue", "pass",
      "True", "False", "None", "and", "or", "not", "is", "lambda",
      "yield", "global", "nonlocal", "assert", "del",
    ],
    rust: [
      "use", "mod", "pub", "fn", "let", "mut", "const", "static",
      "struct", "enum", "trait", "impl", "type", "where", "for", "in",
      "if", "else", "match", "loop", "while", "break", "continue", "return",
      "self", "super", "crate", "async", "await", "move", "ref",
      "true", "false", "Some", "None", "Ok", "Err", "unsafe",
    ],
    typescript: [
      "import", "export", "from", "const", "let", "var", "function",
      "class", "interface", "type", "enum", "extends", "implements",
      "if", "else", "return", "async", "await", "new", "this",
      "true", "false", "null", "undefined", "void", "never",
      "public", "private", "protected", "static", "readonly",
      "default", "switch", "case", "break", "throw", "try", "catch",
    ],
    javascript: [
      "import", "export", "from", "const", "let", "var", "function",
      "class", "extends", "if", "else", "return", "async", "await",
      "new", "this", "true", "false", "null", "undefined",
      "default", "switch", "case", "break", "throw", "try", "catch",
    ],
    go: [
      "package", "import", "func", "type", "struct", "interface",
      "var", "const", "if", "else", "for", "range", "return",
      "switch", "case", "default", "break", "continue", "go",
      "chan", "select", "defer", "map", "make", "new", "true", "false", "nil",
    ],
  };

  const langKeywords = keywords[language] || keywords.typescript || [];

  // Apply syntax highlighting
  // Strings
  html = html.replace(
    /(&quot;|"|')((?:(?!\1).|\\.)*)\1/g,
    '<span class="syn-str">$1$2$1</span>',
  );

  // Comments (single line)
  html = html.replace(
    /(\/\/.*$)/gm,
    '<span class="syn-com">$1</span>',
  );
  // Python comments
  html = html.replace(
    /(#[^<].*$)/gm,
    '<span class="syn-com">$1</span>',
  );

  // Numbers
  html = html.replace(
    /\b(\d+\.?\d*)\b/g,
    '<span class="syn-num">$1</span>',
  );

  // Keywords (word boundary)
  for (const kw of langKeywords) {
    const regex = new RegExp(`\\b(${kw})\\b(?![^<]*>)`, "g");
    html = html.replace(regex, '<span class="syn-kw">$1</span>');
  }

  // Type annotations (capitalized words after : or as)
  html = html.replace(
    /(?<=:\s*|&lt;\s*)([A-Z]\w+)(?![^<]*>)/g,
    '<span class="syn-type">$1</span>',
  );

  // Decorators/attributes
  html = html.replace(
    /(@\w+)/g,
    '<span class="syn-dec">$1</span>',
  );

  return html;
}

export function CodePreview({ code, language }: CodePreviewProps) {
  const { darkMode } = useArchStore();

  if (!code) return null;

  const highlighted = highlightCode(code, language);

  return (
    <pre
      className={`
        code-preview rounded-lg p-3 overflow-x-auto text-xs leading-relaxed
        ${darkMode ? "bg-zinc-900 text-zinc-300" : "bg-zinc-50 text-zinc-700"}
      `}
    >
      <code dangerouslySetInnerHTML={{ __html: highlighted }} />
      <style>{`
        .syn-kw { color: ${darkMode ? "#C084FC" : "#7C3AED"}; font-weight: 600; }
        .syn-str { color: ${darkMode ? "#34D399" : "#059669"}; }
        .syn-com { color: ${darkMode ? "#6B7280" : "#9CA3AF"}; font-style: italic; }
        .syn-num { color: ${darkMode ? "#F59E0B" : "#D97706"}; }
        .syn-type { color: ${darkMode ? "#38BDF8" : "#0284C7"}; }
        .syn-dec { color: ${darkMode ? "#FB923C" : "#EA580C"}; }
      `}</style>
    </pre>
  );
}
