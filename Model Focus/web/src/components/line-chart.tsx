type Point = { x: number; y: number };

export function LineChart({
  series,
  height = 160,
}: {
  series: { label: string; color: string; points: Point[] }[];
  height?: number;
}) {
  const allPoints = series.flatMap((s) => s.points);
  if (allPoints.length === 0) {
    return <p className="text-text-muted text-sm">Pas encore de données.</p>;
  }

  const width = 600;
  const padding = 8;
  const xs = allPoints.map((p) => p.x);
  const ys = allPoints.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs, minX + 1);
  const minY = Math.min(...ys, 0);
  const maxY = Math.max(...ys, minY + 0.01);

  const scaleX = (x: number) => padding + ((x - minX) / (maxX - minX)) * (width - 2 * padding);
  const scaleY = (y: number) => height - padding - ((y - minY) / (maxY - minY)) * (height - 2 * padding);

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height }}>
        <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="var(--border)" strokeWidth={1} />
        {series.map((s) =>
          s.points.length > 1 ? (
            <polyline
              key={s.label}
              points={s.points.map((p) => `${scaleX(p.x)},${scaleY(p.y)}`).join(" ")}
              fill="none"
              stroke={s.color}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ) : null
        )}
        {series.map((s) =>
          s.points.map((p, i) => <circle key={`${s.label}-${i}`} cx={scaleX(p.x)} cy={scaleY(p.y)} r={2.5} fill={s.color} />)
        )}
      </svg>
      <div className="flex items-center gap-4 mt-2">
        {series.map((s) => (
          <div key={s.label} className="flex items-center gap-1.5 text-xs text-text-secondary">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} />
            {s.label}
          </div>
        ))}
      </div>
    </div>
  );
}
