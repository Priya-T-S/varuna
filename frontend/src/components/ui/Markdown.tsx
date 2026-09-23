import { Fragment, type ReactNode } from "react";

/**
 * Minimal Markdown renderer for assistant replies: headings, paragraphs,
 * bullet / numbered lists, **bold**, *italic*, `code`. Builds React elements
 * (never innerHTML), so model output cannot inject markup.
 */
export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push(
        <p className="mt-3 text-[13px] font-semibold text-stone-900 first:mt-0" key={i}>
          {inline(heading[2])}
        </p>,
      );
      i += 1;
      continue;
    }
    if (/^\s*([-*•]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line);
      const items: ReactNode[] = [];
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) {
        const nested = /^\s{2,}/.test(lines[i]);
        items.push(
          <li className={nested ? "ml-4" : undefined} key={i}>
            {inline(lines[i].replace(/^\s*([-*•]|\d+[.)])\s+/, ""))}
          </li>,
        );
        i += 1;
      }
      blocks.push(
        ordered ? (
          <ol className="my-1.5 list-decimal space-y-1 pl-5" key={`l${i}`}>{items}</ol>
        ) : (
          <ul className="my-1.5 list-disc space-y-1 pl-5" key={`l${i}`}>{items}</ul>
        ),
      );
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4})\s|^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) {
      para.push(lines[i]);
      i += 1;
    }
    blocks.push(
      <p className="my-1.5 first:mt-0" key={`p${i}`}>
        {para.map((p, idx) => (
          <Fragment key={idx}>
            {idx > 0 && <br />}
            {inline(p)}
          </Fragment>
        ))}
      </p>,
    );
  }
  return <div className="text-[13.5px] leading-6 text-stone-800">{blocks}</div>;
}

function inline(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("**")) parts.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith("`"))
      parts.push(
        <code className="rounded-sm bg-stone-200/70 px-1 font-mono text-[12px]" key={key++}>
          {token.slice(1, -1)}
        </code>,
      );
    else parts.push(<em key={key++}>{token.slice(1, -1)}</em>);
    last = match.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}
