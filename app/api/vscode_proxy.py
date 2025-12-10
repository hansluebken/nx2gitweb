"""
VS Code Server Proxy
Proxies requests to the local code-server instance for authenticated users
"""
import os
import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response, RedirectResponse

router = APIRouter(prefix="/vscode", tags=["vscode"])

VSCODE_SERVER_URL = os.getenv("VSCODE_SERVER_URL", "http://host.docker.internal:8443")

@router.get("/open")
async def open_vscode(folder: str = None, file: str = None):
    """
    Redirect to VS Code Server with optional folder/file
    
    Args:
        folder: Folder path to open (relative to /home/nx2git-go/webapp/data/ninox-cli)
        file: File path to open
    """
    base_path = "/home/nx2git-go/webapp/data/ninox-cli"
    
    url = VSCODE_SERVER_URL
    
    if folder:
        # Construct full path
        full_path = f"{base_path}/{folder}" if not folder.startswith("/") else folder
        url = f"{VSCODE_SERVER_URL}/?folder={full_path}"
    elif file:
        full_path = f"{base_path}/{file}" if not file.startswith("/") else file
        url = f"{VSCODE_SERVER_URL}/?file={full_path}"
    
    return RedirectResponse(url=url, status_code=302)


@router.get("/status")
async def vscode_status():
    """Check if VS Code Server is running"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{VSCODE_SERVER_URL}/healthz")
            return {"status": "online", "url": VSCODE_SERVER_URL}
    except Exception as e:
        return {"status": "offline", "error": str(e)}
