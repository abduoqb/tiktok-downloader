# Architecture du Site Web TikTok Scraper

## Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────┐
│                         NAVIGATEUR                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Dashboard  │  │    Profils   │  │  Logs Live   │          │
│  │   /          │  │  /profile/   │  │ /stream_logs │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FLASK WEB APP (Port 5001)                     │
│ ┌───────────────────────────────────────────────────────────────┤
│ │                        ROUTES                                  │
│ ├───────────────────────────────────────────────────────────────┤
│ │                                                                │
│ │  Pages HTML:                    API REST:                     │
│ │  • GET  /                       • POST /api/extract           │
│ │  • GET  /profile/<username>     • POST /api/download          │
│ │  • GET  /video/<username>/<f>   • GET  /api/profiles          │
│ │                                 • GET  /api/stats              │
│ │  Streaming:                     • DELETE /api/video/<id>      │
│ │  • GET  /stream_logs (SSE)      • DELETE /api/profile/<user>  │
│ │                                                                │
│ │  Telegram:                                                     │
│ │  • GET    /api/telegram/topics                                │
│ │  • POST   /api/telegram/topics                                │
│ │  • DELETE /api/telegram/topics/<name>                         │
│ └────────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SYSTÈME DE LOGGING SSE                        │
│                                                                   │
│  ┌──────────────┐         ┌──────────────┐                      │
│  │  emit_log()  │ ──────> │  log_queue   │ ──┐                  │
│  └──────────────┘         │  (Queue)     │   │                  │
│        ▲                  └──────────────┘   │                  │
│        │                                      │                  │
│        │  Background                          │  SSE Stream      │
│        │  Threads                             ▼                  │
│        │                          ┌────────────────────┐         │
│        └──────────────────────────│  /stream_logs      │         │
│                                   │  (Server-Sent      │         │
│                                   │   Events)          │         │
│                                   └────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    TÂCHES EN ARRIÈRE-PLAN                        │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┤
│  │  background_extract_task(username, platform, limit)          │
│  │  • Analyse le profil TikTok                                  │
│  │  • Extrait les liens vidéos                                  │
│  │  • Sauvegarde dans metadata.json                             │
│  └──────────────────────────────────────────────────────────────┘
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┤
│  │  background_download_task(username, platform, sleep, ...)    │
│  │  1. Extraction des liens                                     │
│  │  2. Détection slideshow (avec cache)                         │
│  │  3. Téléchargement vidéos/slideshows                         │
│  │  4. Envoi Telegram (optionnel)                               │
│  │  5. Mise à jour metadata.json                                │
│  │  6. Logs en temps réel via emit_log()                        │
│  └──────────────────────────────────────────────────────────────┘
│                                                                   │
│  Threading.Thread(daemon=True)                                   │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MODULES CORE (main.py)                       │
│                                                                   │
│  ┌────────────────────┐  ┌────────────────────┐                 │
│  │  get_video_links() │  │  download_video()  │                 │
│  │  • yt-dlp          │  │  • yt-dlp          │                 │
│  │  • Extraction      │  │  • H.264 codec     │                 │
│  └────────────────────┘  └────────────────────┘                 │
│                                                                   │
│  ┌────────────────────┐  ┌────────────────────┐                 │
│  │  is_slideshow()    │  │download_slideshow()│                 │
│  │  • Cache résultats │  │  • gallery-dl      │                 │
│  │  • API yt-dlp      │  │  • Images only     │                 │
│  └────────────────────┘  └────────────────────┘                 │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              SYSTÈME DE MÉTADONNÉES (metadata_manager.py)        │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┤
│  │  OptimizedMetadataManager                                    │
│  │  • Cache en mémoire (O(1) lookups)                           │
│  │  • Un seul fichier metadata.json                             │
│  │  • Métadonnées riches (type, date, taille, statut)          │
│  │  • Cache is_slideshow() (99% API calls évités)              │
│  │  • Backup automatique                                        │
│  └──────────────────────────────────────────────────────────────┘
│                                                                   │
│  downloads/username/                                              │
│  └── metadata.json                                               │
│      {                                                            │
│        "7123456789": {                                           │
│          "url": "...",                                           │
│          "type": "video",                                        │
│          "date": "2025-11-22T16:30:45",                          │
│          "size": 5242880,                                        │
│          "file_count": 1,                                        │
│          "success": true                                         │
│        }                                                          │
│      }                                                            │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     INTÉGRATIONS EXTERNES                         │
│                                                                   │
│  ┌──────────────────────┐  ┌──────────────────────┐             │
│  │   TELEGRAM BOT API   │  │      yt-dlp          │             │
│  │   • Envoi vidéos     │  │   • Extraction       │             │
│  │   • Topics par user  │  │   • Métadonnées      │             │
│  │   • Auto-création    │  │   • Formats          │             │
│  └──────────────────────┘  └──────────────────────┘             │
│                                                                   │
│  ┌──────────────────────┐                                        │
│  │     gallery-dl       │                                        │
│  │   • Slideshows       │                                        │
│  │   • Images TikTok    │                                        │
│  └──────────────────────┘                                        │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      STOCKAGE FICHIERS                            │
│                                                                   │
│  downloads/                                                       │
│  ├── lapukipuks/                                                 │
│  │   ├── metadata.json              ← Système optimisé          │
│  │   ├── metadata.json.backup       ← Backup auto               │
│  │   ├── lapukipuks_videos.txt      ← Liste URLs                │
│  │   ├── 20251122_lapukipuks_712...mp4  ← Vidéos               │
│  │   └── 20251119_lapukipuks_757...jpg  ← Slideshows           │
│  │                                                                │
│  ├── mariam.shk/                                                 │
│  ├── ss0hane/                                                    │
│  └── ...                                                          │
│                                                                   │
│  config.json                         ← Config Telegram           │
│  telegram_topics.json                ← Mapping topics            │
└─────────────────────────────────────────────────────────────────┘
```

## Flux de travail typique

### 1. Scan d'un profil (Extraction)

```
Utilisateur                Flask                 Background Thread       TikTok API
    │                        │                           │                    │
    │  POST /api/extract     │                           │                    │
    ├───────────────────────>│                           │                    │
    │                        │  Thread.start()           │                    │
    │                        ├──────────────────────────>│                    │
    │  {"success": true}     │                           │                    │
    │<───────────────────────┤                           │                    │
    │                        │                           │  get_video_links() │
    │                        │                           ├───────────────────>│
    │                        │                           │  [list of videos]  │
    │                        │                           │<───────────────────┤
    │                        │                           │  save_links()      │
    │                        │                           ├─> metadata.json    │
    │  SSE: "Scan OK"        │  emit_log()               │                    │
    │<───────────────────────┤<──────────────────────────┤                    │
```

### 2. Téléchargement avec logs en temps réel

```
Utilisateur        Flask          Background Thread      yt-dlp/gallery-dl    Telegram
    │                │                    │                      │                │
    │ /stream_logs   │                    │                      │                │
    ├───────────────>│ SSE Connection     │                      │                │
    │<···············│ (keep-alive)       │                      │                │
    │                │                    │                      │                │
    │ POST /api/     │                    │                      │                │
    │ download       │                    │                      │                │
    ├───────────────>│ Thread.start()     │                      │                │
    │                ├───────────────────>│                      │                │
    │                │                    │ download_video()     │                │
    │                │                    ├─────────────────────>│                │
    │                │                    │      video.mp4       │                │
    │                │                    │<─────────────────────┤                │
    │                │  emit_log()        │                      │                │
    │                │<───────────────────┤                      │                │
    │ SSE: "[1/10]   │                    │                      │                │
    │ Video OK"      │                    │                      │                │
    │<···············│                    │                      │                │
    │                │                    │ send_telegram_video()                 │
    │                │                    ├──────────────────────────────────────>│
    │                │  emit_log()        │                      │                │
    │                │<───────────────────┤                      │                │
    │ SSE: "Envoyée" │                    │                      │                │
    │<···············│                    │                      │                │
    │                │                    │ save_to_history()    │                │
    │                │                    ├─> metadata.json      │                │
```

## Fonctionnalités principales

### Dashboard (/)
- Liste tous les profils
- Statistiques : nombre de vidéos, dernier scan
- Actions : Scan, Download, Delete

### Profil détaillé (/profile/<username>)
- Liste toutes les vidéos téléchargées
- Lecteur vidéo intégré
- Métadonnées : taille, date
- Actions : Supprimer vidéo

### API REST

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/extract` | POST | Lance un scan de profil |
| `/api/download` | POST | Lance le téléchargement |
| `/api/profiles` | GET | Liste tous les profils |
| `/api/stats` | GET | Statistiques globales |
| `/api/video/<id>/delete` | DELETE | Supprime une vidéo |
| `/api/profile/<user>/delete` | DELETE | Supprime un profil |
| `/api/telegram/topics` | GET/POST/DELETE | Gestion topics Telegram |

### Logs en temps réel (SSE)

```javascript
// Côté client
const eventSource = new EventSource('/stream_logs');
eventSource.onmessage = (event) => {
    const log = JSON.parse(event.data);
    console.log(log.message); // [HH:MM:SS] [LEVEL] [MODULE] Message
};
```

### Intégration Telegram

- **Auto-création de topics** : Un topic par utilisateur TikTok
- **Envoi automatique** : Chaque vidéo téléchargée envoyée sur Telegram
- **Mapping persistant** : `telegram_topics.json` stocke les IDs

## Technologies utilisées

- **Flask** : Framework web Python
- **SSE** : Server-Sent Events pour logs temps réel
- **Threading** : Tâches asynchrones en arrière-plan
- **Queue** : Communication thread-safe pour logs
- **yt-dlp** : Extraction et téléchargement vidéos
- **gallery-dl** : Téléchargement slideshows
- **Telegram Bot API** : Envoi automatique des vidéos

## Performance

- **Logs temps réel** : 0 latence grâce au SSE
- **Téléchargements parallèles** : Threading
- **Cache slideshow** : 99% appels API évités
- **Métadonnées O(1)** : Lookups instantanés
