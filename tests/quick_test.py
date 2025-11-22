# -*- coding: utf-8 -*-
"""
Script de test rapide pour vérifier le système avant merge
Automatise les vérifications de base
"""
import os
import sys
import json
import glob

# Fix encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')


def check_file_exists(path, description):
    """Vérifier qu'un fichier existe"""
    if os.path.exists(path):
        print(f"  ✅ {description}: {path}")
        return True
    else:
        print(f"  ❌ {description} MANQUANT: {path}")
        return False


def check_metadata_structure(username):
    """Vérifier la structure du fichier metadata.json"""
    metadata_file = f"../downloads/{username}/metadata.json"

    if not os.path.exists(metadata_file):
        print(f"  ❌ metadata.json n'existe pas pour {username}")
        return False

    try:
        with open(metadata_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not data:
            print(f"  ⚠️  metadata.json est vide")
            return True

        # Vérifier la structure du premier élément
        first_key = list(data.keys())[0]
        first_item = data[first_key]

        required_fields = ["url", "type", "date", "size", "success"]
        missing_fields = [field for field in required_fields if field not in first_item]

        if missing_fields:
            print(f"  ❌ Champs manquants: {missing_fields}")
            return False

        # Vérifier les types
        video_count = sum(1 for item in data.values() if item.get("type") == "video")
        slideshow_count = sum(1 for item in data.values() if item.get("type") == "slideshow")

        print(f"  ✅ metadata.json valide ({len(data)} entrées)")
        print(f"     - Vidéos: {video_count}")
        print(f"     - Slideshows: {slideshow_count}")

        return True

    except Exception as e:
        print(f"  ❌ Erreur de lecture: {e}")
        return False


def check_downloads_folder():
    """Vérifier le dossier downloads"""
    print("\n" + "="*60)
    print("📁 VÉRIFICATION DU DOSSIER DOWNLOADS")
    print("="*60)

    if not os.path.exists("../downloads"):
        print("  ❌ Dossier downloads n'existe pas!")
        return False

    # Lister les utilisateurs
    users = [d for d in os.listdir("../downloads") if os.path.isdir(f"../downloads/{d}")]

    if not users:
        print("  ⚠️  Aucun utilisateur trouvé dans downloads/")
        print("  💡 Téléchargez quelques vidéos d'abord avec:")
        print("     python ../main.py <username> --download --limit 3")
        return False

    print(f"  ✅ {len(users)} utilisateur(s) trouvé(s): {', '.join(users[:5])}")

    return True


def check_user_migration(username):
    """Vérifier qu'un utilisateur a bien été migré"""
    print(f"\n{'='*60}")
    print(f"🔍 VÉRIFICATION UTILISATEUR: {username}")
    print("="*60)

    user_dir = f"../downloads/{username}"

    if not os.path.exists(user_dir):
        print(f"  ❌ Dossier utilisateur n'existe pas: {user_dir}")
        return False

    # Vérifier les fichiers
    checks = []
    checks.append(check_file_exists(f"{user_dir}/metadata.json", "Nouveau système (metadata.json)"))

    # Anciens fichiers (peuvent exister ou non)
    has_old_history = os.path.exists(f"{user_dir}/download_history.json")
    has_slideshows = os.path.exists(f"{user_dir}/slideshows.json")

    if has_old_history:
        print(f"  📋 Ancien fichier conservé: download_history.json")

    if has_slideshows:
        print(f"  📋 Ancien fichier conservé: slideshows.json")

    # Vérifier backup
    if os.path.exists(f"{user_dir}/metadata.json.backup"):
        print(f"  ✅ Backup automatique créé")

    # Vérifier structure metadata
    check_metadata_structure(username)

    # Compter les fichiers
    mp4_files = glob.glob(f"{user_dir}/*.mp4")
    slideshow_images = glob.glob(f"{user_dir}/*_img=*.jpg") + glob.glob(f"{user_dir}/*_img=*.jpeg")

    print(f"\n  📊 Fichiers:")
    print(f"     - Vidéos (.mp4): {len(mp4_files)}")
    print(f"     - Images slideshows: {len(slideshow_images)}")

    return all(checks)


def compare_old_new_counts(username):
    """Comparer le nombre d'entrées ancien vs nouveau système"""
    print(f"\n{'='*60}")
    print(f"📊 COMPARAISON ANCIEN/NOUVEAU - {username}")
    print("="*60)

    old_file = f"../downloads/{username}/download_history.json"
    new_file = f"../downloads/{username}/metadata.json"

    old_count = 0
    new_count = 0

    # Compter ancien système
    if os.path.exists(old_file):
        try:
            with open(old_file, "r", encoding="utf-8") as f:
                old_data = json.load(f)
                old_count = len(old_data)
        except:
            pass

    # Compter nouveau système
    if os.path.exists(new_file):
        try:
            with open(new_file, "r", encoding="utf-8") as f:
                new_data = json.load(f)
                new_count = len(new_data)
        except:
            pass

    print(f"  Ancien système (download_history.json): {old_count} entrées")
    print(f"  Nouveau système (metadata.json):        {new_count} entrées")

    diff = new_count - old_count
    if diff == 0:
        print(f"  ✅ Nombres identiques")
    elif abs(diff) <= 5:
        print(f"  ✅ Différence mineure ({diff:+d}) - normal avec slideshows")
    else:
        print(f"  ⚠️  Différence significative ({diff:+d})")

    return True


def main():
    """Fonction principale de test"""
    print("\n" + "="*60)
    print("🧪 TEST RAPIDE - Système de Métadonnées Optimisé")
    print("="*60)

    all_ok = True

    # 1. Vérifier dossier downloads
    if not check_downloads_folder():
        return False

    # 2. Trouver un utilisateur à tester
    users = [d for d in os.listdir("../downloads") if os.path.isdir(f"../downloads/{d}")]

    if not users:
        print("\n❌ Aucun utilisateur à tester!")
        return False

    # Filtrer les utilisateurs de test
    real_users = [u for u in users if not u.startswith("test_")]

    if real_users:
        test_user = real_users[0]
        print(f"\n💡 Test avec utilisateur réel: {test_user}")
    else:
        test_user = users[0]
        print(f"\n💡 Test avec: {test_user}")

    # 3. Vérifier migration
    if not check_user_migration(test_user):
        all_ok = False

    # 4. Comparer ancien/nouveau
    if not compare_old_new_counts(test_user):
        all_ok = False

    # Résumé final


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
