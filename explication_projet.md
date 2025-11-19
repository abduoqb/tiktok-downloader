# Comment j'ai réalisé le Scraper de Liens TikTok

Ce document explique la démarche et les choix techniques pour créer le script d'extraction de liens vidéos.

## 1. Le Choix de l'Outil : `yt-dlp`

Au lieu d'écrire un "scraper" manuel (qui simule un navigateur web) avec des outils comme Selenium ou BeautifulSoup, j'ai choisi d'utiliser **`yt-dlp`**.

### Pourquoi ?
*   **Robustesse** : TikTok change souvent son code pour empêcher le scraping. `yt-dlp` est une communauté active qui met à jour l'outil constamment pour contourner ces protections.
*   **Simplicité** : Il gère déjà les cookies, les signatures chiffrées et la pagination (charger plus de vidéos).
*   **Performance** : C'est beaucoup plus rapide que d'ouvrir un navigateur web simulé.

## 2. La Technique d'Extraction "À Plat" (Flat Extraction)

Le défi principal était de récupérer **seulement les liens** sans télécharger les vidéos (ce qui prendrait des heures et beaucoup d'espace disque).

Pour cela, j'ai utilisé une option spécifique de `yt-dlp` dans le code :

```python
ydl_opts = {
    'extract_flat': True,  # <--- Le point clé
    'quiet': True,
    'ignoreerrors': True,
}
```

*   **`extract_flat: True`** : Cela dit à `yt-dlp` de ne pas analyser chaque vidéo en profondeur. Il regarde juste la page de profil et note les métadonnées (titre, ID, URL) de tout ce qu'il trouve. C'est ce qui rend le script si rapide (quelques secondes pour 300+ vidéos).

## 3. Structure du Script (`main.py`)

Le script est divisé en trois parties logiques :

### A. Récupération des Arguments
J'utilise le module `argparse`. Cela permet d'appeler le script proprement depuis le terminal :
`python main.py pseudo`
Le script sait ainsi que "pseudo" est la variable `username`.

### B. L'Extraction
La fonction `get_video_links` configure `yt-dlp` avec nos options.
Elle appelle `ydl.extract_info(url, download=False)`.
*   Si c'est un profil, `yt-dlp` renvoie un dictionnaire contenant une liste `entries`.
*   Le script parcourt cette liste et extrait le champ `url` ou `webpage_url` pour chaque vidéo.

### C. Sauvegarde
La fonction `save_links_to_file` prend simplement la liste des liens et l'écrit ligne par ligne dans un fichier texte standard.

## Résumé
En résumé, la "magie" ne vient pas d'un algorithme complexe que j'ai écrit, mais de l'utilisation intelligente d'une librairie existante (`yt-dlp`) configurée spécifiquement pour ne faire que de l'extraction de métadonnées (`extract_flat`). C'est souvent la meilleure approche en programmation : ne pas réinventer la roue !
