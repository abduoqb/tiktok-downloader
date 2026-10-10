# 📚 Documentation TikTok Scraper

Bienvenue dans la documentation complète du projet TikTok Scraper.

## 📖 Table des matières

### 🏗️ Architecture
- **[ARCHITECTURE_WEB.md](ARCHITECTURE_WEB.md)** - Architecture complète de l'interface web avec diagrammes de flux
- **[METADATA_UPGRADE.md](METADATA_UPGRADE.md)** - Système de métadonnées optimisé (O(1) lookup, cache slideshow)

### ⚡ Performance
- **[PERFORMANCE_BOOST.md](PERFORMANCE_BOOST.md)** - Optimisations de performance (générateur streaming, orchestrateur unique)
  - Générateur streaming
  - Orchestrateur (`orchestrator.py`, workers optionnels)
  - Tags & Favoris
  - Export multi-format

### 🖥️ Interfaces
- **[WEB_INTERFACE.md](WEB_INTERFACE.md)** - Guide d'utilisation de l'interface web Flask

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

# Extraction + téléchargement (orchestrateur unique)
python main.py username --download --limit 10
```

### Interface Web
```bash
python web_app.py
# Ouvrir http://127.0.0.1:5001
```

---

## 📊 Statistiques du projet

- **Performance**: extraction en streaming, orchestrateur unique pour le CLI et le web
- **Métadonnées**: O(1) lookup, 99% d'appels API évités
- **Formats**: Support vidéos + slideshows
- **Export**: CSV, JSON, HTML

---

## 🔧 Problèmes connus

Voir [KNOWN_ISSUES.md](KNOWN_ISSUES.md). Le bug de la limite ignorée dans l'interface web est corrigé.

---

## 📞 Support

Pour toute question ou problème, consultez d'abord:
1. [GUIDE_TEST.md](GUIDE_TEST.md) - Tests et vérifications
2. [PERFORMANCE_BOOST.md](PERFORMANCE_BOOST.md) - Optimisations
3. [ARCHITECTURE_WEB.md](ARCHITECTURE_WEB.md) - Architecture détaillée
