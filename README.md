# TikTok Scraper

Un outil CLI Python efficace pour extraire et télécharger des vidéos depuis TikTok et YouTube Shorts.

## Description

Ce script utilise `yt-dlp` pour récupérer les vidéos d'un profil utilisateur de manière optimisée. Il supporte l'extraction rapide de liens (sans téléchargement) et le téléchargement intelligent avec gestion d'historique pour éviter les doublons.

## Fonctionnalités

- **Extraction rapide** : Récupère uniquement les métadonnées sans télécharger (mode `extract_flat`)
- **Mode incrémental intelligent** : S'arrête automatiquement après 10 vidéos consécutives déjà présentes dans l'historique
- **Téléchargement avec retry** : 3 tentatives automatiques en cas d'échec réseau
- **Anti-bannissement** : Délais aléatoires configurables entre chaque téléchargement
- **Gestion d'historique** : Système JSON pour éviter les doublons
- **Multi-plateformes** : Supporte TikTok et YouTube Shorts
- **Organisation automatique** : Structure de dossiers par utilisateur

## Installation

### Prérequis
- Python 3.7+
- pip

### Installation des dépendances

```bash
pip install -r requirements.txt
```

Ou directement :

```bash
pip install yt-dlp
```

## Utilisation

### Syntaxe de base

```bash
python main.py <username> [options]
```

### Arguments

| Argument | Type | Défaut | Description |
|----------|------|--------|-------------|
| `username` | Requis | - | Pseudo du créateur de contenu |
| `--platform` | Optionnel | `tiktok` | Plateforme cible (`tiktok` ou `youtube`) |
| `--download` | Flag | `False` | Active le téléchargement des vidéos |
| `--min-sleep` | Optionnel | `5` | Pause minimale entre téléchargements (secondes) |
| `--max-sleep` | Optionnel | `15` | Pause maximale entre téléchargements (secondes) |
| `--limit` | Optionnel | - | Limite le nombre de vidéos à traiter |

### Exemples d'utilisation

#### 1. Extraire uniquement les liens (sans télécharger)

```bash
python main.py antiheretique
```

Résultat : Fichier `downloads/antiheretique/antiheretique_videos.txt` contenant la liste des URLs.

#### 2. Télécharger toutes les nouvelles vidéos

```bash
python main.py bellapoarch --download
```

#### 3. Limiter à 50 vidéos

```bash
python main.py jujaxtespam --download --limit 50
```

#### 4. YouTube Shorts avec pauses plus longues

```bash
python main.py channelname --platform youtube --download --min-sleep 10 --max-sleep 20
```

#### 5. Mode rapide (pauses courtes - à utiliser avec précaution)

```bash
python main.py username --download --min-sleep 2 --max-sleep 5
```

## Structure du projet

```
tiktok/
├── main.py                          # Script principal
├── requirements.txt                 # Dépendances Python
├── README.md                        # Ce fichier
├── explication_projet.md            # Documentation technique détaillée
├── analysis.md                      # Analyse et recommandations
└── downloads/                       # Dossier de sortie
    └── <username>/
        ├── download_history.json    # Historique des vidéos téléchargées
        ├── <username>_videos.txt    # Liste des URLs extraites
        └── *.mp4                    # Vidéos téléchargées
```

## Format de nommage des vidéos

Les vidéos sont téléchargées avec le format suivant :

```
{date_upload}_{titre_50_caracteres}_{id_video}.mp4
```

Exemple : `20250120_Best_dance_video_ever_[7574516139682729238].mp4`

## Fonctionnement interne

### Mode Incrémental

Le script utilise un système intelligent pour éviter de rescanner tout le profil :

1. Charge l'historique depuis `download_history.json`
2. Parcourt les vidéos du profil du plus récent au plus ancien
3. S'arrête après avoir trouvé **10 vidéos consécutives** déjà dans l'historique
4. Cela suppose que les nouvelles vidéos sont en haut de la liste

### Gestion des erreurs

- **Retry automatique** : 3 tentatives par vidéo en cas d'échec réseau
- **Pause entre retries** : 2 secondes
- **Ignorance des erreurs** : Les vidéos inaccessibles sont sautées (ne bloquent pas le processus)

### Anti-détection

Pour éviter les bannissements d'IP :

- Délais aléatoires entre chaque téléchargement (5-15s par défaut)
- Utilisation de `yt-dlp` qui gère automatiquement les cookies et signatures
- Mode `extract_flat` pour l'extraction de liens (très rapide, peu suspect)

## Exemples de cas d'usage

### Veille quotidienne

```bash
# Extraire uniquement les nouveaux liens (très rapide)
python main.py myuser

# Télécharger les nouvelles vidéos de plusieurs profils
python main.py user1 --download --limit 20
python main.py user2 --download --limit 20
python main.py user3 --download --limit 20
```

### Archivage complet d'un profil

```bash
# Première fois : peut prendre plusieurs heures
python main.py archiveuser --download --min-sleep 10 --max-sleep 20

# Relances suivantes : seulement les nouveaux contenus
python main.py archiveuser --download
```

### Extraction massive de liens pour analyse

```bash
# Récupérer les liens de 10 profils en quelques minutes
python main.py user1
python main.py user2
python main.py user3
# ... etc
```

## Dépannage

### Problème : "No new videos found"

- Vérifiez que le pseudo est correct
- Vérifiez que le profil n'est pas privé
- Essayez de mettre à jour `yt-dlp` : `pip install --upgrade yt-dlp`

### Problème : Téléchargements qui échouent

- Augmentez les délais : `--min-sleep 15 --max-sleep 30`
- Vérifiez votre connexion internet
- Mettez à jour `yt-dlp`

### Problème : Historique corrompu

Supprimez le fichier `downloads/<username>/download_history.json` pour repartir à zéro.

## Limitations

- **Profils privés** : Ne fonctionne pas avec les comptes privés
- **Rate limiting** : TikTok peut limiter le nombre de requêtes. Utilisez des délais raisonnables.
- **Contenu en direct** : Les lives ne sont pas supportés

## Améliorations futures possibles

- Base de données SQLite pour gérer de gros volumes (>10k vidéos)
- Logs structurés avec le module `logging`
- Mode batch pour scraper plusieurs utilisateurs d'un coup
- Interface web (Flask/Streamlit) pour visualiser l'historique

## Licence

Projet personnel - Utilisation libre

## Avertissement

Cet outil est destiné à un usage personnel et éducatif. Respectez les conditions d'utilisation de TikTok et YouTube. Le téléchargement massif de contenu peut violer les CGU des plateformes.
