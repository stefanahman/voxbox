"""Local folder watcher for development mode."""

import logging
import time
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

from .job_processor import JobProcessor

logger = logging.getLogger(__name__)


class JobFileHandler(FileSystemEventHandler):
    """Handler for new job files in watch directory."""

    def __init__(self, job_processor: JobProcessor, archive_dir: Path):
        """Initialize file handler.

        Args:
            job_processor: Job processor instance
            archive_dir: Directory to move processed files to
        """
        super().__init__()
        self.job_processor = job_processor
        self.archive_dir = archive_dir
        self.processing = set()  # Track files being processed

    def on_created(self, event):
        """Handle file creation events.

        Args:
            event: File system event
        """
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Check if it's a job file (.txt)
        if not self.job_processor.is_job_file(str(file_path)):
            return

        # Avoid duplicate processing
        if str(file_path) in self.processing:
            return

        self.processing.add(str(file_path))

        try:
            # Wait a bit to ensure file is fully written
            time.sleep(0.5)

            # Read job content
            with open(file_path, "r", encoding="utf-8") as f:
                job_content = f.read()

            # Process the job
            logger.info(f"New job file detected: {file_path.name}")

            success, output_folder, video_id = self.job_processor.process_job_file(
                job_content=job_content,
                job_filename=file_path.name,
                job_identifier=f"local:{file_path.absolute()}",
                account_id="local",
                account_email="local",
            )

            if success:
                # Move job file to archive
                archive_path = self.archive_dir / file_path.name
                file_path.rename(archive_path)
                logger.info(f"Moved job file to archive: {archive_path}")

        except Exception as e:
            logger.error(f"Error handling new file {file_path}: {e}")

        finally:
            self.processing.discard(str(file_path))


class LocalFolderWatcher:
    """Watches local folder for new job files."""

    def __init__(
        self,
        inbox_dir: str,
        archive_dir: str,
        job_processor: JobProcessor,
    ):
        """Initialize local folder watcher.

        Args:
            inbox_dir: Inbox directory to watch for new files
            archive_dir: Archive directory for processed files
            job_processor: Job processor instance
        """
        self.inbox_dir = Path(inbox_dir)
        self.archive_dir = Path(archive_dir)
        self.job_processor = job_processor
        self.observer = None

        # Ensure directories exist
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized local folder watcher for: {self.inbox_dir}")

    def process_existing_files(self):
        """Process any existing job files in the inbox directory."""
        logger.info("Checking for existing job files in inbox directory...")

        processed_count = 0
        for file_path in self.inbox_dir.iterdir():
            if file_path.is_file() and self.job_processor.is_job_file(str(file_path)):
                try:
                    # Read job content
                    with open(file_path, "r", encoding="utf-8") as f:
                        job_content = f.read()

                    success, _, _ = self.job_processor.process_job_file(
                        job_content=job_content,
                        job_filename=file_path.name,
                        job_identifier=f"local:{file_path.absolute()}",
                        account_id="local",
                        account_email="local",
                    )

                    if success:
                        # Move to archive
                        archive_path = self.archive_dir / file_path.name
                        file_path.rename(archive_path)
                        processed_count += 1

                except Exception as e:
                    logger.error(f"Error processing existing file {file_path.name}: {e}")

        if processed_count > 0:
            logger.info(f"Processed {processed_count} existing job file(s)")
        else:
            logger.info("No existing job files to process")

    def start(self):
        """Start watching the inbox folder."""
        # Process existing files first
        self.process_existing_files()

        # Set up file system observer
        event_handler = JobFileHandler(self.job_processor, self.archive_dir)
        self.observer = Observer()
        self.observer.schedule(event_handler, str(self.inbox_dir), recursive=False)
        self.observer.start()

        logger.info(f"Started watching inbox: {self.inbox_dir}")
        logger.info("Waiting for new .txt job files in Inbox...")

    def stop(self):
        """Stop watching the folder."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("Stopped local folder watcher")

    def run(self):
        """Run the watcher (blocking)."""
        self.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.stop()

