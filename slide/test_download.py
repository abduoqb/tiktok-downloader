import subprocess
import json
import os


def download_with_gallery_dl(url, output_dir="downloads"):
    """Télécharge un slideshow TikTok avec gallery-dl"""
    
    # Configuration gallery-dl pour TikTok
    config = {
        "extractor": {
            "tiktok": {
                "directory": [output_dir, "{author[uniqueId]}", "{id}"],
                "filename": "{num:>02}_{id}.{extension}",
                "videos": False,  # Uniquement les images
            }
        }
    }
    
    # Créer fichier config temporaire
    config_file = "gallery-dl-config.json"
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    try:
        # Exécuter gallery-dl
        cmd = [
            'gallery-dl',
            '--config', config_file,
            url
        ]
        
        print(f"📥 Téléchargement avec gallery-dl: {url}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Téléchargement réussi!")
            return {'status': 'success', 'output': result.stdout}
        else:
            print(f"❌ Erreur: {result.stderr}")
            return {'status': 'error', 'message': result.stderr}
            
    except FileNotFoundError:
        print("❌ gallery-dl n'est pas installé!")
        print("Installation: pip install gallery-dl")
        return {'status': 'error', 'message': 'gallery-dl not found'}
    finally:
        # Nettoyer le fichier config
        if os.path.exists(config_file):
            os.remove(config_file)


# Méthode alternative: Utiliser gallery-dl comme bibliothèque
def download_as_library(url, output_dir="downloads"):
    """Utilise gallery-dl comme bibliothèque Python"""
    try:
        import gallery_dl
        
        # Configuration
        gallery_dl.config.set(("extractor", "tiktok", "videos"), False)
        gallery_dl.config.set(("extractor", "base-directory"), output_dir)
        
        # Téléchargement
        job = gallery_dl.job.DownloadJob(url)
        job.run()
        
        print("✅ Téléchargement terminé!")
        return {'status': 'success'}
        
    except ImportError:
        print("❌ Impossible d'importer gallery_dl")
        return download_with_gallery_dl(url, output_dir)


# UTILISATION
if __name__ == "__main__":
    url = "https://www.tiktok.com/@ferdaus_bbzk/photo/7286530167789407520?lang=fr"
    
    # Méthode 1: Ligne de commande
    result1 = download_with_gallery_dl(url)
    
    # Méthode 2: Bibliothèque (si disponible)
    # result2 = download_as_library(url)