# TikTok Scraper

Un outil CLI Python pour extraire et télécharger des vidéos depuis TikTok et YouTube Shorts avec détection intelligente des slideshows.

## Fonctionnalités

✨ **Core**
- Extraction rapide de liens (mode `extract_flat`)
- Téléchargement avec retry automatique (3 tentatives)
- Gestion d'historique JSON pour éviter les doublons
- Support TikTok et YouTube Shorts
- **Interface Web** : Dashboard complet avec logs en temps réel

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
pip install yt-dlp flask
```

## Utilisation

### Interface Web (Recommandé)

1. Lancez le serveur :
   ```bash
   python web_app.py
   ```
2. Ouvrez `http://localhost:5000` dans votre navigateur.

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
downloads/
  └── charolife/
      ├── charolife_videos.txt          # Liste de tous les liens
      ├── download_history.json         # IDs des vidéos téléchargées
      ├── slideshows.json               # TikToks panorama détectés
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

```bash
python main.py charolife --download --limit 10
python main.py bellapoarch --download --limit 10
python main.py charlidamelio --download --limit 10
```

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

## Limitations

- ❌ **Profils privés** : Non supportés
- ⚠️ **Rate limiting** : Respectez des délais raisonnables
- ❌ **Lives** : Non supportés
- ⚠️ **Slideshows** : Détectés mais non téléchargés (limitations de yt-dlp)

## Licence

Projet personnel - Utilisation libre

## Avertissement

⚠️ Cet outil est destiné à un **usage personnel et éducatif**. Respectez les CGU de TikTok et YouTube. Le téléchargement massif peut violer leurs conditions d'utilisation.
