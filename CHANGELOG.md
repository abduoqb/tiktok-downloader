# Changelog

Tous les changements notables de ce projet seront documentés dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [1.2.0] - 2025-01-22

### Ajouté
- **Statistiques au début du téléchargement** : Tableau récapitulatif affiché avant de commencer
  - Informations sur le profil (plateforme, nombre de vidéos, etc.)
  - Configuration (mode, délais, Telegram)
  - Prévisions (temps estimé, taille estimée)
- **Barre de progression simple** : Affichée toutes les minutes et à la fin
  - Format compact sur une seule ligne
  - Progression visuelle avec barre ASCII `[####····]`
  - Temps écoulé, temps restant, taille, envois Telegram
  - Moins imposante et mieux alignée
- **Résumé final détaillé** : Statistiques complètes en fin de session
  - Taux de succès, durée totale, taille totale
  - Vitesse moyenne de téléchargement
  - Informations Telegram et stockage

### Modifié
- **Format des logs** : Nouveau format sobre `[HH:MM:SS] [NIVEAU] [MODULE] Message`
  - Niveaux : INFO, OK, WARN, ERROR
  - Modules : SCAN, DOWNLOAD, TELEGRAM, PROGRESS, STATS, SUMMARY, SYSTEM
- **Filtrage des slideshows** : Détectés et filtrés **avant** le comptage
  - Ne sont plus affichés dans les logs (traitement silencieux)
  - Mentionnés uniquement dans les statistiques initiales
- **Messages Telegram** : Réduction de la verbosité
  - Suppression des logs de réutilisation de topic
  - Message de succès géré par la fonction appelante

### Amélioré
- Cohérence visuelle dans tous les messages
- Lisibilité avec séparateurs et indentation
- Calcul automatique du temps restant et vitesse moyenne

## [1.1.0] - 2025-01-22

### Ajouté
- Bouton "Télécharger" vert dans l'interface web pour télécharger directement (sans passer par l'extraction)
- API de gestion manuelle des topics Telegram (`/api/telegram/topics`)
  - `GET /api/telegram/topics` - Lister les topics mappés
  - `POST /api/telegram/topics` - Ajouter un mapping manuellement
  - `DELETE /api/telegram/topics/<name>` - Supprimer un mapping
- Documentation complète du déploiement VPS (`DEPLOYMENT.md`)
- Documentation de gestion des topics Telegram (`TELEGRAM_TOPICS.md`)
- Script d'installation automatique pour VPS (`deploy.sh`)
- Support Docker avec `Dockerfile` et `docker-compose.yml`
- Fichier de configuration exemple pour systemd (`tiktok-scraper.service`)
- Fichier de configuration exemple pour Nginx (`nginx.conf`)
- Guide de contribution dans le README
- Section "Technologies" dans le README
- Section "Améliorations futures" dans le README

### Corrigé
- 🐛 **Bug critique** : Les topics Telegram en doublon lors de téléchargements parallèles
  - Ajout d'un verrou (threading.Lock) pour protéger les accès au fichier `telegram_topics.json`
  - Le fichier est rechargé à chaque vérification pour éviter les race conditions
  - Meilleurs messages de log pour tracer la création/réutilisation des topics

### Amélioré
- Logs plus clairs avec émojis (✅, ❌, ⚠️)
- Formatage du fichier `telegram_topics.json` avec indentation (indent=2)
- Gestion d'erreurs plus robuste lors de la lecture/écriture de `telegram_topics.json`
- Documentation README plus complète avec Quick Start et table des matières
- Ajout de `gunicorn` dans les requirements pour la production

## [1.0.0] - 2025-01-20

### Ajouté
- Interface web Flask avec dashboard moderne
- Extraction de liens vidéos (mode extract_flat)
- Téléchargement de vidéos avec retry automatique
- Détection intelligente des slideshows TikTok
- Intégration Telegram avec création automatique de topics
- Mode incrémental (arrêt après 10 vidéos consécutives déjà connues)
- Support TikTok et YouTube Shorts
- Gestion d'historique JSON
- Logs en temps réel via Server-Sent Events (SSE)
- API REST complète
- Lecteur vidéo intégré dans l'interface
- Page détails profil avec statistiques
- Synchronisation des profils (bouton Sync)
- Suppression de profils via l'interface
- Configuration Telegram via `config.json`
- Anti-bannissement avec délais aléatoires configurables

### Connu
- ⚠️ Risque de doublons de topics Telegram lors de téléchargements parallèles (corrigé en v1.1)

---

## Types de changements

- `Ajouté` pour les nouvelles fonctionnalités.
- `Modifié` pour les changements aux fonctionnalités existantes.
- `Obsolète` pour les fonctionnalités qui seront bientôt supprimées.
- `Supprimé` pour les fonctionnalités supprimées.
- `Corrigé` pour les corrections de bugs.
- `Sécurité` pour les corrections de vulnérabilités.
