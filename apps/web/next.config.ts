import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // The packages list is now Resumes (spec §3.4). /pipeline and /pipeline/board are real routes
  // and are deliberately NOT redirected. 307 keeps the query, so /packages?filter=review still
  // lands on the Resumes page with its tab query intact.
  async redirects() {
    return [
      { source: "/packages", destination: "/resumes", permanent: false },
      // The old pitch page is gone; its facts live on / . 308 so clients and search engines move to /.
      { source: "/about", destination: "/", permanent: true },
      // The Pipeline page and its board folded into the Dashboard (Release A). 308: the move is final.
      { source: "/pipeline", destination: "/dashboard", permanent: true },
      { source: "/pipeline/board", destination: "/dashboard", permanent: true },
    ];
  },
};

export default nextConfig;
