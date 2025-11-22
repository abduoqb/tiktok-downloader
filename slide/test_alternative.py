"""
Alternative test script using tiktok-downloader library (krypton-byte).
This library uses multiple services: Snaptik, Tikmate, MusicalDown, etc.
"""

import os
import json

try:
    from tiktok_downloader import snaptik, tikmate, musicaldown
except ImportError:
    print("ERROR: tiktok_downloader not installed!")
    print("Please run: pip install tiktok_downloader")
    exit(1)


# Test URLs from slideshows.json
TEST_URLS = [
    "https://www.tiktok.com/@ss0hane/video/7573935872446352662",
    "https://www.tiktok.com/@ss0hane/video/7573304520772570390",
    "https://www.tiktok.com/@ss0hane/video/7553365581915753750",
]


def download_with_snaptik(url, output_dir="downloads_snaptik"):
    """Test download using Snaptik service."""
    try:
        print(f"\n{'='*60}")
        print(f"Testing SNAPTIK: {url}")
        print(f"{'='*60}")

        os.makedirs(output_dir, exist_ok=True)
        video_id = url.split('/')[-1]

        # Download using Snaptik
        result = snaptik(url)

        if not result:
            print("✗ No results from Snaptik")
            return {'status': 'error', 'service': 'snaptik', 'message': 'No results'}

        # Check result type
        print(f"✓ Snaptik returned {len(result)} item(s)")

        for idx, item in enumerate(result, 1):
            print(f"\nItem {idx}:")
            print(f"  Type: {item.type}")
            print(f"  Watermark: {item.watermark}")

            # Download the content
            filename = f"{video_id}_snaptik_{idx}.mp4"
            filepath = os.path.join(output_dir, filename)

            try:
                item.download(filepath)
                print(f"  ✓ Downloaded: {filename}")
                print(f"  Size: {os.path.getsize(filepath)} bytes")
            except Exception as e:
                print(f"  ✗ Download failed: {e}")

        return {
            'status': 'success',
            'service': 'snaptik',
            'video_id': video_id,
            'items_count': len(result)
        }

    except Exception as e:
        print(f"✗ ERROR: {str(e)}")
        return {'status': 'error', 'service': 'snaptik', 'message': str(e)}


def download_with_tikmate(url, output_dir="downloads_tikmate"):
    """Test download using Tikmate service."""
    try:
        print(f"\n{'='*60}")
        print(f"Testing TIKMATE: {url}")
        print(f"{'='*60}")

        os.makedirs(output_dir, exist_ok=True)
        video_id = url.split('/')[-1]

        # Download using Tikmate
        result = tikmate(url)

        if not result:
            print("✗ No results from Tikmate")
            return {'status': 'error', 'service': 'tikmate', 'message': 'No results'}

        print(f"✓ Tikmate returned {len(result)} item(s)")

        for idx, item in enumerate(result, 1):
            print(f"\nItem {idx}:")
            print(f"  Type: {item.type}")

            # Download the content
            filename = f"{video_id}_tikmate_{idx}.mp4"
            filepath = os.path.join(output_dir, filename)

            try:
                item.download(filepath)
                print(f"  ✓ Downloaded: {filename}")
                print(f"  Size: {os.path.getsize(filepath)} bytes")
            except Exception as e:
                print(f"  ✗ Download failed: {e}")

        return {
            'status': 'success',
            'service': 'tikmate',
            'video_id': video_id,
            'items_count': len(result)
        }

    except Exception as e:
        print(f"✗ ERROR: {str(e)}")
        return {'status': 'error', 'service': 'tikmate', 'message': str(e)}


def download_with_musicaldown(url, output_dir="downloads_musicaldown"):
    """Test download using MusicalDown service."""
    try:
        print(f"\n{'='*60}")
        print(f"Testing MUSICALDOWN: {url}")
        print(f"{'='*60}")

        os.makedirs(output_dir, exist_ok=True)
        video_id = url.split('/')[-1]

        # Download using MusicalDown
        result = musicaldown(url)

        if not result:
            print("✗ No results from MusicalDown")
            return {'status': 'error', 'service': 'musicaldown', 'message': 'No results'}

        print(f"✓ MusicalDown returned {len(result)} item(s)")

        for idx, item in enumerate(result, 1):
            print(f"\nItem {idx}:")
            print(f"  Type: {item.type}")

            # Download the content
            filename = f"{video_id}_musicaldown_{idx}.mp4"
            filepath = os.path.join(output_dir, filename)

            try:
                item.download(filepath)
                print(f"  ✓ Downloaded: {filename}")
                print(f"  Size: {os.path.getsize(filepath)} bytes")
            except Exception as e:
                print(f"  ✗ Download failed: {e}")

        return {
            'status': 'success',
            'service': 'musicaldown',
            'video_id': video_id,
            'items_count': len(result)
        }

    except Exception as e:
        print(f"✗ ERROR: {str(e)}")
        return {'status': 'error', 'service': 'musicaldown', 'message': str(e)}


def test_all_services():
    """Test all available download services."""
    print("\n" + "="*60)
    print("TikTok Slideshow Download Test - Alternative Libraries")
    print("="*60)
    print(f"Testing {len(TEST_URLS)} URLs with multiple services...")

    all_results = []

    for url in TEST_URLS:
        print(f"\n\n{'#'*60}")
        print(f"URL: {url}")
        print(f"{'#'*60}")

        # Test each service
        services = [
            ('Snaptik', download_with_snaptik),
            ('Tikmate', download_with_tikmate),
            ('MusicalDown', download_with_musicaldown),
        ]

        url_results = {'url': url, 'services': {}}

        for service_name, service_func in services:
            result = service_func(url)
            url_results['services'][service_name] = result

        all_results.append(url_results)

    # Generate summary report
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    for url_result in all_results:
        print(f"\nURL: {url_result['url']}")
        for service, result in url_result['services'].items():
            status = "✓" if result['status'] == 'success' else "✗"
            print(f"  {status} {service}: {result['status']}")
            if result['status'] == 'success':
                print(f"      Items: {result.get('items_count', 0)}")

    # Save report
    report_path = "test_alternative_report.json"
    with open(report_path, 'w') as f:
        json.dump({
            'total_urls': len(all_results),
            'results': all_results
        }, f, indent=2)

    print(f"\n✓ Test report saved to: {report_path}")


if __name__ == "__main__":
    print("Starting Alternative TikTok Download Test...")
    print("Make sure you have installed:")
    print("  pip install tiktok_downloader")
    print()

    test_all_services()
