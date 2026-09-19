import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Playwright specs are not Next code and trip eslint-config-next's rules (react-hooks,
    // next/no-img-element, etc. do not apply to e2e/*.spec.ts).
    "e2e/**",
    // Playwright's own generated output — bundled/minified viewer assets, never hand-written.
    ".playwright-report/**",
    "test-results/**",
  ]),
]);

export default eslintConfig;
