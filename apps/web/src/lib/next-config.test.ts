import { describe, expect, it } from "vitest";
import nextConfig from "../../next.config";

describe("next.config redirects", () => {
  it("sends /about to / permanently (308)", async () => {
    const rules = await nextConfig.redirects!();
    expect(rules).toContainEqual({ source: "/about", destination: "/", permanent: true });
  });

  it("keeps /packages -> /resumes temporary (307)", async () => {
    const rules = await nextConfig.redirects!();
    expect(rules).toContainEqual({ source: "/packages", destination: "/resumes", permanent: false });
  });

  it("folds /pipeline and /pipeline/board into /dashboard permanently (308)", async () => {
    const rules = await nextConfig.redirects!();
    expect(rules).toContainEqual({ source: "/pipeline", destination: "/dashboard", permanent: true });
    expect(rules).toContainEqual({ source: "/pipeline/board", destination: "/dashboard", permanent: true });
  });
});
