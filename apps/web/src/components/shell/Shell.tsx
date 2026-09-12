import Link from "next/link";
import { Nav } from "./Nav";
import { StepBar } from "./StepBar";
import { TokenGate } from "./TokenGate";

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <Link href="/" className="font-serif text-xl">
            Rhapto
          </Link>
          <Nav />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <TokenGate>
          <>
            <StepBar />
            {children}
          </>
        </TokenGate>
      </main>
    </div>
  );
}
