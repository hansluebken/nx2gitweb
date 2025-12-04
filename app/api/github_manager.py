"""
GitHub Manager für Ninox2Git
Verwaltet private GitHub Repositories und versioniert Ninox-Datenbanken
"""

import base64
import json
from typing import Optional, Dict, List, Any
from datetime import datetime
from dataclasses import dataclass, field
try:
    from github import Github, GithubException
    from github.Organization import Organization
    from github.AuthenticatedUser import AuthenticatedUser
    from github.Commit import Commit
    from github.Repository import Repository
except ImportError:
    print("PyGithub nicht installiert. Bitte 'pip install PyGithub' ausführen.")
    raise


@dataclass
class CommitInfo:
    """Structured commit information"""
    sha: str
    short_sha: str
    message: str
    date: datetime
    author_name: str
    author_email: str
    url: str
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0
    files: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FileDiff:
    """Structured file diff information"""
    filename: str
    status: str  # added, modified, removed, renamed
    additions: int
    deletions: int
    changes: int
    patch: str  # The actual diff content


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
                   commit_message: str, branch: str = "main",
                   max_retries: int = 3):
        """
        Erstellt oder aktualisiert eine Datei im Repository.
        Bei SHA-Konflikten (409) wird automatisch der aktuelle SHA geholt und erneut versucht.
        
        Args:
            repo: Repository Objekt
            file_path: Pfad zur Datei im Repository
            content: Neuer Dateiinhalt
            commit_message: Commit-Nachricht
            branch: Branch Name (default: main)
            max_retries: Maximale Anzahl Versuche bei SHA-Konflikten (default: 3)
        
        Returns:
            ContentFile Objekt
        """
        import time
        
        for attempt in range(max_retries):
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
                    try:
                        result = repo.create_file(
                            path=file_path,
                            message=commit_message,
                            content=content,
                            branch=branch
                        )
                        print(f"    ✓ Erstellt: {file_path}")
                        return result['content']
                    except GithubException as create_error:
                        # File was created by another process between get_contents and create_file
                        if create_error.status == 422 and attempt < max_retries - 1:
                            print(f"    ⟳ Retry {attempt + 1}/{max_retries} (file created by another process): {file_path}")
                            time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                            continue
                        raise
                
                elif e.status == 409:
                    # SHA conflict - file was modified by another process
                    if attempt < max_retries - 1:
                        print(f"    ⟳ Retry {attempt + 1}/{max_retries} (SHA conflict): {file_path}")
                        time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                        continue
                    else:
                        print(f"    ✗ SHA conflict nach {max_retries} Versuchen: {file_path}")
                        raise
                else:
                    raise
        
        # Should not reach here, but just in case
        raise Exception(f"Failed to update {file_path} after {max_retries} attempts")
    
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
    
    # =========================================================================
    # Commit History & Diff Methods (for ChangeLog feature)
    # =========================================================================
    
    def get_commits(
        self, 
        repo, 
        path: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        max_count: int = 100
    ) -> List[CommitInfo]:
        """
        Holt Commit-Historie für ein Repository oder eine spezifische Datei
        
        Args:
            repo: Repository Objekt
            path: Optional - Pfad zur Datei (nur Commits für diese Datei)
            since: Optional - Nur Commits nach diesem Datum
            until: Optional - Nur Commits vor diesem Datum
            max_count: Maximale Anzahl der Commits (default: 100)
        
        Returns:
            Liste von CommitInfo Objekten
        """
        try:
            # Build query parameters
            kwargs = {}
            if path:
                kwargs['path'] = path
            if since:
                kwargs['since'] = since
            if until:
                kwargs['until'] = until
            
            commits = repo.get_commits(**kwargs)
            
            result = []
            for i, commit in enumerate(commits):
                if i >= max_count:
                    break
                
                # Convert PaginatedList to list to get length
                files_list = list(commit.files) if commit.files else []
                
                commit_info = CommitInfo(
                    sha=commit.sha,
                    short_sha=commit.sha[:7],
                    message=commit.commit.message,
                    date=commit.commit.author.date,
                    author_name=commit.commit.author.name,
                    author_email=commit.commit.author.email,
                    url=commit.html_url,
                    files_changed=len(files_list),
                    additions=commit.stats.additions if commit.stats else 0,
                    deletions=commit.stats.deletions if commit.stats else 0,
                )
                result.append(commit_info)
            
            return result
            
        except GithubException as e:
            print(f"Fehler beim Abrufen der Commits: {e}")
            return []
    
    def get_commit_details(self, repo, commit_sha: str) -> Optional[CommitInfo]:
        """
        Holt detaillierte Informationen zu einem spezifischen Commit
        
        Args:
            repo: Repository Objekt
            commit_sha: SHA des Commits
        
        Returns:
            CommitInfo mit allen Details inkl. geänderter Dateien
        """
        try:
            commit = repo.get_commit(commit_sha)
            
            # Collect file changes
            files = []
            for file in commit.files:
                files.append({
                    'filename': file.filename,
                    'status': file.status,  # added, modified, removed, renamed
                    'additions': file.additions,
                    'deletions': file.deletions,
                    'changes': file.changes,
                    'patch': file.patch if hasattr(file, 'patch') and file.patch else '',
                    'previous_filename': file.previous_filename if hasattr(file, 'previous_filename') else None,
                })
            
            return CommitInfo(
                sha=commit.sha,
                short_sha=commit.sha[:7],
                message=commit.commit.message,
                date=commit.commit.author.date,
                author_name=commit.commit.author.name,
                author_email=commit.commit.author.email,
                url=commit.html_url,
                files_changed=len(files),
                additions=commit.stats.additions if commit.stats else 0,
                deletions=commit.stats.deletions if commit.stats else 0,
                files=files,
            )
            
        except GithubException as e:
            print(f"Fehler beim Abrufen des Commits {commit_sha}: {e}")
            return None
    
    def get_file_commits(
        self, 
        repo, 
        file_path: str,
        max_count: int = 50
    ) -> List[CommitInfo]:
        """
        Holt alle Commits die eine spezifische Datei betreffen
        
        Args:
            repo: Repository Objekt
            file_path: Pfad zur Datei im Repository
            max_count: Maximale Anzahl der Commits
        
        Returns:
            Liste von CommitInfo Objekten
        """
        return self.get_commits(repo, path=file_path, max_count=max_count)
    
    def get_file_diff(self, repo, file_path: str, commit_sha: str) -> Optional[FileDiff]:
        """
        Holt den Diff einer spezifischen Datei für einen Commit
        
        Args:
            repo: Repository Objekt
            file_path: Pfad zur Datei
            commit_sha: SHA des Commits
        
        Returns:
            FileDiff Objekt oder None
        """
        try:
            commit = repo.get_commit(commit_sha)
            
            for file in commit.files:
                if file.filename == file_path:
                    return FileDiff(
                        filename=file.filename,
                        status=file.status,
                        additions=file.additions,
                        deletions=file.deletions,
                        changes=file.changes,
                        patch=file.patch if hasattr(file, 'patch') and file.patch else '',
                    )
            
            return None
            
        except GithubException as e:
            print(f"Fehler beim Abrufen des Diffs: {e}")
            return None
    
    def compare_commits(
        self, 
        repo, 
        base_sha: str, 
        head_sha: str
    ) -> Optional[Dict[str, Any]]:
        """
        Vergleicht zwei Commits und gibt die Unterschiede zurück
        
        Args:
            repo: Repository Objekt
            base_sha: SHA des Basis-Commits (älter)
            head_sha: SHA des Head-Commits (neuer)
        
        Returns:
            Dict mit Vergleichsinformationen:
            {
                'ahead_by': int,
                'behind_by': int,
                'total_commits': int,
                'files': List[FileDiff],
                'commits': List[CommitInfo]
            }
        """
        try:
            comparison = repo.compare(base_sha, head_sha)
            
            files = []
            for file in comparison.files:
                files.append(FileDiff(
                    filename=file.filename,
                    status=file.status,
                    additions=file.additions,
                    deletions=file.deletions,
                    changes=file.changes,
                    patch=file.patch if hasattr(file, 'patch') and file.patch else '',
                ))
            
            commits = []
            for commit in comparison.commits:
                commits.append(CommitInfo(
                    sha=commit.sha,
                    short_sha=commit.sha[:7],
                    message=commit.commit.message,
                    date=commit.commit.author.date,
                    author_name=commit.commit.author.name,
                    author_email=commit.commit.author.email,
                    url=commit.html_url,
                ))
            
            return {
                'ahead_by': comparison.ahead_by,
                'behind_by': comparison.behind_by,
                'total_commits': comparison.total_commits,
                'files': files,
                'commits': commits,
                'diff_url': comparison.diff_url,
                'patch_url': comparison.patch_url,
            }
            
        except GithubException as e:
            print(f"Fehler beim Vergleichen der Commits: {e}")
            return None
    
    def get_latest_commit(self, repo, path: Optional[str] = None) -> Optional[CommitInfo]:
        """
        Holt den neuesten Commit (optional für eine spezifische Datei)
        
        Args:
            repo: Repository Objekt
            path: Optional - Pfad zur Datei
        
        Returns:
            CommitInfo des neuesten Commits oder None
        """
        commits = self.get_commits(repo, path=path, max_count=1)
        return commits[0] if commits else None
    
    def get_commit_diff_for_changelog(
        self, 
        repo, 
        commit_sha: str,
        file_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Holt alle relevanten Informationen für einen ChangeLog-Eintrag
        
        Args:
            repo: Repository Objekt
            commit_sha: SHA des Commits
            file_path: Optional - Nur Diff für diese Datei
        
        Returns:
            Dict mit allen Informationen für ChangeLog:
            {
                'commit': CommitInfo,
                'files': List[Dict],
                'full_patch': str,
                'changed_items': List[Dict]  # Parsed changes for Ninox code
            }
        """
        commit_info = self.get_commit_details(repo, commit_sha)
        
        if not commit_info:
            return {}
        
        # Filter files if path specified
        files = commit_info.files
        if file_path:
            files = [f for f in files if f['filename'] == file_path]
        
        # Combine all patches into full diff
        full_patch = ""
        for file in files:
            if file.get('patch'):
                full_patch += f"\n--- {file['filename']} ---\n"
                full_patch += file['patch']
                full_patch += "\n"
        
        # Parse changed items for Ninox-specific structure
        changed_items = self._parse_ninox_changes(files)
        
        return {
            'commit': commit_info,
            'files': files,
            'full_patch': full_patch.strip(),
            'changed_items': changed_items,
        }
    
    def _parse_ninox_changes(self, files: List[Dict]) -> List[Dict]:
        """
        Parst Dateiänderungen und extrahiert Ninox-spezifische Informationen
        
        Args:
            files: Liste der geänderten Dateien
        
        Returns:
            Liste von geänderten Items mit Ninox-Kontext:
            [
                {
                    'table': 'Rechnungen',
                    'field': 'Summe',
                    'code_type': 'fn',
                    'change_type': 'modified',
                    'additions': 5,
                    'deletions': 2
                }
            ]
        """
        changed_items = []
        
        for file in files:
            filename = file.get('filename', '')
            
            # Parse Ninox code file paths
            # Expected format: databases/TeamName/DatabaseName/code/TableName/FieldName_codetype.nxs
            # or: databases/TeamName/DatabaseName/structure.json
            
            parts = filename.split('/')
            
            if 'code' in parts:
                # Code file
                code_idx = parts.index('code')
                if len(parts) > code_idx + 2:
                    table_name = parts[code_idx + 1]
                    field_file = parts[code_idx + 2] if len(parts) > code_idx + 2 else ''
                    
                    # Parse field_codetype.nxs
                    if field_file.endswith('.nxs'):
                        field_parts = field_file[:-4].rsplit('_', 1)
                        field_name = field_parts[0] if field_parts else field_file[:-4]
                        code_type = field_parts[1] if len(field_parts) > 1 else 'code'
                    else:
                        field_name = field_file
                        code_type = 'unknown'
                    
                    changed_items.append({
                        'table': table_name,
                        'field': field_name,
                        'code_type': code_type,
                        'change_type': file.get('status', 'modified'),
                        'additions': file.get('additions', 0),
                        'deletions': file.get('deletions', 0),
                        'filename': filename,
                    })
            
            elif filename.endswith('structure.json'):
                # Structure file changed
                changed_items.append({
                    'table': '[Schema]',
                    'field': 'structure',
                    'code_type': 'schema',
                    'change_type': file.get('status', 'modified'),
                    'additions': file.get('additions', 0),
                    'deletions': file.get('deletions', 0),
                    'filename': filename,
                })
            
            elif filename.endswith('complete-backup.json'):
                # Complete backup changed
                changed_items.append({
                    'table': '[Backup]',
                    'field': 'complete-backup',
                    'code_type': 'backup',
                    'change_type': file.get('status', 'modified'),
                    'additions': file.get('additions', 0),
                    'deletions': file.get('deletions', 0),
                    'filename': filename,
                })
        
        return changed_items