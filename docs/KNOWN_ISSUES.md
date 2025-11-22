# 🐛 Problèmes Connus

Liste des bugs identifiés et leurs solutions de contournement.

---

## 🔴 Critique

### Bug #1: Limite de téléchargement ignorée dans l'interface web
**Date**: 2025-11-22
**Status**: 🔴 Non résolu
**Priorité**: Haute

**Symptôme**:
- L'utilisateur spécifie une limite (ex: 10 vidéos) dans l'interface web
- Le système télécharge **toutes** les vidéos au lieu de s'arrêter à la limite

**Cause**:
3 failles dans `web_app.py`:
1. Route `/api/download` ne récupère pas le paramètre `limit` (ligne ~413)
2. `limit` n'est pas passé au thread (ligne 432)
3. `background_download_task()` hardcode `limit=None` (ligne 822)

**Workaround**:
Utiliser la ligne de commande avec le flag `--limit`:
```bash
python main.py username --download --limit 10
```

**Plan de résolution**:
1. Ajouter `limit = data.get('limit')` dans `/api/download`
2. Convertir `limit` en int ou None
3. Passer `limit` dans les args du thread
4. Ajouter paramètre `limit=None` à `background_download_task()`
5. Utiliser `limit=limit` dans `get_video_links()`

**Fichiers concernés**:
- `web_app.py:405-444` (route API)
- `web_app.py:787-832` (background task)

---

## 🟡 Mineur

### Encodage Windows avec caractères spéciaux
**Date**: 2025-11-22
**Status**: ✅ Résolu (v1.4.0)

**Symptôme**:
Crash avec `UnicodeEncodeError: 'charmap' codec can't encode`

**Solution appliquée**:
- Reconfiguration UTF-8 automatique au démarrage
- Gestion des erreurs dans `emit_log()`
- Remplacement des caractères Unicode problématiques

---

### Rectangle rouge fantôme après clic bouton
**Date**: 2025-11-22
**Status**: ✅ Résolu (v1.4.0)

**Symptôme**:
Notification d'erreur rouge s'affiche même quand il n'y a pas d'erreur

**Cause**:
- Vérification incorrecte du statut de réponse
- `data.error` était `undefined` mais affiché quand même

**Solution appliquée**:
- Vérification de `response.ok` avant affichage
- Protection contre messages vides/undefined
- Meilleure gestion des cas d'erreur API

---

### Slideshows téléchargés dans le mauvais dossier
**Date**: 2025-11-22
**Status**: ✅ Résolu (v1.4.0)

**Symptôme**:
- `gallery-dl` télécharge dans `gallery-dl/tiktok/username/`
- Le système ne trouve pas les images
- Message "No images found after gallery-dl download"

**Solution appliquée**:
Configuration corrigée dans `main.py`:
```python
"base-directory": temp_dir  # Au niveau racine, pas dans extractor
```

---

## 📋 Améliorations futures

### Performance: Intégrer pipeline dans web_app.py
**Priorité**: Moyenne

Actuellement, l'interface web utilise l'ancien système séquentiel.
Le pipeline ultra-rapide (`pipeline_downloader.py`) n'est accessible que via CLI.

**Impact**: 5-10x amélioration de performance pour les utilisateurs web

---

### UX: Barre de progression en temps réel
**Priorité**: Basse

Actuellement, les logs SSE montrent la progression mais pas de barre visuelle.

**Suggestion**: Ajouter une barre de progression comme dans `emit_progress_bar()`

---

## 🔧 Signaler un bug

Si vous rencontrez un nouveau problème:

1. Vérifier qu'il n'est pas déjà listé ci-dessus
2. Tester avec la dernière version
3. Consulter [GUIDE_TEST.md](GUIDE_TEST.md) pour vérifier le système
4. Noter:
   - Symptôme précis
   - Étapes pour reproduire
   - Messages d'erreur complets
   - Version Python et OS

---

**Dernière mise à jour**: 2025-11-22
**Version**: 1.4.0
