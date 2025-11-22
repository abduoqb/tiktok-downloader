# 📚 Documentation TikTok Scraper

Bienvenue dans la documentation complète du projet TikTok Scraper.

## 📖 Table des matières

### 🏗️ Architecture
- **[ARCHITECTURE_WEB.md](ARCHITECTURE_WEB.md)** - Architecture complète de l'interface web avec diagrammes de flux
- **[METADATA_UPGRADE.md](METADATA_UPGRADE.md)** - Système de métadonnées optimisé (O(1) lookup, cache slideshow)

### ⚡ Performance
- **[PERFORMANCE_BOOST.md](PERFORMANCE_BOOST.md)** - Système de boost ultra-rapide (6-8x plus performant)
  - Générateur streaming
  - Pipeline parallèle
  - Tags & Favoris
  - Export multi-format

### 🖥️ Interfaces
- **[WEB_INTERFACE.md](WEB_INTERFACE.md)** - Guide d'utilisation de l'interface web Flask
- **[TELEGRAM_TOPICS.md](TELEGRAM_TOPICS.md)** - Configuration et utilisation de l'intégration Telegram

### 🧪 Tests & Déploiement
- **[GUIDE_TEST.md](GUIDE_TEST.md)** - Guide de test et validation des fonctionnalités
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Instructions de déploiement en production

### 📝 Historique
- **[CHANGELOG.md](CHANGELOG.md)** - Historique complet des modifications

---

## 🚀 Démarrage rapide

### Installation
```bash
pip install -r requirements.txt
```

### Utilisation CLI
```bash
# Téléchargement simple
python main.py username

# Avec pipeline ultra-rapide (5-10x plus rapide)
python pipeline_downloader.py username 3 10
```

### Interface Web
```bash
python web_app.py
# Ouvrir http://127.0.0.1:5001
```

---

## 📊 Statistiques du projet

- **Performance**: 6-8x plus rapide avec le système de pipeline
- **Métadonnées**: O(1) lookup, 99% d'appels API évités
- **Formats**: Support vidéos + slideshows
- **Export**: CSV, JSON, HTML
- **Intégrations**: Telegram avec topics automatiques

---

## 🔧 Problèmes connus

### Bug #1: Limite de téléchargement ne fonctionne pas
**Symptôme**: La limite spécifiée dans l'interface web est ignorée
**Cause**: Le paramètre `limit` n'est pas passé au thread de téléchargement
**Status**: En cours de résolution
**Fichier**: `web_app.py:405-822`

---

## 📞 Support

Pour toute question ou problème, consultez d'abord:
1. [GUIDE_TEST.md](GUIDE_TEST.md) - Tests et vérifications
2. [PERFORMANCE_BOOST.md](PERFORMANCE_BOOST.md) - Optimisations
3. [ARCHITECTURE_WEB.md](ARCHITECTURE_WEB.md) - Architecture détaillée
