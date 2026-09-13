export function DonutChart({ passed, total, label }: { passed: number; total: number; label: string }) {
  const safeTotal = Math.max(total, 1);
  const failed = Math.max(total - passed, 0);
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const progress = total > 0 ? (passed / safeTotal) * circumference : 0;

  return (
    <div className="flex items-center gap-4" aria-label={`${label} : ${passed} réussis et ${failed} échoués sur ${total}`}>
      <div className="relative h-28 w-28 shrink-0">
        <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90" aria-hidden="true">
          <circle cx="50" cy="50" r={radius} fill="none" stroke="var(--surface-hover)" strokeWidth="12" />
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${progress} ${circumference - progress}`}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-display text-xl text-text-primary">{passed}/{total}</span>
          <span className="text-[10px] text-text-muted">réussis</span>
        </div>
      </div>
      <div className="space-y-2 text-xs">
        <p className="font-medium text-text-primary">{label}</p>
        <p className="flex items-center gap-2 text-text-secondary"><span className="h-2.5 w-2.5 rounded-full bg-accent" />{passed} réussis</p>
        <p className="flex items-center gap-2 text-text-secondary"><span className="h-2.5 w-2.5 rounded-full bg-surface-hover border border-border" />{failed} échoués</p>
      </div>
    </div>
  );
}
