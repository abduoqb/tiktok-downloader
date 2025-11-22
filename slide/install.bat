@echo off
echo ============================================
echo TikTok Slideshow Downloader - Installation
echo ============================================
echo.

echo [1/3] Installing Python dependencies...
pip install tiktok-dlpy playwright requests

echo.
echo [2/3] Installing Playwright browsers...
python -m playwright install --with-deps

echo.
echo [3/3] Installation complete!
echo.
echo To test the slideshow downloader, run:
echo   python test_download.py
echo.
echo For alternative library test:
echo   pip install tiktok_downloader
echo   python test_alternative.py
echo.
pause
