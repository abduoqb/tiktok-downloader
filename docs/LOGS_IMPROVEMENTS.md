# Améliorations des logs du terminal - v1.2

## Vue d'ensemble

Refonte complète du système de logs pour un affichage sobre, structuré et informatif.

## Changements principaux

### 1. Nouveau format de logs

**Avant :**
```
Démarrage du scan pour charolife...
Found 8 new videos. Saving list...
Downloading video 1...
Downloaded: https://www.tiktok.com/...
```

**Après :**
```
[14:23:15] [INFO] [SCAN] Analyse du profil @charolife...
[14:23:18] [OK] [SCAN] Analyse terminée
[14:23:19] [OK] [DOWNLOAD] [1/8] 20250120_charolife_7574516.mp4 (2.8s)
[14:23:21] [OK] [TELEGRAM] Envoyée
```

**Format** : `[HH:MM:SS] [NIVEAU] [MODULE] Message`

**Niveaux** :
- `INFO` - Information générale
- `OK` - Opération réussie (ancien "success")
- `WARN` - Avertissement
- `ERROR` - Erreur

**Modules** :
- `SCAN` - Analyse de profil
- `DOWNLOAD` - Téléchargement
- `TELEGRAM` - Envoi Telegram
- `PROGRESS` - Barre de progression
- `STATS` - Statistiques
- `SUMMARY` - Résumé
- `SYSTEM` - Système (pauses, arrêts)

### 2. Statistiques au début du téléchargement

Affiche un tableau récapitulatif AVANT de commencer :

```
[14:23:18] [OK] [SCAN] Analyse terminée
[14:23:18] [INFO] [SCAN]

[14:23:18] [INFO] [STATS] ════════════════════════════════════════════════════════════════════
[14:23:18] [INFO] [STATS] STATISTIQUES DE TÉLÉCHARGEMENT - @charolife
[14:23:18] [INFO] [STATS] ════════════════════════════════════════════════════════════════════
[14:23:18] [INFO] [STATS]
[14:23:18] [INFO] [STATS] Profil:
[14:23:18] [INFO] [STATS]   Plateforme:                     TIKTOK
[14:23:18] [INFO] [STATS]   Vidéos sur le profil:           175
[14:23:18] [INFO] [STATS]   Déjà téléchargées:              167
[14:23:18] [INFO] [STATS]   Nouvelles détectées:            8
[14:23:18] [INFO] [STATS]   Slideshows (ignorés):           2
[14:23:18] [INFO] [STATS]
[14:23:18] [INFO] [STATS] Configuration:
[14:23:18] [INFO] [STATS]   Mode:                           Incrémental (seuil: 10 doublons)
[14:23:18] [INFO] [STATS]   Délais entre vidéos:            5-15 secondes
[14:23:18] [INFO] [STATS]   Tentatives par vidéo:           3
[14:23:18] [INFO] [STATS]   Telegram:                       Activé (topic: charolife)
[14:23:18] [INFO] [STATS]
[14:23:18] [INFO] [STATS] Prévisions:
[14:23:18] [INFO] [STATS]   Vidéos à télécharger:           8
[14:23:18] [INFO] [STATS]   Temps estimé:                   ~5-6 minutes
[14:23:18] [INFO] [STATS]   Taille estimée:                 ~32-48 MB
[14:23:18] [INFO] [STATS]
[14:23:18] [INFO] [STATS] ════════════════════════════════════════════════════════════════════
```

### 3. Barre de progression simple

Affichée **toutes les minutes** et à la fin :

```
[14:23:23] [OK] [DOWNLOAD] [1/8] 20250120_charolife_7574516.mp4 (2.8s)
[14:23:25] [OK] [TELEGRAM] Envoyée
[14:23:25] [INFO] [SYSTEM] Pause: 12 secondes
[14:23:37] [OK] [DOWNLOAD] [2/8] 20250121_charolife_7575823.mp4 (3.2s)
[14:23:39] [OK] [TELEGRAM] Envoyée
...
[14:24:25] [INFO] [PROGRESS] [##··················] 5/8 (62%) | 1m07s | ~0m45s | 12.3 MB | 5 envoyées
...
[14:28:45] [INFO] [PROGRESS] [####################] 8/8 (100%) | 5m27s | Terminé | 45.2 MB | 8 envoyées
```

**Format compact sur une ligne** :
- Barre visuelle `[####····]`
- Compteur `X/Y (Z%)`
- Temps écoulé
- Temps restant (ou "Terminé")
- Taille totale
- Nombre envoyé sur Telegram

**Fréquence** : Toutes les 60 secondes + à la fin du téléchargement

### 4. Filtrage des slideshows

**Changement important** : Les slideshows sont filtrés **AVANT** le comptage.

**Avant** :
```
Processing (3/10): https://...
Slideshow detected - saving to JSON (skip download)
Processing (4/10): https://...
```

**Après** :
```
# Les slideshows ne sont JAMAIS affichés dans les logs
# Ils sont détectés et enregistrés silencieusement
# Le compteur reflète uniquement les vraies vidéos à télécharger

[14:23:40] [OK] [DOWNLOAD] [3/8] 20250122_charolife_7577234.mp4 (2.5s)
# <-- slideshow traité ici mais invisible
[14:23:55] [OK] [DOWNLOAD] [4/8] 20250123_charolife_7578901.mp4 (3.1s)
```

**Mention uniquement dans les stats initiales** :
```
  Slideshows (ignorés):           2
```

### 5. Résumé final détaillé

```
[14:28:45] [OK] [DOWNLOAD] Téléchargement terminé

[14:28:45] [INFO] [SUMMARY]
[14:28:45] [INFO] [SUMMARY] ════════════════════════════════════════════════════════════════════
[14:28:45] [INFO] [SUMMARY] RÉSUMÉ - @charolife
[14:28:45] [INFO] [SUMMARY] ════════════════════════════════════════════════════════════════════
[14:28:45] [INFO] [SUMMARY]
[14:28:45] [INFO] [SUMMARY] Téléchargement:
[14:28:45] [INFO] [SUMMARY]   Succès:                         8/8 (100%)
[14:28:45] [INFO] [SUMMARY]   Échecs:                         0
[14:28:45] [INFO] [SUMMARY]   Durée totale:                   5m 30s
[14:28:45] [INFO] [SUMMARY]   Taille totale:                  45.2 MB
[14:28:45] [INFO] [SUMMARY]   Vitesse moyenne:                8.2 MB/min
[14:28:45] [INFO] [SUMMARY]
[14:28:45] [INFO] [SUMMARY] Telegram:
[14:28:45] [INFO] [SUMMARY]   Envoyées:                       8/8
[14:28:45] [INFO] [SUMMARY]   Topic:                          charolife (ID: mappé)
[14:28:45] [INFO] [SUMMARY]
[14:28:45] [INFO] [SUMMARY] Stockage:
[14:28:45] [INFO] [SUMMARY]   Dossier:                        downloads/charolife/
[14:28:45] [INFO] [SUMMARY]   Espace utilisé (total):         234.7 MB
[14:28:45] [INFO] [SUMMARY]
[14:28:45] [INFO] [SUMMARY] ════════════════════════════════════════════════════════════════════
```

## Modifications techniques

### Fichiers modifiés

- `web_app.py` : Refonte complète du système de logs

### Fonctions ajoutées

1. **`emit_log(message, level, module)`**
   - Nouveau format avec module
   - Mapping automatique des niveaux

2. **`emit_stats_header(...)`**
   - Affiche les statistiques initiales
   - Calcule les prévisions de temps et taille

3. **`emit_progress_bar(current, total, elapsed, size, telegram_sent)`**
   - Tableau de progression
   - Calcul automatique du temps restant

### Fonctions modifiées

1. **`background_download_task()`**
   - Filtrage préalable des slideshows
   - Affichage des stats au début
   - Barre de progression après chaque vidéo
   - Résumé final structuré
   - Silence des logs intermédiaires

2. **`background_extract_task()`**
   - Nouveau format de logs
   - Silence des logs intermédiaires de main.py

3. **`get_or_create_topic()`**
   - Suppression du log de réutilisation de topic (trop verbeux)

4. **`send_telegram_video()`**
   - Suppression du log de succès (géré par la fonction appelante)

## Avantages

✅ **Clarté** : Format structuré facile à lire
✅ **Sobriété** : Pas d'émojis, pas de surcharge visuelle
✅ **Informativité** : Stats au début, progression en temps réel, résumé à la fin
✅ **Propreté** : Slideshows filtrés avant affichage
✅ **Cohérence** : Tous les messages suivent le même format

## Exemple de session complète

```
[14:23:15] [INFO] [SCAN] Analyse du profil @charolife...
[14:23:18] [OK] [SCAN] Analyse terminée
[14:23:18] [INFO] [SCAN]

[14:23:18] [INFO] [STATS] ════════════════════════════════════════════════════════════════════
[14:23:18] [INFO] [STATS] STATISTIQUES DE TÉLÉCHARGEMENT - @charolife
[14:23:18] [INFO] [STATS] ════════════════════════════════════════════════════════════════════
[14:23:18] [INFO] [STATS]
[14:23:18] [INFO] [STATS] Profil:
[14:23:18] [INFO] [STATS]   Plateforme:                     TIKTOK
[14:23:18] [INFO] [STATS]   Vidéos sur le profil:           175
[14:23:18] [INFO] [STATS]   Déjà téléchargées:              167
[14:23:18] [INFO] [STATS]   Nouvelles détectées:            8
[14:23:18] [INFO] [STATS]
[14:23:18] [INFO] [STATS] Configuration:
[14:23:18] [INFO] [STATS]   Mode:                           Incrémental (seuil: 10 doublons)
[14:23:18] [INFO] [STATS]   Délais entre vidéos:            5-15 secondes
[14:23:18] [INFO] [STATS]   Tentatives par vidéo:           3
[14:23:18] [INFO] [STATS]   Telegram:                       Activé (topic: charolife)
[14:23:18] [INFO] [STATS]
[14:23:18] [INFO] [STATS] Prévisions:
[14:23:18] [INFO] [STATS]   Vidéos à télécharger:           8
[14:23:18] [INFO] [STATS]   Temps estimé:                   ~5-6 minutes
[14:23:18] [INFO] [STATS]   Taille estimée:                 ~32-48 MB
[14:23:18] [INFO] [STATS]
[14:23:18] [INFO] [STATS] ════════════════════════════════════════════════════════════════════

[14:23:19] [INFO] [DOWNLOAD]
[14:23:19] [INFO] [DOWNLOAD] Démarrage du téléchargement
[14:23:19] [INFO] [DOWNLOAD]

[14:23:20] [INFO] [DOWNLOAD] [1/8] En cours...
[14:23:23] [OK] [DOWNLOAD] [1/8] 20250120_charolife_7574516.mp4 (2.8s)
[14:23:25] [OK] [TELEGRAM] Envoyée

[14:23:25] [INFO] [SYSTEM] Pause: 12 secondes
[14:23:37] [OK] [DOWNLOAD] [2/8] 20250121_charolife_7575823.mp4 (3.2s)
[14:23:39] [OK] [TELEGRAM] Envoyée
...

[14:24:25] [INFO] [PROGRESS] [##··················] 3/8 (37%) | 1m07s | ~1m51s | 7.8 MB | 3 envoyées

... (suite des téléchargements)

[14:25:30] [INFO] [PROGRESS] [##########··········] 6/8 (75%) | 2m12s | ~0m44s | 31.2 MB | 6 envoyées

... (suite des téléchargements)

[14:28:45] [INFO] [DOWNLOAD]
[14:28:45] [OK] [DOWNLOAD] Téléchargement terminé
[14:28:45] [INFO] [DOWNLOAD]

[14:28:45] [INFO] [PROGRESS] [####################] 8/8 (100%) | 5m27s | Terminé | 45.2 MB | 8 envoyées

[14:28:45] [INFO] [SUMMARY]
[14:28:45] [INFO] [SUMMARY] ════════════════════════════════════════════════════════════════════
[14:28:45] [INFO] [SUMMARY] RÉSUMÉ - @charolife
[14:28:45] [INFO] [SUMMARY] ════════════════════════════════════════════════════════════════════
[14:28:45] [INFO] [SUMMARY]
[14:28:45] [INFO] [SUMMARY] Téléchargement:
[14:28:45] [INFO] [SUMMARY]   Succès:                         8/8 (100%)
[14:28:45] [INFO] [SUMMARY]   Échecs:                         0
[14:28:45] [INFO] [SUMMARY]   Durée totale:                   5m 27s
[14:28:45] [INFO] [SUMMARY]   Taille totale:                  45.2 MB
[14:28:45] [INFO] [SUMMARY]   Vitesse moyenne:                8.3 MB/min
[14:28:45] [INFO] [SUMMARY]
[14:28:45] [INFO] [SUMMARY] Telegram:
[14:28:45] [INFO] [SUMMARY]   Envoyées:                       8/8
[14:28:45] [INFO] [SUMMARY]   Topic:                          charolife (ID: mappé)
[14:28:45] [INFO] [SUMMARY]
[14:28:45] [INFO] [SUMMARY] Stockage:
[14:28:45] [INFO] [SUMMARY]   Dossier:                        downloads/charolife/
[14:28:45] [INFO] [SUMMARY]   Espace utilisé (total):         234.7 MB
[14:28:45] [INFO] [SUMMARY]
[14:28:45] [INFO] [SUMMARY] ════════════════════════════════════════════════════════════════════
```

## Version

- **v1.2** - 2025-01-22 : Refonte complète du système de logs
