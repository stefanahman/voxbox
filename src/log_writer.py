"""Logging system for VoxBox."""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class LogWriter:
    """Writes comprehensive logs for video processing."""

    def __init__(self, logs_dir: str, enabled: bool = True):
        """Initialize log writer.

        Args:
            logs_dir: Root directory for all logs
            enabled: Whether logging is enabled
        """
        self.logs_dir = Path(logs_dir)
        self.enabled = enabled

        # Ensure directory exists
        if self.enabled:
            self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_filename(self, video_id: str, suffix: str = "") -> str:
        """Generate log filename from video ID.

        Args:
            video_id: YouTube video ID
            suffix: Optional suffix to add

        Returns:
            Log filename (without extension)
        """
        if suffix:
            return f"{video_id}_{suffix}"
        return video_id

    def write_download_log(
        self,
        video_id: str,
        url: str,
        title: str,
        channel: str,
        duration: int,
        caption_source: Optional[str],
        download_duration_ms: int,
    ) -> bool:
        """Write download/extraction log.

        Args:
            video_id: YouTube video ID
            url: Video URL
            title: Video title
            channel: Channel name
            duration: Video duration in seconds
            caption_source: Source of captions ("manual", "auto", None)
            download_duration_ms: Download time in milliseconds

        Returns:
            True if written successfully
        """
        if not self.enabled:
            return False

        try:
            log_filename = f"{video_id}_download.json"
            log_path = self.logs_dir / log_filename

            log_data = {
                "video_id": video_id,
                "url": url,
                "title": title,
                "channel": channel,
                "duration_seconds": duration,
                "caption_source": caption_source,
                "download_duration_ms": download_duration_ms,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Wrote download log: {log_filename}")
            return True

        except Exception as e:
            logger.error(f"Error writing download log: {e}")
            return False

    def write_analysis_log(
        self,
        video_id: str,
        analysis_result: Dict[str, Any],
        available_tags: List[str],
        transcript_length: int,
    ) -> bool:
        """Write Gemini analysis log.

        Args:
            video_id: YouTube video ID
            analysis_result: Raw analysis result from Gemini
            available_tags: List of tags that were available
            transcript_length: Length of transcript in characters

        Returns:
            True if written successfully
        """
        if not self.enabled:
            return False

        try:
            log_filename = f"{video_id}_analysis.json"
            log_path = self.logs_dir / log_filename

            log_data = {
                "video_id": video_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "transcript_length": transcript_length,
                "available_tags": available_tags,
                "analysis_result": analysis_result,
            }

            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Wrote analysis log: {log_filename}")
            return True

        except Exception as e:
            logger.error(f"Error writing analysis log: {e}")
            return False

    def write_processing_log(
        self,
        video_id: str,
        input_filename: str,
        output_folder: str,
        processing_duration_ms: int,
        status: str,
        transcription_source: str,
        selected_tags: List[str],
        error_message: Optional[str] = None,
    ) -> bool:
        """Write processing audit log.

        Args:
            video_id: YouTube video ID
            input_filename: Original job file name
            output_folder: Generated output folder name
            processing_duration_ms: Processing time in milliseconds
            status: Processing status (success, error, skipped)
            transcription_source: Source of transcript ("youtube_manual", "youtube_auto", "whisper")
            selected_tags: Tags that were selected
            error_message: Optional error message if status is error

        Returns:
            True if written successfully
        """
        if not self.enabled:
            return False

        try:
            log_filename = f"{video_id}_processing.json"
            log_path = self.logs_dir / log_filename

            log_data = {
                "video_id": video_id,
                "input_file": input_filename,
                "output_folder": output_folder,
                "processed_at": datetime.utcnow().isoformat() + "Z",
                "processing_duration_ms": processing_duration_ms,
                "status": status,
                "transcription_source": transcription_source,
                "selected_tags": selected_tags,
            }

            if error_message:
                log_data["error_message"] = error_message

            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Wrote processing log: {log_filename}")
            return True

        except Exception as e:
            logger.error(f"Error writing processing log: {e}")
            return False

    def write_error_log(
        self,
        video_id: str,
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Write error log.

        Args:
            video_id: YouTube video ID
            error_type: Type/class of error
            error_message: Error message
            stack_trace: Optional stack trace
            context: Optional additional context

        Returns:
            True if written successfully
        """
        if not self.enabled:
            return False

        try:
            log_filename = f"{video_id}_error.json"
            log_path = self.logs_dir / log_filename

            log_data = {
                "video_id": video_id,
                "error_at": datetime.utcnow().isoformat() + "Z",
                "error_type": error_type,
                "error_message": error_message,
            }

            if stack_trace:
                log_data["stack_trace"] = stack_trace

            if context:
                log_data["context"] = context

            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Wrote error log: {log_filename}")
            return True

        except Exception as e:
            logger.error(f"Error writing error log: {e}")
            return False

    def cleanup_old_logs(self, days_to_keep: int = 30) -> int:
        """Clean up log files older than specified days.

        Args:
            days_to_keep: Number of days to keep logs

        Returns:
            Number of files deleted
        """
        if not self.enabled:
            return 0

        import time

        cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
        deleted_count = 0

        try:
            for log_file in self.logs_dir.glob("*.json"):
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    deleted_count += 1

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old log files")

            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up old logs: {e}")
            return deleted_count

