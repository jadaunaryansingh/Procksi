import React from 'react';
import { parseRichText } from '../lib/richText';

// Renders admin-authored markdown (notifications, announcements) as React
// elements. Never builds an HTML string, so React escapes all text by
// construction — no dangerouslySetInnerHTML and no sanitiser to get wrong.
// Parsing and URL vetting live in ../lib/richText.js, which is unit tested.

function Spans({ spans }) {
  return spans.map((span, i) => {
    if (span.type === 'bold') return <strong key={i} className="font-bold">{span.text}</strong>;
    if (span.type === 'italic') return <em key={i} className="italic">{span.text}</em>;
    if (span.type === 'link') {
      return (
        <a
          key={i}
          href={span.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-indigo-600 dark:text-indigo-400 font-semibold underline underline-offset-2 hover:opacity-80"
        >
          {span.text}
        </a>
      );
    }
    return <React.Fragment key={i}>{span.text}</React.Fragment>;
  });
}

/**
 * @param {string} text       markdown source
 * @param {string} className  typography for the block wrapper — pass whatever the
 *                            call site used on its original <p> so nothing shifts
 */
export default function RichText({ text, className = '' }) {
  const blocks = React.useMemo(() => parseRichText(text), [text]);

  if (blocks.length === 0) return null;

  return (
    <div className={className}>
      {blocks.map((block, bi) => {
        if (block.type === 'list') {
          return (
            <ul key={bi} className="list-disc pl-5 space-y-1 my-2 marker:text-indigo-400">
              {block.items.map((item, ii) => (
                <li key={ii}><Spans spans={item} /></li>
              ))}
            </ul>
          );
        }
        return (
          <p key={bi} className={bi > 0 ? 'mt-2' : undefined}>
            {block.lines.map((line, li) => (
              <React.Fragment key={li}>
                {li > 0 && <br />}
                <Spans spans={line} />
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
