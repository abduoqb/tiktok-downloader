# Quick Start Guide

## Installation (Windows)

### Method 1: Automated (Recommended)
```bash
cd slide
install.bat
```

### Method 2: Manual
```bash
cd slide
pip install tiktok-dlpy playwright requests
python -m playwright install --with-deps
```

## Run Tests

### Test TikTokDL Library (Recommended)
```bash
python test_download.py
```

Expected output:
- Downloads 3 slideshows
- Creates `downloads/slideshow_{id}/` folders
- Saves images and audio
- Generates `test_report.json`

### Test Alternative Library (Backup)
```bash
pip install tiktok_downloader
python test_alternative.py
```

Tests 3 services: Snaptik, Tikmate, MusicalDown

## What to Check

1. **Image Quality**: Open downloaded images - should be full resolution
2. **Success Rate**: Check `test_report.json` - aim for 100%
3. **File Structure**: Verify organized folders per slideshow
4. **Audio**: Check if audio files are downloaded

## Troubleshooting

### Playwright not installed
```bash
python -m playwright install --with-deps
```

### tiktok-dlpy import error
```bash
pip uninstall tiktok-dlpy
pip install tiktok-dlpy
```

### Downloads fail
- Check internet connection
- Try alternative library (`test_alternative.py`)
- URLs might be private/deleted

## Next Steps

If tests succeed:
- Report results
- Integrate into main project
- Update main `requirements.txt`
