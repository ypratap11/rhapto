import { TopBar } from "./TopBar";
import { TokenGate } from "./TokenGate";

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <TopBar />
      <main className="mx-auto max-w-6xl px-6 py-8">
        <TokenGate>{children}</TokenGate>
      </main>
    </div>
  );
}
