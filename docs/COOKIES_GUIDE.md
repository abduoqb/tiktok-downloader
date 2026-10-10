# Guide : Télécharger des vidéos de comptes privés TikTok

## Méthode Automatique (Recommandée)

### Utilisation de base

```bash
python main.py nom_utilisateur --download --cookies-browser chrome
```

### Navigateurs supportés

- `chrome` - Google Chrome
- `firefox` - Mozilla Firefox
- `edge` - Microsoft Edge
- `safari` - Safari (macOS)
- `opera` - Opera
- `brave` - Brave Browser

### Exemples

**Télécharger toutes les vidéos d'un compte privé :**
```bash
python main.py compte_prive --download --cookies-browser chrome
```

**Télécharger avec limite de 50 vidéos :**
```bash
python main.py compte_prive --download --limit 50 --cookies-browser chrome
```

**Télécharger une seule vidéo :**
```bash
python main.py "https://www.tiktok.com/@compte_prive/video/123456789" --cookies-browser chrome
```

**Avec un fichier de cookies :**
```bash
python main.py compte_prive --download --cookies-file tiktok.com_cookies.txt
```

## Prérequis

1. ✅ Être **connecté à TikTok** dans votre navigateur
2. ✅ **Suivre le compte privé** dont vous voulez télécharger les vidéos
3. ✅ Fermer le navigateur avant de lancer le script (recommandé)

## Comment ça marche ?

Lorsque vous ajoutez `--cookies-browser chrome`, le script :

1. Extrait automatiquement vos cookies de session depuis Chrome
2. Utilise ces cookies pour s'authentifier auprès de TikTok
3. Accède aux vidéos privées comme si c'était vous qui naviguiez

**C'est 100% légal et sécurisé** : vous téléchargez uniquement les vidéos auxquelles vous avez accès légitimement.

## Dépannage

### Erreur : "Unable to extract cookies"

**Solutions :**
- Fermez complètement votre navigateur
- Vérifiez que vous êtes bien connecté à TikTok
- Essayez avec un autre navigateur (edge, firefox, etc.)

**Sous Windows :**
Si Chrome refuse de partager les cookies, essayez Edge :
```bash
python main.py compte_prive --download --cookies-browser edge
```

### Erreur : "This video is private"

**Solutions :**
- Vérifiez que vous suivez bien le compte dans votre navigateur
- Déconnectez-vous puis reconnectez-vous sur TikTok
- Videz le cache de votre navigateur et reconnectez-vous
- Attendez quelques minutes (TikTok peut avoir des limites de taux)

### Le script est lent

Le délai entre deux téléchargements est volontaire (anti-ban). Réduisez-le avec `--min-sleep` / `--max-sleep` (au risque d'un blocage de TikTok) :
```bash
python main.py compte_prive --download --min-sleep 2 --max-sleep 5 --cookies-browser chrome
```

## Méthode Alternative : Fichier cookies.txt

Si l'extraction automatique ne fonctionne pas, vous pouvez exporter manuellement vos cookies :

### Étape 1 : Installer l'extension

- **Chrome/Edge** : [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- **Firefox** : [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

### Étape 2 : Exporter les cookies

1. Allez sur https://www.tiktok.com (connecté)
2. Cliquez sur l'extension
3. Cliquez sur "Export" ou "Download"
4. Sauvegardez le fichier `cookies.txt` dans le dossier du projet

### Étape 3 : Utiliser les cookies

Modifiez le code pour utiliser le fichier au lieu du navigateur :

```python
# Dans main.py, ligne ~64
ydl_opts = {
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'cookiefile': 'cookies.txt'  # Ajoutez cette ligne
}
```

Puis lancez normalement :
```bash
python main.py compte_prive --download
```

## Sécurité et vie privée

- ⚠️ **Ne partagez jamais votre fichier cookies.txt** - il contient vos identifiants de session
- ✅ Les cookies restent sur votre machine
- ✅ Aucune donnée n'est envoyée à des tiers
- ✅ Le script utilise uniquement vos propres cookies pour accéder aux vidéos que vous pouvez déjà voir

## Support

Si vous rencontrez des problèmes :
1. Vérifiez que yt-dlp est à jour : `pip install --upgrade yt-dlp`
2. Testez avec un compte public d'abord
3. Essayez différents navigateurs
