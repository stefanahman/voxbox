"""yt-dlp wrapper for audio and caption extraction."""

import logging
import os
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import yt_dlp

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """Result of a video download operation."""

    video_id: str
    title: str
    channel: str
    duration: int  # seconds
    upload_date: Optional[str]  # YYYYMMDD format
    audio_path: Optional[str]  # Path to downloaded MP3
    caption_path: Optional[str]  # Path to downloaded captions (.vtt)
    caption_source: Optional[str]  # "manual", "auto", or None
    thumbnail_url: Optional[str]
    description: Optional[str]


class AudioDownloader:
    """Downloads audio and captions from YouTube videos using yt-dlp."""

    def __init__(
        self,
        temp_dir: str,
        audio_quality: int = 192,
        preferred_caption_langs: Optional[List[str]] = None,
    ):
        """Initialize the downloader.

        Args:
            temp_dir: Directory for temporary files
            audio_quality: Audio bitrate in kbps
            preferred_caption_langs: List of preferred caption languages (default: ["en"])
        """
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.audio_quality = audio_quality
        self.preferred_caption_langs = preferred_caption_langs or ["en"]

    def _get_yt_dlp_options(self, output_template: str) -> dict:
        """Get yt-dlp options for audio extraction.

        Args:
            output_template: Output filename template

        Returns:
            Dictionary of yt-dlp options
        """
        return {
            # Output template
            "outtmpl": output_template,
            # Extract audio only
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(self.audio_quality),
                }
            ],
            # Subtitles/Captions
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": self.preferred_caption_langs,
            "subtitlesformat": "vtt",
            # Metadata
            "writethumbnail": False,
            # Behavior
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "ignoreerrors": False,
            # Network
            "retries": 3,
            "fragment_retries": 3,
        }

    def get_video_info(self, url: str) -> Optional[dict]:
        """Get video metadata without downloading.

        Args:
            url: YouTube URL

        Returns:
            Video metadata dictionary or None on error
        """
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        except Exception as e:
            logger.error(f"Failed to get video info: {e}")
            return None

    def download(self, url: str, video_id: str) -> Optional[DownloadResult]:
        """Download audio and captions for a YouTube video.

        Args:
            url: YouTube URL
            video_id: Video ID (used for filenames)

        Returns:
            DownloadResult with paths to downloaded files, or None on error
        """
        # Create output paths
        output_base = self.temp_dir / video_id
        output_template = str(output_base)

        opts = self._get_yt_dlp_options(output_template)

        try:
            logger.info(f"Downloading audio and captions for: {video_id}")

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)

            if not info:
                logger.error("No info returned from yt-dlp")
                return None

            # Find the downloaded audio file
            audio_path = None
            expected_audio = f"{output_base}.mp3"
            if os.path.exists(expected_audio):
                audio_path = expected_audio
            else:
                # Search for mp3 files with the video_id prefix
                for f in self.temp_dir.glob(f"{video_id}*.mp3"):
                    audio_path = str(f)
                    break

            if not audio_path:
                logger.error(f"Audio file not found for {video_id}")
                return None

            # Find caption files
            caption_path, caption_source = self._find_best_caption(video_id)

            # Extract metadata
            result = DownloadResult(
                video_id=video_id,
                title=info.get("title", "Unknown"),
                channel=info.get("channel", info.get("uploader", "Unknown")),
                duration=info.get("duration", 0),
                upload_date=info.get("upload_date"),
                audio_path=audio_path,
                caption_path=caption_path,
                caption_source=caption_source,
                thumbnail_url=info.get("thumbnail"),
                description=info.get("description"),
            )

            logger.info(
                f"Downloaded: {result.title} "
                f"(duration: {result.duration}s, "
                f"captions: {caption_source or 'none'})"
            )

            return result

        except yt_dlp.DownloadError as e:
            logger.error(f"Download error for {video_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading {video_id}: {e}")
            return None

    def _find_best_caption(self, video_id: str) -> tuple[Optional[str], Optional[str]]:
        """Find the best available caption file.

        Priority:
        1. Manual captions in preferred language
        2. Auto-generated captions in preferred language

        Args:
            video_id: Video ID to search for

        Returns:
            Tuple of (caption_path, source) or (None, None)
        """
        # Look for caption files
        for lang in self.preferred_caption_langs:
            # Check for manual captions first (e.g., video_id.en.vtt)
            manual_path = self.temp_dir / f"{video_id}.{lang}.vtt"
            if manual_path.exists():
                logger.debug(f"Found manual captions: {manual_path}")
                return str(manual_path), "manual"

            # Check for auto-generated (e.g., video_id.en-orig.vtt or similar patterns)
            for pattern in [
                f"{video_id}.{lang}-orig.vtt",
                f"{video_id}.{lang}.vtt",
            ]:
                auto_path = self.temp_dir / pattern
                if auto_path.exists():
                    logger.debug(f"Found auto-generated captions: {auto_path}")
                    return str(auto_path), "auto"

        # Search more broadly
        for vtt_file in self.temp_dir.glob(f"{video_id}*.vtt"):
            logger.debug(f"Found caption file: {vtt_file}")
            # Determine if manual or auto based on filename
            source = "auto" if "-orig" in vtt_file.name else "manual"
            return str(vtt_file), source

        logger.debug(f"No captions found for {video_id}")
        return None, None

    def cleanup(self, video_id: str):
        """Remove temporary files for a video.

        Args:
            video_id: Video ID to clean up
        """
        try:
            for f in self.temp_dir.glob(f"{video_id}*"):
                if f.is_file():
                    f.unlink()
                    logger.debug(f"Cleaned up: {f}")
        except Exception as e:
            logger.warning(f"Cleanup error for {video_id}: {e}")

    def cleanup_all(self):
        """Remove all temporary files."""
        try:
            for f in self.temp_dir.iterdir():
                if f.is_file():
                    f.unlink()
            logger.info("Cleaned up all temporary files")
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")

