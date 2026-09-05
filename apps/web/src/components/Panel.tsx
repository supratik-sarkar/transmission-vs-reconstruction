import type { ReactNode } from 'react';

export function Panel(
  { title, area, actions, children }:
  { title: string; area?: string; actions?: ReactNode; children: ReactNode },
) {
  return (
    <section className={`panel ${area ?? ''}`} aria-label={title}>
      <header>
        <h2>{title}</h2>
        {actions ? <div style={{ marginLeft: 'auto' }}>{actions}</div> : null}
      </header>
      <div className="body">{children}</div>
    </section>
  );
}
