import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { SectionList } from '../src/sections/SectionList';
import { storyParagraphs } from '../src/sections/StorySection';
import { imageSrcSet } from '../src/StorefrontImage';
import type { PublicSection } from '../src/contract';
import {
  contactSection,
  gallerySection,
  heroSection,
  imageFixture,
  menuSection,
  storySection,
} from '../src/fixtures';

describe('SectionList dispatch and ordering', () => {
  test('renders every registered type in exactly the projection order', () => {
    const sections: PublicSection[] = [
      storySection(),
      heroSection(),
      contactSection(),
      gallerySection(),
      menuSection(),
    ];
    render(<SectionList sections={sections} />);
    const headings = screen
      .getAllByRole('heading', { level: 2 })
      .map((h) => h.textContent);
    expect(headings).toEqual([
      'Our story',
      'Neighborhood kitchen, open late',
      'Find us',
      'Gallery',
      'Our menu',
    ]);
  });

  test('an unknown runtime section type fails to the error boundary, undisclosed', () => {
    const drifted = {
      id: 'x',
      type: 'campaign',
      props: {},
    } as unknown as PublicSection;
    expect(() => render(<SectionList sections={[drifted]} />)).toThrow(
      /unhandled contract variant/,
    );
  });
});

describe('hero', () => {
  test('renders heading, subheading, eager LCP image, and the menu action', () => {
    render(<SectionList sections={[heroSection()]} />);
    expect(
      screen.getByRole('heading', { level: 2, name: /neighborhood kitchen/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/family recipes/i)).toBeInTheDocument();
    const image = screen.getByRole('img', { name: /plated dish/i });
    expect(image).toHaveAttribute('loading', 'eager');
    expect(image).toHaveAttribute('fetchpriority', 'high');
    expect(image).toHaveAttribute('width', '1600');
    expect(image).toHaveAttribute('height', '1200');
    expect(screen.getByRole('link', { name: 'View menu' })).toHaveAttribute(
      'href',
      '/menu',
    );
  });

  test('omits every optional value rather than fabricating', () => {
    render(
      <SectionList
        sections={[
          heroSection({
            subheading: null,
            image: null,
            primary_action: 'none',
          }),
        ]}
      />,
    );
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.queryByText(/family recipes/i)).not.toBeInTheDocument();
  });
});

describe('story', () => {
  test('storyParagraphs preserves paragraph and line structure exactly', () => {
    expect(storyParagraphs('One.\nTwo.\n\nThree.')).toEqual([
      ['One.', 'Two.'],
      ['Three.'],
    ]);
  });

  test('renders paragraphs and line breaks without interpreting markup', () => {
    const { container } = render(
      <SectionList
        sections={[
          storySection({ body: 'Safe <b>text</b>.\n\n</script> stays text.' }),
        ]}
      />,
    );
    const paragraphs = container.querySelectorAll('p');
    expect(paragraphs).toHaveLength(2);
    expect(paragraphs[0]?.textContent).toBe('Safe <b>text</b>.');
    expect(paragraphs[1]?.textContent).toBe('</script> stays text.');
    expect(container.querySelector('b')).toBeNull();
  });
});

describe('contact', () => {
  test('renders address lines and derives safe links', () => {
    render(<SectionList sections={[contactSection()]} />);
    expect(screen.getByText('12 Main Street')).toBeInTheDocument();
    expect(screen.getByText('Buffalo, NY 14201')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: '(716) 555-0100' }),
    ).toHaveAttribute('href', 'tel:7165550100');
    expect(
      screen.getByRole('link', { name: 'hello@example.com' }),
    ).toHaveAttribute('href', 'mailto:hello@example.com');
  });

  test('unlinkable phone and email render as plain text, never as links', () => {
    render(
      <SectionList
        sections={[
          contactSection({ phone: 'ask for Rob', email: 'front desk' }),
        ]}
      />,
    );
    expect(screen.getByText('ask for Rob')).toBeInTheDocument();
    expect(screen.getByText('front desk')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});

describe('gallery', () => {
  test('renders lazy images with delivered alt text (missing alt is decorative)', () => {
    const { container } = render(<SectionList sections={[gallerySection()]} />);
    const images = container.querySelectorAll('img');
    expect(images).toHaveLength(2);
    expect(images[0]).toHaveAttribute('loading', 'lazy');
    expect(images[0]).toHaveAttribute('alt', 'A plated dish on a wooden table');
    expect(images[1]).toHaveAttribute('alt', '');
  });

  test('an empty gallery renders nothing at all', () => {
    const { container } = render(
      <SectionList sections={[gallerySection({ images: [] })]} />,
    );
    expect(container.innerHTML).toBe('');
  });
});

describe('menu section', () => {
  test('renders heading, intro, and the full-menu navigation', () => {
    render(<SectionList sections={[menuSection()]} />);
    expect(
      screen.getByRole('link', { name: /view the full menu/i }),
    ).toHaveAttribute('href', '/menu');
  });
});

describe('imageSrcSet', () => {
  test('is built from the delivered variants plus the canonical, widths intact', () => {
    expect(imageSrcSet(imageFixture())).toBe(
      '/api/v1/public/media/00000000-0000-0000-0000-00000000aaaa/w320 320w, ' +
        '/api/v1/public/media/00000000-0000-0000-0000-00000000aaaa/w640 640w, ' +
        '/api/v1/public/media/00000000-0000-0000-0000-00000000aaaa/w1280 1600w',
    );
  });
});
