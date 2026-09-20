import type { DecisionConfusionRow } from "@/lib/api";

// Hand-rolled div-grid heatmap, same lightweight style as bar-chart.tsx/
// donut-chart.tsx — no charting library. Cell intensity is relative to the
// row's own max so each actual-class row stays readable regardless of class
// imbalance.
export function ConfusionMatrix({ rows, labels }: { rows: DecisionConfusionRow[]; labels: string[] }) {
  if (rows.length === 0) return null;
  const columns = [...labels, "__invalid__"];

  return (
    <div className="overflow-x-auto">
      <table className="text-xs border-collapse">
        <thead>
          <tr>
            <th className="p-1.5 text-left text-text-muted font-normal">actual \ predicted</th>
            {columns.map((col) => (
              <th key={col} className="p-1.5 text-text-secondary font-mono font-normal text-right">
                {col === "__invalid__" ? "invalide" : col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const rowMax = Math.max(...columns.map((c) => row.predicted[c] ?? 0), 1);
            return (
              <tr key={row.actual}>
                <td className="p-1.5 font-mono text-text-secondary whitespace-nowrap">{row.actual}</td>
                {columns.map((col) => {
                  const value = row.predicted[col] ?? 0;
                  const isDiagonal = col === row.actual;
                  const intensity = value / rowMax;
                  return (
                    <td
                      key={col}
                      className={`p-1.5 text-right font-mono rounded-sm ${isDiagonal ? "text-success" : value > 0 ? "text-error" : "text-text-muted"}`}
                      style={{ backgroundColor: value > 0 ? `rgba(${isDiagonal ? "34,197,94" : "239,68,68"},${0.08 + intensity * 0.25})` : undefined }}
                    >
                      {value}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
