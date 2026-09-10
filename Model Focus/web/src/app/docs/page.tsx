import Link from "next/link";
import type { ReactNode } from "react";
import { Card, PageHeader, Pill, SectionTitle } from "@/components/ui";

const SCREENS = [
  {
    href: "/",
    name: "Dashboard",
    description: "Résume le volume du dataset et du RAG, les derniers entraînements, leur qualité et les jobs en cours.",
  },
  {
    href: "/dataset",
    name: "Dataset",
    description: "Crée et corrige les exemples qui apprennent au modèle comment répondre, puis construit les jeux d’entraînement et de test.",
  },
  {
    href: "/rag",
    name: "RAG",
    description: "Ajoute des documents de référence que le modèle peut rechercher au moment de répondre, sans réentraînement.",
  },
  {
    href: "/training",
    name: "Training",
    description: "Configure et lance un entraînement LoRA, suit les métriques et conserve les adapters produits.",
  },
  {
    href: "/chat",
    name: "Chat",
    description: "Teste le modèle de base ou un adapter, avec ou sans documents RAG, dans une conversation réelle.",
  },
  {
    href: "/system",
    name: "System",
    description: "Contrôle Python, PyTorch, CUDA, le GPU, la mémoire vidéo, le disque et Ollama.",
  },
];

const GLOSSARY = [
  ["Modèle de base", "Le LLM général utilisé comme point de départ. Il sait déjà produire du texte, mais il n’a pas encore le comportement spécialisé du projet."],
  ["LLM", "Large Language Model : réseau neuronal entraîné sur beaucoup de texte pour comprendre une consigne et générer une réponse."],
  ["Fine-tuning / SFT", "Entraînement supervisé qui montre au modèle des exemples entrée → bonne réponse afin de modifier son comportement."],
  ["LoRA", "Méthode de fine-tuning qui entraîne de petites couches supplémentaires au lieu de modifier tous les poids du modèle. Elle réduit le temps, la VRAM et la taille du résultat."],
  ["QLoRA", "Variante de LoRA qui charge le modèle de base avec moins de bits pendant l’entraînement pour consommer encore moins de VRAM."],
  ["Adapter", "Petit fichier de poids produit par LoRA. Il se branche sur le modèle de base et contient le comportement appris par un entraînement."],
  ["Rang LoRA (r)", "Capacité de l’adapter. Un rang plus élevé peut apprendre davantage de nuances, mais crée plus de paramètres et un fichier plus lourd."],
  ["Dataset", "Collection d’exemples de conversations utilisée pour apprendre au modèle le ton, le format, les refus et la façon de découper une tâche."],
  ["Train / validation / test", "Trois parties séparées du dataset : apprentissage, réglage pendant l’entraînement, puis mesure finale sur des exemples non appris."],
  ["Epoch", "Un passage complet sur tous les exemples d’entraînement. Trop de passages peuvent conduire au surapprentissage."],
  ["Learning rate", "Taille des corrections appliquées aux poids à chaque étape. Trop haut rend l’apprentissage instable ; trop bas le ralentit."],
  ["Batch", "Petit groupe d’exemples traité en une étape. L’accumulation de gradients simule un batch plus grand quand la VRAM est limitée."],
  ["Loss", "Mesure de l’erreur du modèle. Elle sert à suivre l’apprentissage ; plus bas est généralement mieux, mais la qualité réelle doit aussi être testée avec un benchmark."],
  ["Surapprentissage", "Cas où le modèle mémorise le dataset et devient moins bon sur de nouvelles demandes. Un écart entre train loss et eval loss peut l’indiquer."],
  ["Benchmark", "Liste stable de demandes servant à comparer plusieurs modèles ou adapters avec les mêmes critères."],
  ["RAG", "Retrieval-Augmented Generation : recherche de passages utiles dans les documents, puis ajout de ces passages au contexte envoyé au modèle."],
  ["Chunk", "Petit passage découpé depuis un document. La recherche RAG compare la question à ces passages plutôt qu’au document entier."],
  ["Embedding", "Suite de nombres représentant le sens d’un texte. Deux textes proches par le sens produisent des vecteurs proches."],
  ["Index vectoriel", "Structure qui stocke les embeddings et retrouve rapidement les chunks les plus proches d’une question."],
  ["Inférence", "Moment où le modèle déjà entraîné génère une réponse. Le chat est une interface d’inférence."],
  ["Quantification", "Réduction de la précision numérique des poids pour diminuer la RAM, la VRAM et parfois accélérer l’inférence."],
  ["GGUF", "Format de modèle optimisé pour l’exécution locale, notamment avec llama.cpp et Ollama."],
  ["Ollama", "Outil qui exécute facilement des modèles quantifiés en local et expose une API de génération."],
  ["CUDA / VRAM", "CUDA permet à PyTorch d’utiliser un GPU NVIDIA. La VRAM est la mémoire du GPU disponible pour charger et entraîner le modèle."],
  ["API / FastAPI", "L’API est le pont entre l’interface web et les opérations Python. FastAPI est le serveur qui reçoit ces demandes."],
  ["Job", "Opération longue exécutée en arrière-plan, comme un entraînement, une évaluation ou la reconstruction de l’index RAG."],
];

export default function DocsPage() {
  return (
    <div className="space-y-10">
      <PageHeader
        title="Documentation"
        description="Comprendre ce que fait Biscuits Focus, comment utiliser chaque écran et à quoi correspondent les termes techniques."
      />

      <section className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Card className="space-y-3">
          <Pill>Vue d’ensemble</Pill>
          <h2 className="font-display text-xl text-text-primary">Un atelier pour construire et tester un assistant spécialisé</h2>
          <p className="text-sm text-text-secondary leading-relaxed">
            Biscuits Focus permet de partir d’un modèle de langage existant, de lui apprendre une manière précise de
            répondre, de lui fournir des documents de référence et de comparer les résultats. L’application regroupe
            la préparation des données, l’entraînement, l’évaluation et les tests dans une seule interface locale.
          </p>
          <p className="text-sm text-text-secondary leading-relaxed">
            Chaque projet possède ses propres exemples, documents, configurations et adapters. Changer de projet
            évite donc de mélanger les données ou les résultats de deux assistants différents.
          </p>
        </Card>
        <Card className="border-accent/30 bg-accent-soft/40 space-y-3">
          <p className="text-accent-strong text-xs uppercase tracking-wide font-medium">Ce que l’application ne fait pas</p>
          <p className="text-sm text-text-secondary leading-relaxed">
            Elle ne crée pas un grand modèle depuis zéro et ne garantit pas la qualité d’une réponse uniquement parce
            que la loss baisse. Elle aide à produire, mesurer et comparer un assistant spécialisé. Les résultats du
            benchmark et les essais dans le chat restent indispensables.
          </p>
          <p className="text-sm text-text-secondary leading-relaxed">
            Biscuits Focus n’est pas un dispositif médical : il organise et aide à passer à l’action, sans poser de
            diagnostic ni recommander de traitement.
          </p>
        </Card>
      </section>

      <section>
        <SectionTitle>Le parcours complet</SectionTitle>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Step number="1" title="Définir le comportement">Écris des exemples de demandes et de bonnes réponses dans le Dataset.</Step>
          <Step number="2" title="Préparer les données">Valide, retire les doublons et crée les parties train, validation et test.</Step>
          <Step number="3" title="Entraîner">Lance LoRA pour produire un adapter spécialisé à partir du modèle de base.</Step>
          <Step number="4" title="Mesurer">Compare la loss et le benchmark, puis vérifie les réponses dans le Chat.</Step>
          <Step number="5" title="Ajouter du savoir">Place les informations qui changent ou les références longues dans le RAG.</Step>
          <Step number="6" title="Indexer">Découpe les documents en chunks et calcule leurs embeddings pour la recherche.</Step>
          <Step number="7" title="Tester ensemble">Active l’adapter et le RAG dans le Chat pour contrôler la réponse finale.</Step>
          <Step number="8" title="Exporter">Fusionne ou quantifie le modèle si tu veux ensuite l’exécuter avec Ollama.</Step>
        </div>
      </section>

      <section>
        <SectionTitle>Ce que contient chaque écran</SectionTitle>
        <div className="grid gap-3 sm:grid-cols-2">
          {SCREENS.map((screen) => (
            <Link key={screen.href} href={screen.href} className="group">
              <Card className="h-full transition-colors group-hover:border-border-strong group-hover:bg-surface-hover">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <h3 className="font-medium text-text-primary">{screen.name}</h3>
                  <span className="text-accent group-hover:translate-x-0.5 transition-transform">→</span>
                </div>
                <p className="text-sm text-text-secondary leading-relaxed">{screen.description}</p>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <SectionTitle>Dataset, LoRA et RAG : trois rôles différents</SectionTitle>
        <div className="grid gap-4 md:grid-cols-3">
          <Concept title="Dataset" subtitle="Apprend comment répondre" color="accent">
            Ton, structure, priorisation, découpage des tâches et réponses de sécurité. Modifier le dataset demande un
            nouvel entraînement pour changer l’adapter.
          </Concept>
          <Concept title="Adapter LoRA" subtitle="Stocke le comportement appris" color="info">
            Petits poids ajoutés au modèle de base. Plusieurs adapters peuvent être entraînés et comparés sans copier
            le modèle complet à chaque essai.
          </Concept>
          <Concept title="RAG" subtitle="Fournit quoi utiliser comme information" color="success">
            Documents recherchés au moment de la question. Une modification devient disponible après réindexation,
            sans refaire l’entraînement LoRA.
          </Concept>
        </div>
      </section>

      <section>
        <SectionTitle>Comment lire les résultats</SectionTitle>
        <Card className="grid gap-5 md:grid-cols-3 text-sm">
          <Metric title="Train loss">
            Erreur mesurée sur les exemples utilisés pour apprendre. Sa baisse confirme que le modèle apprend le dataset.
          </Metric>
          <Metric title="Eval loss">
            Erreur sur des exemples gardés à part. Elle aide à comparer les expériences et à repérer le surapprentissage.
          </Metric>
          <Metric title="Benchmark comportemental">
            Vérifie des propriétés concrètes : format attendu, concision, sécurité et qualité des actions proposées.
          </Metric>
        </Card>
        <p className="text-xs text-text-muted mt-3 leading-relaxed">
          Une loss plus basse ne suffit pas à choisir un modèle. Compare aussi les réponses du benchmark et teste des
          demandes réalistes qui n’existent pas dans le dataset.
        </p>
      </section>

      <section>
        <SectionTitle>Glossaire technique</SectionTitle>
        <div className="grid gap-x-8 gap-y-0 md:grid-cols-2">
          {GLOSSARY.map(([term, definition]) => (
            <div key={term} className="py-4 border-b border-border">
              <h3 className="font-medium text-text-primary text-sm">{term}</h3>
              <p className="text-text-secondary text-sm leading-relaxed mt-1">{definition}</p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <SectionTitle>Par où commencer ?</SectionTitle>
        <Card className="flex items-center justify-between gap-5 flex-wrap">
          <div>
            <p className="text-text-primary font-medium">Commence par contrôler les exemples existants.</p>
            <p className="text-text-secondary text-sm mt-1">Valide le dataset, lis quelques réponses par catégorie, puis lance un entraînement court.</p>
          </div>
          <Link href="/dataset" className="px-3 py-1.5 text-sm rounded-md font-medium bg-accent text-[#20140a] hover:bg-accent-strong transition-colors">
            Ouvrir le Dataset
          </Link>
        </Card>
      </section>
    </div>
  );
}

function Step({ number, title, children }: { number: string; title: string; children: ReactNode }) {
  return (
    <Card className="relative overflow-hidden">
      <span className="absolute -right-1 -top-4 font-display text-7xl text-border/70 select-none">{number}</span>
      <div className="relative">
        <span className="text-accent font-mono text-xs">ÉTAPE {number}</span>
        <h3 className="font-medium text-text-primary mt-1 mb-2">{title}</h3>
        <p className="text-sm text-text-secondary leading-relaxed">{children}</p>
      </div>
    </Card>
  );
}

function Concept({ title, subtitle, color, children }: { title: string; subtitle: string; color: "accent" | "info" | "success"; children: ReactNode }) {
  const styles = {
    accent: "border-accent/30 bg-accent-soft/30 text-accent-strong",
    info: "border-info/30 bg-info-soft/30 text-info",
    success: "border-success/30 bg-success-soft/30 text-success",
  };
  return (
    <Card className={styles[color]}>
      <h3 className="font-display text-lg">{title}</h3>
      <p className="text-text-primary text-sm font-medium mt-1">{subtitle}</p>
      <p className="text-text-secondary text-sm leading-relaxed mt-3">{children}</p>
    </Card>
  );
}

function Metric({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="font-mono text-accent text-xs uppercase tracking-wide mb-2">{title}</h3>
      <p className="text-text-secondary leading-relaxed">{children}</p>
    </div>
  );
}
