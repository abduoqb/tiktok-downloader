# TikTok Scraper

Outil Python pour extraire et télécharger les vidéos et slideshows d'un profil TikTok (YouTube Shorts en option), avec une interface web et une ligne de commande.

## Table des matières

- [Démarrage rapide](#démarrage-rapide)
- [Fonctionnalités](#fonctionnalités)
- [Installation](#installation)
- [Cookies TikTok (obligatoires)](#cookies-tiktok-obligatoires)
- [Utilisation](#utilisation)
  - [Interface web](#interface-web)
  - [Ligne de commande](#ligne-de-commande)
- [Comment ça marche](#comment-ça-marche)
- [Structure du projet](#structure-du-projet)
- [Dépannage](#dépannage)
- [Tests](#tests)
- [Déploiement](#déploiement)
- [Documentation complémentaire](#documentation-complémentaire)

## Démarrage rapide

```bash
# 1. Dépendances Python + ffmpeg installé sur la machine
pip install -r requirements.txt

# 2. Exportez vos cookies TikTok vers tiktok.com_cookies.txt (voir plus bas)

# 3. Interface web : http://localhost:5001
python web_app.py

# ou ligne de commande
python main.py nom_du_compte --download --cookies-file tiktok.com_cookies.txt
```

## Fonctionnalités

- Extraction des liens d'un profil et téléchargement incrémental (s'arrête après 10 vidéos consécutives déjà connues).
- Vidéos **et slideshows** (les images sont rangées dans un dossier par slideshow).
- **Toujours en H.264** : les vidéos HEVC/AV1/VP9 sont converties automatiquement (sinon écran noir avec le son dans les navigateurs).
- Nouvelle tentative automatique (3 essais) et pauses aléatoires anti-bannissement.
- Un téléchargement n'est marqué réussi que si le fichier existe vraiment.
- Les téléchargements en échec sont mémorisés ; `--force-update` les relance.
- Interface web : logs en temps réel, lecteur vidéo intégré, statistiques, gestion des profils.
- Mode URL unique : télécharger une vidéo à partir de son lien.

## Installation

### Prérequis

- Python 3.10 ou plus récent
- **ffmpeg** (avec `ffprobe`) dans le PATH : indispensable pour la conversion H.264
- Dépendances Python : `yt-dlp`, `gallery-dl` (version 1.32 ou plus), `flask`, `requests`

```bash
pip install -r requirements.txt
```

Au démarrage, `preflight.py` vérifie yt-dlp, gallery-dl, ffmpeg, ffprobe et l'âge du fichier de cookies, et affiche un avertissement en cas de problème. Vous pouvez aussi le lancer seul : `python preflight.py`.

**Maintenez les outils à jour.** TikTok change souvent, et un yt-dlp ou gallery-dl trop ancien est la première cause de panne :

```bash
pip install -U yt-dlp gallery-dl
```

## Cookies TikTok (obligatoires)

TikTok bloque désormais le listing des profils pour les outils automatiques. Sans cookies de connexion, l'extraction échoue (le message d'erreur est explicite).

1. Connectez-vous à TikTok dans votre navigateur.
2. Exportez les cookies au format Netscape (extension de type « Get cookies.txt »).
3. Enregistrez le fichier sous le nom `tiktok.com_cookies.txt` **à la racine du projet** (il est ignoré par git, ne le partagez jamais : il donne accès à votre session).

L'interface web le détecte automatiquement. En ligne de commande, passez-le avec `--cookies-file tiktok.com_cookies.txt`. Les cookies expirent : réexportez-les si les téléchargements se remettent à échouer. Détails dans [docs/COOKIES_GUIDE.md](docs/COOKIES_GUIDE.md).

## Utilisation

### Interface web

```bash
python web_app.py
```

Ouvrez `http://localhost:5001`.

1. Ajoutez un profil (nom d'utilisateur, sans le `@`).
2. Cliquez sur **Download** : réglez la limite et les pauses puis lancez. Les logs s'affichent en direct.
3. Utilisez **Sync** sur un profil existant pour ne récupérer que les nouveautés.
4. Ouvrez la page d'un profil pour lire les vidéos dans le navigateur.

Champs du formulaire :

| Champ | Effet |
|-------|-------|
| **Limite** | Nombre maximal de **nouvelles** vidéos à traiter. **`0` = illimité** (champ vide aussi). |
| **Min / Max sleep** | Pause aléatoire entre deux éléments, en secondes (2 et 6 par défaut). |
| **MODE MAJ (Forcer scan complet)** | Revérifie tout l'historique et relance aussi les téléchargements en échec. |

### Ligne de commande

```bash
python main.py <username_ou_url> [options]
```

| Option | Défaut | Description |
|--------|--------|-------------|
| `username_ou_url` | requis | Nom du compte, ou URL d'une vidéo TikTok |
| `--download` | désactivé | Télécharge (sans cette option : extraction des liens seulement) |
| `--limit N` | aucune | Nombre maximal de nouvelles vidéos. **`0` ou absent = illimité** |
| `--min-sleep S` / `--max-sleep S` | `2` / `6` | Pause aléatoire entre deux éléments (secondes) |
| `--force-update` | désactivé | Ignore l'arrêt incrémental et relance les échecs |
| `--cookies-file FICHIER` | aucun | Fichier de cookies au format Netscape |
| `--cookies-browser NAVIGATEUR` | aucun | `chrome`, `firefox`, `edge`, `safari`, `opera`, `brave` (le fichier prime s'il est donné) |
| `--platform` | `tiktok` | `tiktok` ou `youtube` |

Le code de sortie est `1` si l'extraction échoue ou si le type d'une URL est inconnu.

#### Exemples

```bash
# Lister les liens d'un profil sans télécharger
python main.py moncompte --cookies-file tiktok.com_cookies.txt

# Télécharger les nouvelles vidéos
python main.py moncompte --download --cookies-file tiktok.com_cookies.txt

# Tester sur 2 vidéos seulement
python main.py moncompte --download --limit 2 --cookies-file tiktok.com_cookies.txt

# Archiver tout un profil, en allant doucement
python main.py moncompte --download --limit 0 --min-sleep 10 --max-sleep 20 --cookies-file tiktok.com_cookies.txt

# Relancer aussi les échecs précédents
python main.py moncompte --download --force-update --cookies-file tiktok.com_cookies.txt

# Une vidéo seule, à partir de son lien
python main.py "https://www.tiktok.com/@moncompte/video/7574516139682729238"
```

Des pauses trop courtes peuvent faire bannir votre IP.

## Comment ça marche

1. **Listing** : yt-dlp essaie de lister le profil. TikTok le bloque en ce moment ; l'appli bascule alors sur gallery-dl (avec vos cookies). Si les deux échouent, une erreur explicite s'affiche.
2. **Classification** : pour chaque lien, détection vidéo ou slideshow. Si le type ne peut pas être déterminé (cookies expirés, 403, réseau), l'élément est signalé en erreur, non marqué dans l'historique, et réessayé au prochain lancement.
3. **Téléchargement** : vidéo via yt-dlp, slideshow via gallery-dl. L'extraction faite à l'étape 2 est réutilisée (une seule requête par vidéo). yt-dlp choisit d'abord le **H.264 natif de TikTok (540p)** ; contrepartie : 540p au lieu des 720p/1080p HEVC. Le fichier est vérifié avant d'être enregistré dans l'historique.
4. **Conversion H.264 (repli)** : seulement si TikTok ne propose pas de H.264 et que le HEVC est téléchargé, la vidéo est convertie avec ffmpeg (8 bits, yuv420p). L'original n'est remplacé qu'une fois la nouvelle version valide.
5. **Pause** anti-bannissement avant chaque élément suivant, y compris après un échec.

### Mode incrémental

Les vidéos sont parcourues de la plus récente à la plus ancienne. L'extraction s'arrête après 10 vidéos consécutives déjà dans l'historique, donc un `Sync` régulier est rapide. `--force-update` désactive cet arrêt.

### Échecs

Une vidéo en échec est mémorisée et **ignorée aux lancements suivants**, sauf avec `--force-update` (ou la case « MODE MAJ » de l'interface web).

## Structure du projet

```
tiktok/
├── main.py              # CLI + fonctions de téléchargement (yt-dlp, gallery-dl, ffmpeg)
├── orchestrator.py      # Boucle de téléchargement unique (web et CLI)
├── ytdlp_options.py     # Options yt-dlp / gallery-dl et gestion des cookies
├── web_app.py           # Interface web Flask + API
├── metadata_manager.py  # Historique et métadonnées par profil
├── preflight.py         # Vérification de l'environnement au démarrage
├── export_data.py       # Export des données d'un profil
├── requirements.txt
├── templates/ static/   # Interface web
├── tests/               # Tests pytest
├── scripts/             # Déploiement, nettoyage
├── docs/                # Documentation détaillée
├── tiktok.com_cookies.txt   # Vos cookies (ignoré par git)
└── downloads/
    └── moncompte/
        ├── moncompte_videos.txt                       # Liens connus
        ├── metadata.json                              # Historique
        ├── 20250120_moncompte_7574516139682729238.mp4 # Vidéo
        └── 20250121_moncompte_7575823..._img=1/       # Slideshow (images)
```

Nom des vidéos : `{date}_{username}_{id}.mp4`.

## Dépannage

| Symptôme | Cause probable et solution |
|----------|----------------------------|
| `Failed to parse JSON` dans la console | Message de yt-dlp, attendu : l'appli bascule sur gallery-dl. Ce n'est pas fatal tant que « repli sur gallery-dl » est suivi d'éléments trouvés. |
| `Listing impossible pour @compte` | Cookies absents ou expirés, compte supprimé/privé, ou gallery-dl trop ancien. Réexportez les cookies et lancez `pip install -U yt-dlp gallery-dl`. |
| Vidéo noire avec le son dans le navigateur | Vidéo en HEVC téléchargée avant la garantie H.264. Les nouveaux téléchargements sont convertis automatiquement ; la reconversion des anciens fichiers est notée dans [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md). |
| `[H264] WARNING … still hevc` | ffmpeg est absent ou la conversion a échoué. Installez ffmpeg et vérifiez `ffmpeg -version`. |
| Les téléchargements échouent en boucle | Augmentez les pauses, mettez à jour yt-dlp, réexportez les cookies. |
| Une vidéo ratée n'est jamais retentée | Normal sans `--force-update` : relancez avec cette option. |

## Tests

```bash
python -m pytest tests -q
```

Les tests n'utilisent pas le réseau. Les tests de conversion H.264 utilisent un vrai ffmpeg et sont ignorés s'il est absent.

## Déploiement

Docker (`Dockerfile`, `docker-compose.yml`) et un script d'installation VPS (`scripts/deploy.sh`) sont fournis. Le serveur de production utilise `gunicorn web_app:app`. L'état des tâches étant en mémoire, **gardez un seul processus** (`-w 1`) si vous voulez que le suivi des tâches et des logs soit cohérent. Le fichier de cookies n'est pas inclus dans l'image : montez-le en volume. Guide complet : [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Documentation complémentaire

- [docs/COOKIES_GUIDE.md](docs/COOKIES_GUIDE.md) : export et gestion des cookies
- [docs/WEB_INTERFACE.md](docs/WEB_INTERFACE.md) : interface web et API REST
- [docs/ARCHITECTURE_WEB.md](docs/ARCHITECTURE_WEB.md) : architecture
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) : déploiement
- [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) : problèmes connus et tâches reportées
- [docs/CHANGELOG.md](docs/CHANGELOG.md) : historique des versions

## Avertissement

Cet outil est destiné à un usage personnel et éducatif. Respectez les conditions d'utilisation de TikTok et YouTube, ainsi que les droits d'auteur du contenu. Utilisez des pauses raisonnables pour éviter le bannissement de votre IP.
