// CSS Modules are compiled by the consuming bundler (Next/Turbopack in
// the storefront, Vite in the control center, Vite in this package's own
// test runner); TypeScript only needs the shape of the imported mapping.
declare module '*.module.css' {
  const classes: Record<string, string>;
  export default classes;
}
