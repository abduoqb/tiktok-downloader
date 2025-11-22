# Gestion des Topics Telegram

Guide pour éviter les doublons de topics et gérer le mapping des profils TikTok vers les topics Telegram.

## Comprendre le système

### Comment ça fonctionne

1. **Fichier de mapping** : `telegram_topics.json` stocke la correspondance `profil → topic_id`
2. **Création automatique** : Quand vous téléchargez des vidéos d'un nouveau profil, un topic Telegram est créé automatiquement
3. **Réutilisation** : Si le profil existe déjà dans le fichier, le topic existant est réutilisé

### Structure du fichier `telegram_topics.json`

```json
{
  "charolife": 15888,
  "bellapoarch": 15890,
  "charlidamelio": 15935
}
```

- **Clé** : Nom du profil TikTok
- **Valeur** : ID du topic Telegram (message_thread_id)

---

## Problème : Topics en doublon

### Causes possibles

1. **Fichier supprimé ou corrompu** : Si `telegram_topics.json` est supprimé, le système crée de nouveaux topics
2. **Topic créé manuellement** : Si vous créez un topic sur Telegram, le système ne le détecte pas automatiquement
3. **Race condition (ancien bug)** : Plusieurs threads créaient le même topic en même temps (corrigé depuis la v1.1)

### Solution 1 : Utiliser le fichier de mapping existant

Si vous avez déjà des topics sur Telegram mais le fichier `telegram_topics.json` est vide ou perdu :

#### Méthode A : Via l'API (Recommandé)

```bash
# Pour chaque profil, ajoutez manuellement le mapping
curl -X POST http://localhost:5000/api/telegram/topics \
  -H "Content-Type: application/json" \
  -d '{
    "topic_name": "charolife",
    "thread_id": 15888
  }'
```

#### Méthode B : Éditer le fichier directement

```bash
# Éditez telegram_topics.json
nano telegram_topics.json
```

Ajoutez vos mappings :
```json
{
  "profil1": 12345,
  "profil2": 67890
}
```

### Solution 2 : Trouver l'ID d'un topic existant

Pour récupérer l'ID d'un topic que vous avez créé manuellement sur Telegram :

#### Méthode 1 : Via le bot Telegram

1. Envoyez un message dans le topic que vous voulez récupérer
2. Faites forward ce message à [@userinfobot](https://t.me/userinfobot)
3. Le bot vous donnera le `message_thread_id`

#### Méthode 2 : Via l'API Telegram

```bash
# Récupérez les dernières mises à jour
curl "https://api.telegram.org/bot<VOTRE_BOT_TOKEN>/getUpdates"
```

Cherchez dans la réponse :
```json
{
  "message": {
    "message_thread_id": 15888,
    "forum_topic_created": {
      "name": "charolife"
    }
  }
}
```

#### Méthode 3 : Depuis l'interface web Telegram

1. Ouvrez Telegram sur navigateur (web.telegram.org)
2. Cliquez sur le topic
3. L'URL contient l'ID : `https://web.telegram.org/k/#-1002497069227_15888`
   - Le nombre après le `_` est le `message_thread_id` (ici : `15888`)

---

## API de gestion des topics

### Voir tous les topics mappés

```bash
GET /api/telegram/topics
```

**Exemple :**
```bash
curl http://localhost:5000/api/telegram/topics
```

**Réponse :**
```json
{
  "charolife": 15888,
  "bellapoarch": 15890
}
```

### Ajouter un topic manuellement

```bash
POST /api/telegram/topics
Content-Type: application/json

{
  "topic_name": "nouveau_profil",
  "thread_id": 16000
}
```

**Exemple :**
```bash
curl -X POST http://localhost:5000/api/telegram/topics \
  -H "Content-Type: application/json" \
  -d '{"topic_name": "nouveau_profil", "thread_id": 16000}'
```

### Supprimer un mapping

```bash
DELETE /api/telegram/topics/<topic_name>
```

**Exemple :**
```bash
curl -X DELETE http://localhost:5000/api/telegram/topics/ancien_profil
```

---

## Prévention des doublons

### Bonnes pratiques

1. **Ne supprimez jamais** `telegram_topics.json` manuellement
2. **Sauvegardez** régulièrement ce fichier :
   ```bash
   cp telegram_topics.json telegram_topics.json.bak
   ```
3. **Utilisez l'API** pour ajouter des topics existants avant de télécharger
4. **Vérifiez** les logs pour voir si un topic existe déjà :
   ```bash
   journalctl -u tiktok-scraper -f | grep "Topic Telegram"
   ```

### Si vous avez déjà des doublons

#### Option 1 : Supprimer les doublons sur Telegram

1. Allez dans votre groupe Telegram
2. Supprimez les topics en doublon (gardez le plus ancien)
3. Mettez à jour `telegram_topics.json` avec les bons IDs

#### Option 2 : Fusionner les topics

Malheureusement, Telegram ne permet pas de fusionner des topics. Vous devrez :
1. Choisir quel topic garder
2. Supprimer les autres
3. Mettre à jour le mapping

---

## Dépannage

### Le système crée toujours de nouveaux topics

**Vérifications :**

1. Le fichier `telegram_topics.json` existe-t-il ?
   ```bash
   cat telegram_topics.json
   ```

2. Le fichier est-il valide (JSON bien formé) ?
   ```bash
   python3 -m json.tool telegram_topics.json
   ```

3. Les permissions sont-elles correctes ?
   ```bash
   ls -la telegram_topics.json
   # Devrait appartenir à l'utilisateur tiktok
   ```

4. Le service a-t-il redémarré depuis la correction du bug ?
   ```bash
   sudo systemctl restart tiktok-scraper
   ```

### Le topic existe dans le fichier mais un nouveau est créé quand même

Cela ne devrait plus arriver depuis la v1.1 (système de verrous). Si ça persiste :

1. Vérifiez que vous utilisez la dernière version :
   ```bash
   cd /home/tiktok/tiktok-scraper
   git pull
   sudo systemctl restart tiktok-scraper
   ```

2. Vérifiez les logs :
   ```bash
   sudo journalctl -u tiktok-scraper -n 50 | grep "Topic Telegram"
   ```

### Erreur "Telegram API: Bad Request"

Le topic_id est probablement invalide. Vérifiez :
- Le topic existe toujours sur Telegram
- Le bot a toujours accès au groupe
- L'ID est correct (nombre entier)

---

## Sauvegarde et restauration

### Sauvegarder le mapping

```bash
# Sauvegarde manuelle
cp telegram_topics.json telegram_topics.json.$(date +%Y%m%d)

# Ou inclure dans votre script de backup
tar -czf backup_$(date +%Y%m%d).tar.gz \
  config.json \
  telegram_topics.json \
  downloads/
```

### Restaurer le mapping

```bash
# Restaurer depuis une sauvegarde
cp telegram_topics.json.20250122 telegram_topics.json

# Redémarrer le service
sudo systemctl restart tiktok-scraper
```

---

## Changelog

### v1.1 (2025-01-22)
- ✅ Ajout d'un système de verrous (threading.Lock) pour éviter les race conditions
- ✅ Amélioration des logs (émojis, messages plus clairs)
- ✅ API de gestion manuelle des topics (`/api/telegram/topics`)
- ✅ Rechargement du fichier à chaque vérification (thread-safe)

### v1.0 (2025-01-20)
- ⚠️ Version initiale avec risque de doublons en cas de téléchargements parallèles

---

## Support

Si vous rencontrez toujours des problèmes :
1. Vérifiez la section [Dépannage](#dépannage)
2. Consultez les logs : `sudo journalctl -u tiktok-scraper -f`
3. Ouvrez une issue sur GitHub avec les logs
