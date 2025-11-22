"""
Script de nettoyage des anciens fichiers de métadonnées
Supprime download_history.json et slideshows.json de tous les profils
"""
import os
import shutil

def cleanup_old_metadata_files():
    """Supprime les anciens fichiers de métadonnées de tous les profils"""
    downloads_dir = "../downloads"

    if not os.path.exists(downloads_dir):
        print("Aucun dossier downloads trouvé")
        return

    # Fichiers à supprimer
    files_to_remove = [
        "download_history.json",
        "slideshows.json"
    ]

    total_removed = 0
    profiles_cleaned = 0

    print("Nettoyage des anciens fichiers de métadonnées...")
    print()

    for username in os.listdir(downloads_dir):
        user_dir = os.path.join(downloads_dir, username)

        if not os.path.isdir(user_dir) or username == '.gitkeep':
            continue

        removed_in_profile = 0

        for old_file in files_to_remove:
            file_path = os.path.join(user_dir, old_file)

            if os.path.exists(file_path):
                try:
                    # Vérifier la taille du fichier pour info
                    file_size = os.path.getsize(file_path)
                    file_size_kb = file_size / 1024

                    os.remove(file_path)
                    print(f"  Supprimé: {username}/{old_file} ({file_size_kb:.1f} KB)")
                    removed_in_profile += 1
                    total_removed += 1
                except Exception as e:
                    print(f"  Erreur lors de la suppression de {file_path}: {e}")

        if removed_in_profile > 0:
            profiles_cleaned += 1

    print()
    print(f"Nettoyage terminé:")
    print(f"  Profils nettoyés: {profiles_cleaned}")
    print(f"  Fichiers supprimés: {total_removed}")
    print()
    print("Les fichiers conservés:")
    print("  - metadata.json (nouveau système)")
    print("  - metadata.json.backup (backups)")
    print("  - *_videos.txt (URLs)")
    print("  - *.mp4, *.jpg (médias)")

if __name__ == "__main__":
    cleanup_old_metadata_files()
