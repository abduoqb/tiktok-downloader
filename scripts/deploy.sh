#!/bin/bash

#######################################
# TikTok Scraper - Auto Deploy Script
# Pour Ubuntu 22.04+ / Debian 11+
#######################################

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_USER="tiktok"
APP_DIR="/home/$APP_USER/tiktok-scraper"
GIT_REPO="https://github.com/VOTRE-USERNAME/tiktok-scraper.git"  # CHANGEZ CETTE VALEUR

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  TikTok Scraper - Installation VPS${NC}"
echo -e "${GREEN}========================================${NC}"

# Vérifier si root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Erreur: Ce script doit être exécuté en tant que root${NC}"
    echo "Utilisez: sudo ./deploy.sh"
    exit 1
fi

# Demander l'URL du repo Git
echo -e "${YELLOW}Entrez l'URL de votre repository Git:${NC}"
echo "(Laissez vide pour utiliser: $GIT_REPO)"
read -r user_repo
if [ -n "$user_repo" ]; then
    GIT_REPO="$user_repo"
fi

# Demander si on doit installer nginx
echo -e "${YELLOW}Voulez-vous installer et configurer Nginx? (y/n)${NC}"
read -r install_nginx

echo ""
echo -e "${GREEN}[1/8] Mise à jour du système...${NC}"
apt update && apt upgrade -y

echo ""
echo -e "${GREEN}[2/8] Installation des dépendances système...${NC}"
apt install -y python3 python3-pip python3-venv git ufw

if [ "$install_nginx" = "y" ] || [ "$install_nginx" = "Y" ]; then
    apt install -y nginx certbot python3-certbot-nginx
fi

echo ""
echo -e "${GREEN}[3/8] Création de l'utilisateur $APP_USER...${NC}"
if id "$APP_USER" &>/dev/null; then
    echo "L'utilisateur $APP_USER existe déjà"
else
    useradd -m -s /bin/bash $APP_USER
    echo "Utilisateur $APP_USER créé"
fi

echo ""
echo -e "${GREEN}[4/8] Clonage du projet...${NC}"
if [ -d "$APP_DIR" ]; then
    echo "Le dossier existe déjà. Mise à jour..."
    cd $APP_DIR
    sudo -u $APP_USER git pull
else
    sudo -u $APP_USER git clone $GIT_REPO $APP_DIR
    cd $APP_DIR
fi

echo ""
echo -e "${GREEN}[5/8] Configuration de l'environnement Python...${NC}"
sudo -u $APP_USER python3 -m venv venv
sudo -u $APP_USER venv/bin/pip install --upgrade pip
sudo -u $APP_USER venv/bin/pip install -r requirements.txt
sudo -u $APP_USER venv/bin/pip install gunicorn

echo ""
echo -e "${GREEN}[6/8] Configuration de l'application...${NC}"
if [ ! -f "$APP_DIR/config.json" ]; then
    if [ -f "$APP_DIR/config.json.example" ]; then
        sudo -u $APP_USER cp $APP_DIR/config.json.example $APP_DIR/config.json
        echo -e "${YELLOW}⚠️  Pensez à éditer config.json avec vos tokens Telegram !${NC}"
        echo "   sudo nano $APP_DIR/config.json"
    fi
fi

# Créer le dossier downloads
sudo -u $APP_USER mkdir -p $APP_DIR/downloads

echo ""
echo -e "${GREEN}[7/8] Configuration du service systemd...${NC}"
if [ -f "$APP_DIR/scripts/tiktok-scraper.service" ]; then
    cp $APP_DIR/scripts/tiktok-scraper.service /etc/systemd/system/
else
    # Créer le fichier service
    cat > /etc/systemd/system/tiktok-scraper.service <<EOF
[Unit]
Description=TikTok Scraper Web Application
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 --timeout 300 web_app:app
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
fi

systemctl daemon-reload
systemctl enable tiktok-scraper
systemctl start tiktok-scraper

echo ""
echo -e "${GREEN}[8/8] Configuration du pare-feu...${NC}"
ufw allow 22/tcp  # SSH
if [ "$install_nginx" = "y" ] || [ "$install_nginx" = "Y" ]; then
    ufw allow 80/tcp   # HTTP
    ufw allow 443/tcp  # HTTPS
else
    ufw allow 5000/tcp # Flask direct
fi

# Activer UFW si pas déjà actif
if ! ufw status | grep -q "Status: active"; then
    echo "y" | ufw enable
fi

# Configuration nginx si demandée
if [ "$install_nginx" = "y" ] || [ "$install_nginx" = "Y" ]; then
    echo ""
    echo -e "${GREEN}Configuration de Nginx...${NC}"

    if [ -f "$APP_DIR/nginx.conf" ]; then
        cp $APP_DIR/nginx.conf /etc/nginx/sites-available/tiktok-scraper
    else
        cat > /etc/nginx/sites-available/tiktok-scraper <<EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # SSE Support
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;

        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    access_log /var/log/nginx/tiktok-scraper-access.log;
    error_log /var/log/nginx/tiktok-scraper-error.log;
}
EOF
    fi

    ln -sf /etc/nginx/sites-available/tiktok-scraper /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default  # Supprimer le site par défaut
    nginx -t && systemctl reload nginx
fi

# Vérifier le statut
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Installation terminée !${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
systemctl status tiktok-scraper --no-pager

echo ""
echo -e "${GREEN}✅ Application installée et démarrée !${NC}"
echo ""
echo "📝 Prochaines étapes:"
echo ""
echo "1. Configurer Telegram:"
echo "   sudo nano $APP_DIR/config.json"
echo ""
echo "2. Redémarrer le service:"
echo "   sudo systemctl restart tiktok-scraper"
echo ""
if [ "$install_nginx" = "y" ] || [ "$install_nginx" = "Y" ]; then
    IP=$(hostname -I | awk '{print $1}')
    echo "3. Accéder à l'application:"
    echo "   http://$IP"
    echo ""
    echo "4. (Optionnel) Configurer SSL avec Let's Encrypt:"
    echo "   sudo certbot --nginx -d votre-domaine.com"
else
    IP=$(hostname -I | awk '{print $1}')
    echo "3. Accéder à l'application:"
    echo "   http://$IP:5000"
fi
echo ""
echo "📊 Commandes utiles:"
echo "   sudo systemctl status tiktok-scraper    # Voir le statut"
echo "   sudo systemctl restart tiktok-scraper   # Redémarrer"
echo "   sudo journalctl -u tiktok-scraper -f    # Voir les logs"
echo ""
echo -e "${GREEN}Bonne utilisation ! 🚀${NC}"
