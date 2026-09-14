"""Seed data for the five initial ESN AI business opportunities. Consumed once,
at first startup, by EnterpriseStore._seed_opportunities_if_empty()."""

from __future__ import annotations

SEED_OPPORTUNITIES: list[dict] = [
    {
        "name": "IA Enterprise souveraine",
        "description": (
            "Déploiement d'un LLM open source hébergé chez le client (on-premise ou "
            "cloud privé), avec authentification et gestion des rôles, pour les "
            "entreprises qui ne peuvent pas envoyer leurs données à une API externe."
        ),
        "customer_problem": (
            "Les PME et ETI de secteurs réglementés veulent utiliser l'IA générative "
            "mais leur politique de sécurité ou la réglementation leur interdit "
            "d'envoyer leurs données à une API SaaS externe."
        ),
        "proposed_solution": (
            "Installation et exploitation d'un LLM open source (Llama, Mistral, Qwen) "
            "sur l'infrastructure du client ou dans un cloud privé souverain, avec "
            "authentification OIDC, RBAC applicatif et supervision."
        ),
        "target_customer": "PME et ETI des secteurs santé, finance, défense, industrie",
        "sector": "Multisectoriel réglementé",
        "value_proposition": "Toute la puissance d'un LLM moderne sans qu'une seule donnée ne quitte le périmètre du client",
        "technologies": ["Llama/Mistral/Qwen open source", "vLLM ou Ollama", "OIDC/SSO", "RBAC applicatif", "Kubernetes on-premise"],
        "maturity": "pilote",
        "dev_difficulty": 4,
        "sales_difficulty": 4,
        "competition": "Éditeurs de cloud souverain (OVHcloud AI, Scaleway) et grands intégrateurs",
        "differentiation": "Accompagnement de bout en bout (infra + modèle + intégration) par une équipe unique, cycle de déploiement court",
        "business_model": "Frais de déploiement initial + abonnement mensuel de maintenance et supervision",
        "setup_cost": 12000, "monthly_cost": 1800, "setup_price": 35000, "monthly_price": 4000,
        "estimated_margin_pct": 55, "recurring_revenue_potential": 48000,
        "risks": ["Dépendance à l'infrastructure et au support IT du client", "Compétences MLOps souverain rares en interne", "Cycle de vente long (validation sécurité)"],
        "regulatory_constraints": "RGPD, hébergement souverain, parfois SecNumCloud ou HDS selon le secteur",
        "status": "pilote",
        "scores": {"market": 17, "profitability": 17, "feasibility": 13, "commercialization": 13, "scalability": 13, "retention": 9, "risk": 5},
        "kpis": [
            {"category": "commercial", "name": "Nombre de leads qualifiés", "unit": "leads/mois", "current_value": 6, "previous_value": 4, "target_value": 12, "higher_is_better": True},
            {"category": "financier", "name": "MRR", "unit": "€", "current_value": 24000, "previous_value": 20000, "target_value": 40000, "higher_is_better": True},
            {"category": "ia", "name": "Taux d'hallucination", "unit": "%", "current_value": 3.2, "previous_value": 4.1, "target_value": 2, "higher_is_better": False},
        ],
    },
    {
        "name": "RAG-as-a-Service",
        "description": (
            "Plateforme RAG-as-a-Service permettant à une entreprise de connecter ses "
            "propres documents à un LLM : ingestion documentaire, OCR, embeddings, base "
            "vectorielle, recherche hybride, reranking, citations, gestion des "
            "permissions, évaluation et monitoring du RAG."
        ),
        "customer_problem": "Les entreprises ont des milliers de documents internes mais aucun moyen simple d'interroger cette connaissance avec un assistant IA fiable et traçable.",
        "proposed_solution": "Socle RAG mutualisé (ingestion, OCR, embeddings, vector DB, recherche hybride, reranking, citations, permissions, évaluation, feedback utilisateur) déployé par client, avec un maximum de composants réutilisés d'un client à l'autre.",
        "target_customer": "PME et ETI avec une base documentaire interne importante",
        "sector": "Multisectoriel",
        "value_proposition": "Un assistant qui répond en citant les vraies sources internes, sans réentraîner de modèle",
        "technologies": ["OCR", "Embeddings multilingues", "Base vectorielle (Chroma/Qdrant)", "Recherche hybride BM25+vecteurs", "Reranking", "LLM open source ou API"],
        "maturity": "production",
        "dev_difficulty": 3,
        "sales_difficulty": 3,
        "competition": "Éditeurs SaaS RAG généralistes (Glean, Danswer) et intégrateurs low-code",
        "differentiation": "Socle technique déjà éprouvé et réutilisable, déploiement rapide par client, évaluation du RAG intégrée dès le départ",
        "business_model": "Frais d'intégration initiale + abonnement mensuel selon volume d'utilisateurs et de documents",
        "setup_cost": 6000, "monthly_cost": 900, "setup_price": 15000, "monthly_price": 2500,
        "estimated_margin_pct": 60, "recurring_revenue_potential": 30000,
        "risks": ["Qualité variable des documents sources", "Attentes de précision parfois irréalistes côté client", "Coût d'infrastructure vectorielle qui grimpe avec le volume"],
        "regulatory_constraints": "RGPD sur les documents ingérés, droits d'accès par utilisateur",
        "status": "commercialisation",
        "scores": {"market": 14, "profitability": 14, "feasibility": 11, "commercialization": 11, "scalability": 13, "retention": 8, "risk": 5},
        "kpis": [
            {"category": "commercial", "name": "Taux de conversion", "unit": "%", "current_value": 18, "previous_value": 14, "target_value": 25, "higher_is_better": True},
            {"category": "ia", "name": "Précision du RAG (top-1)", "unit": "%", "current_value": 87, "previous_value": 83, "target_value": 92, "higher_is_better": True},
            {"category": "retention", "name": "Churn", "unit": "%", "current_value": 2.8, "previous_value": 3.5, "target_value": 3, "higher_is_better": False},
        ],
    },
    {
        "name": "AI Agents Business",
        "description": "Conception et exploitation d'agents IA spécialisés capables d'utiliser des outils métiers (emails, CRM, tickets, documents) pour automatiser des tâches mesurables plutôt que des démonstrations gadget.",
        "customer_problem": "Les équipes opérationnelles perdent un temps considérable sur des tâches répétitives (qualification de leads, traitement de tickets, génération de rapports) que l'IA peut prendre en charge si elle est reliée aux bons outils.",
        "proposed_solution": "Agents IA spécialisés par cas d'usage (qualification de leads, traitement d'e-mails, support interne, automatisation CRM) connectés aux outils du client via API/MCP, avec approbation humaine sur les actions sensibles.",
        "target_customer": "PME et ETI avec des processus répétitifs bien identifiés",
        "sector": "Multisectoriel",
        "value_proposition": "Un agent qui termine réellement la tâche dans les outils existants, pas un chatbot de démonstration",
        "technologies": ["LLM avec function calling", "MCP", "Connecteurs CRM/ticketing", "Workflow d'approbation humaine"],
        "maturity": "poc",
        "dev_difficulty": 4,
        "sales_difficulty": 3,
        "competition": "Plateformes no-code d'automatisation (Zapier IA, Make) et agences d'automatisation",
        "differentiation": "Sélection stricte des cas d'usage à impact mesurable, mise en place d'un vrai suivi de KPI d'usage plutôt que des démonstrations",
        "business_model": "Setup par agent + abonnement mensuel par agent/workflow + maintenance",
        "setup_cost": 5000, "monthly_cost": 700, "setup_price": 10000, "monthly_price": 1800,
        "estimated_margin_pct": 58, "recurring_revenue_potential": 21600,
        "risks": ["Fiabilité de l'agent sur les cas limites", "Résistance au changement des équipes", "Dépendance à la stabilité des API tierces connectées"],
        "regulatory_constraints": "RGPD si traitement de données personnelles (emails, leads)",
        "status": "poc",
        "scores": {"market": 16, "profitability": 15, "feasibility": 11, "commercialization": 12, "scalability": 12, "retention": 8, "risk": 5},
        "kpis": [
            {"category": "commercial", "name": "Taux de succès des agents", "unit": "%", "current_value": 81, "previous_value": 74, "target_value": 90, "higher_is_better": True},
            {"category": "financier", "name": "Coût par requête", "unit": "€", "current_value": 0.06, "previous_value": 0.09, "target_value": 0.04, "higher_is_better": False},
            {"category": "retention", "name": "Taux de renouvellement", "unit": "%", "current_value": 88, "previous_value": 82, "target_value": 95, "higher_is_better": True},
        ],
    },
    {
        "name": "AI Modernization",
        "description": "Service d'audit et d'amélioration des systèmes IA déjà en place chez le client (benchmark, dataset engineering, RAG, prompt engineering, fine-tuning LoRA/QLoRA, quantification, optimisation d'inférence), avec pour principe de ne jamais vendre du fine-tuning quand une autre approche est plus pertinente.",
        "customer_problem": "Des entreprises ont déjà mis en place une solution IA mais sont déçues par sa précision, ses coûts d'inférence ou sa latence, sans savoir quel levier technique actionner.",
        "proposed_solution": "Audit du modèle existant, benchmark objectif, puis recommandation et mise en œuvre du levier le plus pertinent (RAG, prompt engineering, fine-tuning LoRA/QLoRA, quantification, optimisation d'inférence) — vente du résultat, pas d'une technologie imposée.",
        "target_customer": "Entreprises ayant déjà une solution IA en production",
        "sector": "Multisectoriel",
        "value_proposition": "Une amélioration mesurable de la précision ou des coûts, avec la technique la plus adaptée et non la plus vendable",
        "technologies": ["Frameworks de benchmark", "Dataset engineering", "LoRA/QLoRA", "Quantification GGUF", "Optimisation d'inférence (vLLM, TensorRT)"],
        "maturity": "analyse",
        "dev_difficulty": 4,
        "sales_difficulty": 3,
        "competition": "Cabinets de conseil data/IA et freelances spécialisés fine-tuning",
        "differentiation": "Méthodologie d'audit avant toute recommandation technique, refus explicite de vendre du fine-tuning hors de propos",
        "business_model": "Mission d'audit puis prestation au forfait selon le levier retenu",
        "setup_cost": 4000, "monthly_cost": 400, "setup_price": 12000, "monthly_price": 1200,
        "estimated_margin_pct": 50, "recurring_revenue_potential": 14400,
        "risks": ["Dépendance à la qualité des données du client", "Résultat parfois incertain avant l'audit complet", "Risque de vendre la mauvaise solution sous pression commerciale"],
        "regulatory_constraints": "RGPD sur les données d'entraînement/évaluation",
        "status": "analyse",
        "scores": {"market": 13, "profitability": 13, "feasibility": 10, "commercialization": 11, "scalability": 12, "retention": 9, "risk": 5},
        "kpis": [
            {"category": "ia", "name": "Taux d'hallucination après optimisation", "unit": "%", "current_value": 4.5, "previous_value": 7.2, "target_value": 3, "higher_is_better": False},
            {"category": "financier", "name": "Marge brute", "unit": "%", "current_value": 48, "previous_value": 41, "target_value": 55, "higher_is_better": True},
            {"category": "commercial", "name": "Cycle de vente", "unit": "jours", "current_value": 52, "previous_value": 60, "target_value": 40, "higher_is_better": False},
        ],
    },
    {
        "name": "AI Continuous Improvement",
        "description": "Service récurrent d'amélioration continue des systèmes IA déjà en production chez le client (RAG, fine-tuning, monitoring, SLA), avec un coût marginal faible par client additionnel.",
        "customer_problem": "Une IA en production se dégrade ou stagne sans supervision continue (dérive du RAG, hallucinations, coûts d'inférence qui grimpent) mais le client n'a pas d'équipe LLMOps interne.",
        "proposed_solution": "Abonnement de supervision et d'amélioration continue : monitoring des KPI IA, réentraînement/réindexation périodique, ajustement du RAG et du fine-tuning, SLA de disponibilité et de qualité, prestations ponctuelles en sus.",
        "target_customer": "Entreprises ayant déjà une IA en production, sans équipe LLMOps interne",
        "sector": "Multisectoriel",
        "value_proposition": "Une IA qui s'améliore dans le temps au lieu de se dégrader, sans que le client ait à recruter une équipe dédiée",
        "technologies": ["Monitoring LLMOps", "Réindexation RAG automatisée", "Ré-entraînement périodique", "Alerting sur dérive de qualité"],
        "maturity": "production",
        "dev_difficulty": 3,
        "sales_difficulty": 3,
        "competition": "Équipes data internes des grands comptes, plateformes d'observabilité IA généralistes",
        "differentiation": "Service géré de bout en bout avec SLA contractuel, coût marginal faible car mutualisé sur plusieurs clients",
        "business_model": "Abonnement mensuel avec SLA + prestations ponctuelles supplémentaires",
        "setup_cost": 3000, "monthly_cost": 500, "setup_price": 5000, "monthly_price": 1500,
        "estimated_margin_pct": 65, "recurring_revenue_potential": 18000,
        "risks": ["Dépendance forte du client à l'équipe prestataire", "SLA difficile à tenir si la charge augmente trop vite", "Dépendance aux fournisseurs de modèles tiers"],
        "regulatory_constraints": "RGPD, engagements contractuels de disponibilité (SLA)",
        "status": "production",
        "scores": {"market": 15, "profitability": 17, "feasibility": 13, "commercialization": 11, "scalability": 14, "retention": 9, "risk": 5},
        "kpis": [
            {"category": "financier", "name": "MRR", "unit": "€", "current_value": 18500, "previous_value": 16500, "target_value": 20000, "higher_is_better": True},
            {"category": "retention", "name": "Churn", "unit": "%", "current_value": 2.1, "previous_value": 2.6, "target_value": 3, "higher_is_better": False},
            {"category": "ia", "name": "Taux de résolution", "unit": "%", "current_value": 91, "previous_value": 86, "target_value": 95, "higher_is_better": True},
        ],
    },
]
