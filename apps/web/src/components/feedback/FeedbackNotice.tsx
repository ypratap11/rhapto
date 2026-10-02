/** The one disclosure sentence (AC 5). One component so the survey and the quick dialog cannot drift. */
export function FeedbackNotice({ className }: { className?: string }) {
  return (
    <p className={className ?? "text-xs text-muted-foreground"}>
      Your answers are read by the Rhapto maintainer to improve the product. Don&rsquo;t include anything you wouldn&rsquo;t
      want them to see.
    </p>
  );
}
