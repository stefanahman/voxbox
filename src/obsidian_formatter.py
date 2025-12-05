"""Obsidian markdown formatter for video notes."""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ObsidianFormatter:
    """Formats video analysis results into Obsidian-compatible markdown."""

    def __init__(self, outbox_dir: str):
        """Initialize formatter.

        Args:
            outbox_dir: Directory for output files
        """
        self.outbox_dir = Path(outbox_dir)
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

    def create_note(
        self,
        video_id: str,
        url: str,
        channel: str,
        duration: int,
        upload_date: Optional[str],
        analysis: Dict[str, Any],
        transcript: str,
        audio_filename: str = "audio.mp3",
    ) -> tuple[Path, Path]:
        """Create Obsidian note folder with audio and markdown.

        Args:
            video_id: YouTube video ID
            url: Original video URL
            channel: Channel name
            duration: Video duration in seconds
            upload_date: Upload date in YYYYMMDD format
            analysis: Analysis results from Gemini
            transcript: Formatted transcript with timestamps
            audio_filename: Name of the audio file

        Returns:
            Tuple of (folder_path, markdown_path)
        """
        # Get clean title from analysis
        title = analysis.get("title", "Untitled")
        safe_title = self._sanitize_filename(title)

        # Create folder name: YYYY-MM-DD_Safe_Title
        today = datetime.now().strftime("%Y-%m-%d")
        folder_name = f"{today}_{safe_title}"
        folder_path = self.outbox_dir / folder_name

        # Handle duplicate folders
        folder_path = self._ensure_unique_path(folder_path)
        folder_path.mkdir(parents=True, exist_ok=True)

        # Generate markdown content
        markdown_content = self._generate_markdown(
            title=title,
            url=url,
            channel=channel,
            duration=duration,
            upload_date=upload_date,
            analysis=analysis,
            transcript=transcript,
            audio_filename=audio_filename,
        )

        # Write markdown file
        markdown_filename = f"{safe_title}.md"
        markdown_path = folder_path / markdown_filename

        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        logger.info(f"Created note: {markdown_path}")

        return folder_path, markdown_path

    def _generate_markdown(
        self,
        title: str,
        url: str,
        channel: str,
        duration: int,
        upload_date: Optional[str],
        analysis: Dict[str, Any],
        transcript: str,
        audio_filename: str,
    ) -> str:
        """Generate markdown content for the note.

        Args:
            title: Video title
            url: Video URL
            channel: Channel name
            duration: Duration in seconds
            upload_date: Upload date (YYYYMMDD)
            analysis: Analysis results
            transcript: Formatted transcript
            audio_filename: Audio file name

        Returns:
            Complete markdown content
        """
        # Format dates
        processed_date = datetime.now().strftime("%Y-%m-%d")
        if upload_date and len(upload_date) == 8:
            formatted_upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
        else:
            formatted_upload_date = upload_date or "Unknown"

        # Extract tags
        tags = analysis.get("tags", [])
        tag_names = [tag.get("name", "uncategorized") for tag in tags]

        # Build YAML frontmatter
        frontmatter = self._build_frontmatter(
            title=title,
            channel=channel,
            url=url,
            upload_date=formatted_upload_date,
            tags=tag_names,
            processed_date=processed_date,
            duration=duration,
        )

        # Build summary section
        summary = analysis.get("summary", "No summary available.")

        # Build key takeaways section
        takeaways = analysis.get("key_takeaways", [])
        takeaways_md = self._format_takeaways(takeaways)

        # Build topics section
        topics = analysis.get("topics", [])
        topics_md = self._format_topics(topics)

        # Assemble the full document
        content = f"""{frontmatter}

# {title}

## AI Summary

{summary}

### Key Takeaways

{takeaways_md}
{topics_md}
---

## Audio

![[{audio_filename}]]

---

## Full Transcript

{transcript}
"""

        return content

    def _build_frontmatter(
        self,
        title: str,
        channel: str,
        url: str,
        upload_date: str,
        tags: List[str],
        processed_date: str,
        duration: int,
    ) -> str:
        """Build YAML frontmatter.

        Args:
            title: Video title
            channel: Channel name
            url: Video URL
            upload_date: Upload date
            tags: List of tag names
            processed_date: Processing date
            duration: Duration in seconds

        Returns:
            YAML frontmatter string
        """
        # Format duration
        duration_str = self._format_duration(duration)

        # Build tags list
        tags_yaml = "\n".join(f"  - {tag}" for tag in tags)

        frontmatter = f"""---
title: "{self._escape_yaml(title)}"
channel: "{self._escape_yaml(channel)}"
url: "{url}"
upload_date: {upload_date}
duration: "{duration_str}"
tags:
{tags_yaml}
processed_date: {processed_date}
---"""

        return frontmatter

    def _format_takeaways(self, takeaways: List[str]) -> str:
        """Format key takeaways as bullet points."""
        if not takeaways:
            return "* No key takeaways extracted."

        return "\n".join(f"* {takeaway}" for takeaway in takeaways)

    def _format_topics(self, topics: List[str]) -> str:
        """Format topics section if present."""
        if not topics:
            return ""

        topics_list = ", ".join(topics)
        return f"\n### Topics Covered\n\n{topics_list}\n"

    @staticmethod
    def _sanitize_filename(name: str, max_length: int = 50) -> str:
        """Sanitize a string for use as filename.

        Args:
            name: Original name
            max_length: Maximum filename length

        Returns:
            Sanitized filename
        """
        # Remove or replace problematic characters
        sanitized = re.sub(r'[<>:"/\\|?*]', "", name)

        # Replace spaces and multiple hyphens
        sanitized = re.sub(r"\s+", "_", sanitized)
        sanitized = re.sub(r"_+", "_", sanitized)

        # Remove leading/trailing underscores
        sanitized = sanitized.strip("_")

        # Truncate if needed
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length].rstrip("_")

        # Ensure we have something
        if not sanitized:
            sanitized = "Untitled"

        return sanitized

    @staticmethod
    def _escape_yaml(text: str) -> str:
        """Escape text for YAML string value."""
        # Escape quotes
        return text.replace('"', '\\"')

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Format duration as human-readable string."""
        if seconds <= 0:
            return "Unknown"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"

    def _ensure_unique_path(self, path: Path) -> Path:
        """Ensure path is unique by adding counter if needed.

        Args:
            path: Original path

        Returns:
            Unique path
        """
        if not path.exists():
            return path

        counter = 1
        base_name = path.name

        while True:
            new_path = path.parent / f"{base_name}_{counter}"
            if not new_path.exists():
                return new_path
            counter += 1

            # Safety limit
            if counter > 100:
                timestamp = datetime.now().strftime("%H%M%S")
                return path.parent / f"{base_name}_{timestamp}"

