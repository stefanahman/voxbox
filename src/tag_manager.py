"""Tag management system for VoxBox."""

import logging
import re
from pathlib import Path
from typing import List, Set, Optional

logger = logging.getLogger(__name__)

# Default tags for video content
DEFAULT_TAGS = [
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
    "fitness",
    "meditation",
    "music",
    "cooking",
    "travel",
    "news",
    "review",
    "howto",
    "motivation",
    "finance",
]


class TagManager:
    """Manages tags from tags.txt and learns from existing filenames."""

    def __init__(
        self,
        outbox_dir: str,
        tags_file_path: Optional[str] = None,
        enable_learning: bool = True,
    ):
        """Initialize tag manager.

        Args:
            outbox_dir: Path to outbox directory
            tags_file_path: Path to tags.txt file (defaults to outbox / tags.txt)
            enable_learning: Whether to learn tags from existing folder names
        """
        self.outbox_dir = Path(outbox_dir)
        self.enable_learning = enable_learning

        # tags.txt in outbox directory
        if tags_file_path:
            self.tags_file = Path(tags_file_path)
        else:
            self.tags_file = self.outbox_dir / "tags.txt"

        # Ensure outbox directory exists
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

        # Create default tags.txt if it doesn't exist
        if not self.tags_file.exists():
            self._create_default_tags_file()

    def _create_default_tags_file(self):
        """Create tags.txt with default tags."""
        try:
            with open(self.tags_file, "w", encoding="utf-8") as f:
                f.write("\n".join(DEFAULT_TAGS))
            logger.info(f"Created default tags.txt with {len(DEFAULT_TAGS)} tags")
        except Exception as e:
            logger.error(f"Error creating tags.txt: {e}")

    def _load_tags_from_file(self) -> Set[str]:
        """Load tags from tags.txt file.

        Returns:
            Set of tag names
        """
        tags = set()

        if not self.tags_file.exists():
            logger.warning(f"tags.txt not found at {self.tags_file}")
            return tags

        try:
            with open(self.tags_file, "r", encoding="utf-8") as f:
                for line in f:
                    tag = line.strip().lower()
                    if tag and self._is_valid_tag(tag):
                        tags.add(tag)

            logger.debug(f"Loaded {len(tags)} tags from tags.txt")
            return tags

        except Exception as e:
            logger.error(f"Error loading tags.txt: {e}")
            return tags

    def _learn_tags_from_folders(self) -> Set[str]:
        """Learn tags from existing folder names in outbox.

        Scans for patterns in markdown frontmatter or folder names.

        Returns:
            Set of learned tag names
        """
        if not self.enable_learning:
            return set()

        learned_tags = set()

        try:
            for folder in self.outbox_dir.iterdir():
                if not folder.is_dir():
                    continue

                # Look for markdown files in folders
                for md_file in folder.glob("*.md"):
                    try:
                        with open(md_file, "r", encoding="utf-8") as f:
                            content = f.read(2000)  # Just read frontmatter area

                        # Extract tags from YAML frontmatter
                        if content.startswith("---"):
                            frontmatter_end = content.find("---", 3)
                            if frontmatter_end > 0:
                                frontmatter = content[3:frontmatter_end]
                                # Find tags section
                                tags_match = re.search(
                                    r"tags:\s*\n((?:\s+-\s+\w+\n?)+)", frontmatter
                                )
                                if tags_match:
                                    tag_lines = tags_match.group(1)
                                    for match in re.finditer(r"-\s+(\w+)", tag_lines):
                                        tag = match.group(1).lower()
                                        if self._is_valid_tag(tag):
                                            learned_tags.add(tag)
                    except Exception as e:
                        logger.debug(f"Could not read {md_file}: {e}")

            if learned_tags:
                logger.debug(
                    f"Learned {len(learned_tags)} tags from existing notes: {sorted(learned_tags)}"
                )

            return learned_tags

        except Exception as e:
            logger.error(f"Error learning tags from folders: {e}")
            return learned_tags

    @staticmethod
    def _is_valid_tag(tag: str) -> bool:
        """Validate tag name.

        Args:
            tag: Tag name to validate

        Returns:
            True if valid
        """
        # Must be alphanumeric + hyphens/underscores, lowercase, 2-30 chars
        if not tag or len(tag) < 2 or len(tag) > 30:
            return False

        if not re.match(r"^[a-z0-9_-]+$", tag):
            return False

        # Reserved names
        if tag in ["uncategorized", "logs", "archive", "inbox", "outbox", "temp"]:
            return False

        return True

    def get_available_tags(self) -> List[str]:
        """Get all available tags (from file + learned).

        Returns:
            Sorted list of unique tag names
        """
        # Load from tags.txt
        file_tags = self._load_tags_from_file()

        # Learn from existing folders
        learned_tags = self._learn_tags_from_folders()

        # Combine and sort
        all_tags = file_tags.union(learned_tags)

        # Always include 'uncategorized' as fallback
        all_tags.add("uncategorized")

        sorted_tags = sorted(all_tags)

        logger.debug(f"Total available tags: {len(sorted_tags)}")

        return sorted_tags

    def add_tag_to_file(self, tag: str) -> bool:
        """Add a new tag to tags.txt.

        Args:
            tag: Tag name to add

        Returns:
            True if added successfully
        """
        tag = tag.strip().lower()

        if not self._is_valid_tag(tag):
            logger.warning(f"Invalid tag name: {tag}")
            return False

        # Check if already exists
        existing_tags = self._load_tags_from_file()
        if tag in existing_tags:
            logger.debug(f"Tag already exists: {tag}")
            return True

        try:
            # Append to file
            with open(self.tags_file, "a", encoding="utf-8") as f:
                f.write(f"\n{tag}")

            logger.info(f"Added new tag to tags.txt: {tag}")
            return True

        except Exception as e:
            logger.error(f"Error adding tag to tags.txt: {e}")
            return False

