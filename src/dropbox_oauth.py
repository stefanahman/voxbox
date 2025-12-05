"""Dropbox OAuth 2.0 authorization with allowlist validation."""

import logging
import secrets
import hashlib
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, parse_qs, urlparse

import dropbox
import requests

from .storage import TokenStorage

logger = logging.getLogger(__name__)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    oauth_manager = None  # Set by OAuthManager

    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.debug(f"OAuth callback: {format % args}")

    def do_GET(self):
        """Handle GET request (OAuth callback)."""
        parsed_path = urlparse(self.path)

        if parsed_path.path == "/oauth/callback":
            query_params = parse_qs(parsed_path.query)

            auth_code = query_params.get("code", [None])[0]
            state = query_params.get("state", [None])[0]
            error = query_params.get("error", [None])[0]

            if error:
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    f"<h1>Authorization Failed</h1><p>Error: {error}</p>".encode()
                )
                return

            if not auth_code or not state:
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<h1>Bad Request</h1><p>Missing authorization code or state</p>"
                )
                return

            # Validate state (CSRF protection)
            if state != self.oauth_manager.state:
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Invalid State</h1><p>CSRF validation failed</p>")
                return

            # Exchange code for token
            try:
                success, message = self.oauth_manager.exchange_code_for_token(auth_code)

                if success:
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(
                        b"<h1>Authorization Successful!</h1>"
                        b"<p>You can close this window and return to the application.</p>"
                        b"<p>VoxBox is now connected to your Dropbox.</p>"
                    )
                else:
                    self.send_response(403)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(
                        f"<h1>Authorization Failed</h1><p>{message}</p>".encode()
                    )

                # Signal server to stop
                self.oauth_manager.authorization_complete = True

            except Exception as e:
                logger.error(f"Error during token exchange: {e}")
                self.send_response(500)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(f"<h1>Server Error</h1><p>{str(e)}</p>".encode())

        elif parsed_path.path == "/":
            # Root page with authorization link
            auth_url = self.oauth_manager.get_authorization_url()

            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = f"""
            <html>
            <head><title>VoxBox Authorization</title></head>
            <body>
                <h1>VoxBox - Dropbox Authorization</h1>
                <p>Click the link below to authorize this application with your Dropbox account:</p>
                <p><a href="{auth_url}">Authorize with Dropbox</a></p>
                <p style="color: #666; margin-top: 20px;">
                    VoxBox will create an App Folder in your Dropbox with Inbox, Outbox, and Archive folders.
                </p>
            </body>
            </html>
            """
            self.wfile.write(html.encode())

        else:
            self.send_response(404)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Not Found</h1>")


class OAuthManager:
    """Manages Dropbox OAuth 2.0 flow with allowlist validation."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        redirect_uri: str,
        token_storage: TokenStorage,
        allowed_accounts: list,
    ):
        """Initialize OAuth manager.

        Args:
            app_key: Dropbox app key
            app_secret: Dropbox app secret
            redirect_uri: OAuth redirect URI
            token_storage: Token storage instance
            allowed_accounts: List of allowed account IDs or emails
        """
        self.app_key = app_key
        self.app_secret = app_secret
        self.redirect_uri = redirect_uri
        self.token_storage = token_storage
        self.allowed_accounts = allowed_accounts

        # OAuth state for CSRF protection
        self.state = secrets.token_urlsafe(32)
        self.code_verifier = None
        self.authorization_complete = False

        logger.info("Initialized OAuth manager")

    def get_authorization_url(self) -> str:
        """Generate Dropbox authorization URL.

        Returns:
            Authorization URL
        """
        # PKCE code verifier and challenge
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        # Store for later use
        self.code_verifier = code_verifier

        # Build authorization URL
        params = {
            "client_id": self.app_key,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "state": self.state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "token_access_type": "offline",  # Request refresh token
        }

        auth_url = f"https://www.dropbox.com/oauth2/authorize?{urlencode(params)}"
        logger.info("Generated authorization URL")
        return auth_url

    def exchange_code_for_token(self, auth_code: str) -> tuple[bool, str]:
        """Exchange authorization code for access token.

        Args:
            auth_code: Authorization code from callback

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Exchange code for token
            token_url = "https://api.dropboxapi.com/oauth2/token"
            data = {
                "code": auth_code,
                "grant_type": "authorization_code",
                "client_id": self.app_key,
                "client_secret": self.app_secret,
                "redirect_uri": self.redirect_uri,
                "code_verifier": self.code_verifier,
            }

            response = requests.post(token_url, data=data)
            response.raise_for_status()

            token_data = response.json()
            access_token = token_data["access_token"]
            refresh_token = token_data.get("refresh_token")

            # Get account info
            dbx = dropbox.Dropbox(access_token)
            account = dbx.users_get_current_account()

            account_id = account.account_id
            account_email = account.email

            logger.info(f"Retrieved account info: {account_email} ({account_id})")

            # Check allowlist
            if self.allowed_accounts:
                if (
                    account_id not in self.allowed_accounts
                    and account_email not in self.allowed_accounts
                ):
                    logger.warning(
                        f"Account not in allowlist: {account_email} ({account_id})"
                    )
                    return (
                        False,
                        f"Account {account_email} is not authorized to use this service.",
                    )

            # Save token
            self.token_storage.save_token(
                {
                    "account_id": account_id,
                    "account_email": account_email,
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                }
            )

            logger.info(f"Successfully authorized account: {account_email}")
            return True, "Authorization successful"

        except Exception as e:
            logger.error(f"Error exchanging code for token: {e}")
            return False, f"Error: {str(e)}"

    def run_authorization_server(self, host: str, port: int) -> bool:
        """Run OAuth callback server and wait for authorization.

        Args:
            host: Server host
            port: Server port

        Returns:
            True if authorization was successful
        """
        # Set up callback handler
        OAuthCallbackHandler.oauth_manager = self

        # Create server
        server = HTTPServer((host, port), OAuthCallbackHandler)

        logger.info(f"OAuth server started at http://{host}:{port}")
        logger.info(f"Visit http://localhost:{port} to begin authorization")

        # Run until authorization complete
        while not self.authorization_complete:
            server.handle_request()

        logger.info("Authorization flow completed")
        return True

    def refresh_token(self, account_id: str) -> bool:
        """Refresh an expired access token.

        Args:
            account_id: Account ID to refresh token for

        Returns:
            True if refresh was successful
        """
        token_data = self.token_storage.load_token(account_id)

        if not token_data or not token_data.get("refresh_token"):
            logger.error(f"No refresh token available for account: {account_id}")
            return False

        try:
            token_url = "https://api.dropboxapi.com/oauth2/token"
            data = {
                "grant_type": "refresh_token",
                "refresh_token": token_data["refresh_token"],
                "client_id": self.app_key,
                "client_secret": self.app_secret,
            }

            response = requests.post(token_url, data=data)
            response.raise_for_status()

            new_token_data = response.json()

            # Update token
            token_data["access_token"] = new_token_data["access_token"]
            self.token_storage.save_token(token_data)

            logger.info(f"Successfully refreshed token for account: {account_id}")
            return True

        except Exception as e:
            logger.error(f"Error refreshing token for {account_id}: {e}")
            return False

