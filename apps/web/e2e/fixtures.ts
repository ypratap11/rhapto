import { test as base, expect } from "@playwright/test";

// There is no /login page: the app gates on a bearer token in localStorage (components/shell/
// TokenGate.tsx). Seed the same keys src/lib/api/client.ts reads, before any page script runs.
export const test = base.extend<{ theme: "light" | "dark" }>({
  theme: ["light", { option: true }],
  context: async ({ context, theme }, use) => {
    await context.addInitScript(
      ({ token, apiUrl, theme }) => {
        window.localStorage.setItem("rhapto.token", token);
        window.localStorage.setItem("rhapto.apiUrl", apiUrl);
        window.localStorage.setItem("rhapto.theme", theme);
      },
      { token: process.env.RHAPTO_API_TOKEN ?? "", apiUrl: process.env.RHAPTO_PUBLIC_API_URL ?? "http://localhost:8000", theme },
    );
    await use(context);
  },
});

export { expect };
