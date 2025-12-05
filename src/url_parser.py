"""YouTube URL parser and validator."""

import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

# Regex patterns for YouTube URLs
YOUTUBE_PATTERNS = [
    # Standard watch URLs: youtube.com/watch?v=VIDEO_ID
    r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
    # Short URLs: youtu.be/VIDEO_ID
    r"(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})",
    # Embed URLs: youtube.com/embed/VIDEO_ID
    r"(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})",
    # Shorts URLs: youtube.com/shorts/VIDEO_ID
    r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    # Live URLs: youtube.com/live/VIDEO_ID
    r"(?:https?://)?(?:www\.)?youtube\.com/live/([a-zA-Z0-9_-]{11})",
    # Mobile URLs: m.youtube.com/watch?v=VIDEO_ID
    r"(?:https?://)?m\.youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
]


@dataclass
class VideoInfo:
    """Container for extracted video information."""

    video_id: str
    url: str
    title: Optional[str] = None
    channel: Optional[str] = None
    duration: Optional[int] = None  # seconds
    upload_date: Optional[str] = None  # YYYYMMDD format


class URLParser:
    """Parses and validates YouTube URLs."""

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """Extract YouTube video ID from various URL formats.

        Args:
            url: YouTube URL in any supported format

        Returns:
            Video ID (11 characters) or None if not found
        """
        url = url.strip()

        # Try each pattern
        for pattern in YOUTUBE_PATTERNS:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                logger.debug(f"Extracted video ID: {video_id} from {url}")
                return video_id

        # Fallback: try parsing URL parameters
        try:
            parsed = urlparse(url)
            if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
                # Check query parameters for 'v'
                params = parse_qs(parsed.query)
                if "v" in params and params["v"]:
                    video_id = params["v"][0]
                    if len(video_id) == 11:
                        logger.debug(f"Extracted video ID from params: {video_id}")
                        return video_id
        except Exception as e:
            logger.debug(f"URL parsing fallback failed: {e}")

        logger.warning(f"Could not extract video ID from URL: {url}")
        return None

    @staticmethod
    def is_valid_youtube_url(url: str) -> bool:
        """Check if URL is a valid YouTube URL.

        Args:
            url: URL to validate

        Returns:
            True if valid YouTube URL
        """
        video_id = URLParser.extract_video_id(url)
        return video_id is not None

    @staticmethod
    def normalize_url(url: str) -> Optional[str]:
        """Convert any YouTube URL format to standard watch URL.

        Args:
            url: YouTube URL in any format

        Returns:
            Normalized URL (https://www.youtube.com/watch?v=VIDEO_ID) or None
        """
        video_id = URLParser.extract_video_id(url)
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
        return None

    @staticmethod
    def parse_job_file(content: str) -> Optional[str]:
        """Extract YouTube URL from job file content.

        Job files can contain:
        - Just a URL on a single line
        - URL with additional metadata
        - Multiple lines (first valid URL is used)

        Args:
            content: Content of the job file

        Returns:
            First valid YouTube URL found, or None
        """
        lines = content.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Check if this line contains a YouTube URL
            if URLParser.is_valid_youtube_url(line):
                return URLParser.normalize_url(line)

            # Try to find URL within the line (e.g., "URL: https://...")
            url_match = re.search(r"https?://[^\s]+", line)
            if url_match:
                potential_url = url_match.group(0)
                if URLParser.is_valid_youtube_url(potential_url):
                    return URLParser.normalize_url(potential_url)

        logger.warning("No valid YouTube URL found in job file content")
        return None

