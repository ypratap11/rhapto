/** The stitched-line motif in a hero band's right third (spec §8): Rhapto "stitches" each
 * application, so the band's only ornament is a running stitch. Decorative — always aria-hidden. */
export function StitchMotif({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 320 160"
      preserveAspectRatio="none"
      className={className}
      style={{ opacity: 0.08 }}
    >
      {[0, 1, 2, 3].map((row) => (
        <path
          key={row}
          d={`M0 ${28 + row * 34} C 60 ${4 + row * 34}, 100 ${52 + row * 34}, 160 ${28 + row * 34} S 260 ${4 + row * 34}, 320 ${28 + row * 34}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeDasharray="10 8"
        />
      ))}
    </svg>
  );
}
