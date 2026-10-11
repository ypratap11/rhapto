import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Help" };

// Every factual sentence below is backed by a source; the page claims nothing the code does not check.
//  1  docs/product/overview.md (what Rhapto is)
//  2  docs/user-guide/faq.md "Does Rhapto apply for me?"; docs/product/overview.md "The human-in-the-loop rule"
//  3  Light touch / Full rewrite checks per .superpowers/sdd/release-b/plan-review.md C1; a failing resume is
//     held back with its reason (docs/user-guide/faq.md "Why did a resume get blocked?")
//  4  same two-mode wording (plan-review C1); "Your experience" is the T9 label for the profile's blocks
//  5  docs/user-guide/settings-and-sources.md (AI key in Settings); no number: the trial count is a setting
//  6  docs/product/privacy.md "What is stored", "What leaves the machine", "Keys"; "Download my data" is the
//     T9 label in Settings
//  7, 8  the account menu's "Send feedback" (TopBar); privacy.md on feedback
const QUESTIONS: ReadonlyArray<{ q: string; a: string[] }> = [
  {
    q: "What does Rhapto do?",
    a: [
      "Rhapto finds jobs, matches each one to the roles you want, and writes a resume for that job from your own experience. You read it, fix anything that looks off, and download it.",
    ],
  },
  {
    q: "Does Rhapto apply for me?",
    a: [
      "No, never. Rhapto opens the employer's own application page and gives you the resume to download. The last click, the one that sends your application, is always yours.",
    ],
  },
  {
    q: "How do I know the resume is true?",
    a: [
      "Light touch rewords a few lines of your own resume file and is not allowed to add a number that is not already in that file. Full rewrite builds each line from an item in Your experience, and every number must appear in an item you confirmed.",
      "A resume that fails these checks is held back and shows the reason. Please still read it before you send it.",
    ],
  },
  {
    q: "Where do the numbers come from?",
    a: [
      "With Light touch, from your uploaded resume file: a number that is not in that file is not allowed. With Full rewrite, from items you marked as confirmed in Your profile, under Your experience.",
    ],
  },
  {
    q: "Do I need my own AI key?",
    a: ["A small number of free resumes are included. After that, add your own AI key in Settings to keep making resumes."],
  },
  {
    q: "What happens to my resume and data?",
    a: [
      "Your profile, the jobs Rhapto finds and the resumes it makes are saved in the database behind this copy of Rhapto. The text of your experience and the job is sent to the AI service that writes the resume, and job searches go to the job sources that are switched on. Rhapto sends no usage analytics to anyone.",
      "Your AI key is stored encrypted and is never shown in full again. In Settings, Download my data gives you a copy of what you have saved.",
    ],
  },
  {
    q: "A job looks wrong, or a resume is off",
    a: ["Choose Send feedback in the account menu (the round button at the top right) and say which job or resume it was."],
  },
  {
    q: "How do I contact you?",
    a: ["Use Send feedback in the account menu from any page after you sign in. It reaches the people who run Rhapto."],
  },
];

export default function HelpPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="space-y-2">
        <h1 className="font-serif text-2xl font-medium">Help</h1>
        <p className="text-sm text-muted-foreground">Short answers to the questions people ask most.</p>
        <Link href="/" prefetch={false} className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline underline-offset-4">
          Back to Rhapto
        </Link>
      </div>
      <div className="space-y-2">
        {QUESTIONS.map(({ q, a }) => (
          <details key={q} className="rounded-card border border-border bg-surface px-4">
            <summary className="flex min-h-11 cursor-pointer items-center py-2 text-base font-medium">{q}</summary>
            <div className="space-y-2 pb-4 text-sm text-muted-foreground">
              {a.map((p) => (
                <p key={p}>{p}</p>
              ))}
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}
