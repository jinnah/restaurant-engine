// Preview link mode (ADR-022 §3).
//
// The renderer's three in-site navigation elements (layout nav, hero call
// to action, menu-section link) render through `siteLinkHref`. In the
// default `'active'` mode they are ordinary anchors. In `'inert'` mode the
// same `<a>` renders with **no `href`**: without a URL there is no mouse,
// keyboard, auxiliary-click, or context-menu navigation path to suppress,
// the element exposes no link role (assistive technology is never told an
// active link exists that cannot be followed), and element-selector
// styling still applies, so the visual presentation is byte-identical.
// The public storefront passes nothing and renders exactly as before;
// only the control-center preview passes `'inert'`.

export type LinkMode = 'active' | 'inert';

/** The `href` value for an in-site navigation anchor under `mode`. */
export function siteLinkHref(mode: LinkMode, href: string): string | undefined {
  return mode === 'active' ? href : undefined;
}
