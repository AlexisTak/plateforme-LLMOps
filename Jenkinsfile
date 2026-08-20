// Jenkins pipeline — Biscuits Focus
//
// Le projet n'a pas de depot Git pour l'instant. Ce pipeline est donc concu pour
// tourner SANS SCM : configurer le job Jenkins en "Pipeline script from SCM" est
// impossible ici, il faut le declarer en "Pipeline script" et pointer le
// workspace sur le dossier du projet, ou copier ce fichier dans la definition du
// job. Aucune etape n'appelle `checkout scm`.
//
// Agent : machine Windows avec le venv du projet deja installe (.venv) et Node
// disponible dans le PATH. Le pipeline ne reinstalle pas les dependances Python :
// requirements.txt est epingle sur torch 2.6.0+cu124 et une reinstallation
// automatique a deja casse l'environnement une fois (voir README).
//
// Par defaut le build est rapide et n'exige PAS de GPU. Les tests qui chargent le
// modele 1B sont marques `@pytest.mark.gpu` et ne tournent que si RUN_GPU_TESTS
// est coche.

pipeline {
    agent any

    parameters {
        booleanParam(
            name: 'RUN_GPU_TESTS',
            defaultValue: false,
            description: 'Lance aussi les tests marques "gpu" (chargent le modele 1B en 4-bit, necessitent CUDA, plusieurs minutes).'
        )
        booleanParam(
            name: 'RUN_ARCHIVE',
            defaultValue: false,
            description: "Cree une sauvegarde datee du code source. Sans depot Git, c'est le seul filet de securite avant une operation destructive (train.py --resume supprime son output_dir)."
        )
    }

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 60, unit: 'MINUTES')
    }

    environment {
        PY = '.venv\\Scripts\\python.exe'
    }

    stages {

        stage('Environnement') {
            steps {
                bat '''
                    if not exist "%PY%" (
                        echo Le venv est introuvable a %PY% - installer l'environnement avant de lancer ce job.
                        exit /b 1
                    )
                    "%PY%" --version
                    "%PY%" -c "import torch; print('torch', torch.__version__); print('cuda_available', torch.cuda.is_available())"
                '''
            }
        }

        stage('Contrat dataset') {
            steps {
                // Chaque projet sous projects/ a ses propres datasets/ et data/ —
                // le glob couvre tous les projets present sur le disque, pas
                // seulement le projet par defaut.
                //
                // Les sources : erreurs bloquantes (format, revendication medicale,
                // champs manquants). Fait echouer le build - un dataset invalide ne
                // doit jamais atteindre un entrainement.
                bat '"%PY%" scripts\\validate_dataset.py "projects/*/datasets/**/*.jsonl"'

                // Les splits generes : --check-leakage passe les doublons entre
                // fichiers en erreur. Une fuite train/test rend toutes les metriques
                // d'evaluation fausses sans qu'aucune etape ne s'en apercoive.
                bat '"%PY%" scripts\\validate_dataset.py "projects/*/data/train/*.jsonl" "projects/*/data/validation/*.jsonl" "projects/*/data/test/*.jsonl" --check-leakage'
            }
        }

        stage('Tests rapides') {
            steps {
                bat '''
                    if not exist build mkdir build
                    "%PY%" -m pytest -m "not gpu" -q --junitxml=build\\pytest-fast.xml
                '''
            }
        }

        stage('Console web') {
            steps {
                dir('web') {
                    // npm ci et non npm install : package-lock.json est present et
                    // fait foi, on ne veut pas qu'un build fasse deriver les versions.
                    bat 'npm ci'
                    bat 'npm run lint'
                    bat 'npm run build'
                }
            }
        }

        stage('Tests GPU') {
            when { expression { return params.RUN_GPU_TESTS } }
            steps {
                bat '''
                    if not exist build mkdir build
                    "%PY%" -m pytest -m gpu -q -s --junitxml=build\\pytest-gpu.xml
                '''
            }
        }

        stage('Sauvegarde source') {
            when { expression { return params.RUN_ARCHIVE } }
            steps {
                // Remplace l'historique Git absent. On exclut les poids, le venv et
                // les dependances : l'archive ne fait que quelques centaines de Ko et
                // reste donc creable a chaque build sans cout.
                powershell '''
                    $stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
                    $out = "build\\biscuits-focus_$stamp.zip"
                    $exclude = @('.venv', 'node_modules', '.next', 'models', 'data', '.llama-cpp-tools', 'build', '__pycache__')
                    New-Item -ItemType Directory -Force build | Out-Null
                    $items = Get-ChildItem -Force . | Where-Object { $exclude -notcontains $_.Name }
                    Compress-Archive -Path $items.FullName -DestinationPath $out -Force
                    Write-Output "Sauvegarde ecrite : $out"
                '''
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true, testResults: 'build/pytest-*.xml'
            archiveArtifacts artifacts: 'build/*.zip, evaluation/report.md, evaluation/report_summary.json, experiments/*.json',
                             allowEmptyArchive: true,
                             fingerprint: true
        }
        failure {
            echo 'Build en echec - verifier en priorite le stage "Contrat dataset" : une erreur la signifie que des donnees invalides sont sur le disque, pas seulement que le build casse.'
        }
    }
}
