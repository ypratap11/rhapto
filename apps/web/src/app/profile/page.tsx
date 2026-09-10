"use client";

import { AnswersTab } from "@/components/profile/AnswersTab";
import { BasesTab } from "@/components/profile/BasesTab";
import { BlocksTab } from "@/components/profile/BlocksTab";
import { GuardrailsTab } from "@/components/profile/GuardrailsTab";
import { ImportExport } from "@/components/profile/ImportExport";
import { TracksTab } from "@/components/profile/TracksTab";
import { WatchlistTab } from "@/components/profile/WatchlistTab";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const TABS = [
  ["blocks", "Blocks", <BlocksTab key="blocks" />],
  ["bases", "Bases", <BasesTab key="bases" />],
  ["tracks", "Tracks", <TracksTab key="tracks" />],
  ["guardrails", "Guardrails", <GuardrailsTab key="guardrails" />],
  ["answers", "Answers", <AnswersTab key="answers" />],
  ["watchlist", "Watchlist", <WatchlistTab key="watchlist" />],
] as const;

export default function ProfilePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl">Profile</h1>
        <p className="text-sm text-muted-foreground">
          Your blocks, bases, tracks, guardrails, answers, and watchlist live in the database now. Import YAML to replace them, or export to take them back to files — <code className="font-mono text-xs">rhapto profile export</code> writes the
          same files locally.
        </p>
      </div>
      <ImportExport />
      <Tabs defaultValue="blocks">
        <TabsList>
          {TABS.map(([value, label]) => (
            <TabsTrigger key={value} value={value}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
        {TABS.map(([value, , content]) => (
          <TabsContent key={value} value={value}>
            {content}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
