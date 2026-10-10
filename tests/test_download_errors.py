"""Tests de download_errors.classify_error (table de vrais messages yt-dlp / gallery-dl)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from download_errors import classify_error  # noqa: E402

ID = "7212345678901234567"
REPORT = ("; please report this issue on  https://github.com/yt-dlp/yt-dlp/issues?q= , "
          "filling out the appropriate issue template. Confirm you are on the latest version "
          "using  yt-dlp -U")

PERMANENT = [
    f"ERROR: [TikTok] {ID}: Video not available, status code 10204",
    f"ERROR: [TikTok] {ID}: Video not available, status code 10216",
    f"ERROR: [TikTok] {ID}: This video is private",
    "ERROR: [youtube] dQw4w9WgXcQ: Video unavailable",
    "ERROR: [youtube] dQw4w9WgXcQ: Video unavailable. This video has been removed by the uploader",
    "ERROR: [youtube] dQw4w9WgXcQ: Private video. Sign in if you've been granted access to this video",
    "ERROR: [youtube] dQw4w9WgXcQ: The uploader has not made this video available in your country",
    f"ERROR: [TikTok] {ID}: This video is not available in your country",
    f"ERROR: [TikTok] {ID}: Unable to extract video data: this video has been removed",
    f"ERROR: [TikTok] {ID}: The video does not exist",
    f"ERROR: [TikTok] {ID}: This post is unavailable",
    "ERROR: [TikTok] someone: This account has been banned",
    "ERROR: [TikTok] someone: Couldn't find this account",
    f"ERROR: [TikTok] {ID}: Unable to download webpage: HTTP Error 404: Not Found "
    "(caused by <HTTPError 404: Not Found>)",
    f"ERROR: [TikTok] {ID}: Unable to download webpage: HTTP Error 410: Gone",
    "[tiktok][error] NotFoundError: Requested post could not be found",
    f"[tiktok][error] HttpError: '404 Not Found' for 'https://www.tiktok.com/@u/photo/{ID}'",
    f"This video has been removed for violating our Community Guidelines",
]

TRANSIENT = [
    f"ERROR: [TikTok] {ID}: Unable to extract webpage video data" + REPORT,
    f"ERROR: [TikTok] {ID}: Unable to extract universal data for rehydration" + REPORT,
    f"ERROR: [TikTok] {ID}: Failed to parse JSON (caused by JSONDecodeError(\"Expecting value "
    "in '': line 1 column 1 (char 0)\"))" + REPORT,
    "ERROR: unable to download video data: HTTP Error 403: Forbidden",
    f"ERROR: [TikTok] {ID}: Unable to download webpage: HTTP Error 429: Too Many Requests "
    "(caused by <HTTPError 429: Too Many Requests>)",
    f"ERROR: [TikTok] {ID}: Unable to download webpage: HTTP Error 503: Service Unavailable",
    f"ERROR: [TikTok] {ID}: Unable to download webpage: HTTP Error 500: Internal Server Error",
    f"ERROR: [TikTok] {ID}: Unable to download webpage: <urlopen error [Errno 11001] "
    "getaddrinfo failed> (caused by TransportError('<urlopen error [Errno 11001] getaddrinfo "
    "failed>'))",
    f"ERROR: [TikTok] {ID}: Unable to download webpage: The read operation timed out",
    "ERROR: [download] Got error: [WinError 10054] An existing connection was forcibly closed "
    "by the remote host",
    f"ERROR: [TikTok] {ID}: Your IP address is blocked from accessing this post",
    "ERROR: [TikTok] Please complete the captcha to continue",
    f"[tiktok][error] HttpError: '429 Too Many Requests' for 'https://www.tiktok.com/@u/photo/{ID}'",
    f"[tiktok][error] HttpError: '503 Service Unavailable' for 'https://www.tiktok.com/@u/photo/{ID}'",
    f"[tiktok][error] HttpError: '403 Forbidden' for 'https://www.tiktok.com/@u/photo/{ID}'",
    f"ERROR: [TikTok] {ID}: Video not available, status code 0",
    # Ambigus : temporaires par défaut (retentés au plus MAX_ATTEMPTS fois)
    f"no video file found for {ID} after download (yt-dlp retcode=1)",
    "gallery-dl a échoué (code 1)",
    "No images found after gallery-dl download",
    "échec du téléchargement de la vidéo",
    f"no info returned for https://www.tiktok.com/@u/video/{ID}",
    "gallery-dl is not installed",
    "boom",
]


@pytest.mark.parametrize("message", PERMANENT)
def test_permanent_messages(message):
    kind, reason = classify_error(message)
    assert kind == "permanent", message
    assert isinstance(reason, str) and reason


@pytest.mark.parametrize("message", TRANSIENT)
def test_transient_messages(message):
    kind, reason = classify_error(message)
    assert kind == "transient", message
    assert isinstance(reason, str) and reason


@pytest.mark.parametrize("error", [None, "", "   ", TimeoutError(), ConnectionError("x"),
                                   OSError("disk"), RuntimeError("boom")])
def test_empty_and_exceptions_are_transient(error):
    kind, reason = classify_error(error)
    assert kind == "transient" and reason


def test_exceptions_use_their_message():
    assert classify_error(RuntimeError("ERROR: [TikTok] 1: This video is private"))[0] == "permanent"
    assert classify_error(ValueError("Failed to parse JSON"))[0] == "transient"


def test_reasons_are_specific():
    assert classify_error("This video is private")[1] == "Vidéo privée"
    assert "429" in classify_error("HTTP Error 429: Too Many Requests")[1]
    assert "403" in classify_error("HTTP Error 403: Forbidden")[1]
    assert "404" in classify_error("HTTP Error 404: Not Found")[1]
    assert "JSON" in classify_error("Failed to parse JSON")[1]
