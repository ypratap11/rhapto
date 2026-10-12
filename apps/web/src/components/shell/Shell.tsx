import { Footer } from "./Footer";
import { TopBar } from "./TopBar";
import { TokenGate } from "./TokenGate";

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    // overflow-x-clip: HeroBand's breakout and PageHero's `::before` wash are both `w-screen`, which includes
    // the scrollbar's width and so is a few pixels wider than the real viewport on any scrollable page.
    // Clipping it here keeps that overflow from turning into a horizontal scrollbar instead of trying to
    // size it exactly.
    <div className="min-h-screen overflow-x-clip bg-background">
      <TopBar />
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <TokenGate>{children}</TokenGate>
      </main>
      <Footer />
    </div>
  );
}
