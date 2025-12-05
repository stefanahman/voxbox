# VoxBox - Video to Obsidian Knowledge Pipeline

**A "Set and Forget" automation system that turns YouTube videos into structured, searchable Knowledge Assets in your Obsidian vault.**

## Features

- **YouTube Caption Priority**: Instantly extracts existing YouTube captions (manual or auto-generated) - processes most videos in seconds
- **Whisper Fallback**: Uses local faster-whisper for videos without captions
- **AI Summarization**: Google Gemini generates summaries, key takeaways, and smart tags
- **Obsidian-Ready**: Creates beautifully formatted markdown notes with YAML frontmatter
- **Dropbox Integration**: Share a YouTube URL from your iPhone, get a processed note in your vault
- **Tag Learning**: System learns from your tags and improves categorization over time

## Architecture

```
Dropbox /Inbox/          VoxBox Service                    Dropbox /Outbox/
┌─────────────┐    ┌──────────────────────────┐    ┌─────────────────────────┐
│ job_xxx.txt │───>│ URL Parser               │    │ 2024-12-05_Video_Title/ │
│ (YouTube    │    │      ↓                   │───>│   ├── audio.mp3         │
│  URL)       │    │ yt-dlp (audio + captions)│    │   └── Video_Title.md    │
└─────────────┘    │      ↓                   │    └─────────────────────────┘
                   │ Transcriber (smart)       │
                   │   1. YouTube captions     │
                   │   2. Local Whisper        │
                   │      ↓                   │
                   │ Gemini (summary + tags)   │
                   │      ↓                   │
                   │ Obsidian Formatter        │
                   └──────────────────────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Google Gemini API key ([Get one here](https://makersuite.google.com/app/apikey))
- For Dropbox mode: Dropbox App credentials ([Create app](https://www.dropbox.com/developers/apps))

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/voxbox.git
   cd voxbox
   ```

2. **Create environment file**
   ```bash
   cp env.example .env
   ```

3. **Configure environment variables** (edit `.env`)
   ```env
   # Required
   GEMINI_API_KEY=your_gemini_api_key
   MODE=local  # or 'dropbox'

   # For Dropbox mode
   DROPBOX_APP_KEY=your_app_key
   DROPBOX_APP_SECRET=your_app_secret
   ALLOWED_ACCOUNTS=user@example.com
   ```

4. **Start the service**
   ```bash
   docker-compose up -d
   ```

### Local Development Mode

Perfect for testing without Dropbox:

```bash
# Set MODE=local in .env
MODE=local

# Start service
docker-compose up

# In another terminal, create a job file
echo "https://www.youtube.com/watch?v=dQw4w9WgXcQ" > data/Inbox/test.txt

# Check output
ls data/Outbox/
```

### Dropbox Mode

For production with iOS Shortcut integration:

1. **Create Dropbox App**
   - Go to [Dropbox App Console](https://www.dropbox.com/developers/apps)
   - Create new "Scoped App" with "App folder" access
   - Set Redirect URI: `http://localhost:8080/oauth/callback`

2. **Start and authorize**
   ```bash
   docker-compose up
   # Visit http://localhost:8080
   # Click "Authorize with Dropbox"
   ```

3. **Upload job files** to your Dropbox App Folder's `/Inbox/`

## Output Format

Each processed video creates a folder:

```
YYYY-MM-DD_Video_Title/
├── audio.mp3           # Audio for offline listening
└── Video_Title.md      # Obsidian note
```

### Markdown Note Structure

```markdown
---
title: "10 Minute Mindfulness Meditation"
channel: "Great Meditation"
url: "https://www.youtube.com/watch?v=XXXXXX"
upload_date: 2023-12-05
duration: "10:00"
tags:
  - meditation
  - mindfulness
  - health
processed_date: 2025-12-05
---

# 10 Minute Mindfulness Meditation

## AI Summary

This meditation focuses on breath awareness and body scanning...

### Key Takeaways

* Technique: 4-7-8 breathing method
* Focus: Use breath sensation as an anchor
* Insight: "You are not your thoughts"

---

## Audio

![[audio.mp3]]

---

## Full Transcript

(00:00) Welcome to this session...
```

## Configuration Reference

### Core Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `MODE` | Operation mode (`local` or `dropbox`) | `local` |
| `GEMINI_API_KEY` | Google Gemini API key | Required |
| `GEMINI_MODEL` | Gemini model to use | `gemini-2.5-flash` |
| `WHISPER_MODEL` | Whisper model for fallback | `base` |
| `AUDIO_QUALITY` | MP3 bitrate (kbps) | `192` |

### Dropbox Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DROPBOX_APP_KEY` | Dropbox app key | Required for dropbox mode |
| `DROPBOX_APP_SECRET` | Dropbox app secret | Required for dropbox mode |
| `ALLOWED_ACCOUNTS` | Comma-separated account emails | - |

### Processing Options

| Variable | Description | Default |
|----------|-------------|---------|
| `POLL_INTERVAL` | Seconds between polls | `30` |
| `MAX_RETRIES` | Maximum API retry attempts | `3` |
| `ENABLE_TAGS` | Enable automatic tagging | `true` |
| `ENABLE_TAG_LEARNING` | Learn tags from existing notes | `true` |

## Transcription Strategy

VoxBox uses a smart fallback approach:

1. **YouTube Manual Captions** - Highest quality, instant
2. **YouTube Auto-Generated Captions** - Good quality, instant
3. **Local Whisper** - Fallback when no captions available

This means ~90% of videos process in seconds (using existing captions), with Whisper as a reliable fallback.

### Whisper Model Selection

| Model | VRAM | Speed (10 min video) | Quality |
|-------|------|---------------------|---------|
| `tiny` | ~1GB | ~15-20 min (CPU) | Acceptable |
| `base` | ~1GB | ~30-40 min (CPU) | Good |
| `small` | ~2GB | ~1 hour (CPU) | Great |
| `medium` | ~5GB | ~2 hours (CPU) | Excellent |

Recommendation: Start with `base` for CPU-only systems.

## iOS Shortcut Integration

Create an iOS Shortcut that:
1. Gets the YouTube URL from the Share Sheet
2. Creates a .txt file with the URL
3. Uploads to Dropbox `/Apps/VoxBox/Inbox/`

Then just share any YouTube video and it automatically appears in your Obsidian vault!

## License

MIT License - see LICENSE file for details

