type BarDatum = { label: string; value: number; highlight?: boolean };

export function BarChart({
  data,
  formatValue,
  unit,
}: {
  data: BarDatum[];
  formatValue?: (v: number) => string;
  unit?: string;
}) {
  const max = Math.max(...data.map((d) => d.value), 0.0001);
  const fmt = formatValue ?? ((v: number) => v.toFixed(2));

  return (
    <div className="space-y-2.5">
      {data.map((d) => (
        <div key={d.label} className="flex items-center gap-3" title={`${d.label}: ${fmt(d.value)}${unit ? " " + unit : ""}`}>
          <span className="text-xs font-mono text-text-secondary w-28 shrink-0 truncate">{d.label}</span>
          <div className="flex-1 h-2.5 rounded-full bg-surface-hover overflow-hidden">
            <div
              className={`h-full rounded-full ${d.highlight ? "bg-accent-strong" : "bg-accent"}`}
              style={{ width: `${Math.max((d.value / max) * 100, 3)}%` }}
            />
          </div>
          <span className={`text-xs font-mono w-16 text-right shrink-0 ${d.highlight ? "text-accent-strong" : "text-text-secondary"}`}>
            {fmt(d.value)}
            {unit ?? ""}
          </span>
        </div>
      ))}
    </div>
  );
}
