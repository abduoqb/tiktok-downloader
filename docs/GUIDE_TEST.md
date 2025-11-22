# Guide de Test - Système de Métadonnées Optimisé

## Plan de Test Complet

Suivez ces étapes dans l'ordre pour valider le nouveau système.

---

## ✅ ÉTAPE 1 : Tests automatiques (2 min)

### 1.1 Tests unitaires
```bash
python tests/test_metadata_system.py
```

**Résultat attendu:**
```
============================================================
✅ TOUS LES TESTS RÉUSSIS!
============================================================
```

✅ Si tous les tests passent → Continuer
❌ Si un test échoue → M'alerter immédiatement

---

## ✅ ÉTAPE 2 : Sauvegarde de sécurité (1 min)

Avant de tester avec de vraies données, faites une sauvegarde:

```bash
# Sauvegarder le dossier downloads complet
cp -r downloads downloads_backup

# Ou sur Windows (PowerShell)
Copy-Item -Path downloads -Destination downloads_backup -Recurse
```

💡 Ainsi, en cas de problème, vous pourrez restaurer vos données.

---

## ✅ ÉTAPE 3 : Test de migration (5 min)

### 3.1 Vérifier vos données actuelles

Allez dans un dossier utilisateur existant:
```bash
ls downloads/<votre_username>/
```

**Vous devriez voir:**
```
download_history.json     ← Ancien système
slideshows.json          ← Ancien système (peut-être)
<username>_videos.txt    ← Ancien système (peut-être)
<files>.mp4              ← Vos vidéos
```

### 3.2 Tester la migration automatique

Lancez un simple scan (sans téléchargement):
```bash
python main.py <votre_username>
```

**Ce qui va se passer:**
```
Migrating <username> to new metadata system...
Migrated X entries from download_history.json
Migrated Y slideshows from slideshows.json
Migration complete: Z total entries migrated
```

### 3.3 Vérifier le nouveau fichier

```bash
ls downloads/<votre_username>/
```

**Vous devriez maintenant voir:**
```
metadata.json            ← ✅ NOUVEAU fichier
metadata.json.backup     ← ✅ Backup auto
download_history.json    ← Toujours là (conservé)
slideshows.json         ← Toujours là (conservé)
```

### 3.4 Inspecter metadata.json

Ouvrez le fichier et vérifiez le contenu:
```bash
cat downloads/<votre_username>/metadata.json
```

**Vous devriez voir vos vidéos avec métadonnées:**
```json
{
  "7123456789": {
    "url": "https://tiktok.com/@user/video/7123456789",
    "type": "video",
    "date": "2025-01-22T...",
    "size": 5242880,
    "file_count": 1,
    "success": true
  },
  ...
}
```

✅ Vérifications:
- [ ] Fichier metadata.json créé
- [ ] Nombre d'entrées correct (comparé à download_history.json)
- [ ] Anciens fichiers toujours présents
- [ ] Backup créé automatiquement

---

## ✅ ÉTAPE 4 : Test de téléchargement (10 min)

### 4.1 Test avec limite pour sécurité

Téléchargez seulement 2-3 nouvelles vidéos pour tester:
```bash
python main.py <username> --download --limit 3 --platform tiktok
```

**Observez la sortie:**
```
Checking (1/3): https://...
📸 Slideshow detected - downloading with gallery-dl (1 slideshows so far)
✅ Slideshow downloaded: 12 images saved to downloads/user/

Checking (2/3): https://...
🎥 Downloading video (1): https://...
✅ Video downloaded

📊 Download Summary:
   Videos: 1
   Slideshows: 1
   Total: 2
```

### 4.2 Vérifier les métadonnées enrichies

```bash
cat downloads/<username>/metadata.json | grep -A 8 "\"type\": \"slideshow\""
```

**Vous devriez voir:**
```json
{
  "id": "...",
  "url": "...",
  "type": "slideshow",
  "date": "2025-01-22T...",
  "size": 0,
  "file_count": 12,  ← ✅ Nombre d'images
  "success": true
}
```

✅ Vérifications:
- [ ] Vidéos téléchargées correctement
- [ ] Slideshows téléchargés correctement
- [ ] Format de nommage correct pour slideshows (date_pseudo_id_img=numero.jpg)
- [ ] Métadonnées enrichies présentes
- [ ] file_count correct pour slideshows

---

## ✅ ÉTAPE 5 : Test du cache (2 min)

### 5.1 Re-scanner le même profil

Lancez le scan 2 fois de suite:
```bash
# Premier scan
time python main.py <username>

# Deuxième scan (devrait être BEAUCOUP plus rapide)
time python main.py <username>
```

**Résultat attendu:**
- Premier scan : X secondes (appels API)
- Deuxième scan : ~Y secondes (cache, beaucoup plus rapide)

✅ Le deuxième scan devrait être **significativement plus rapide** grâce au cache.

---

## ✅ ÉTAPE 6 : Test Web App (5 min)

### 6.1 Lancer l'application web

```bash
python web_app.py
```

### 6.2 Ouvrir dans le navigateur

```
http://localhost:5001
```

### 6.3 Tester un téléchargement

1. Entrez un username
2. Cliquez sur "Démarrer"
3. Observez les logs en temps réel

**Dans les logs, vous devriez voir:**
```
[INFO] [SCAN] Analyse du profil @username...
[OK] [SCAN] Analyse terminée

[INFO] [STATS] STATISTIQUES DE TÉLÉCHARGEMENT
[INFO] [STATS]   Vidéos sur le profil: 150
[INFO] [STATS]   Slideshows détectés: 12  ← ✅ Nouveau

[OK] [DOWNLOAD] [1/10] Slideshow (8 images) (3.2s)  ← ✅ Nouveau
[OK] [DOWNLOAD] [2/10] 20250122_user_123.mp4 (2.1s)

[INFO] [SUMMARY] Téléchargement:
[INFO] [SUMMARY]   Succès: 10/10 (100%)
[INFO] [SUMMARY]     - Vidéos: 8        ← ✅ Breakdown
[INFO] [SUMMARY]     - Slideshows: 2    ← ✅ Breakdown
```

✅ Vérifications:
- [ ] Interface fonctionne
- [ ] Logs s'affichent correctement
- [ ] Statistiques montrent vidéos ET slideshows
- [ ] Téléchargements réussissent
- [ ] Résumé final affiche le breakdown

---

## ✅ ÉTAPE 7 : Test de performance (optionnel, 5 min)

### 7.1 Créer un profil avec beaucoup d'entrées

```python
# Script de test rapide
from metadata_manager import OptimizedMetadataManager
import time

manager = OptimizedMetadataManager("test_perf", "downloads/test_perf")

# Ajouter 10,000 entrées
for i in range(10000):
    manager.add(f"id_{i}", f"url_{i}", "video", file_size=1024*1024)

# Tester la vitesse de vérification
start = time.time()
for i in range(10000):
    manager.is_downloaded(f"id_{i}")
elapsed = time.time() - start

print(f"10,000 vérifications en {elapsed*1000:.1f}ms")
print(f"Moyenne: {elapsed/10000*1000000:.1f}µs par vérification")
```

**Résultat attendu:**
- < 10ms pour 10,000 vérifications
- ~1µs par vérification

---

## ✅ ÉTAPE 8 : Vérifications finales (2 min)

### 8.1 Vérifier l'intégrité des données

```bash
# Compter les entrées dans ancien vs nouveau système
old_count=$(cat downloads/<username>/download_history.json | grep -o "\"" | wc -l)
new_count=$(cat downloads/<username>/metadata.json | grep -o "\"url\"" | wc -l)

echo "Ancien: $old_count entrées"
echo "Nouveau: $new_count entrées"
```

Les nombres devraient être similaires (±2-3 pour les slideshows).

### 8.2 Vérifier les fichiers

```bash
# Compter les fichiers MP4
ls downloads/<username>/*.mp4 | wc -l

# Compter les images de slideshows
find downloads/<username> -name "*_img=*.jpg" | wc -l
```

✅ Vérifications:
- [ ] Nombre d'entrées cohérent
- [ ] Tous les fichiers présents
- [ ] Aucune perte de données

---

## 📊 Checklist Finale

Avant de confirmer le merge, vérifiez que:

### Fonctionnalités de base
- [ ] Migration automatique fonctionne
- [ ] metadata.json créé correctement
- [ ] Anciens fichiers conservés
- [ ] Backup automatique créé

### Téléchargements
- [ ] Vidéos se téléchargent
- [ ] Slideshows se téléchargent
- [ ] Format de nommage correct
- [ ] Comptage vidéos/slideshows séparé

### Métadonnées
- [ ] Type (video/slideshow) correct
- [ ] Date enregistrée
- [ ] Taille fichier enregistrée
- [ ] file_count correct pour slideshows

### Performance
- [ ] Deuxième scan plus rapide (cache)
- [ ] Pas de ralentissement visible
- [ ] Tests unitaires passent

### Web App
- [ ] Interface fonctionne
- [ ] Logs corrects
- [ ] Statistiques enrichies
- [ ] Breakdown vidéos/slideshows

---

## 🆘 En cas de problème

### Problème mineur (petits bugs)
→ Décrivez-moi le problème, je corrige et on re-teste

### Problème majeur (crash, perte de données)
→ Rollback immédiat:

```bash
# Revenir sur master
git checkout master

# Restaurer les données si nécessaire
rm -rf downloads
mv downloads_backup downloads
```

---

## ✅ Validation finale

Une fois TOUS les tests passés, confirmez-moi avec:

**"✅ Tests validés, prêt pour le merge"**

Je procéderai alors au merge automatique sur master.

---

## 💡 Temps estimé total

- Tests automatiques: 2 min
- Sauvegarde: 1 min
- Migration: 5 min
- Téléchargement: 10 min
- Web app: 5 min
- Vérifications: 5 min

**Total: ~30 minutes** pour une validation complète et sécurisée.
