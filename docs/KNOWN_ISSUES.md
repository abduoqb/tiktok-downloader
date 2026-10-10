# 🐛 Problèmes Connus

Liste des bugs identifiés et leurs solutions de contournement.

---

## 🔴 Critique

Aucun bug critique connu.

---

## 🟡 Mineur

### Limite de téléchargement ignorée dans l'interface web
**Date**: 2025-11-22
**Status**: ✅ Résolu (v1.6.0)

**Symptôme**:
La limite saisie dans l'interface web était ignorée : toutes les vidéos étaient téléchargées.

**Solution appliquée**:
- La route `POST /api/download` lit `limit` (entier positif ou `null`, sinon réponse 400)
- `limit` est transmis à `background_download_task()` puis à `orchestrator.run_download()`

---

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

**Dernière mise à jour**: 2026-10-10
**Version**: 1.6.0
