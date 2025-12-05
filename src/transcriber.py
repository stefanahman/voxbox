"""Transcription with YouTube captions priority and Whisper fallback."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import webvtt

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    """A single segment of transcript with timing."""

    start: float  # seconds
    end: float  # seconds
    text: str


@dataclass
class TranscriptResult:
    """Result of transcription."""

    segments: List[TranscriptSegment]
    source: str  # "youtube_manual", "youtube_auto", "whisper"
    language: Optional[str] = None

    @property
    def full_text(self) -> str:
        """Get full transcript as plain text."""
        return " ".join(seg.text for seg in self.segments)

    def format_with_timestamps(self, interval_seconds: int = 60) -> str:
        """Format transcript with periodic timestamps.

        Args:
            interval_seconds: Insert timestamp every N seconds

        Returns:
            Formatted transcript with timestamps
        """
        if not self.segments:
            return ""

        lines = []
        last_timestamp = -interval_seconds  # Ensure first timestamp is shown

        for segment in self.segments:
            # Add timestamp if enough time has passed
            if segment.start - last_timestamp >= interval_seconds:
                timestamp = self._format_timestamp(segment.start)
                lines.append(f"\n({timestamp})")
                last_timestamp = segment.start

            lines.append(segment.text)

        return " ".join(lines).strip()

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """Format seconds as MM:SS or HH:MM:SS."""
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"


class Transcriber:
    """Handles transcription with YouTube captions and Whisper fallback."""

    def __init__(self, whisper_model: str = "base"):
        """Initialize transcriber.

        Args:
            whisper_model: Whisper model size for fallback transcription
        """
        self.whisper_model = whisper_model
        self._whisper_model_instance = None

    def transcribe(
        self,
        audio_path: str,
        caption_path: Optional[str] = None,
        caption_source: Optional[str] = None,
    ) -> TranscriptResult:
        """Transcribe audio, preferring YouTube captions if available.

        Args:
            audio_path: Path to audio file (MP3)
            caption_path: Path to caption file (.vtt) if available
            caption_source: Source of captions ("manual" or "auto")

        Returns:
            TranscriptResult with segments and source info
        """
        # Try YouTube captions first
        if caption_path and Path(caption_path).exists():
            logger.info(f"Using YouTube captions ({caption_source}): {caption_path}")
            try:
                result = self._parse_vtt_captions(caption_path)
                result.source = f"youtube_{caption_source}" if caption_source else "youtube"
                return result
            except Exception as e:
                logger.warning(f"Failed to parse captions, falling back to Whisper: {e}")

        # Fallback to Whisper
        logger.info(f"Using Whisper ({self.whisper_model}) for transcription")
        return self._transcribe_with_whisper(audio_path)

    def _parse_vtt_captions(self, vtt_path: str) -> TranscriptResult:
        """Parse VTT caption file into transcript segments.

        Args:
            vtt_path: Path to .vtt file

        Returns:
            TranscriptResult with parsed segments
        """
        segments = []

        try:
            captions = webvtt.read(vtt_path)

            for caption in captions:
                # Parse timestamps
                start = self._vtt_time_to_seconds(caption.start)
                end = self._vtt_time_to_seconds(caption.end)

                # Clean text (remove HTML tags, extra whitespace)
                text = self._clean_caption_text(caption.text)

                if text:  # Skip empty segments
                    segments.append(TranscriptSegment(start=start, end=end, text=text))

            # Merge duplicate/overlapping segments (common in auto-captions)
            segments = self._merge_segments(segments)

            logger.info(f"Parsed {len(segments)} caption segments from VTT")

        except Exception as e:
            logger.error(f"Error parsing VTT file: {e}")
            raise

        return TranscriptResult(segments=segments, source="youtube")

    @staticmethod
    def _vtt_time_to_seconds(time_str: str) -> float:
        """Convert VTT timestamp to seconds.

        Args:
            time_str: Timestamp in format "HH:MM:SS.mmm" or "MM:SS.mmm"

        Returns:
            Time in seconds as float
        """
        parts = time_str.replace(",", ".").split(":")

        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        elif len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)
        else:
            return float(time_str)

    @staticmethod
    def _clean_caption_text(text: str) -> str:
        """Clean caption text by removing HTML tags and normalizing whitespace.

        Args:
            text: Raw caption text

        Returns:
            Cleaned text
        """
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Remove speaker labels like "[Music]" or "(applause)"
        text = re.sub(r"\[[^\]]*\]", "", text)
        text = re.sub(r"\([^)]*\)", "", text)

        # Normalize whitespace
        text = " ".join(text.split())

        return text.strip()

    @staticmethod
    def _merge_segments(segments: List[TranscriptSegment]) -> List[TranscriptSegment]:
        """Merge adjacent segments with identical or overlapping text.

        YouTube auto-captions often have overlapping/duplicate segments.

        Args:
            segments: List of transcript segments

        Returns:
            Merged segments with duplicates removed
        """
        if not segments:
            return []

        merged = []
        seen_texts = set()

        for segment in segments:
            # Clean and normalize text for comparison
            clean_text = segment.text.strip().lower()

            # Skip empty or duplicate segments
            if not clean_text or clean_text in seen_texts:
                continue

            # Check if this is a substring of the previous segment or vice versa
            if merged:
                last = merged[-1]
                last_clean = last.text.strip().lower()

                # Skip if current is subset of previous
                if clean_text in last_clean:
                    continue

                # If previous is subset of current, replace it
                if last_clean in clean_text:
                    merged[-1] = segment
                    seen_texts.discard(last_clean)
                    seen_texts.add(clean_text)
                    continue

            merged.append(segment)
            seen_texts.add(clean_text)

        return merged

    def _transcribe_with_whisper(self, audio_path: str) -> TranscriptResult:
        """Transcribe audio using faster-whisper.

        Args:
            audio_path: Path to audio file

        Returns:
            TranscriptResult with Whisper segments
        """
        try:
            from faster_whisper import WhisperModel

            # Lazy load model
            if self._whisper_model_instance is None:
                logger.info(f"Loading Whisper model: {self.whisper_model}")
                self._whisper_model_instance = WhisperModel(
                    self.whisper_model,
                    device="cpu",
                    compute_type="int8",
                )

            logger.info(f"Transcribing with Whisper: {audio_path}")
            segments_iter, info = self._whisper_model_instance.transcribe(
                audio_path,
                beam_size=5,
                word_timestamps=False,
                vad_filter=True,
            )

            segments = []
            for segment in segments_iter:
                segments.append(
                    TranscriptSegment(
                        start=segment.start,
                        end=segment.end,
                        text=segment.text.strip(),
                    )
                )

            logger.info(
                f"Whisper transcription complete: {len(segments)} segments, "
                f"language: {info.language}"
            )

            return TranscriptResult(
                segments=segments,
                source="whisper",
                language=info.language,
            )

        except ImportError:
            logger.error(
                "faster-whisper not installed. "
                "Install with: pip install faster-whisper"
            )
            raise
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            raise

