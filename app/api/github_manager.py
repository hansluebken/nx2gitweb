"""
GitHub Manager für Ninox2Git
Verwaltet private GitHub Repositories und versioniert Ninox-Datenbanken
"""

import base64
import json
from typing import Optional, Dict, List, Any
from datetime import datetime
try:
    from github import Github, GithubException
    from github.Organization import Organization
    from github.AuthenticatedUser import AuthenticatedUser
except ImportError:
    print("PyGithub nicht installiert. Bitte 'pip install PyGithub' ausführen.")
    raise


class GitHubManager:
    def __init__(self, access_token: str, organization: Optional[str] = None):
        """
        Initialisiert den GitHub Manager

        Args:
            access_token: GitHub Personal Access Token
            organization: GitHub Organisation (optional, sonst User-Repos)
        """
        self.github = Github(access_token)
        self.access_token = access_token  # Store token for authenticated requests
        self.organization = organization
        
        # Hole User oder Organisation
        if organization:
            try:
                # Versuche als Organisation
                self.owner = self.github.get_organization(organization)
                self.is_org = True
            except GithubException:
                # Falls das fehlschlägt, prüfe ob es der authentifizierte User ist
                auth_user = self.github.get_user()
                if auth_user.login.lower() == organization.lower():
                    # Es ist der eigene Account
                    self.owner = auth_user
                    self.is_org = False
                else:
                    # Es ist ein anderer User oder nicht gefunden
                    raise ValueError(f"'{organization}' ist keine Organisation oder Sie haben keinen Zugriff. Falls es Ihr persönlicher Account ist, verwenden Sie ein Personal Access Token von diesem Account.")
        else:
            self.owner = self.github.get_user()
            self.is_org = False
    
    def ensure_repository(self, repo_name: str, description: Optional[str] = None):
        """
        Stellt sicher, dass ein Repository existiert (erstellt es wenn nötig)
        
        Args:
            repo_name: Name des Repositories
            description: Beschreibung des Repositories
        
        Returns:
            GitHub Repository Objekt
        """
        try:
            # Versuche das Repository zu holen
            return self.owner.get_repo(repo_name)
        except GithubException as e:
            if e.status == 404:
                # Repository existiert nicht, erstelle es
                print(f"  📝 Erstelle neues Repository: {repo_name}")
                
                repo_data = {
                    'name': repo_name,
                    'description': description or f'Ninox Database Backup - {repo_name}',
                    'private': True,  # Immer private Repositories
                    'auto_init': True,  # Mit README.md initialisieren
                }
                
                # create_repo funktioniert für Organization und AuthenticatedUser
                # Für User-Accounts verwenden wir immer den authentifizierten User
                if self.is_org:
                    return self.owner.create_repo(**repo_data)  # type: ignore
                else:
                    return self.github.get_user().create_repo(**repo_data)  # type: ignore
            else:
                raise
    
    def delete_repository(self, repo_name: str) -> bool:
        """
        Löscht ein Repository
        
        Args:
            repo_name: Name des Repositories
            
        Returns:
            True wenn erfolgreich, False bei Fehler
        """
        try:
            repo = self.owner.get_repo(repo_name)
            repo.delete()
            return True
        except GithubException as e:
            print(f"Fehler beim Löschen: {e}")
            return False
    
    def get_file_content(self, repo, file_path: str) -> Optional[str]:
        """
        Holt den Inhalt einer Datei aus dem Repository

        Args:
            repo: Repository Objekt
            file_path: Pfad zur Datei im Repository

        Returns:
            Dateiinhalt als String oder None wenn nicht vorhanden
        """
        try:
            content = repo.get_contents(file_path)
            if isinstance(content, list):
                # Sollte nicht passieren für einzelne Dateien
                return None

            # Handle different encoding types
            if content.encoding == "base64":
                # Normal case: file is base64 encoded
                return content.decoded_content.decode('utf-8')
            elif content.encoding == "none" or content.size > 1024 * 1024:
                # Large file (>1MB) or encoding is "none": use download_url with authentication
                import requests
                # For private repos, we need to authenticate the download request
                headers = {
                    'Authorization': f'token {self.access_token}',
                    'Accept': 'application/vnd.github.v3.raw'
                }
                response = requests.get(content.download_url, headers=headers)
                response.raise_for_status()
                return response.text
            else:
                # Try decoded_content as fallback
                return content.decoded_content.decode('utf-8')

        except GithubException as e:
            if e.status == 404:
                return None
            raise
    
    def update_file(self, repo, file_path: str, content: str, 
                   commit_message: str, branch: str = "main"):
        """
        Erstellt oder aktualisiert eine Datei im Repository
        
        Args:
            repo: Repository Objekt
            file_path: Pfad zur Datei im Repository
            content: Neuer Dateiinhalt
            commit_message: Commit-Nachricht
            branch: Branch Name (default: main)
        
        Returns:
            ContentFile Objekt
        """
        try:
            # Versuche existierende Datei zu holen
            existing_file = repo.get_contents(file_path, ref=branch)
            if isinstance(existing_file, list):
                # Sollte nicht passieren für einzelne Dateien
                raise ValueError(f"Pfad {file_path} ist ein Verzeichnis")
            
            # Datei existiert, aktualisiere sie
            result = repo.update_file(
                path=file_path,
                message=commit_message,
                content=content,
                sha=existing_file.sha,
                branch=branch
            )
            print(f"    ✓ Aktualisiert: {file_path}")
            return result['content']
            
        except GithubException as e:
            if e.status == 404:
                # Datei existiert nicht, erstelle sie
                result = repo.create_file(
                    path=file_path,
                    message=commit_message,
                    content=content,
                    branch=branch
                )
                print(f"    ✓ Erstellt: {file_path}")
                return result['content']
            raise
    
    def delete_file(self, repo, file_path: str, commit_message: str) -> None:
        """
        Löscht eine Datei aus dem Repository
        
        Args:
            repo: Repository Objekt
            file_path: Pfad zur Datei
            commit_message: Commit-Nachricht
        """
        try:
            file = repo.get_contents(file_path)
            if isinstance(file, list):
                raise ValueError(f"Pfad {file_path} ist ein Verzeichnis")
            
            repo.delete_file(
                path=file_path,
                message=commit_message,
                sha=file.sha,
                branch="main"
            )
            print(f"    ✓ Gelöscht: {file_path}")
            
        except GithubException as e:
            if e.status == 404:
                print(f"    ⚠ Datei nicht gefunden: {file_path}")
            else:
                raise
    
    def create_or_update_readme(self, repo, team_name: str, 
                               databases: List[Dict]) -> None:
        """
        Erstellt oder aktualisiert die README.md mit Informationen über die Datenbanken
        
        Args:
            repo: Repository Objekt
            team_name: Name des Teams
            databases: Liste der Datenbanken mit Metadaten
        """
        readme_content = f"""# Ninox Database Backup - {team_name}

Dieses Repository enthält automatische Backups der Ninox-Datenbanken für das Team **{team_name}**.

## 📊 Datenbanken

| Datenbank | Letzte Aktualisierung | Pfad |
|-----------|----------------------|------|
"""
        
        for db in databases:
            last_update = db.get('last_modified', 'Unbekannt')
            path = db.get('github_path', f"databases/{db['name']}/")
            readme_content += f"| {db['name']} | {last_update} | `{path}` |\n"
        
        readme_content += f"""

## 🔄 Synchronisation

Dieses Repository wird automatisch mit dem Ninox-Server synchronisiert.

- **Sync-Tool**: Ninox2Git
- **Letzte Synchronisation**: {datetime.now().isoformat()}
- **Team ID**: {team_name}

## 📝 Struktur

Jede Datenbank wird in einem eigenen Verzeichnis gespeichert:

```
databases/
├── [Team1]/
│   ├── Datenbank1-structure.json  # Datenbankstruktur mit Tabellen und Feldern
│   ├── Datenbank2-structure.json
│   └── ...
├── [Team2]/
│   ├── Datenbank3-structure.json
│   └── ...
└── ...
```

## ⚠️ Hinweise

- Dies ist ein automatisch generiertes Repository
- Manuelle Änderungen können bei der nächsten Synchronisation überschrieben werden
- Die Daten sind im JSON-Format für beste Lesbarkeit und Git-Diff-Unterstützung

---

*Automatisch generiert von Ninox2Git*
"""
        
        self.update_file(
            repo,
            "README.md",
            readme_content,
            "Update README with database information"
        )
    
    def list_repositories(self) -> List:
        """
        Listet alle Repositories des Users/der Organisation
        
        Returns:
            Liste der Repositories
        """
        return list(self.owner.get_repos())
    
    def get_repository(self, repo_name: str):
        """
        Holt ein spezifisches Repository
        
        Args:
            repo_name: Name des Repositories
        
        Returns:
            Repository Objekt oder None
        """
        try:
            return self.owner.get_repo(repo_name)
        except GithubException:
            return None
    
    def test_connection(self) -> bool:
        """
        Testet die Verbindung zu GitHub
        
        Returns:
            True wenn die Verbindung erfolgreich ist
        """
        try:
            user = self.github.get_user()
            _ = user.login  # Trigger API call
            return True
        except Exception:
            return False
    
    def create_backup_branch(self, repo, branch_name: str) -> str:
        """
        Erstellt einen Backup-Branch für Versionierung
        
        Args:
            repo: Repository Objekt
            branch_name: Name des neuen Branches
        
        Returns:
            Name des erstellten Branches
        """
        try:
            # Hole den main branch
            main_branch = repo.get_branch("main")
            
            # Erstelle neuen Branch vom main branch
            repo.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=main_branch.commit.sha
            )
            
            print(f"    ✓ Backup-Branch erstellt: {branch_name}")
            return branch_name
            
        except GithubException as e:
            if e.status == 422:
                # Branch existiert bereits
                print(f"    ℹ Branch existiert bereits: {branch_name}")
                return branch_name
            raise