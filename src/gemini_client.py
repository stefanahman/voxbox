"""Gemini API client for video summarization and tagging."""

import logging
import time
import json
from typing import Optional, Dict, Any, List

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

logger = logging.getLogger(__name__)


class GeminiClient:
    """Client for Gemini API video summarization operations."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.5-flash",
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        """Initialize Gemini client.

        Args:
            api_key: Gemini API key
            model_name: Model to use
            max_retries: Maximum number of retry attempts
            retry_delay: Initial retry delay in seconds
        """
        self.api_key = api_key
        self.model_name = model_name
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Configure API
        genai.configure(api_key=api_key)

        # Initialize model
        self.model = genai.GenerativeModel(model_name)

        # Safety settings - be permissive for transcript content
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

        logger.info(f"Initialized Gemini client with model: {model_name}")

    def analyze_video(
        self,
        transcript: str,
        video_title: str,
        channel: str,
        available_tags: List[str],
        duration_seconds: int = 0,
    ) -> Dict[str, Any]:
        """Analyze video transcript to generate summary, takeaways, and tags.

        Args:
            transcript: Full video transcript
            video_title: Original video title
            channel: Channel name
            available_tags: List of available tags for categorization
            duration_seconds: Video duration in seconds

        Returns:
            Dictionary with title, summary, key_takeaways, and tags

        Raises:
            Exception: If analysis fails after all retries
        """
        attempt = 0
        last_error = None

        while attempt < self.max_retries:
            try:
                # Build prompt
                tags_str = ", ".join(available_tags)
                duration_str = self._format_duration(duration_seconds)

                prompt = f"""Analyze this video transcript and provide a structured summary.

VIDEO INFORMATION:
- Title: {video_title}
- Channel: {channel}
- Duration: {duration_str}

TRANSCRIPT:
{transcript[:15000]}  # Limit transcript length for API

---

Return a JSON response with:

1. "title": A clean, descriptive title for the note (use the video title as base, clean up clickbait if present, max 60 chars)

2. "summary": A 2-3 paragraph summary of the main content. Be specific about what is discussed. Write in clear, engaging prose.

3. "key_takeaways": An array of 3-5 key points or insights from the video. Each should be actionable or memorable.

4. "tags": Select 2-3 most appropriate tags from this list: [{tags_str}]
   Return as array with confidence scores:
   [
     {{"name": "tag_name", "confidence": 0-100, "primary": true/false}}
   ]
   Rules:
   - Mark ONE tag as primary (highest confidence)
   - Primary tag confidence should be ≥ 80%
   - If no tag fits well, use "uncategorized"

5. "topics": An array of 3-5 specific topics or themes discussed (these can be new, not from the tag list)

Return ONLY valid JSON, no other text."""

                # Generate content
                logger.debug(
                    f"Sending analysis request for '{video_title}' "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )

                response = self.model.generate_content(
                    prompt,
                    safety_settings=self.safety_settings,
                )

                # Parse response
                if response.text:
                    result = self._parse_response(response.text, available_tags)
                    logger.info(f"Successfully analyzed video: {video_title}")
                    return result
                else:
                    logger.warning(f"Empty response from Gemini for {video_title}")
                    return self._fallback_response(video_title)

            except Exception as e:
                last_error = e
                attempt += 1

                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"Analysis attempt {attempt} failed for '{video_title}': {e}. "
                        f"Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"All analysis attempts failed for '{video_title}': {e}"
                    )

        # All retries exhausted
        raise Exception(
            f"Failed to analyze video after {self.max_retries} attempts: {last_error}"
        )

    def _parse_response(
        self, response_text: str, available_tags: List[str]
    ) -> Dict[str, Any]:
        """Parse and validate JSON response from Gemini.

        Args:
            response_text: Raw text response from Gemini
            available_tags: List of available tags for validation

        Returns:
            Validated response dictionary
        """
        try:
            # Clean up response (remove markdown code blocks if present)
            json_str = response_text.strip()

            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]

            json_str = json_str.strip()

            # Parse JSON
            data = json.loads(json_str)

            # Validate required fields
            required = ["title", "summary", "key_takeaways", "tags"]
            for field in required:
                if field not in data:
                    logger.warning(f"Missing required field: {field}")
                    data[field] = self._get_default_value(field)

            # Validate and normalize tags
            if not isinstance(data["tags"], list) or len(data["tags"]) == 0:
                data["tags"] = [
                    {"name": "uncategorized", "confidence": 100, "primary": True}
                ]

            # Ensure at least one primary tag
            has_primary = any(tag.get("primary", False) for tag in data["tags"])
            if not has_primary and len(data["tags"]) > 0:
                data["tags"][0]["primary"] = True

            # Add topics if missing
            if "topics" not in data:
                data["topics"] = []

            return data

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return self._fallback_response("Unknown")

        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return self._fallback_response("Unknown")

    @staticmethod
    def _get_default_value(field: str) -> Any:
        """Get default value for a field."""
        defaults = {
            "title": "Untitled Video",
            "summary": "No summary available.",
            "key_takeaways": ["No key takeaways extracted."],
            "tags": [{"name": "uncategorized", "confidence": 100, "primary": True}],
            "topics": [],
        }
        return defaults.get(field, "")

    @staticmethod
    def _fallback_response(title: str) -> Dict[str, Any]:
        """Generate fallback response when parsing fails.

        Args:
            title: Video title

        Returns:
            Fallback response dictionary
        """
        return {
            "title": title,
            "summary": "Unable to generate summary.",
            "key_takeaways": ["Summary generation failed."],
            "tags": [{"name": "uncategorized", "confidence": 100, "primary": True}],
            "topics": [],
        }

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Format duration in human-readable form."""
        if seconds <= 0:
            return "Unknown"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

