import { useMemo } from "react";

/**
 * Lightweight markdown renderer (no external deps).
 * Handles: headings, bold, italic, code blocks, inline code, links, lists, blockquotes, HR, tables.
 */
export function MarkdownRenderer({ content, darkMode }: { content: string; darkMode: boolean }) {
  const html = useMemo(() => renderMarkdown(content), [content]);

  return (
    <div
      className={`
        prose prose-sm max-w-none
        ${darkMode ? "markdown-dark" : "markdown-light"}
      `}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderInline(text: string): string {
  let result = escapeHtml(text);

  // Inline code
  result = result.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>');

  // Bold + italic
  result = result.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  // Bold
  result = result.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  result = result.replace(/__(.+?)__/g, "<strong>$1</strong>");
  // Italic
  result = result.replace(/\*(.+?)\*/g, "<em>$1</em>");
  result = result.replace(/_(.+?)_/g, "<em>$1</em>");

  // Links
  result = result.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener" class="md-link">$1</a>'
  );

  // Strikethrough
  result = result.replace(/~~(.+?)~~/g, "<del>$1</del>");

  return result;
}

function renderMarkdown(markdown: string): string {
  const lines = markdown.split("\n");
  const output: string[] = [];
  let i = 0;
  let inCodeBlock = false;
  let codeBlockLang = "";
  let codeLines: string[] = [];

  while (i < lines.length) {
    const line = lines[i];

    // Code blocks
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        output.push(
          `<pre class="md-code-block"><code class="language-${escapeHtml(codeBlockLang)}">${escapeHtml(codeLines.join("\n"))}</code></pre>`
        );
        codeLines = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
        codeBlockLang = line.trim().slice(3).trim();
      }
      i++;
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      i++;
      continue;
    }

    // Empty line
    if (line.trim() === "") {
      i++;
      continue;
    }

    // Headings
    const headingMatch = line.match(/^(#{1,6})\s+(.+)/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      output.push(`<h${level} class="md-h${level}">${renderInline(headingMatch[2])}</h${level}>`);
      i++;
      continue;
    }

    // HR
    if (/^[-*_]{3,}\s*$/.test(line.trim())) {
      output.push('<hr class="md-hr" />');
      i++;
      continue;
    }

    // Blockquote
    if (line.trim().startsWith(">")) {
      const quoteLines: string[] = [];
      while (i < lines.length && (lines[i].trim().startsWith(">") || (lines[i].trim() !== "" && quoteLines.length > 0 && !lines[i].trim().startsWith("#")))) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ""));
        i++;
        if (i < lines.length && lines[i].trim() === "") break;
      }
      output.push(`<blockquote class="md-blockquote">${renderInline(quoteLines.join(" "))}</blockquote>`);
      continue;
    }

    // Unordered list
    if (/^\s*[-*+]\s/.test(line)) {
      output.push('<ul class="md-ul">');
      while (i < lines.length && /^\s*[-*+]\s/.test(lines[i])) {
        const item = lines[i].replace(/^\s*[-*+]\s/, "");
        output.push(`<li>${renderInline(item)}</li>`);
        i++;
      }
      output.push("</ul>");
      continue;
    }

    // Ordered list
    if (/^\s*\d+\.\s/.test(line)) {
      output.push('<ol class="md-ol">');
      while (i < lines.length && /^\s*\d+\.\s/.test(lines[i])) {
        const item = lines[i].replace(/^\s*\d+\.\s/, "");
        output.push(`<li>${renderInline(item)}</li>`);
        i++;
      }
      output.push("</ol>");
      continue;
    }

    // Table
    if (line.includes("|") && i + 1 < lines.length && /^\s*\|?\s*[-:]+/.test(lines[i + 1])) {
      const headerCells = line.split("|").filter(c => c.trim()).map(c => c.trim());
      output.push('<table class="md-table"><thead><tr>');
      headerCells.forEach(cell => {
        output.push(`<th>${renderInline(cell)}</th>`);
      });
      output.push("</tr></thead><tbody>");
      i += 2; // Skip header and separator
      while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") {
        const cells = lines[i].split("|").filter(c => c.trim()).map(c => c.trim());
        output.push("<tr>");
        cells.forEach(cell => {
          output.push(`<td>${renderInline(cell)}</td>`);
        });
        output.push("</tr>");
        i++;
      }
      output.push("</tbody></table>");
      continue;
    }

    // Regular paragraph
    const paraLines: string[] = [line];
    i++;
    while (i < lines.length && lines[i].trim() !== "" && !lines[i].match(/^#{1,6}\s/) && !lines[i].trim().startsWith("```") && !/^\s*[-*+]\s/.test(lines[i]) && !/^\s*\d+\.\s/.test(lines[i]) && !lines[i].trim().startsWith(">") && !/^[-*_]{3,}\s*$/.test(lines[i].trim())) {
      paraLines.push(lines[i]);
      i++;
    }
    output.push(`<p class="md-p">${renderInline(paraLines.join(" "))}</p>`);
  }

  // Close unclosed code block
  if (inCodeBlock && codeLines.length > 0) {
    output.push(
      `<pre class="md-code-block"><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`
    );
  }

  return output.join("\n");
}
