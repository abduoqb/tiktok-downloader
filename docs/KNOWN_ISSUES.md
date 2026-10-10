# 🐛 Problèmes Connus

Liste des bugs identifiés et leurs solutions de contournement.

---

## 🔴 Critique

Aucun bug critique connu.

---

## 🟡 Mineur

### Cookies expirés et vidéos « indisponibles »
Il n'y a pas de disjoncteur : si les cookies sont expirés, des vidéos valides peuvent échouer trois fois de suite et passer « indisponibles » (retentées après 10 min, 1 h puis 6 h). Une fois les cookies renouvelés, cochez « Tout rescanner » pour les retenter.

### Doublons de fichiers sur le disque
D'anciens téléchargements peuvent avoir laissé plusieurs fichiers pour la même vidéo. `disk_index` sait les détecter, mais ils ne sont pas encore nettoyés automatiquement.

### Script d'export de liens non vérifié sur le vrai DOM TikTok
`static/js/export_links.js` (import de liste de liens) n'a été testé que sur une page simulée : le vrai DOM n'a pas pu être consulté (captcha sans session). Il ne s'appuie que sur les ancres `href` `/video/` et `/photo/` du profil ouvert. Si l'export est incomplet, relancez-le (doublons et vidéos déjà téléchargées ignorés) ou ouvrez une issue avec le comportement observé. Les liens courts `vm.tiktok.com` ne sont pas pris en charge.

### Mode incrémental après un téléchargement partiel (corrigé en 1.8.0)

Avant la 1.8.0, l'arrêt après 10 vidéos connues empêchait d'atteindre les anciennes
vidéos après un téléchargement partiel (limite, arrêt, échec). Corrigé : un profil sans
`scan_state.json` est entièrement scanné une première fois ; le mode rapide ne s'active
qu'ensuite. À noter : les types inconnus (non historisés) empêchent le marquage « scanné »,
et « Tout rescanner » / `--force-update` force un nouveau passage complet.

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

### Qualité 540p (H.264 natif)
Depuis la v1.7.0, le téléchargement privilégie le H.264 natif de TikTok, limité à 540p,
plutôt que le HEVC 720p+ (qui exigeait un ré-encodage). Si une résolution supérieure
est souhaitée, il faut changer le sélecteur dans `ytdlp_options.py` et accepter la conversion.

### Conversion des anciens téléchargements HEVC en H.264
**Priorité**: Moyenne (tâche reportée)

Environ 1 490 vidéos téléchargées avant la garantie H.264 sont en HEVC (H.265) et
s'affichent en noir (son seul) dans le navigateur. Profils les plus touchés :
`ferdaus_bbzk` (350), `ss0hane` (299), `okmanny___` (167), `bebeta.n` (131),
`chayy.922` (114), `nabila_akk` (114), `toomochelucile` (111).

**Suggestion**: script `scripts/reencode_hevc.py` réutilisant `main.ensure_h264`,
avec `--dry-run`, `--user` (commencer par `bebeta.n` pour valider), reprise
possible (fichiers déjà convertis sautés). Compter plusieurs heures de calcul.

### UX: Barre de progression en temps réel
**Priorité**: Basse

Actuellement, les logs SSE montrent la progression mais pas de barre visuelle.

**Suggestion**: Ajouter une barre de progression comme dans `emit_progress_bar()`

---

### ✅ Télécharger au fil du listing (flux continu) plutôt qu'en deux temps
**Statut**: RÉALISÉ (v1.9.0)
**Décision**: flux continu retenu (pas de lots de 10).

Aujourd'hui l'appli liste tout le profil puis télécharge. Sur un gros profil :
longue attente avant le premier téléchargement, listing gallery-dl coupé par le
délai de 300 s, rien de téléchargé si on interrompt pendant le listing.

**Suggestion**: lire la sortie de `gallery-dl -g` ligne par ligne (`Popen`) et
traiter chaque vidéo dès qu'elle arrive, plutôt que des lots `--range 1-10`,
`11-20` qui reparcourent le profil à chaque fois (et `--range` compte des
fichiers, pas des posts). L'arrêt incrémental (10 vidéos connues) et `limit`
fonctionnent naturellement en flux (l'arrêt incrémental n'est actif qu'après un premier
scan complet réussi, voir `scan_state.json`).

**Réalisé**: `orchestrator.run_download` (workers=1, web et CLI) traite chaque élément dès qu'il est listé ; le plafond total gallery-dl ne compte plus le temps du consommateur ; une erreur de listing en cours de route conserve ce qui est téléchargé. Le mode `workers>1` garde le fonctionnement par lots (listing complet puis pool), sans file producteur/consommateur.

**Était à prévoir**: plus de total connu à l'avance (progression « i traitées » au
lieu de « i/n »), arrêt propre si le listing échoue en cours de route, et
adapter le mode `workers>1` (file d'attente producteur/consommateur).

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
