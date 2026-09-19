import type { Metadata } from "next";
import { Fraunces, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { Shell } from "@/components/shell/Shell";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains" });

export const metadata: Metadata = { title: "Rhapto", description: "Every application, stitched to fit." };

// Runs before React hydrates so the stored (or system) theme is on <html> for the first paint and
// there is no light-to-dark flash. Kept in sync with ThemeToggle, which writes the same key.
const THEME_SCRIPT = `(function(){try{var s=localStorage.getItem("rhapto.theme");var dark=s==="dark"||(s!=="light"&&window.matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.classList.toggle("dark",dark);}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${fraunces.variable} ${mono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      {/* Browser extensions (e.g. ColorZilla) inject attributes like cz-shortcut-listen onto
          <body> before React hydrates, tripping a hydration-mismatch warning that has nothing to
          do with our app. <html> above already needs suppressHydrationWarning for the theme boot
          script; body needs it for the same class of reason — extension-injected attributes, not
          an app bug. This only ignores mismatches on body's own attributes, one level deep. */}
      <body suppressHydrationWarning>
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  );
}
