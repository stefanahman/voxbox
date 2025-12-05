"""Notification system for video processing results."""

import logging
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)


class NotificationProvider(ABC):
    """Abstract base class for notification providers."""

    @abstractmethod
    def send(self, message: str, **kwargs) -> bool:
        """Send a notification message.

        Args:
            message: Message text
            **kwargs: Additional provider-specific parameters

        Returns:
            True if sent successfully, False otherwise
        """
        pass


class TelegramNotification(NotificationProvider):
    """Telegram notification provider."""

    def __init__(self, bot_token: str, chat_id: str):
        """Initialize Telegram notifier.

        Args:
            bot_token: Telegram bot token
            chat_id: Target chat ID
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send(self, message: str, parse_mode: str = "HTML", **kwargs) -> bool:
        """Send a message via Telegram.

        Args:
            message: Message text
            parse_mode: Message parsing mode (HTML or Markdown)
            **kwargs: Additional parameters

        Returns:
            True if sent successfully
        """
        try:
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode,
            }

            response = requests.post(self.api_url, json=payload, timeout=10)
            response.raise_for_status()

            logger.debug("Telegram notification sent successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False


class EmailNotification(NotificationProvider):
    """Email notification provider."""

    def __init__(self, smtp_config: Dict[str, Any]):
        """Initialize email notifier.

        Args:
            smtp_config: Dictionary with SMTP configuration
        """
        self.smtp_host = smtp_config["smtp_host"]
        self.smtp_port = smtp_config["smtp_port"]
        self.username = smtp_config["username"]
        self.password = smtp_config["password"]
        self.from_address = smtp_config["from_address"]
        self.to_address = smtp_config["to_address"]

    def send(
        self, message: str, subject: str = "VoxBox Notification", **kwargs
    ) -> bool:
        """Send an email notification.

        Args:
            message: Message text
            subject: Email subject
            **kwargs: Additional parameters

        Returns:
            True if sent successfully
        """
        try:
            msg = MIMEMultipart()
            msg["From"] = self.from_address
            msg["To"] = self.to_address
            msg["Subject"] = subject

            msg.attach(MIMEText(message, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.debug("Email notification sent successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return False


class NotificationManager:
    """Manages multiple notification providers."""

    def __init__(self):
        """Initialize notification manager."""
        self.providers: List[NotificationProvider] = []

    def add_provider(self, provider: NotificationProvider):
        """Add a notification provider.

        Args:
            provider: Notification provider instance
        """
        self.providers.append(provider)
        logger.info(f"Added notification provider: {provider.__class__.__name__}")

    def notify_video_success(
        self,
        video_id: str,
        title: str,
        channel: str,
        duration: int,
        output_folder: str,
        tags: List[Dict[str, Any]],
        transcription_source: str,
        summary_excerpt: str,
        account: Optional[str] = None,
    ) -> None:
        """Send video processing success notification.

        Args:
            video_id: YouTube video ID
            title: Video title
            channel: Channel name
            duration: Video duration in seconds
            output_folder: Output folder name
            tags: List of tag dictionaries
            transcription_source: Source of transcript
            summary_excerpt: Short excerpt from summary
            account: Account identifier
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Format duration
        duration_str = f"{duration // 60}m {duration % 60}s"

        # Format tags
        tags_list = []
        for tag in tags:
            name = tag.get("name", "unknown")
            confidence = tag.get("confidence", 0)
            is_primary = tag.get("primary", False)
            emoji = "⭐" if is_primary else ""
            tags_list.append(f"  • {name} ({confidence}%) {emoji}")

        # Build message
        message_parts = [
            "✅ <b>Video Processed Successfully</b>",
            "",
            f"<b>Title:</b> {title}",
            f"<b>Channel:</b> {channel}",
            f"<b>Duration:</b> {duration_str}",
            f"<b>Time:</b> {timestamp}",
        ]

        if account:
            message_parts.append(f"<b>Account:</b> {account}")

        message_parts.extend(
            [
                "",
                f"<b>Transcript Source:</b> {transcription_source}",
                f"<b>Output:</b> {output_folder}",
                "",
                "<b>Tags:</b>",
                *tags_list,
                "",
                "<b>Summary Preview:</b>",
                f"<code>{summary_excerpt[:300]}...</code>",
            ]
        )

        message = "\n".join(message_parts)

        for provider in self.providers:
            provider.send(message)

    def notify_error(
        self,
        video_id: str,
        url: str,
        error_message: str,
        account: Optional[str] = None,
    ) -> None:
        """Send error notification.

        Args:
            video_id: YouTube video ID
            url: Video URL
            error_message: Error message
            account: Account identifier
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message_parts = [
            "❌ <b>Video Processing Failed</b>",
            "",
            f"<b>Video ID:</b> {video_id}",
            f"<b>URL:</b> {url}",
            f"<b>Time:</b> {timestamp}",
        ]

        if account:
            message_parts.append(f"<b>Account:</b> {account}")

        message_parts.extend(
            [
                "",
                "<b>Error:</b>",
                f"<code>{error_message}</code>",
            ]
        )

        message = "\n".join(message_parts)

        for provider in self.providers:
            provider.send(message)

    def notify_processing_started(
        self,
        video_id: str,
        title: str,
        account: Optional[str] = None,
    ) -> None:
        """Send processing started notification (optional).

        Args:
            video_id: YouTube video ID
            title: Video title
            account: Account identifier
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message = f"🎬 <b>Processing Started</b>\n\n<b>Title:</b> {title}\n<b>ID:</b> {video_id}\n<b>Time:</b> {timestamp}"

        if account:
            message += f"\n<b>Account:</b> {account}"

        for provider in self.providers:
            provider.send(message)

