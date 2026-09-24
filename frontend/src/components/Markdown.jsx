/** Kleiner, sicherer Markdown-Renderer (ohne HTML) für Antworten von Claude. */

function inline(text, keyBase = "") {
  const parts = [];
  const re = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_|\[[^\]]+\]\([^)\s]+\))/g;
  let last = 0;
  let m;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    const key = `${keyBase}-${i++}`;
    if (tok.startsWith("**") || tok.startsWith("__")) parts.push(<strong key={key} className="font-semibold text-ink">{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) parts.push(<code key={key} className="rounded bg-white/5 px-1 py-0.5 font-mono text-[0.85em] text-accent">{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("[")) {
      const [, label, href] = tok.match(/\[([^\]]+)\]\(([^)]+)\)/);
      const safe = /^https?:\/\//.test(href) ? href : "#";
      parts.push(
        <a key={key} href={safe} target="_blank" rel="noreferrer" className="text-accent underline">
          {label}
        </a>,
      );
    } else parts.push(<em key={key}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export default function Markdown({ text }) {
  const lines = (text || "").replace(/\r/g, "").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      blocks.push(
        <div key={i} className={`${level <= 2 ? "font-display text-[0.8rem] text-accent" : "text-sm font-semibold text-ink"} mb-1.5 mt-3 first:mt-0`}>
          {inline(heading[2], `h${i}`)}
        </div>,
      );
      i++;
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const rows = [];
      const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = cells(line);
      i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]));
      blocks.push(
        <div key={`t${i}`} className="my-2 overflow-x-auto">
          <table className="table text-sm">
            <thead>
              <tr>
                {head.map((h, j) => (
                  <th key={j}>{inline(h, `th${j}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>
                  {r.map((c, j) => (
                    <td key={j}>{inline(c, `td${ri}${j}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^\s*([-*•]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]/.test(line);
      const items = [];
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*•]|\d+[.)])\s+/, ""));
        i++;
      }
      const Tag = ordered ? "ol" : "ul";
      blocks.push(
        <Tag key={`l${i}`} className={`my-1.5 space-y-1 pl-5 ${ordered ? "list-decimal" : "list-disc"} marker:text-accent`}>
          {items.map((it, j) => (
            <li key={j}>{inline(it, `li${i}${j}`)}</li>
          ))}
        </Tag>,
      );
      continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|\s*([-*•]|\d+[.)])\s+|\s*\|)/.test(lines[i])) para.push(lines[i++]);
    blocks.push(
      <p key={`p${i}`} className="my-1.5">
        {para.map((p, j) => (
          <span key={j}>
            {j > 0 && <br />}
            {inline(p, `p${i}${j}`)}
          </span>
        ))}
      </p>,
    );
  }
  return <div className="text-sm leading-relaxed text-ink-2">{blocks}</div>;
}
