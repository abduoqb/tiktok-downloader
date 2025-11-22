# TikTok Slideshow Download - Test Folder

This folder contains isolated test scripts to download TikTok slideshows without impacting the main project.

## Problem Statement

The main project currently **SKIPS all TikTok slideshows** - they are detected and saved to `slideshows.json` but never downloaded. The reason: `yt-dlp` cannot extract full-resolution images from TikTok slideshows.

## Solutions Tested

### Solution 1: TikTokDL (Recommended)
- **Library**: `tiktok-dlpy`
- **GitHub**: https://github.com/Fluxticks/TikTokDL
- **Key Feature**: Explicitly supports slideshows
- **Method**: Uses Playwright for browser automation

### Solution 2: tiktok-downloader (Alternative)
- **Library**: `tiktok_downloader`
- **GitHub**: https://github.com/krypton-byte/tiktok-downloader
- **Key Feature**: Multiple download services (Snaptik, Tikmate, etc.)
- **Method**: Uses requests & BeautifulSoup

## Installation

### Option 1: TikTokDL (test_download.py)

```bash
cd slide
pip install -r requirements.txt
python -m playwright install --with-deps
```

### Option 2: tiktok-downloader (test_alternative.py)

```bash
cd slide
pip install tiktok_downloader
```

## Usage

### Test TikTokDL

```bash
python test_download.py
```

This will:
- Download 3 sample slideshows from `slideshows.json`
- Save images in `downloads/slideshow_{video_id}/`
- Generate a `test_report.json` with results
- Display summary statistics

### Test Alternative Library

```bash
python test_alternative.py
```

This will test the krypton-byte library with multiple download services.

## Expected Output

For each slideshow, you should see:
```
downloads/
└── slideshow_7573935872446352662/
    ├── image_01.jpg
    ├── image_02.jpg
    ├── image_03.jpg
    ├── ...
    └── audio.mp3 (if available)
```

## Results Validation

After running tests, validate:
1. **Image count**: All images from slideshow downloaded
2. **Image quality**: Full resolution (not thumbnails)
3. **File organization**: Clean folder structure
4. **Success rate**: Check `test_report.json`
5. **Performance**: Download speed and stability

## Next Steps

If tests are successful:
1. Add `download_slideshow()` function to `main.py`
2. Replace SKIP logic with actual download
3. Update `requirements.txt` in main project
4. Test with real user profiles

## Notes

- Test URLs are taken from existing `slideshows.json` files
- Downloads are isolated in `slide/downloads/` folder
- No impact on main project until integration approved
- Rate limiting implemented (2s between downloads)
