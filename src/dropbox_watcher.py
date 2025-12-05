"""Dropbox App Folder watcher for video processing jobs."""

import logging
import time
from typing import Dict, Optional, List

import dropbox
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import FileMetadata

from .storage import TokenStorage
from .job_processor import JobProcessor
from .dropbox_oauth import OAuthManager

logger = logging.getLogger(__name__)


class DropboxWatcher:
    """Watches Dropbox App Folders for new job files (.txt with YouTube URLs)."""

    def __init__(
        self,
        token_storage: TokenStorage,
        job_processor: JobProcessor,
        oauth_manager: OAuthManager,
        poll_interval: int = 30,
    ):
        """Initialize Dropbox watcher.

        Args:
            token_storage: Token storage instance
            job_processor: Job processor instance
            oauth_manager: OAuth manager for token refresh
            poll_interval: Seconds between polling for new files
        """
        self.token_storage = token_storage
        self.job_processor = job_processor
        self.oauth_manager = oauth_manager
        self.poll_interval = poll_interval

        # Track cursors for each account (for delta sync)
        self.cursors: Dict[str, Optional[str]] = {}

        # Track initialized accounts (to avoid re-creating folders)
        self.initialized_accounts = set()

        logger.info("Initialized Dropbox watcher for VoxBox")

    def get_dropbox_client(self, account_id: str) -> Optional[dropbox.Dropbox]:
        """Get authenticated Dropbox client for an account.

        Args:
            account_id: Dropbox account ID

        Returns:
            Dropbox client or None if token invalid
        """
        token_data = self.token_storage.load_token(account_id)

        if not token_data:
            logger.error(f"No token found for account: {account_id}")
            return None

        try:
            dbx = dropbox.Dropbox(token_data["access_token"])
            # Test the connection
            dbx.users_get_current_account()
            return dbx

        except AuthError:
            logger.warning(
                f"Token expired for account {account_id}, attempting refresh..."
            )

            # Try to refresh token
            if self.oauth_manager.refresh_token(account_id):
                # Try again with refreshed token
                token_data = self.token_storage.load_token(account_id)
                dbx = dropbox.Dropbox(token_data["access_token"])
                return dbx
            else:
                logger.error(f"Failed to refresh token for account: {account_id}")
                return None

        except Exception as e:
            logger.error(f"Error creating Dropbox client for {account_id}: {e}")
            return None

    def list_new_files(self, account_id: str) -> List[FileMetadata]:
        """List new .txt job files in the App Folder's Inbox.

        Args:
            account_id: Dropbox account ID

        Returns:
            List of new file metadata
        """
        dbx = self.get_dropbox_client(account_id)

        if not dbx:
            return []

        try:
            new_files = []
            cursor = self.cursors.get(account_id)

            if cursor:
                # Get changes since last check
                result = dbx.files_list_folder_continue(cursor)
            else:
                # First time - list all files in Inbox
                result = dbx.files_list_folder("/Inbox", recursive=False)

            # Update cursor for next time
            self.cursors[account_id] = result.cursor

            # Collect new .txt files from /Inbox/
            for entry in result.entries:
                if isinstance(entry, FileMetadata):
                    if self.job_processor.is_job_file(entry.path_lower):
                        new_files.append(entry)

            # Handle pagination
            while result.has_more:
                result = dbx.files_list_folder_continue(result.cursor)
                self.cursors[account_id] = result.cursor

                for entry in result.entries:
                    if isinstance(entry, FileMetadata):
                        if self.job_processor.is_job_file(entry.path_lower):
                            new_files.append(entry)

            return new_files

        except ApiError as e:
            # Handle case where /Inbox doesn't exist yet
            if "path/not_found" in str(e):
                logger.debug(f"Inbox folder not found for account {account_id}")
                return []
            logger.error(f"Dropbox API error for account {account_id}: {e}")
            return []

        except Exception as e:
            logger.error(f"Error listing files for account {account_id}: {e}")
            return []

    def download_and_process_file(
        self, account_id: str, account_email: str, file_metadata: FileMetadata
    ) -> bool:
        """Download and process a job file from Dropbox.

        Args:
            account_id: Dropbox account ID
            account_email: User's email
            file_metadata: File metadata from Dropbox

        Returns:
            True if processed successfully
        """
        dbx = self.get_dropbox_client(account_id)

        if not dbx:
            return False

        try:
            # Download file
            logger.info(f"Downloading job file from Dropbox: {file_metadata.name}")
            metadata, response = dbx.files_download(file_metadata.path_lower)
            job_content = response.content.decode("utf-8")

            # Create unique identifier for idempotency
            file_identifier = f"dropbox:{account_id}:{file_metadata.id}"

            # Process job
            success, output_folder, video_id = self.job_processor.process_job_file(
                job_content=job_content,
                job_filename=file_metadata.name,
                job_identifier=file_identifier,
                account_id=account_id,
                account_email=account_email,
            )

            if success and output_folder:
                # Upload the output folder to Dropbox /Outbox/
                self.upload_output_folder(dbx, output_folder)

                # Move the processed job file to /Archive/
                self.move_to_archive(dbx, file_metadata)

            return success

        except Exception as e:
            logger.error(
                f"Error downloading/processing file {file_metadata.name}: {e}"
            )
            return False

    def upload_output_folder(self, dbx: dropbox.Dropbox, folder_name: str) -> bool:
        """Upload output folder contents to Dropbox /Outbox/.

        Args:
            dbx: Dropbox client
            folder_name: Name of the local output folder

        Returns:
            True if uploaded successfully
        """
        try:
            from pathlib import Path

            local_folder = Path(self.job_processor.outbox_dir) / folder_name
            dropbox_folder = f"/Outbox/{folder_name}"

            # Create folder in Dropbox
            try:
                dbx.files_create_folder_v2(dropbox_folder)
            except ApiError as e:
                if "conflict" not in str(e).lower():
                    raise

            # Upload each file in the folder
            for file_path in local_folder.iterdir():
                if file_path.is_file():
                    dropbox_path = f"{dropbox_folder}/{file_path.name}"

                    with open(file_path, "rb") as f:
                        dbx.files_upload(
                            f.read(),
                            dropbox_path,
                            mode=dropbox.files.WriteMode.overwrite,
                        )

                    logger.debug(f"Uploaded to Dropbox: {dropbox_path}")

            logger.info(f"Uploaded output folder to Dropbox: {dropbox_folder}")
            return True

        except Exception as e:
            logger.error(f"Error uploading output folder to Dropbox: {e}")
            return False

    def move_to_archive(self, dbx: dropbox.Dropbox, file_metadata: FileMetadata) -> bool:
        """Move processed job file to /Archive/ folder.

        Args:
            dbx: Dropbox client
            file_metadata: Original file metadata

        Returns:
            True if moved successfully
        """
        try:
            dest_path = f"/Archive/{file_metadata.name}"

            dbx.files_move_v2(
                file_metadata.path_lower,
                dest_path,
                autorename=True,
            )

            logger.info(f"Moved processed job to: {dest_path}")
            return True

        except Exception as e:
            logger.error(f"Error moving file to archive: {e}")
            return False

    def initialize_folder_structure(self, account_id: str) -> bool:
        """Initialize required folder structure in Dropbox App Folder.

        Creates:
        - /Inbox/ - For job files (YouTube URLs)
        - /Outbox/ - For processed notes and audio
        - /Archive/ - For processed job files
        - /Logs/ - For processing logs

        Args:
            account_id: Dropbox account ID

        Returns:
            True if initialization successful
        """
        if account_id in self.initialized_accounts:
            return True

        dbx = self.get_dropbox_client(account_id)

        if not dbx:
            return False

        folders_to_create = ["/Inbox", "/Outbox", "/Archive", "/Logs"]

        try:
            for folder_path in folders_to_create:
                try:
                    dbx.files_create_folder_v2(folder_path)
                    logger.info(f"Created folder: {folder_path}")
                except ApiError as e:
                    if "conflict" not in str(e).lower():
                        logger.warning(f"Could not create folder {folder_path}: {e}")

            # Create default tags.txt
            default_tags = "\n".join(
                [
                    "education",
                    "tutorial",
                    "podcast",
                    "interview",
                    "documentary",
                    "entertainment",
                    "technology",
                    "science",
                    "business",
                    "health",
                ]
            )

            try:
                dbx.files_upload(
                    default_tags.encode("utf-8"),
                    "/Outbox/tags.txt",
                    mode=dropbox.files.WriteMode.add,
                )
                logger.info("Created default tags.txt")
            except ApiError as e:
                if "conflict" not in str(e).lower():
                    logger.warning(f"Could not create tags.txt: {e}")

            # Create README
            readme_content = """# VoxBox - Video to Obsidian Knowledge Pipeline

This is your VoxBox App Folder. Here's how it works:

## Folder Structure
- **/Inbox/** - Drop .txt files containing YouTube URLs here
- **/Outbox/** - Processed notes and audio appear here
- **/Archive/** - Processed job files are moved here
- **/Logs/** - Processing logs

## Usage
1. Create a .txt file with a YouTube URL (just paste the URL)
2. Upload it to /Inbox/
3. VoxBox processes it automatically
4. Find your note in /Outbox/YYYY-MM-DD_Video_Title/
   - audio.mp3 - The audio file
   - Video_Title.md - Obsidian note with summary and transcript

## Tags
Edit /Outbox/tags.txt to customize available tags for categorization.

---
Powered by VoxBox - Video to Obsidian Knowledge Pipeline
"""

            try:
                dbx.files_upload(
                    readme_content.encode("utf-8"),
                    "/README.txt",
                    mode=dropbox.files.WriteMode.add,
                )
                logger.info("Created README.txt")
            except ApiError:
                pass

            self.initialized_accounts.add(account_id)

            token_data = self.token_storage.load_token(account_id)
            account_email = (
                token_data.get("account_email", account_id) if token_data else account_id
            )
            logger.info(f"Initialized folder structure for: {account_email}")

            return True

        except Exception as e:
            logger.error(f"Error initializing folder structure: {e}")
            return False

    def process_account(self, account_id: str) -> int:
        """Process all new job files for a single account.

        Args:
            account_id: Dropbox account ID

        Returns:
            Number of files processed
        """
        token_data = self.token_storage.load_token(account_id)

        if not token_data:
            logger.warning(f"No token data for account: {account_id}")
            return 0

        account_email = token_data.get("account_email", account_id)

        # Initialize folder structure on first poll
        if account_id not in self.initialized_accounts:
            self.initialize_folder_structure(account_id)

        # List new files
        new_files = self.list_new_files(account_id)

        if not new_files:
            return 0

        logger.info(f"Found {len(new_files)} new job file(s) for {account_email}")

        # Process each file
        processed_count = 0
        for file_metadata in new_files:
            try:
                if self.download_and_process_file(
                    account_id, account_email, file_metadata
                ):
                    processed_count += 1
            except Exception as e:
                logger.error(f"Error processing file {file_metadata.name}: {e}")

        return processed_count

    def poll_once(self) -> int:
        """Poll all accounts once for new files.

        Returns:
            Total number of files processed
        """
        accounts = self.token_storage.list_accounts()

        if not accounts:
            logger.debug("No authorized accounts to poll")
            return 0

        logger.debug(f"Polling {len(accounts)} account(s) for new job files...")

        total_processed = 0
        for account_id in accounts:
            try:
                count = self.process_account(account_id)
                total_processed += count
            except Exception as e:
                logger.error(f"Error polling account {account_id}: {e}")

        return total_processed

    def run(self):
        """Run the watcher (blocking)."""
        logger.info(f"Started Dropbox watcher (polling every {self.poll_interval}s)")

        accounts = self.token_storage.list_accounts()
        if not accounts:
            logger.warning(
                "No authorized Dropbox accounts found. "
                "Please complete OAuth authorization first."
            )
        else:
            logger.info(f"Monitoring {len(accounts)} authorized account(s)")

        try:
            while True:
                self.poll_once()
                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Watcher error: {e}")
            raise

