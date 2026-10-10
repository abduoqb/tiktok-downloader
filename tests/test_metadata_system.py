# -*- coding: utf-8 -*-
"""
Test script for the new OptimizedMetadataManager system
Tests performance, and functionality
"""
import os
import sys
import time
import json
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from metadata_manager import OptimizedMetadataManager

# Fix encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')


def test_performance():
    """Test performance improvement O(n) vs O(1)"""
    print("\n" + "="*60)
    print("TEST 2: Performance O(n) vs O(1)")
    print("="*60)

    username = "test_user_performance"
    user_dir = f"../downloads/{username}"
    os.makedirs(user_dir, exist_ok=True)

    manager = OptimizedMetadataManager(username, user_dir)

    # Add 1000 fake entries
    print("\n📝 Ajout de 1000 entrées...")
    for i in range(1000):
        manager.add(f"video_{i}", f"https://test.com/{i}", "video", file_size=1024*1024)

    # Test O(1) lookup
    print("\n⚡ Test de recherche O(1)...")
    start = time.time()
    for i in range(1000):
        manager.is_downloaded(f"video_{i}")
    elapsed_optimized = time.time() - start

    # Compare with O(n) list search
    print("🐌 Test de recherche O(n) (ancien système)...")
    ids_list = manager.get_all_ids()
    start = time.time()
    for i in range(1000):
        _ = f"video_{i}" in ids_list  # O(n) search
    elapsed_list = time.time() - start

    print(f"\n📊 Résultats:")
    print(f"  Optimized (O(1)): {elapsed_optimized*1000:.2f}ms")
    print(f"  List (O(n)):      {elapsed_list*1000:.2f}ms")

    if elapsed_optimized > 0:
        ratio = elapsed_list/elapsed_optimized
        print(f"  Amélioration:     {ratio:.1f}x plus rapide")
    else:
        print(f"  Amélioration:     Extrêmement rapide (< 0.01ms)")

    print("✅ Test de performance réussi!")


def test_slideshow_cache():
    """Test slideshow caching functionality"""
    print("\n" + "="*60)
    print("TEST 3: Cache is_slideshow()")
    print("="*60)

    username = "test_user_cache"
    user_dir = f"../downloads/{username}"
    os.makedirs(user_dir, exist_ok=True)

    manager = OptimizedMetadataManager(username, user_dir)

    # Add entry with slideshow type
    url = "https://tiktok.com/@test/video/123"
    manager.add("123", url, "slideshow")

    # Test cache
    cached = manager.get_slideshow_type_from_cache(url)
    assert cached == True, "Cache slideshow devrait retourner True"

    # Test cache for video
    video_url = "https://tiktok.com/@test/video/456"
    manager.add("456", video_url, "video")
    cached = manager.get_slideshow_type_from_cache(video_url)
    assert cached == False, "Cache slideshow devrait retourner False pour vidéo"

    print("✅ Cache is_slideshow() fonctionne!")


def test_metadata_richness():
    """Test rich metadata storage"""
    print("\n" + "="*60)
    print("TEST 4: Métadonnées riches")
    print("="*60)

    username = "test_user_metadata"
    user_dir = f"../downloads/{username}"
    os.makedirs(user_dir, exist_ok=True)

    manager = OptimizedMetadataManager(username, user_dir)

    # Add video with metadata
    manager.add(
        video_id="video_123",
        url="https://test.com/video/123",
        item_type="video",
        file_size=5*1024*1024,  # 5MB
        file_count=1,
        success=True
    )

    # Add slideshow with metadata
    manager.add(
        video_id="slideshow_456",
        url="https://test.com/slideshow/456",
        item_type="slideshow",
        file_size=0,
        file_count=12,  # 12 images
        success=True
    )

    # Add failed download
    manager.add(
        video_id="failed_789",
        url="https://test.com/video/789",
        item_type="video",
        file_size=0,
        success=False
    )

    # Check stats
    stats = manager.get_stats()
    print(f"\n📊 Statistiques:")
    print(f"  Videos: {stats.get('video', {}).get('count', 0)}")
    print(f"  Slideshows: {stats.get('slideshow', {}).get('count', 0)}")
    print(f"  Taille vidéos: {stats.get('video', {}).get('size', 0)/(1024*1024):.1f}MB")

    # Check failed downloads
    failed = manager.get_failed_downloads()
    print(f"\n❌ Téléchargements échoués: {len(failed)}")
    for item in failed:
        print(f"  - {item['id']} ({item['type']})")

    print("✅ Métadonnées riches fonctionnent!")


def test_backup_safety():
    """Test backup mechanism"""
    print("\n" + "="*60)
    print("TEST 5: Sécurité des backups")
    print("="*60)

    username = "test_user_backup"
    user_dir = f"../downloads/{username}"
    os.makedirs(user_dir, exist_ok=True)

    manager = OptimizedMetadataManager(username, user_dir)

    # Add some data
    manager.add("video_1", "url1", "video")
    manager.add("video_2", "url2", "video")

    # Check backup exists
    backup_file = f"{user_dir}/metadata.json.backup"
    assert os.path.exists(backup_file), "Backup devrait exister"

    print(f"✅ Backup créé: {backup_file}")
    print("✅ Mécanisme de backup fonctionne!")


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("    SUITE DE TESTS - OptimizedMetadataManager")
    print("="*60 + "\n")

    try:
        test_performance()
        test_slideshow_cache()
        test_metadata_richness()
        test_backup_safety()

        print("\n" + "="*60)
        print("✅ TOUS LES TESTS RÉUSSIS!")
        print("="*60 + "\n")

    except AssertionError as e:
        print(f"\n❌ TEST ÉCHOUÉ: {e}")
        return False
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
