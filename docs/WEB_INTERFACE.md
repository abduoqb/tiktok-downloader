# Interface Web Flask - TikTok Scraper

Interface web moderne pour gérer vos profils TikTok/YouTube et télécharger des vidéos.

## Fonctionnalités

### Dashboard Principal
- **Ajouter des profils** : Formulaire pour extraire/télécharger des vidéos
- **Liste des profils** : Visualiser tous les profils suivis avec leurs stats
- **Statistiques globales** : Nombre de profils, vidéos totales, espace disque
- **Logs en temps réel** : Activité récente dans l'interface
- **Actions rapides** : Sync, suppression de profils

### Page Détails Profil
- **Statistiques détaillées** : Vidéos dans l'historique vs téléchargées
- **Liste des vidéos** : Toutes les vidéos téléchargées avec métadonnées
- **Synchronisation** : Télécharger les nouvelles vidéos
- **Vue liste/galerie** : Deux modes d'affichage avec lecteur vidéo intégré
- **Lecteur Vidéo** : Lecture directe des vidéos téléchargées

## Installation

### 1. Installer les dépendances

```bash
pip install -r requirements.txt
```

Cela installera :
- `yt-dlp` (scraper vidéo)
- `flask` (serveur web)

### 2. Lancer le serveur

```bash
python web_app.py
```

Le serveur démarre sur **http://localhost:5000**

### 3. Ouvrir dans le navigateur

```
http://localhost:5000
```

## Utilisation

### Ajouter un profil

1. Entrez le username (avec ou sans @)
2. Sélectionnez la plateforme (TikTok ou YouTube)
3. (Optionnel) Définissez une limite de vidéos
4. Cliquez sur **Extraire** pour récupérer les liens
5. Ou cliquez sur **Télécharger** pour extraire ET télécharger

### Gérer les profils

Sur la page d'accueil, pour chaque profil :
- **Détails** : Voir la liste des vidéos téléchargées
- **Sync** : Télécharger les nouvelles vidéos
- **Supprimer** : Supprimer le profil et ses données

### Voir les détails d'un profil

1. Cliquez sur **Détails** pour un profil
2. Vous verrez :
   - Statistiques (vidéos, espace disque)
   - Liste de toutes les vidéos téléchargées
   - Bouton de synchronisation
3. Vous pouvez :
   - Copier le chemin d'une vidéo
   - Synchroniser les nouvelles vidéos

## Architecture Technique

### Backend (Flask)

**Fichier principal :** `web_app.py`

**Routes disponibles :**

| Route | Méthode | Description |
|-------|---------|-------------|
| `/` | GET | Page d'accueil (dashboard) |
| `/profile/<username>` | GET | Page détails d'un profil |
| `/api/profiles` | GET | Liste des profils (JSON) |
| `/api/extract` | POST | Extraire les liens vidéos |
| `/api/download` | POST | Télécharger les vidéos (background) |
| `/api/task/<task_id>` | GET | Statut d'une tâche background |
| `/api/profile/<username>/delete` | DELETE | Supprimer un profil |
| `/api/stats` | GET | Statistiques globales |

**Exemple d'appel API :**

```javascript
// Extraire les liens
fetch('/api/extract', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        username: 'antiheretique',
        platform: 'tiktok',
        limit: 50
    })
})
```

### Frontend (HTML + Tailwind + HTMX)

**Templates :**
- `templates/index.html` : Dashboard principal
- `templates/profile.html` : Page détails profil

**Technologies :**
- **Tailwind CSS** (via CDN) : Framework CSS moderne
- **HTMX** (via CDN) : Interactions AJAX sans JavaScript
- **Vanilla JavaScript** : Logique client (formulaires, API)

### Système de Tâches Background

Les téléchargements s'exécutent en arrière-plan via Python Threading :

```python
# Démarrer un téléchargement
POST /api/download
→ Retourne task_id

# Vérifier le statut
GET /api/task/<task_id>
→ { status: 'running', progress: 5, total: 10 }
```

## Structure des Fichiers

```
tiktok/
├── web_app.py                    # Serveur Flask
├── main.py                       # Logique scraping (réutilisée)
├── requirements.txt              # Dépendances
├── templates/
│   ├── base.html                 # Template de base (héritage)
│   ├── index.html                # Dashboard
│   └── profile.html              # Détails profil
├── static/                       # Assets statiques (vide pour l'instant)
└── downloads/                    # Données des profils
    └── <username>/
        ├── download_history.json
        ├── <username>_videos.txt
        └── *.mp4
```

## Configuration

### Changer le port

```python
# Dans web_app.py, ligne 264
app.run(debug=True, port=5000)  # Changez 5000
```

### Mode Production

Pour déployer en production, utilisez un serveur WSGI comme Gunicorn :

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 web_app:app
```

## API REST Complète

### Extraction de liens

```bash
curl -X POST http://localhost:5000/api/extract \
  -H "Content-Type: application/json" \
  -d '{"username": "antiheretique", "platform": "tiktok", "limit": 10}'
```

**Réponse :**
```json
{
  "success": true,
  "count": 10,
  "message": "10 new videos found"
}
```

### Téléchargement

```bash
curl -X POST http://localhost:5000/api/download \
  -H "Content-Type: application/json" \
  -d '{
    "username": "antiheretique",
    "platform": "tiktok",
    "min_sleep": 5,
    "max_sleep": 15
  }'
```

**Réponse :**
```json
{
  "success": true,
  "task_id": "antiheretique_1737408000.123",
  "message": "Download started"
}
```

### Statistiques

```bash
curl http://localhost:5000/api/stats
```

**Réponse :**
```json
{
  "total_profiles": 3,
  "total_videos": 1234,
  "total_size": 48561234567,
  "total_size_gb": 45.23
}
```

## Améliorations Futures

### Court terme
- [x] Vue galerie pour les vidéos (thumbnails)
- [x] Lecteur vidéo intégré dans l'interface
- [x] Logs en temps réel (SSE)
- [ ] Barre de progression en temps réel pour les téléchargements
- [ ] Filtres et recherche dans la liste des vidéos
- [ ] Dark mode

### Moyen terme
- [ ] Planification de tâches (cron jobs)
- [ ] Notifications (emails, webhooks)
- [ ] Export des données (CSV, JSON)
- [ ] Graphiques de statistiques (Chart.js)
- [ ] Gestion multi-utilisateurs (authentification)

### Long terme
- [ ] Migration SQLite pour meilleures performances
- [ ] API REST avec authentification (JWT)
- [ ] Application mobile (React Native)
- [ ] Support de plus de plateformes (Instagram, Twitter)

## Dépannage

### Erreur "Module not found: flask"

```bash
pip install flask
```

### Le serveur ne démarre pas

Vérifiez que le port 5000 n'est pas déjà utilisé :

```bash
# Windows
netstat -ano | findstr :5000

# Linux/Mac
lsof -i :5000
```

### Les téléchargements ne fonctionnent pas

Vérifiez que `main.py` est bien dans le même dossier et que `yt-dlp` est installé :

```bash
yt-dlp --version
```

## Contribution

Cette interface web est construite sur la branche `feature/web-interface`. Pour contribuer :

1. Vérifiez la branche actuelle : `git branch`
2. Faites vos modifications
3. Testez localement : `python web_app.py`
4. Committez : `git commit -m "Description"`

## Licence

Même licence que le projet principal (usage personnel/éducatif).
