# VoxBox Deployment Quick Reference

This directory contains files for deploying VoxBox as a systemd service.

## Deployment Overview

VoxBox uses a CI/CD approach for production deployments:
- GitHub Actions builds and pushes Docker images to GitHub Container Registry (ghcr.io)
- Images are built automatically on every push to `main` branch
- Production servers pull pre-built images (no compilation needed)
- Development uses local Docker builds

## Quick Installation

```bash
# On your server
cd /path/to/voxbox
sudo ./deployment/install.sh
```

## Configuration

Edit your environment file:
```bash
sudo nano /opt/voxbox/.env
```

Required settings:
```env
# Docker image repository (automatically set by install.sh)
GITHUB_REPOSITORY=stefanahman/voxbox

# Application mode
MODE=dropbox  # or 'local'
GEMINI_API_KEY=your_api_key_here

# Whisper model (fallback when no YouTube captions)
WHISPER_MODEL=base  # tiny, base, small, medium, large-v3

# For Dropbox mode:
DROPBOX_APP_KEY=your_app_key
DROPBOX_APP_SECRET=your_app_secret
ALLOWED_ACCOUNTS=user@example.com
```

**Important**: The default is set to `stefanahman/voxbox`. Update if you've forked the repository.

## Service Management

```bash
# Start the service
sudo systemctl start voxbox@username

# Stop the service
sudo systemctl stop voxbox@username

# Restart the service
sudo systemctl restart voxbox@username

# Check status
sudo systemctl status voxbox@username

# View logs (live)
sudo journalctl -u voxbox@username -f

# View last 100 lines
sudo journalctl -u voxbox@username -n 100

# Disable autostart
sudo systemctl disable voxbox@username

# Enable autostart
sudo systemctl enable voxbox@username
```

Replace `username` with your actual username.

## SSH Tunnel for OAuth (Dropbox Mode)

To authorize Dropbox accounts without exposing your server publicly:

```bash
# From your local machine (default port 8080)
ssh -L 8080:localhost:8080 user@yourserver.com

# Keep this terminal open and visit in your browser:
# http://localhost:8080

# Complete the OAuth authorization
# Then you can close the SSH connection
```

The Dropbox redirect URI stays as:
```
http://localhost:8080/oauth/callback
```

### Using a Different Port

If port 8080 is already in use, configure an alternative port in your `.env`:

```env
OAUTH_SERVER_PORT=8081
DROPBOX_REDIRECT_URI=http://localhost:8081/oauth/callback
```

**Important**: Also update the redirect URI in your [Dropbox App Console](https://www.dropbox.com/developers/apps) to match.

Then use the new port for SSH tunneling:
```bash
ssh -L 8081:localhost:8081 user@yourserver.com
```

## File Locations

- **Installation**: `/opt/voxbox`
- **Data**: `/opt/voxbox/data/`
  - `Inbox/` - Drop .txt files with YouTube URLs here
  - `Outbox/` - Processed notes and audio files
  - `Archive/` - Processed job files
  - `Logs/` - Processing logs
  - `tokens/` - OAuth tokens (700 permissions)
  - `temp/` - Temporary audio/caption files
- **Logs**: `journalctl -u voxbox@username`
- **Service**: `/etc/systemd/system/voxbox@.service`

## Usage

### iOS Shortcut Integration

Create an iOS Shortcut that:
1. Gets the YouTube URL from the Share Sheet
2. Creates a .txt file with the URL
3. Uploads to Dropbox `/Apps/VoxBox/Inbox/`

Then just share any YouTube video and it automatically appears in your Obsidian vault!

### Manual Usage

```bash
# Create a job file
echo "https://www.youtube.com/watch?v=VIDEO_ID" > /opt/voxbox/data/Inbox/video.txt

# The service will automatically:
# 1. Download audio and captions
# 2. Generate transcript (YouTube captions or Whisper)
# 3. Create AI summary with Gemini
# 4. Output folder in /opt/voxbox/data/Outbox/
```

## Troubleshooting

### Service won't start

```bash
# Check detailed status
sudo systemctl status voxbox@username

# Check full logs
sudo journalctl -u voxbox@username -n 50

# Test Docker Compose manually
cd /opt/voxbox
docker compose up
```

### Permission issues

```bash
# Fix data directory permissions
sudo chown -R username:username /opt/voxbox/data
sudo chmod 700 /opt/voxbox/data/tokens
```

### OAuth not accessible

```bash
# Check if configured port is listening (default 8080)
sudo ss -tlnp | grep ${OAUTH_SERVER_PORT:-8080}

# Test SSH tunnel (adjust port if using custom OAUTH_SERVER_PORT)
ssh -L 8080:localhost:8080 -N user@server
# Then visit http://localhost:8080
```

### Port already in use

If you see a port conflict error, set a different port in `.env`:

```env
OAUTH_SERVER_PORT=8081
DROPBOX_REDIRECT_URI=http://localhost:8081/oauth/callback
```

Remember to update the redirect URI in your Dropbox App Console as well.

### View Docker logs directly

```bash
cd /opt/voxbox
docker compose logs -f
```

## Updating VoxBox

Production deployments automatically pull the latest image from GitHub Container Registry:

```bash
# Stop the service
sudo systemctl stop voxbox@username

# Pull latest image from registry
cd /opt/voxbox
docker compose -f docker-compose.prod.yml pull

# Start service (will use new image)
sudo systemctl start voxbox@username

# Check status
sudo systemctl status voxbox@username

# Verify running version
docker images | grep voxbox
```

The image is automatically built and pushed when you push to the `main` branch on GitHub.

## Uninstalling

```bash
# Stop and disable service
sudo systemctl stop voxbox@username
sudo systemctl disable voxbox@username

# Remove service file
sudo rm /etc/systemd/system/voxbox@.service
sudo systemctl daemon-reload

# Remove installation (optional, backs up data first)
sudo tar -czf ~/voxbox-data-backup.tar.gz /opt/voxbox/data
sudo rm -rf /opt/voxbox
```

## Security Notes

- OAuth server (port 8080) is only bound to localhost
- Use SSH tunnel to access it remotely - keeps server private
- Gemini API key is never exposed via web interface
- Token files have restrictive permissions (700)
- Service runs as your user, not root
- `.env` file should have 600 permissions

