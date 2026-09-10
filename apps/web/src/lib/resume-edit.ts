import type { ResumeDocument } from "@/lib/api/queries";
import { parsePath } from "./resume-paths";

export function updateBulletText(resume: ResumeDocument, path: string, text: string): ResumeDocument {
  const p = parsePath(path);
  if (p.kind === "summary") {
    if (!resume.summary[p.index]) return resume;
    return { ...resume, summary: resume.summary.map((b, i) => (i === p.index ? { ...b, text } : b)) };
  }
  if (p.kind === "bullet") {
    const section = resume.sections[p.section];
    const entry = section?.entries[p.entry];
    if (!section || !entry || !entry.bullets[p.bullet]) return resume;
    return {
      ...resume,
      sections: resume.sections.map((s, si) =>
        si !== p.section ? s : { ...s, entries: s.entries.map((e, ei) => (ei !== p.entry ? e : { ...e, bullets: e.bullets.map((b, bi) => (bi === p.bullet ? { ...b, text } : b)) })) },
      ),
    };
  }
  return resume;
}

export function removeBullet(resume: ResumeDocument, path: string): ResumeDocument {
  const p = parsePath(path);
  if (p.kind === "summary") return { ...resume, summary: resume.summary.filter((_, i) => i !== p.index) };
  if (p.kind !== "bullet") return resume;
  return {
    ...resume,
    sections: resume.sections.map((s, si) => {
      if (si !== p.section) return s;
      const entries = s.entries.flatMap((e, ei) => {
        if (ei !== p.entry) return [e];
        const bullets = e.bullets.filter((_, bi) => bi !== p.bullet);
        const headerless = !e.org && !e.role && !e.period && !e.title;
        return bullets.length === 0 && headerless ? [] : [{ ...e, bullets }];
      });
      return { ...s, entries };
    }),
  };
}

export function isSameResume(a: ResumeDocument, b: ResumeDocument): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
