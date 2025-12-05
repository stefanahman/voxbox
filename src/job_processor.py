"""Main job processing pipeline for VoxBox."""

import logging
import shutil
import time
import traceback
from pathlib import Path
from typing import Optional, Tuple

from .url_parser import URLParser
from .audio_downloader import AudioDownloader, DownloadResult
from .transcriber import Transcriber, TranscriptResult
from .gemini_client import GeminiClient
from .obsidian_formatter import ObsidianFormatter
from .storage import ProcessedFilesDB
from .notifications import NotificationManager
from .tag_manager import TagManager
from .log_writer import LogWriter

logger = logging.getLogger(__name__)


class JobProcessor:
    """Processes video jobs through the complete pipeline."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        processed_db: ProcessedFilesDB,
        notification_manager: NotificationManager,
        config,
    ):
        """Initialize job processor.

        Args:
            gemini_client: Gemini client for summarization
            processed_db: Processed files database
            notification_manager: Notification manager
            config: Config object with all settings
        """
        self.gemini_client = gemini_client
        self.processed_db = processed_db
        self.notification_manager = notification_manager
        self.config = config

        # Initialize components
        self.url_parser = URLParser()
        self.audio_downloader = AudioDownloader(
            temp_dir=config.temp_dir,
            audio_quality=config.audio_quality,
        )
        self.transcriber = Transcriber(whisper_model=config.whisper_model)
        self.tag_manager = TagManager(
            outbox_dir=config.outbox_dir,
            enable_learning=config.enable_tag_learning,
        )
        self.formatter = ObsidianFormatter(outbox_dir=config.outbox_dir)
        self.log_writer = LogWriter(
            logs_dir=config.logs_dir,
            enabled=config.enable_detailed_logs,
        )

        self.outbox_dir = Path(config.outbox_dir)
        self.archive_dir = Path(config.archive_dir)

    def process_job_file(
        self,
        job_content: str,
        job_filename: str,
        job_identifier: str,
        account_id: Optional[str] = None,
        account_email: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Process a job file containing a YouTube URL.

        Args:
            job_content: Content of the job file (YouTube URL)
            job_filename: Original job filename
            job_identifier: Unique identifier for idempotency
            account_id: Dropbox account ID (if applicable)
            account_email: User's email (if applicable)

        Returns:
            Tuple of (success, output_folder_name, video_id)
        """
        start_time = time.time()
        video_id = None
        url = None

        try:
            # Check if already processed
            if self.processed_db.is_processed(job_identifier):
                logger.info(f"Job already processed, skipping: {job_filename}")
                return False, None, None

            # Parse URL from job content
            url = self.url_parser.parse_job_file(job_content)
            if not url:
                raise ValueError(f"No valid YouTube URL found in job file: {job_filename}")

            video_id = self.url_parser.extract_video_id(url)
            if not video_id:
                raise ValueError(f"Could not extract video ID from URL: {url}")

            logger.info(f"Processing video: {video_id} ({url})")

            # Download audio and captions
            download_start = time.time()
            download_result = self.audio_downloader.download(url, video_id)
            download_duration = int((time.time() - download_start) * 1000)

            if not download_result:
                raise RuntimeError(f"Failed to download video: {video_id}")

            # Log download
            self.log_writer.write_download_log(
                video_id=video_id,
                url=url,
                title=download_result.title,
                channel=download_result.channel,
                duration=download_result.duration,
                caption_source=download_result.caption_source,
                download_duration_ms=download_duration,
            )

            # Transcribe (YouTube captions preferred, Whisper fallback)
            transcript_result = self.transcriber.transcribe(
                audio_path=download_result.audio_path,
                caption_path=download_result.caption_path,
                caption_source=download_result.caption_source,
            )

            # Get available tags
            available_tags = self.tag_manager.get_available_tags()

            # Analyze with Gemini
            formatted_transcript = transcript_result.format_with_timestamps(
                interval_seconds=60
            )
            analysis = self.gemini_client.analyze_video(
                transcript=formatted_transcript,
                video_title=download_result.title,
                channel=download_result.channel,
                available_tags=available_tags,
                duration_seconds=download_result.duration,
            )

            # Log analysis
            self.log_writer.write_analysis_log(
                video_id=video_id,
                analysis_result=analysis,
                available_tags=available_tags,
                transcript_length=len(formatted_transcript),
            )

            # Create Obsidian note
            folder_path, markdown_path = self.formatter.create_note(
                video_id=video_id,
                url=url,
                channel=download_result.channel,
                duration=download_result.duration,
                upload_date=download_result.upload_date,
                analysis=analysis,
                transcript=formatted_transcript,
            )

            # Copy audio file to output folder
            if download_result.audio_path:
                audio_dest = folder_path / "audio.mp3"
                shutil.copy2(download_result.audio_path, audio_dest)
                logger.info(f"Copied audio to: {audio_dest}")

            # Calculate total processing time
            total_duration = int((time.time() - start_time) * 1000)

            # Get tags for logging
            tags = analysis.get("tags", [])
            tag_names = [t.get("name", "uncategorized") for t in tags]

            # Log processing
            self.log_writer.write_processing_log(
                video_id=video_id,
                input_filename=job_filename,
                output_folder=folder_path.name,
                processing_duration_ms=total_duration,
                status="success",
                transcription_source=transcript_result.source,
                selected_tags=tag_names,
            )

            # Mark as processed
            self.processed_db.mark_processed(
                file_path=job_identifier,
                status="success",
                account_id=account_id,
                file_hash=video_id,
                output_path=str(folder_path),
            )

            # Send success notification
            self.notification_manager.notify_video_success(
                video_id=video_id,
                title=analysis.get("title", download_result.title),
                channel=download_result.channel,
                duration=download_result.duration,
                output_folder=folder_path.name,
                tags=tags,
                transcription_source=transcript_result.source,
                summary_excerpt=analysis.get("summary", "")[:300],
                account=account_email or account_id,
            )

            # Cleanup temp files
            self.audio_downloader.cleanup(video_id)

            logger.info(
                f"Successfully processed video: {download_result.title} "
                f"(took {total_duration / 1000:.1f}s)"
            )

            return True, folder_path.name, video_id

        except Exception as e:
            error_msg = str(e)
            stack_trace = traceback.format_exc()
            logger.error(f"Error processing job {job_filename}: {error_msg}")

            # Log error
            if video_id:
                self.log_writer.write_error_log(
                    video_id=video_id,
                    error_type=type(e).__name__,
                    error_message=error_msg,
                    stack_trace=stack_trace,
                    context={"url": url, "job_file": job_filename},
                )

            # Mark as error
            self.processed_db.mark_processed(
                file_path=job_identifier,
                status="error",
                account_id=account_id,
                error_message=error_msg,
            )

            # Send error notification
            self.notification_manager.notify_error(
                video_id=video_id or "unknown",
                url=url or job_content[:100],
                error_message=error_msg,
                account=account_email or account_id,
            )

            # Cleanup on error
            if video_id:
                self.audio_downloader.cleanup(video_id)

            return False, None, video_id

    @staticmethod
    def is_job_file(file_path: str) -> bool:
        """Check if a file is a valid job file.

        Args:
            file_path: Path to file

        Returns:
            True if file is a .txt job file
        """
        return Path(file_path).suffix.lower() == ".txt"

