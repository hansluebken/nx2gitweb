"""
Google Drive Service for uploading JSON as Google Docs
Handles folder creation and document management in Shared Drives
"""
import os
import re
import json
import logging
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# Google API endpoints
DRIVE_API_URL = "https://www.googleapis.com/drive/v3"
DOCS_API_URL = "https://docs.googleapis.com/v1"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Extended scopes for Drive access
DRIVE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
]


@dataclass
class DriveUploadResult:
    """Result of a Drive upload operation"""
    success: bool
    document_id: Optional[str] = None
    document_url: Optional[str] = None
    error: Optional[str] = None


def sanitize_path_name(name: str) -> str:
    """
    Sanitize a name for use in Google Drive path
    Replace invalid characters with hyphens
    """
    # Replace common problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '-', name)
    # Replace multiple hyphens with single
    sanitized = re.sub(r'-+', '-', sanitized)
    # Remove leading/trailing hyphens and spaces
    sanitized = sanitized.strip('- ')
    return sanitized or 'unnamed'


class GoogleDriveService:
    """Service for Google Drive and Docs operations"""
    
    def __init__(self, access_token: str):
        """
        Initialize with an access token
        
        Args:
            access_token: Valid Google OAuth access token with drive.file scope
        """
        self.access_token = access_token
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
    
    async def _make_request(
        self, 
        method: str, 
        url: str, 
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        content: Optional[bytes] = None,
        content_type: Optional[str] = None
    ) -> Tuple[int, Dict]:
        """Make an async HTTP request"""
        headers = self._headers.copy()
        if content_type:
            headers["Content-Type"] = content_type
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                params=params,
                content=content
            )
            
            try:
                data = response.json()
            except:
                data = {"raw": response.text}
            
            return response.status_code, data
    
    async def find_shared_drive(self, name: str) -> Optional[str]:
        """
        Find a Shared Drive by name
        
        Args:
            name: Name of the Shared Drive
            
        Returns:
            Drive ID or None if not found
        """
        url = f"{DRIVE_API_URL}/drives"
        params = {
            "q": f"name = '{name}'",
            "pageSize": 10
        }
        
        status, data = await self._make_request("GET", url, params=params)
        
        if status == 200 and "drives" in data:
            for drive in data["drives"]:
                if drive.get("name") == name:
                    logger.info(f"Found Shared Drive '{name}': {drive['id']}")
                    return drive["id"]
        
        logger.warning(f"Shared Drive '{name}' not found")
        return None
    
    async def find_or_create_folder(
        self, 
        name: str, 
        parent_id: str,
        is_shared_drive: bool = False
    ) -> Optional[str]:
        """
        Find or create a folder
        
        Args:
            name: Folder name
            parent_id: Parent folder ID or Shared Drive ID
            is_shared_drive: Whether parent is a Shared Drive
            
        Returns:
            Folder ID or None on error
        """
        # Search for existing folder
        url = f"{DRIVE_API_URL}/files"
        query = f"name = '{name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        params = {
            "q": query,
            "fields": "files(id, name)",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        
        if is_shared_drive:
            params["corpora"] = "drive"
            params["driveId"] = parent_id
        
        status, data = await self._make_request("GET", url, params=params)
        
        if status == 200 and data.get("files"):
            folder_id = data["files"][0]["id"]
            logger.debug(f"Found existing folder '{name}': {folder_id}")
            return folder_id
        
        # Create new folder
        logger.info(f"Creating folder '{name}' in {parent_id}")
        
        create_url = f"{DRIVE_API_URL}/files"
        create_params = {"supportsAllDrives": "true"}
        
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        
        status, data = await self._make_request(
            "POST", create_url, json_data=metadata, params=create_params
        )
        
        if status in (200, 201):
            folder_id = data.get("id")
            logger.info(f"Created folder '{name}': {folder_id}")
            return folder_id
        
        logger.error(f"Failed to create folder '{name}': {data}")
        return None
    
    async def create_folder_path(
        self, 
        shared_drive_id: str, 
        path_parts: list[str]
    ) -> Optional[str]:
        """
        Create a folder path in a Shared Drive
        
        Args:
            shared_drive_id: Shared Drive ID
            path_parts: List of folder names (e.g., ["server", "team", "database"])
            
        Returns:
            Final folder ID or None on error
        """
        current_parent = shared_drive_id
        is_shared_drive = True
        
        for part in path_parts:
            sanitized = sanitize_path_name(part)
            folder_id = await self.find_or_create_folder(
                sanitized, current_parent, is_shared_drive
            )
            
            if not folder_id:
                return None
            
            current_parent = folder_id
            is_shared_drive = False
        
        return current_parent
    
    async def find_document(self, name: str, folder_id: str) -> Optional[str]:
        """
        Find a Google Doc by name in a folder
        
        Args:
            name: Document name
            folder_id: Parent folder ID
            
        Returns:
            Document ID or None if not found
        """
        url = f"{DRIVE_API_URL}/files"
        query = f"name = '{name}' and '{folder_id}' in parents and mimeType = 'application/vnd.google-apps.document' and trashed = false"
        params = {
            "q": query,
            "fields": "files(id, name)",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        
        status, data = await self._make_request("GET", url, params=params)
        
        if status == 200 and data.get("files"):
            doc_id = data["files"][0]["id"]
            logger.debug(f"Found existing document '{name}': {doc_id}")
            return doc_id
        
        return None
    
    async def create_google_doc(
        self, 
        name: str, 
        folder_id: str,
        content: str
    ) -> Optional[str]:
        """
        Create a new Google Doc
        
        Args:
            name: Document name
            folder_id: Parent folder ID
            content: Text content
            
        Returns:
            Document ID or None on error
        """
        # Create empty document
        url = f"{DRIVE_API_URL}/files"
        params = {"supportsAllDrives": "true"}
        
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [folder_id],
        }
        
        status, data = await self._make_request(
            "POST", url, json_data=metadata, params=params
        )
        
        if status not in (200, 201):
            logger.error(f"Failed to create document '{name}': {data}")
            return None
        
        doc_id = data.get("id")
        logger.info(f"Created Google Doc '{name}': {doc_id}")
        
        # Now insert content
        await self.update_document_content(doc_id, content)
        
        return doc_id
    
    async def update_document_content(self, doc_id: str, content: str) -> bool:
        """
        Update a Google Doc's content (replaces all content)
        
        Args:
            doc_id: Google Doc ID
            content: New text content
            
        Returns:
            True on success
        """
        # First, get the current document to find the end index
        url = f"{DOCS_API_URL}/documents/{doc_id}"
        status, doc_data = await self._make_request("GET", url)
        
        if status != 200:
            logger.error(f"Failed to get document {doc_id}: {doc_data}")
            return False
        
        # Build the batch update request
        requests = []
        
        # Delete existing content (if any)
        body = doc_data.get("body", {})
        end_index = body.get("content", [{}])[-1].get("endIndex", 1)
        
        if end_index > 1:
            requests.append({
                "deleteContentRange": {
                    "range": {
                        "startIndex": 1,
                        "endIndex": end_index - 1
                    }
                }
            })
        
        # Insert new content
        requests.append({
            "insertText": {
                "location": {"index": 1},
                "text": content
            }
        })
        
        # Execute batch update
        update_url = f"{DOCS_API_URL}/documents/{doc_id}:batchUpdate"
        update_data = {"requests": requests}
        
        status, result = await self._make_request("POST", update_url, json_data=update_data)
        
        if status != 200:
            logger.error(f"Failed to update document content: {result}")
            return False
        
        logger.info(f"Updated document {doc_id} content")
        return True
    
    async def upload_json_as_doc(
        self,
        shared_drive_name: str,
        server_name: str,
        team_name: str,
        database_name: str,
        json_content: Dict[str, Any],
        existing_doc_id: Optional[str] = None
    ) -> DriveUploadResult:
        """
        Upload JSON content as a Google Doc
        
        Args:
            shared_drive_name: Name of the Shared Drive
            server_name: Server name for folder path
            team_name: Team name for folder path  
            database_name: Database name for folder path
            json_content: JSON content to upload
            existing_doc_id: Existing document ID to update (optional)
            
        Returns:
            DriveUploadResult with document info
        """
        try:
            # Find Shared Drive
            drive_id = await self.find_shared_drive(shared_drive_name)
            if not drive_id:
                return DriveUploadResult(
                    success=False,
                    error=f"Shared Drive '{shared_drive_name}' nicht gefunden. "
                          f"Bitte erstellen Sie den Shared Drive und laden Sie als Mitbearbeiter ein."
                )
            
            # Create folder path
            path_parts = [
                sanitize_path_name(server_name),
                sanitize_path_name(team_name),
                sanitize_path_name(database_name),
            ]
            
            folder_id = await self.create_folder_path(drive_id, path_parts)
            if not folder_id:
                return DriveUploadResult(
                    success=False,
                    error="Konnte Ordnerstruktur nicht erstellen"
                )
            
            # Format JSON content for readability
            formatted_json = json.dumps(json_content, indent=2, ensure_ascii=False)
            
            doc_name = "komplett.json"
            doc_id = existing_doc_id
            
            # If we have an existing doc ID, try to update it
            if doc_id:
                success = await self.update_document_content(doc_id, formatted_json)
                if success:
                    return DriveUploadResult(
                        success=True,
                        document_id=doc_id,
                        document_url=f"https://docs.google.com/document/d/{doc_id}/edit"
                    )
                else:
                    # Document might have been deleted, create new
                    logger.warning(f"Could not update existing doc {doc_id}, creating new")
                    doc_id = None
            
            # Check if document already exists in folder
            if not doc_id:
                doc_id = await self.find_document(doc_name, folder_id)
            
            if doc_id:
                # Update existing document
                success = await self.update_document_content(doc_id, formatted_json)
                if not success:
                    return DriveUploadResult(
                        success=False,
                        error="Konnte Dokument nicht aktualisieren"
                    )
            else:
                # Create new document
                doc_id = await self.create_google_doc(doc_name, folder_id, formatted_json)
                if not doc_id:
                    return DriveUploadResult(
                        success=False,
                        error="Konnte Dokument nicht erstellen"
                    )
            
            return DriveUploadResult(
                success=True,
                document_id=doc_id,
                document_url=f"https://docs.google.com/document/d/{doc_id}/edit"
            )
            
        except Exception as e:
            logger.error(f"Drive upload error: {e}")
            return DriveUploadResult(
                success=False,
                error=str(e)
            )


async def refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str
) -> Optional[str]:
    """
    Refresh an expired access token using the refresh token
    
    Args:
        client_id: OAuth client ID
        client_secret: OAuth client secret
        refresh_token: Refresh token
        
    Returns:
        New access token or None on error
    """
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(TOKEN_URL, data=data)
        
        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.text}")
            return None
        
        tokens = response.json()
        return tokens.get("access_token")


def get_drive_scopes() -> list[str]:
    """Get the OAuth scopes needed for Drive access"""
    return DRIVE_SCOPES


def is_drive_enabled() -> bool:
    """Check if Google Drive integration is enabled"""
    try:
        from ..database import get_db
        from ..models.oauth_config import OAuthConfig
        
        db = get_db()
        try:
            config = db.query(OAuthConfig).filter(
                OAuthConfig.provider == 'google',
                OAuthConfig.is_enabled == True,
                OAuthConfig.drive_enabled == True
            ).first()
            
            return config is not None and bool(config.drive_shared_folder_name)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error checking drive enabled: {e}")
        return False


def get_drive_config() -> Optional[Dict[str, Any]]:
    """Get Drive configuration"""
    try:
        from ..database import get_db
        from ..models.oauth_config import OAuthConfig
        from ..utils.encryption import get_encryption_manager
        
        db = get_db()
        try:
            config = db.query(OAuthConfig).filter(
                OAuthConfig.provider == 'google'
            ).first()
            
            if not config:
                return None
            
            enc = get_encryption_manager()
            client_secret = None
            if config.client_secret_encrypted:
                client_secret = enc.decrypt(config.client_secret_encrypted)
            
            return {
                "enabled": config.is_enabled and config.drive_enabled,
                "client_id": config.client_id,
                "client_secret": client_secret,
                "shared_folder_name": config.drive_shared_folder_name,
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error getting drive config: {e}")
        return None
