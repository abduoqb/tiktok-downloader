FROM python:3.11-slim

# Installer les dépendances système
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Créer un utilisateur non-root
RUN useradd -m -s /bin/bash tiktok

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers de requirements
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste de l'application
COPY . .

# Créer le dossier downloads
RUN mkdir -p downloads

# Changer les permissions
RUN chown -R tiktok:tiktok /app

# Passer à l'utilisateur non-root
USER tiktok

# Exposer le port
EXPOSE 5000

# Commande de démarrage
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "--timeout", "300", "web_app:app"]
