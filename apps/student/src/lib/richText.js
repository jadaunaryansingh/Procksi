// Minimal markdown parser for admin-authored notification and announcement text.
//
// Announcements are written in markdown and the backend already renders that
// subset for email (`parse_markdown_formatting` in admin-api/app/email_notifier.py).
// The portal used to print the raw string, so students saw literal `**` and every
// paragraph and bullet collapsed into one run of text. This parses the same
// subset so both channels agree.
//
// It emits a token tree, never an HTML string: <RichText> turns tokens into React
// elements, which React escapes by construction. That matters because anything
// able to write a `notifications` row would otherwise control markup on every
// student's screen — so no `dangerouslySetInnerHTML`, and no sanitiser to
// misconfigure.
//
// Supported (matching the backend): **bold**, __bold__, *italic*, _italic_,
// [title](url), leading * - + bullets, blank-line paragraphs, soft line breaks.

const BULLET = /^[ \t]*[*+-][ \t]+/;
const WORD = /[\w]/;

// Schemes a link may use. Anything else renders as plain text.
const ALLOWED_SCHEME = /^(https?:|mailto:)/i;

/**
 * Return `url` if it is safe to put in an href, else null.
 * Site-relative paths ("/student/…") are allowed; everything that isn't an
 * explicitly allowed scheme is rejected — notably javascript: and data:.
 */
export function safeUrl(url) {
  const trimmed = String(url ?? '').trim();
  if (!trimmed) return null;
  if (trimmed.startsWith('/') && !trimmed.startsWith('//')) return trimmed;
  return ALLOWED_SCHEME.test(trimmed) ? trimmed : null;
}

// Is the italic marker at `i` a real emphasis opener rather than punctuation or
// a stray asterisk? Guards mirror the backend's negative lookarounds.
function opensEmphasis(text, i, marker) {
  const before = i > 0 ? text[i - 1] : '';
  const after = text[i + 1] ?? '';
  if (!after || /\s/.test(after) || after === marker) return false;
  return !(WORD.test(before) || before === marker);
}

function closesEmphasis(text, i, marker) {
  const before = text[i - 1] ?? '';
  const after = text[i + 1] ?? '';
  if (!before || /\s/.test(before)) return false;
  return !(WORD.test(after) || after === marker);
}

/**
 * Index of the ')' that closes a link's URL, starting from `start`.
 *
 * Parens inside the URL are balanced rather than ending it at the first ')',
 * so `[x](javascript:alert(1))` consumes the whole thing instead of leaving a
 * stray ')' behind as text.
 */
function findUrlEnd(line, start) {
  let depth = 0;
  for (let j = start; j < line.length; j++) {
    if (line[j] === '(') depth += 1;
    else if (line[j] === ')') {
      if (depth === 0) return j;
      depth -= 1;
    }
  }
  return -1;
}

/** Parse one line into text / bold / italic / link spans. */
function parseInline(line) {
  const spans = [];
  let buffer = '';
  let i = 0;

  const flush = () => {
    if (buffer) {
      spans.push({ type: 'text', text: buffer });
      buffer = '';
    }
  };

  while (i < line.length) {
    const ch = line[i];
    const pair = line.slice(i, i + 2);

    // Bold first — ** must win over *.
    if (pair === '**' || pair === '__') {
      const end = line.indexOf(pair, i + 2);
      if (end > i + 2) {
        flush();
        spans.push({ type: 'bold', text: line.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }

    // Link: [title](url)
    if (ch === '[') {
      const close = line.indexOf(']', i + 1);
      if (close > i && line[close + 1] === '(') {
        const paren = findUrlEnd(line, close + 2);
        if (paren > close) {
          const label = line.slice(i + 1, close);
          const href = safeUrl(line.slice(close + 2, paren));
          flush();
          // A rejected scheme degrades to the label as plain text.
          if (href) spans.push({ type: 'link', text: label, url: href });
          else if (label) spans.push({ type: 'text', text: label });
          i = paren + 1;
          continue;
        }
      }
    }

    // Italic
    if ((ch === '*' || ch === '_') && opensEmphasis(line, i, ch)) {
      let end = -1;
      for (let j = i + 1; j < line.length; j++) {
        if (line[j] === ch && closesEmphasis(line, j, ch)) { end = j; break; }
      }
      if (end > i + 1) {
        flush();
        spans.push({ type: 'italic', text: line.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }

    buffer += ch;
    i += 1;
  }

  flush();
  return spans;
}

/**
 * Parse markdown text into renderable blocks.
 *
 * Returns an array of:
 *   { type: 'paragraph', lines: Span[][] }   — soft breaks between lines
 *   { type: 'list',      items: Span[][] }
 */
export function parseRichText(text) {
  const source = String(text ?? '');
  if (!source.trim()) return [];

  const blocks = [];
  let paragraph = null;
  let list = null;

  const closeParagraph = () => { if (paragraph) { blocks.push(paragraph); paragraph = null; } };
  const closeList = () => { if (list) { blocks.push(list); list = null; } };

  for (const rawLine of source.split(/\r?\n/)) {
    const line = rawLine.trim();

    if (!line) {                       // blank line ends whatever is open
      closeParagraph();
      closeList();
      continue;
    }

    if (BULLET.test(rawLine)) {        // bullet — never treat the marker as italic
      closeParagraph();
      if (!list) list = { type: 'list', items: [] };
      list.items.push(parseInline(rawLine.replace(BULLET, '')));
      continue;
    }

    closeList();
    if (!paragraph) paragraph = { type: 'paragraph', lines: [] };
    paragraph.lines.push(parseInline(line));
  }

  closeParagraph();
  closeList();
  return blocks;
}
