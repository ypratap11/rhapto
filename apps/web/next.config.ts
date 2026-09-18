import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // The packages list is now Resumes (spec §3.4). /pipeline and /pipeline/board are real routes
  // and are deliberately NOT redirected. 307 keeps the query, so /packages?filter=review still
  // lands on the Resumes page with its tab query intact.
  async redirects() {
    return [{ source: "/packages", destination: "/resumes", permanent: false }];
  },
};

export default nextConfig;
