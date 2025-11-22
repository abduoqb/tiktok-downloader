# Déploiement sur VPS - TikTok Scraper

Guide complet pour déployer le TikTok Scraper sur un serveur VPS (Ubuntu/Debian).

## Table des matières

- [Prérequis](#prérequis)
- [Installation rapide (Script automatique)](#installation-rapide-script-automatique)
- [Installation manuelle](#installation-manuelle)
- [Configuration](#configuration)
- [Gestion du service](#gestion-du-service)
- [Sécurité](#sécurité)
- [Maintenance](#maintenance)
- [Dépannage](#dépannage)

---

## Prérequis

### VPS recommandé
- **OS** : Ubuntu 22.04 LTS ou Debian 11+
- **RAM** : 2 GB minimum (4 GB recommandé)
- **CPU** : 2 vCPU minimum
- **Stockage** : 20 GB minimum (+ espace pour les vidéos)
- **Bande passante** : Illimitée ou généreuse

### Providers recommandés
- **Hetzner Cloud** : 4.5€/mois (CX21 - 2 vCPU, 4 GB RAM)
- **DigitalOcean** : 6$/mois (Basic Droplet - 2 vCPU, 2 GB RAM)
- **OVH** : 3.50€/mois (VPS Starter)
- **Contabo** : 6€/mois (VPS S)

---

## Installation rapide (Script automatique)

### 1. Connectez-vous à votre VPS

```bash
ssh root@votre-ip-vps
- ✅ Créer un utilisateur dédié `tiktok`
- ✅ Cloner le projet
- ✅ Installer les dépendances
- ✅ Configurer systemd
- ✅ Configurer nginx (optionnel)
- ✅ Activer le pare-feu

### 3. Configuration post-installation

```bash
# Éditez la configuration Telegram
sudo nano /home/tiktok/tiktok-scraper/config.json

# Redémarrez le service
sudo systemctl restart tiktok-scraper
```

Votre application sera accessible sur `http://votre-ip:5000` ou via votre domaine si vous avez configuré nginx.

---

## Installation manuelle

### Étape 1 : Mise à jour du système

```bash
# Se connecter en root
ssh root@votre-ip-vps

# Mettre à jour le système
apt update && apt upgrade -y

# Installer les dépendances système
apt install -y python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx ufw
```

### Étape 2 : Créer un utilisateur dédié

```bash
# Créer l'utilisateur tiktok
useradd -m -s /bin/bash tiktok

# Passer à cet utilisateur
su - tiktok
```

### Étape 3 : Cloner le projet

```bash
# Depuis l'utilisateur tiktok
cd /home/tiktok
git clone https://github.com/votre-username/tiktok-scraper.git
cd tiktok-scraper
```

### Étape 4 : Créer un environnement virtuel

```bash
# Créer l'environnement virtuel
python3 -m venv venv

# Activer l'environnement
source venv/bin/activate

# Installer les dépendances
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn  # Pour la production
```

### Étape 5 : Configuration

```bash
# Copier le fichier de config exemple
cp config.json.example config.json

# Éditer la configuration
nano config.json
```

Ajoutez vos tokens Telegram :
```json
{
    "TELEGRAM_BOT_TOKEN": "votre_token_ici",
    "TELEGRAM_CHAT_ID": "votre_chat_id_ici"
}
```

### Étape 6 : Tester l'application

```bash
# Lancer le serveur de test
python web_app.py
```

Ouvrez `http://votre-ip:5000` dans votre navigateur. Si ça fonctionne, passez à l'étape suivante.

**Arrêtez le serveur** avec `Ctrl+C` avant de continuer.

### Étape 7 : Créer le service systemd

Retournez en root :
```bash
exit  # Quitter l'utilisateur tiktok
```

Créez le fichier service :
```bash
nano /etc/systemd/system/tiktok-scraper.service
```

Copiez ce contenu :
```ini
[Unit]
Description=TikTok Scraper Web Application
After=network.target

[Service]
Type=simple
User=tiktok
Group=tiktok
WorkingDirectory=/home/tiktok/tiktok-scraper
Environment="PATH=/home/tiktok/tiktok-scraper/venv/bin"
ExecStart=/home/tiktok/tiktok-scraper/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 web_app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Activez et démarrez le service :
```bash
systemctl daemon-reload
systemctl enable tiktok-scraper
systemctl start tiktok-scraper
systemctl status tiktok-scraper
```

### Étape 8 : Configurer Nginx (Reverse Proxy)

#### Option A : Accès par IP uniquement

```bash
nano /etc/nginx/sites-available/tiktok-scraper
```

```nginx
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Support pour SSE (Server-Sent Events)
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
    }
}
```

#### Option B : Avec nom de domaine

```nginx
server {
    listen 80;
    server_name tiktok.votredomaine.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Support pour SSE
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
    }
}
```

Activez le site :
```bash
ln -s /etc/nginx/sites-available/tiktok-scraper /etc/nginx/sites-enabled/
nginx -t  # Tester la configuration
systemctl reload nginx
```

### Étape 9 : SSL avec Let's Encrypt (si domaine)

```bash
certbot --nginx -d tiktok.votredomaine.com
```

### Étape 10 : Configurer le pare-feu

```bash
# Autoriser SSH
ufw allow 22/tcp

# Autoriser HTTP et HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# OU si pas de nginx, autoriser le port 5000
ufw allow 5000/tcp

# Activer le pare-feu
ufw enable
ufw status
```

---

## Configuration

### Variables d'environnement (Production)

Pour plus de sécurité, utilisez des variables d'environnement au lieu de `config.json` :

```bash
# Créer un fichier .env
nano /home/tiktok/tiktok-scraper/.env
```

Contenu :
```env
TELEGRAM_BOT_TOKEN=votre_token
TELEGRAM_CHAT_ID=votre_chat_id
FLASK_ENV=production
```

Modifiez le service systemd :
```bash
nano /etc/systemd/system/tiktok-scraper.service
```

Ajoutez :
```ini
[Service]
EnvironmentFile=/home/tiktok/tiktok-scraper/.env
```

### Stockage des vidéos

Par défaut, les vidéos sont dans `/home/tiktok/tiktok-scraper/downloads/`.

Pour utiliser un disque externe :
```bash
# Monter un disque
mkdir -p /mnt/videos

# Créer un lien symbolique
ln -s /mnt/videos /home/tiktok/tiktok-scraper/downloads
chown -R tiktok:tiktok /mnt/videos
```

---

## Gestion du service

### Commandes utiles

```bash
# Démarrer
sudo systemctl start tiktok-scraper

# Arrêter
sudo systemctl stop tiktok-scraper

# Redémarrer
sudo systemctl restart tiktok-scraper

# Voir le statut
sudo systemctl status tiktok-scraper

# Voir les logs en temps réel
sudo journalctl -u tiktok-scraper -f

# Voir les derniers logs
sudo journalctl -u tiktok-scraper -n 100
```

### Mise à jour de l'application

```bash
# Se connecter en utilisateur tiktok
sudo su - tiktok
cd /home/tiktok/tiktok-scraper

# Sauvegarder les données
cp config.json config.json.bak
cp telegram_topics.json telegram_topics.json.bak 2>/dev/null

# Mettre à jour le code
git pull origin master

# Activer l'environnement virtuel
source venv/bin/activate

# Mettre à jour les dépendances
pip install -r requirements.txt --upgrade

# Retour en root et redémarrer
exit
sudo systemctl restart tiktok-scraper
```

---

## Sécurité

### 1. Authentification basique (Recommandé)

Protégez l'interface avec un mot de passe :

```bash
# Installer apache2-utils
apt install apache2-utils

# Créer un fichier de mots de passe
htpasswd -c /etc/nginx/.htpasswd admin
```

Modifiez nginx :
```nginx
location / {
    auth_basic "TikTok Scraper Admin";
    auth_basic_user_file /etc/nginx/.htpasswd;

    proxy_pass http://127.0.0.1:5000;
    # ... reste de la config
}
```

```bash
systemctl reload nginx
```

### 2. Restriction par IP

Limitez l'accès à votre IP uniquement :

```nginx
location / {
    allow 1.2.3.4;  # Votre IP
    deny all;

    proxy_pass http://127.0.0.1:5000;
    # ...
}
```

### 3. Fail2ban (Anti brute-force)

```bash
apt install fail2ban
systemctl enable fail2ban
systemctl start fail2ban
```

### 4. Mise à jour automatique des dépendances

```bash
# Créer un cron job
crontab -e
```

Ajoutez :
```bash
# Mise à jour hebdomadaire
0 3 * * 0 apt update && apt upgrade -y
```

---

## Maintenance

### Sauvegarde automatique

Créez un script de sauvegarde :

```bash
nano /home/tiktok/backup.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/home/tiktok/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Sauvegarder les configs
tar -czf $BACKUP_DIR/config_$DATE.tar.gz \
    /home/tiktok/tiktok-scraper/config.json \
    /home/tiktok/tiktok-scraper/telegram_topics.json

# Sauvegarder les historiques
tar -czf $BACKUP_DIR/downloads_$DATE.tar.gz \
    /home/tiktok/tiktok-scraper/downloads/

# Garder seulement les 7 dernières sauvegardes
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
```

```bash
chmod +x /home/tiktok/backup.sh
```

Automatiser avec cron :
```bash
crontab -e -u tiktok
```

```bash
# Sauvegarde quotidienne à 2h du matin
0 2 * * * /home/tiktok/backup.sh >> /home/tiktok/backup.log 2>&1
```

### Rotation des logs

```bash
nano /etc/logrotate.d/tiktok-scraper
```

```
/var/log/tiktok-scraper/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 tiktok tiktok
    sharedscripts
}
```

### Monitoring de l'espace disque

```bash
# Créer un script de vérification
nano /home/tiktok/check_disk.sh
```

```bash
#!/bin/bash
THRESHOLD=90
USAGE=$(df -h /home/tiktok/tiktok-scraper/downloads | tail -1 | awk '{print $5}' | sed 's/%//')

if [ $USAGE -gt $THRESHOLD ]; then
    echo "ALERT: Disk usage is at ${USAGE}%"
    # Envoyer une alerte (email, Telegram, etc.)
fi
```

---

## Dépannage

### L'application ne démarre pas

```bash
# Vérifier les logs
sudo journalctl -u tiktok-scraper -n 50

# Vérifier que le port n'est pas déjà utilisé
netstat -tulpn | grep 5000

# Tester manuellement
sudo su - tiktok
cd /home/tiktok/tiktok-scraper
source venv/bin/activate
python web_app.py
```

### Nginx retourne 502 Bad Gateway

```bash
# Vérifier que le service tourne
systemctl status tiktok-scraper

# Vérifier la configuration nginx
nginx -t

# Voir les logs nginx
tail -f /var/log/nginx/error.log
```

### Erreur "Permission denied"

```bash
# Vérifier les permissions
ls -la /home/tiktok/tiktok-scraper

# Réparer les permissions
chown -R tiktok:tiktok /home/tiktok/tiktok-scraper
```

### yt-dlp ne télécharge pas

```bash
# Mettre à jour yt-dlp
sudo su - tiktok
cd /home/tiktok/tiktok-scraper
source venv/bin/activate
pip install --upgrade yt-dlp
exit
sudo systemctl restart tiktok-scraper
```

### Manque d'espace disque

```bash
# Voir l'utilisation
du -sh /home/tiktok/tiktok-scraper/downloads/*

# Supprimer les anciennes vidéos (exemple)
find /home/tiktok/tiktok-scraper/downloads -name "*.mp4" -mtime +30 -delete
```

---

## Optimisations avancées

### 1. Utiliser Redis pour les tâches (optionnel)

Pour gérer de gros volumes, remplacez le threading par Celery + Redis.

### 2. CDN pour les vidéos

Stockez les vidéos sur S3/Wasabi et servez-les via CloudFlare.

### 3. Docker (alternative)

Voir `docker-compose.yml` pour une installation containerisée.

---

## Support

- **GitHub Issues** : [Lien vers vos issues]
- **Documentation** : [Lien vers votre doc]
- **Email** : votre@email.com

---

## Licence

Voir [LICENSE](LICENSE)
