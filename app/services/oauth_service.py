"""
OAuth Service for Google Workspace authentication
Handles the OAuth2 flow with Google
"""
import os
import logging
import secrets
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

# Google OAuth2 endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Basic scopes for authentication
GOOGLE_SCOPES_BASIC = [
    "openid",
    "email",
    "profile",
]

# Extended scopes including Drive access
# Note: drive.file only allows access to files created by the app
# For Shared Drives access, we need the full drive scope
GOOGLE_SCOPES_WITH_DRIVE = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]


@dataclass
class GoogleUserInfo:
    """User info from Google OAuth"""
    google_id: str
    email: str
    name: str
    given_name: Optional[str]
    family_name: Optional[str]
    picture: Optional[str]
    verified_email: bool
    refresh_token: Optional[str] = None  # For Drive API access


class OAuthError(Exception):
    """Base OAuth error"""
    pass


class DomainNotAllowedError(OAuthError):
    """Raised when user's email domain is not allowed"""
    pass


class OAuthNotConfiguredError(OAuthError):
    """Raised when OAuth is not configured"""
    pass


class OAuthService:
    """Service for handling Google OAuth2 flow"""
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        """
        Initialize OAuth service
        
        Args:
            client_id: Google OAuth Client ID
            client_secret: Google OAuth Client Secret  
            redirect_uri: Callback URL for OAuth
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        
        # In-memory state storage (in production, use Redis or DB)
        self._states: Dict[str, bool] = {}
    
    def generate_auth_url(self, state: Optional[str] = None, include_drive: bool = False) -> Tuple[str, str]:
        """
        Generate Google OAuth authorization URL
        
        Args:
            state: Optional state parameter (will be generated if not provided)
            include_drive: Whether to include Drive/Docs scopes
            
        Returns:
            Tuple of (auth_url, state)
        """
        if not state:
            state = secrets.token_urlsafe(32)
        
        # Store state for validation
        self._states[state] = True
        
        # Select scopes based on whether Drive is enabled
        scopes = GOOGLE_SCOPES_WITH_DRIVE if include_drive else GOOGLE_SCOPES_BASIC
        
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",  # Force consent to get refresh token
        }
        
        auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
        logger.info(f"Generated Google OAuth URL with state: {state[:8]}... (drive={include_drive})")
        
        return auth_url, state
    
    def validate_state(self, state: str) -> bool:
        """
        Validate OAuth state parameter
        
        Args:
            state: State parameter from callback
            
        Returns:
            True if valid, False otherwise
        """
        if state in self._states:
            del self._states[state]  # One-time use
            return True
        return False
    
    async def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access tokens
        
        Args:
            code: Authorization code from callback
            
        Returns:
            Token response dict with access_token, id_token, etc.
        """
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(GOOGLE_TOKEN_URL, data=data)
            
            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.text}")
                raise OAuthError(f"Token exchange failed: {response.status_code}")
            
            tokens = response.json()
            logger.info("Successfully exchanged code for tokens")
            return tokens
    
    async def get_user_info(self, access_token: str) -> GoogleUserInfo:
        """
        Get user info from Google using access token
        
        Args:
            access_token: OAuth access token
            
        Returns:
            GoogleUserInfo object
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(GOOGLE_USERINFO_URL, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to get user info: {response.text}")
                raise OAuthError(f"Failed to get user info: {response.status_code}")
            
            data = response.json()
            
            user_info = GoogleUserInfo(
                google_id=data.get("id"),
                email=data.get("email"),
                name=data.get("name", ""),
                given_name=data.get("given_name"),
                family_name=data.get("family_name"),
                picture=data.get("picture"),
                verified_email=data.get("verified_email", False),
            )
            
            logger.info(f"Got user info for: {user_info.email}")
            return user_info
    
    async def authenticate(self, code: str) -> GoogleUserInfo:
        """
        Complete authentication flow: exchange code and get user info
        
        Args:
            code: Authorization code from callback
            
        Returns:
            GoogleUserInfo object (includes refresh_token if available)
        """
        tokens = await self.exchange_code_for_tokens(code)
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")  # Only returned on first auth with consent
        
        if not access_token:
            raise OAuthError("No access token in response")
        
        user_info = await self.get_user_info(access_token)
        user_info.refresh_token = refresh_token
        
        logger.info(f"Authentication complete, refresh_token={'yes' if refresh_token else 'no'}")
        return user_info


def get_oauth_service() -> Optional[OAuthService]:
    """
    Get OAuth service instance if configured
    
    Returns:
        OAuthService instance or None if not configured
    """
    try:
        from ..database import get_db
        from ..models.oauth_config import OAuthConfig
        from ..utils.encryption import get_encryption_manager
        
        db = get_db()
        try:
            config = db.query(OAuthConfig).filter(
                OAuthConfig.provider == 'google',
                OAuthConfig.is_enabled == True
            ).first()
            
            if not config:
                logger.debug("Google OAuth not configured or not enabled")
                return None
            
            if not config.client_id or not config.client_secret_encrypted:
                logger.warning("Google OAuth missing client_id or client_secret")
                return None
            
            # Decrypt client secret
            enc_manager = get_encryption_manager()
            client_secret = enc_manager.decrypt(config.client_secret_encrypted)
            
            if not client_secret:
                logger.warning("Could not decrypt Google OAuth client secret")
                return None
            
            # Build redirect URI if not set
            redirect_uri = config.redirect_uri
            if not redirect_uri:
                # Try to build from environment
                app_url = os.getenv('APP_URL', 'http://localhost:8765')
                redirect_uri = f"{app_url}/auth/google/callback"
            
            return OAuthService(
                client_id=config.client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri
            )
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error getting OAuth service: {e}")
        return None


def get_oauth_config():
    """
    Get OAuth config from database
    
    Returns:
        OAuthConfig or None
    """
    try:
        from ..database import get_db
        from ..models.oauth_config import OAuthConfig
        
        db = get_db()
        try:
            return db.query(OAuthConfig).filter(
                OAuthConfig.provider == 'google'
            ).first()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting OAuth config: {e}")
        return None


def is_oauth_enabled() -> bool:
    """Check if OAuth is enabled"""
    config = get_oauth_config()
    return config is not None and config.is_enabled
