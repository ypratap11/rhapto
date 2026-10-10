import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // /packages -> /resumes is temporary (307 keeps the query, so /packages?filter=review keeps its
  // tab); /about and /pipeline* moved for good (308).
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
