"""Storage management for OAuth tokens (JSON) and processed files (SQLite)."""

import os
import json
import sqlite3
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class TokenStorage:
    """Manages OAuth tokens as JSON files, one per user."""

    def __init__(self, tokens_dir: str):
        """Initialize token storage.

        Args:
            tokens_dir: Directory to store token JSON files
        """
        self.tokens_dir = Path(tokens_dir)
        self.tokens_dir.mkdir(parents=True, exist_ok=True)

        # Set restrictive permissions on tokens directory
        try:
            os.chmod(self.tokens_dir, 0o700)
        except Exception as e:
            logger.warning(f"Could not set permissions on tokens directory: {e}")

    def _get_token_path(self, account_id: str) -> Path:
        """Get path to token file for an account.

        Args:
            account_id: Dropbox account ID

        Returns:
            Path to token JSON file
        """
        # Sanitize account ID for filename
        safe_id = account_id.replace(":", "_").replace("/", "_")
        return self.tokens_dir / f"{safe_id}.json"

    def save_token(self, token_data: Dict[str, Any]) -> None:
        """Save or update token data for a user.

        Args:
            token_data: Dictionary containing:
                - account_id: Dropbox account ID
                - account_email: User's email
                - access_token: OAuth access token
                - refresh_token: OAuth refresh token (optional)
                - expires_at: Token expiration timestamp (optional)
        """
        account_id = token_data.get("account_id")
        if not account_id:
            raise ValueError("account_id is required in token_data")

        token_path = self._get_token_path(account_id)

        # Add timestamp
        token_data["updated_at"] = datetime.utcnow().isoformat()
        if "authorized_at" not in token_data:
            token_data["authorized_at"] = token_data["updated_at"]

        # Write token file
        with open(token_path, "w") as f:
            json.dump(token_data, f, indent=2)

        # Set restrictive permissions
        try:
            os.chmod(token_path, 0o600)
        except Exception as e:
            logger.warning(f"Could not set permissions on token file: {e}")

        logger.info(f"Saved token for account: {account_id}")

    def load_token(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Load token data for a user.

        Args:
            account_id: Dropbox account ID

        Returns:
            Token data dictionary or None if not found
        """
        token_path = self._get_token_path(account_id)

        if not token_path.exists():
            return None

        try:
            with open(token_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading token for {account_id}: {e}")
            return None

    def delete_token(self, account_id: str) -> bool:
        """Delete token for a user.

        Args:
            account_id: Dropbox account ID

        Returns:
            True if deleted, False if not found
        """
        token_path = self._get_token_path(account_id)

        if token_path.exists():
            token_path.unlink()
            logger.info(f"Deleted token for account: {account_id}")
            return True
        return False

    def list_accounts(self) -> List[str]:
        """List all authorized account IDs.

        Returns:
            List of account IDs
        """
        accounts = []
        for token_file in self.tokens_dir.glob("*.json"):
            try:
                with open(token_file, "r") as f:
                    data = json.load(f)
                    if "account_id" in data:
                        accounts.append(data["account_id"])
            except Exception as e:
                logger.warning(f"Error reading token file {token_file}: {e}")
        return accounts

    def get_all_tokens(self) -> List[Dict[str, Any]]:
        """Get all stored tokens.

        Returns:
            List of token data dictionaries
        """
        tokens = []
        for account_id in self.list_accounts():
            token = self.load_token(account_id)
            if token:
                tokens.append(token)
        return tokens


class ProcessedFilesDB:
    """SQLite database for tracking processed files (idempotency)."""

    def __init__(self, db_path: str):
        """Initialize processed files database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create database schema if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL UNIQUE,
                    file_hash TEXT,
                    account_id TEXT,
                    processed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    output_path TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_file_path
                ON processed_files(file_path)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_account_id
                ON processed_files(account_id)
            """)
            conn.commit()
        logger.info("Initialized processed files database")

    def is_processed(self, file_path: str) -> bool:
        """Check if a file has been processed.

        Args:
            file_path: Path or identifier of the file

        Returns:
            True if file has been processed successfully
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT status FROM processed_files WHERE file_path = ?",
                (file_path,),
            )
            result = cursor.fetchone()
            return result is not None and result[0] == "success"

    def mark_processed(
        self,
        file_path: str,
        status: str,
        account_id: Optional[str] = None,
        file_hash: Optional[str] = None,
        error_message: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> None:
        """Mark a file as processed.

        Args:
            file_path: Path or identifier of the file
            status: Processing status ('success', 'error', 'skipped')
            account_id: Dropbox account ID (for multi-tenant tracking)
            file_hash: File content hash (for duplicate detection)
            error_message: Error message if status is 'error'
            output_path: Path to output file if status is 'success'
        """
        processed_at = datetime.utcnow().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_files
                (file_path, file_hash, account_id, processed_at, status, error_message, output_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    file_path,
                    file_hash,
                    account_id,
                    processed_at,
                    status,
                    error_message,
                    output_path,
                ),
            )
            conn.commit()

        logger.debug(f"Marked file as processed: {file_path} (status: {status})")

    def get_stats(self, account_id: Optional[str] = None) -> Dict[str, int]:
        """Get processing statistics.

        Args:
            account_id: Optional account ID to filter stats

        Returns:
            Dictionary with counts by status
        """
        with sqlite3.connect(self.db_path) as conn:
            if account_id:
                cursor = conn.execute(
                    """
                    SELECT status, COUNT(*)
                    FROM processed_files
                    WHERE account_id = ?
                    GROUP BY status
                """,
                    (account_id,),
                )
            else:
                cursor = conn.execute("""
                    SELECT status, COUNT(*)
                    FROM processed_files
                    GROUP BY status
                """)

            stats = {row[0]: row[1] for row in cursor.fetchall()}
            return stats

