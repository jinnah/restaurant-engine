import { Fragment } from 'react';

import type { PublicStorySection } from '../../lib/contract';
import styles from './sections.module.css';

// Body text is plain text with normalized newlines (backend
// `normalize_block`): blank lines separate paragraphs, single newlines are
// line breaks within one. Rendering preserves exactly that structure —
// React escaping everywhere, no markup interpretation of any kind.
export function storyParagraphs(body: string): string[][] {
  return body.split(/\n{2,}/).map((paragraph) => paragraph.split('\n'));
}

export function StorySection({ section }: { section: PublicStorySection }) {
  const { heading, body } = section.props;
  return (
    <section className={styles.section}>
      <h2 className={styles.heading}>{heading}</h2>
      <div className={styles.storyBody}>
        {storyParagraphs(body).map((lines, paragraphIndex) => (
          // Positional keys: paragraph order is the content's identity.
          <p key={paragraphIndex}>
            {lines.map((line, lineIndex) => (
              <Fragment key={lineIndex}>
                {lineIndex > 0 ? <br /> : null}
                {line}
              </Fragment>
            ))}
          </p>
        ))}
      </div>
    </section>
  );
}
