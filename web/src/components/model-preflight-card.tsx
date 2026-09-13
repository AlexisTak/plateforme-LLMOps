import { ModelPreflight } from "@/lib/api";
import { Button, Card } from "@/components/ui";

export function ModelPreflightCard({ result, loading, onRetry }: {
  result: ModelPreflight | null;
  loading: boolean;
  onRetry: () => void;
}) {
  if (loading) return <Card className="text-text-muted text-sm">Vérification du modèle…</Card>;
  if (!result) return <Card className="border-error/30 text-error text-sm">Prévalidation indisponible. <Button onClick={onRetry}>Réessayer</Button></Card>;
  return (
    <Card className={result.ready ? "border-success/30" : "border-error/30"}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className={result.ready ? "text-success text-sm font-medium" : "text-error text-sm font-medium"}>
            {result.ready ? "Modèle prêt" : "Modèle non prêt"}
          </p>
          <p className="font-mono text-xs text-text-secondary mt-1 break-all">{result.model}</p>
        </div>
        <Button variant="ghost" onClick={onRetry}>Revérifier</Button>
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-text-muted mt-3">
        {result.architecture ? <span>{result.architecture}</span> : null}
        {result.estimated_download_gb != null ? <span>≈ {result.estimated_download_gb} Go à télécharger</span> : null}
        {result.estimated_vram_gb != null ? <span>≈ {result.estimated_vram_gb} Go VRAM requis</span> : null}
        {result.available_vram_gb != null ? <span>{result.available_vram_gb} Go VRAM libres</span> : null}
      </div>
      {[...result.errors, ...result.warnings].length > 0 ? (
        <ul className="list-disc pl-5 text-xs mt-3 space-y-1 text-text-secondary">
          {result.errors.map((message) => <li className="text-error" key={message}>{message}</li>)}
          {result.warnings.map((message) => <li key={message}>{message}</li>)}
        </ul>
      ) : null}
    </Card>
  );
}
