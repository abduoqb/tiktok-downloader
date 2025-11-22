# TikTok Scraper

Un outil Python complet pour extraire et télécharger des vidéos depuis TikTok et YouTube Shorts avec interface web moderne, détection intelligente des slideshows et intégration Telegram.

## Table des matières

- [Quick Start](#quick-start)
- [Fonctionnalités](#fonctionnalités)
- [Installation](#installation)
- [Utilisation](#utilisation)
  - [Interface Web](#interface-web-recommandé)
  - [Configuration Telegram](#configuration-optionnel)
  - [Ligne de Commande](#ligne-de-commande-cli)
- [Structure des fichiers](#structure-des-fichiers)
- [Exemples de workflows](#exemples-de-workflows)
- [Interface Web - Fonctionnalités détaillées](#interface-web---fonctionnalités-détaillées)
- [Sécurité](#sécurité)
- [Dépannage](#dépannage)
- [Limitations](#limitations)
- [Technologies](#technologies)
- [Contribuer](#contribuer)
- [Améliorations futures](#améliorations-futures)
- [Documentation complémentaire](#documentation-complémentaire)

## Quick Start

```bash
# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Lancer l'interface web
python web_app.py

# 3. Ouvrir dans le navigateur
# http://localhost:5000

# Ou en ligne de commande
python main.py charolife --download
```

## Fonctionnalités

✨ **Core**
- Extraction rapide de liens (mode `extract_flat`)
- Téléchargement avec retry automatique (3 tentatives)
- Gestion d'historique JSON pour éviter les doublons
- Support TikTok et YouTube Shorts
- **Interface Web** : Dashboard complet avec logs en temps réel
- **Intégration Telegram** : Envoi automatique des vidéos téléchargées vers des topics Telegram

🧠 **Intelligence**
- **Mode incrémental smart** : S'arrête après 10 vidéos consécutives déjà connues
- **Détection de slideshows** : Identifie et sauvegarde les panoramas dans un fichier JSON séparé (sans télécharger)
- **Anti-bannissement** : Délais aléatoires configurables

🎯 **Simplicité**
- **Mode URL unique** : Téléchargez un TikTok directement via son lien
- **Format de fichier simple** : `20250120_charolife_7574516139682729238.mp4`
- Organisation automatique par profil

## Installation

### Prérequis
- Python 3.7+
- `yt-dlp`

```bash
pip install -r requirements.txt
```

Ou manuellement :
```bash
pip install yt-dlp flask
```

## Utilisation

### Interface Web (Recommandé)

1. Lancez le serveur :
   ```bash
   python web_app.py
   ```
2. Ouvrez `http://localhost:5000` dans votre navigateur.

### Configuration (Optionnel)

#### Intégration Telegram

Pour envoyer automatiquement les vidéos téléchargées vers un groupe Telegram :

1. Créez un fichier `config.json` à la racine du projet (vous pouvez copier `config.json.example`) :
   ```bash
   cp config.json.example config.json
   ```

   Puis éditez-le avec vos informations :
   ```json
   {
       "TELEGRAM_BOT_TOKEN": "votre_token_bot",
       "TELEGRAM_CHAT_ID": "votre_chat_id"
   }
   ```

2. Configuration du bot :
   - Créez un bot via [@BotFather](https://t.me/BotFather) sur Telegram
   - Récupérez le token du bot
   - Ajoutez le bot à votre groupe
   - Activez les topics dans votre groupe (Paramètres > Topics)
   - Récupérez le chat ID du groupe

3. Le système créera automatiquement un topic par profil TikTok
   - Chaque vidéo téléchargée sera envoyée dans le topic correspondant
   - Le mapping est sauvegardé dans `telegram_topics.json`

**Note** : Si `config.json` n'existe pas, l'intégration Telegram est simplement désactivée.

#### Gestion des topics Telegram

Pour éviter les doublons de topics et gérer le mapping des profils existants, consultez **[TELEGRAM_TOPICS.md](TELEGRAM_TOPICS.md)**.

Points clés :
- Le système crée automatiquement un topic par profil
- Le mapping est sauvegardé dans `telegram_topics.json`
- Vous pouvez ajouter manuellement des topics existants via l'API
- Depuis la v1.1, un système de verrous évite les doublons lors de téléchargements parallèles

### Ligne de Commande (CLI)

#### Syntaxe

```bash
python main.py <username_ou_url> [options]
```

### Arguments

| Argument | Type | Défaut | Description |
|----------|------|--------|-------------|
| `username_ou_url` | Requis | - | Pseudo du créateur OU URL directe d'un TikTok |
| `--platform` | Optionnel | `tiktok` | Plateforme (`tiktok` ou `youtube`) |
| `--download` | Flag | `False` | Active le téléchargement |
| `--limit` | Optionnel | - | Limite le nombre de vidéos |
| `--min-sleep` | Optionnel | `5` | Pause min entre téléchargements (s) |
| `--max-sleep` | Optionnel | `15` | Pause max entre téléchargements (s) |

### Exemples

#### 1. Extraire les liens d'un profil (sans télécharger)

```bash
python main.py charolife
```

Génère : `downloads/charolife/charolife_videos.txt`

#### 2. Télécharger toutes les nouvelles vidéos

```bash
python main.py bellapoarch --download
```

#### 3. Limiter à 20 vidéos

```bash
python main.py charlidamelio --download --limit 20
```

#### 4. Télécharger une vidéo unique via son URL

```bash
python main.py "https://www.tiktok.com/@charolife/video/7574516139682729238"
```

#### 5. Mode rapide (pour profil de confiance)

```bash
python main.py addisonre --download --min-sleep 1 --max-sleep 3
```

⚠️ **Attention** : Des délais trop courts peuvent causer un bannissement IP !

## Structure des fichiers

```
tiktok/
├── main.py                           # Script CLI principal
├── web_app.py                        # Interface web Flask
├── config.json                       # Configuration Telegram (créer depuis .example)
├── config.json.example               # Template de configuration
├── telegram_topics.json              # Mapping profils → topics Telegram
├── requirements.txt                  # Dépendances Python
├── .gitignore                        # Fichiers à ignorer (dont config.json)
├── README.md                         # Ce fichier
├── templates/                        # Templates HTML
│   ├── base.html
│   ├── index.html
│   └── profile.html
└── downloads/
    └── charolife/
        ├── charolife_videos.txt      # Liste de tous les liens
        ├── download_history.json     # IDs des vidéos téléchargées
        ├── slideshows.json           # TikToks panorama détectés
        ├── 20250120_charolife_7574516.mp4
        └── 20250121_charolife_7575823.mp4
```

## Format de nommage

**Vidéos normales** : `{date}_{username}_{id}.mp4`

Exemple : `20250120_charolife_7574516139682729238.mp4`

**Slideshows** : Sauvegardés dans `slideshows.json` (non téléchargés)

```json
[
  {
    "id": "7572951061078625558",
    "url": "https://www.tiktok.com/@user/video/7572951061078625558"
  }
]
```

## Fonctionnement interne

### Mode Incrémental

1. Charge l'historique depuis `download_history.json`
2. Parcourt les vidéos du plus récent au plus ancien
3. S'arrête après **10 vidéos consécutives** déjà dans l'historique
4. Permet de combler les "trous" (vidéos manquées lors d'un téléchargement partiel)

### Détection de Slideshows

Avant chaque téléchargement, le script vérifie si c'est un panorama (images + audio uniquement) :
- ✅ **Vidéo normale** → Téléchargement
- ⚠️ **Slideshow** → Sauvegarde dans `slideshows.json` + Skip

### Retry & Anti-détection

- **3 tentatives** par vidéo en cas d'échec
- **Pause de 2s** entre tentatives
- **Délais aléatoires** entre téléchargements (5-15s par défaut)

## Exemples de workflows

### Veille quotidienne (plusieurs profils)

**Avec CLI :**
```bash
python main.py charolife --download --limit 10
python main.py bellapoarch --download --limit 10
python main.py charlidamelio --download --limit 10
```

**Avec Interface Web :**
1. Ajoutez les profils via le formulaire
2. Utilisez le bouton "Sync" sur chaque profil pour télécharger les nouveautés
3. Les vidéos sont automatiquement envoyées vers Telegram (si configuré)

### Archivage complet d'un profil

```bash
# Première fois (peut prendre du temps)
python main.py khaby.lame --download --min-sleep 10 --max-sleep 20

# Relances suivantes (que les nouveaux)
python main.py khaby.lame --download
```

### Téléchargement manuel de vidéos spécifiques

```bash
python main.py "https://www.tiktok.com/@charolife/video/123456"
python main.py "https://www.tiktok.com/@bellapoarch/video/789012"
```

## Interface Web - Fonctionnalités détaillées

### Dashboard Principal
- Formulaire d'ajout de profils (TikTok/YouTube)
- Liste des profils avec statistiques (vidéos téléchargées, espace disque)
- Actions rapides : Détails, Sync, Suppression
- Statistiques globales en temps réel

### Page Profil
- Statistiques détaillées du profil
- Liste complète des vidéos téléchargées
- Lecteur vidéo intégré (lecture directe dans le navigateur)
- Bouton de synchronisation pour télécharger les nouvelles vidéos
- Copie rapide des chemins de fichiers

### API REST
L'interface web expose une API REST complète :
- `GET /api/profiles` - Liste des profils
- `POST /api/extract` - Extraire les liens
- `POST /api/download` - Télécharger (tâche background)
- `GET /api/task/<task_id>` - Statut d'une tâche
- `DELETE /api/profile/<username>/delete` - Supprimer un profil
- `GET /api/stats` - Statistiques globales

Plus de détails dans [WEB_INTERFACE.md](WEB_INTERFACE.md)

## Sécurité

**IMPORTANT** : Le fichier `config.json` contient des informations sensibles (token Telegram).

Assurez-vous de :
- Ne **jamais** commiter `config.json` dans Git (déjà dans `.gitignore`)
- Créer votre `config.json` depuis `config.json.example`
- Utiliser des variables d'environnement en production
- Ne pas partager votre bot token publiquement

**Note** : `config.json` et `telegram_topics.json` sont déjà ignorés par Git.

## Dépannage

### "No new videos found"

- Vérifiez le pseudo
- Le profil est peut-être privé
- Mettez à jour `yt-dlp` : `pip install --upgrade yt-dlp`

### Téléchargements qui échouent

- Augmentez les délais : `--min-sleep 15 --max-sleep 30`
- Vérifiez votre connexion
- Mettez à jour `yt-dlp`

### Historique corrompu

Supprimez `downloads/<username>/download_history.json` pour recommencer.

### Problèmes Telegram

**Les vidéos ne sont pas envoyées sur Telegram :**
- Vérifiez que `config.json` existe et contient les bonnes informations
- Vérifiez que le bot est bien ajouté au groupe
- Vérifiez que le bot a les droits d'administrateur dans le groupe
- Vérifiez que les topics sont activés dans le groupe
- Consultez les logs de l'application pour voir les erreurs

**Le topic n'est pas créé automatiquement :**
- Le bot doit avoir les droits de "Manage Topics" dans le groupe
- Vérifiez que les topics sont activés (Paramètres du groupe > Topics)

**Fichier trop volumineux :**
- Telegram a une limite de 50 MB pour les fichiers envoyés par bot
- Les vidéos > 50 MB ne seront pas envoyées (erreur dans les logs)

## Limitations

- ❌ **Profils privés** : Non supportés
- ⚠️ **Rate limiting** : Respectez des délais raisonnables
- ❌ **Lives** : Non supportés
- ⚠️ **Slideshows** : Détectés mais non téléchargés (limitations de yt-dlp)
- ⚠️ **Telegram** : Limite de 50 MB par fichier (limite Telegram Bot API)

## Technologies

### Backend
- **Python 3.7+** : Langage principal
- **yt-dlp** : Moteur d'extraction vidéo (fork de youtube-dl)
- **Flask 3.0+** : Framework web pour l'interface
- **Threading** : Gestion des tâches asynchrones

### Frontend
- **HTML5/CSS3** : Structure et style
- **Tailwind CSS** : Framework CSS utilitaire
- **JavaScript (Vanilla)** : Interactions client
- **Jinja2** : Moteur de templates

### Intégrations
- **Telegram Bot API** : Envoi automatique de vidéos
- **JSON** : Stockage des données (historique, configuration, mapping)

### Architecture
- **RESTful API** : Communication frontend-backend
- **Server-Sent Events (SSE)** : Logs en temps réel
- **Mode Extract Flat** : Extraction optimisée sans téléchargement complet

Pour plus de détails techniques, voir [explication_projet.md](explication_projet.md)

## Contribuer

Les contributions sont les bienvenues ! Pour contribuer :

1. **Forkez** le projet
2. **Créez une branche** pour votre fonctionnalité (`git checkout -b feature/ma-fonctionnalite`)
3. **Commitez** vos changements (`git commit -m 'Ajout de ma fonctionnalité'`)
4. **Pushez** vers la branche (`git push origin feature/ma-fonctionnalite`)
5. Ouvrez une **Pull Request**

### Bugs et suggestions

- Utilisez les **Issues** GitHub pour signaler des bugs
- Proposez des **améliorations** via les Issues
- Partagez vos **cas d'usage** intéressants

### Développement local

```bash
# Cloner le projet
git clone <url-du-repo>
cd tiktok

# Installer les dépendances
pip install -r requirements.txt

# Lancer en mode développement
python web_app.py
```

## Améliorations futures

### Court terme
- ✅ Interface web moderne
- ✅ Intégration Telegram
- ✅ Lecteur vidéo intégré
- ⬜ Barre de progression en temps réel
- ⬜ Filtres et recherche dans la liste des vidéos
- ⬜ Mode sombre (dark mode)

### Moyen terme
- ⬜ Planification de tâches (cron jobs)
- ⬜ Notifications par email
- ⬜ Export des données (CSV)
- ⬜ Graphiques de statistiques
- ⬜ Support de playlists

### Long terme
- ⬜ Migration vers SQLite/PostgreSQL
- ⬜ Authentification multi-utilisateurs
- ⬜ Support Instagram Reels
- ⬜ API documentée avec Swagger
- ⬜ Docker & docker-compose

## Déploiement sur serveur (VPS)

Pour déployer l'application sur un serveur VPS (Ubuntu/Debian) :

### Installation rapide (script automatique)

```bash
# Se connecter au VPS
ssh root@votre-ip

# Télécharger et exécuter le script
wget https://raw.githubusercontent.com/votre-repo/tiktok-scraper/master/deploy.sh
chmod +x deploy.sh
sudo ./deploy.sh
```

Le script installe automatiquement :
- ✅ Python, pip, git
- ✅ Environnement virtuel Python
- ✅ Service systemd pour démarrage automatique
- ✅ Nginx (optionnel) comme reverse proxy
- ✅ Pare-feu UFW configuré
- ✅ Gunicorn pour la production

### Configuration post-installation

```bash
# Éditer la configuration Telegram
sudo nano /home/tiktok/tiktok-scraper/config.json

# Redémarrer le service
sudo systemctl restart tiktok-scraper

# Voir les logs
sudo journalctl -u tiktok-scraper -f
```

### Guide complet

Pour une installation manuelle détaillée, configuration SSL, sauvegardes automatiques, etc., consultez **[DEPLOYMENT.md](DEPLOYMENT.md)**.

## Documentation complémentaire

- **[DEPLOYMENT.md](DEPLOYMENT.md)** : Guide complet de déploiement sur VPS (installation, configuration, sécurité)
- **[TELEGRAM_TOPICS.md](TELEGRAM_TOPICS.md)** : Gestion des topics Telegram et résolution des doublons
- **[WEB_INTERFACE.md](WEB_INTERFACE.md)** : Guide détaillé de l'interface web et de l'API REST
- **[explication_projet.md](explication_projet.md)** : Architecture technique et choix de conception
- **[analysis.md](analysis.md)** : Analyse approfondie du projet

## Licence

Projet personnel - Utilisation libre

## Avertissement

⚠️ **Usage responsable** : Cet outil est destiné à un **usage personnel et éducatif** uniquement.

- Respectez les conditions d'utilisation de TikTok et YouTube
- Le téléchargement massif peut violer leurs CGU
- Respectez les droits d'auteur du contenu
- N'utilisez pas cet outil à des fins commerciales sans autorisation
- Utilisez des délais raisonnables pour éviter le bannissement IP
