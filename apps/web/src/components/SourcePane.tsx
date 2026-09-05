import { useMemo } from 'react';
import type { AtomView } from '../lib/contracts';
import { fateOf, FATE_LABEL } from '../lib/format';

/**
 * Source text with atom highlighting.
 *
 * Spans come from the backend inventory. The component never re-detects atoms:
 * doing so would create a second, divergent atomizer in the browser.
 */
export function SourcePane(
  { text, atoms, selected, onSelect }:
  { text: string; atoms: AtomView[]; selected: string | null;
    onSelect: (id: string | null) => void },
) {
  const segments = useMemo(() => {
    const sorted = [...atoms].sort((a, b) => a.char_start - b.char_start);
    const out: Array<{ key: string; text: string; atom: AtomView | null }> = [];
    let cursor = 0;
    for (const atom of sorted) {
      if (atom.char_start < cursor) continue;   // overlap already emitted
      if (atom.char_start > cursor) {
        out.push({ key: `t${cursor}`, text: text.slice(cursor, atom.char_start), atom: null });
      }
      out.push({
        key: atom.atom_id,
        text: text.slice(atom.char_start, atom.char_end),
        atom,
      });
      cursor = atom.char_end;
    }
    if (cursor < text.length) out.push({ key: `t${cursor}`, text: text.slice(cursor), atom: null });
    return out;
  }, [text, atoms]);

  if (!text) return <p className="unavailable">NOT RUN — no source frame loaded.</p>;

  return (
    <div className="source-text">
      {segments.map((seg) =>
        seg.atom ? (
          <mark
            key={seg.key}
            className="atom-mark"
            data-focal={seg.atom.focal}
            aria-current={selected === seg.atom.atom_id}
            tabIndex={0}
            role="button"
            aria-label={`${seg.atom.role} atom, ${FATE_LABEL[fateOf(seg.atom)]}`}
            onClick={() => onSelect(selected === seg.atom!.atom_id ? null : seg.atom!.atom_id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelect(selected === seg.atom!.atom_id ? null : seg.atom!.atom_id);
              }
            }}
          >
            {seg.text}
          </mark>
        ) : (
          <span key={seg.key}>{seg.text}</span>
        ),
      )}
    </div>
  );
}
