# Folder Restructuring Plan - Klarnamen Implementation

## Ziel
Team- und Datenbank-Ordner verwenden Klarnamen statt IDs.
Tabellen und Felder bleiben wie von ninox-cli (bereits Klarnamen).

## Strategie

### Phase 1: Download (ninox-cli Standard)
```
ninox-cli download -i {db_id}
→ src/Objects/database_{db_id}/     ← ID (von ninox-cli)
```

### Phase 2: Umstrukturierung (Post-Download)
```
src/Objects/database_{db_id}/
→ MOVE TO →
{server_name}/{team_name}/{db_name}/src/Objects/
```

### Phase 3: Git Commit (Klarnamen-Struktur)
```
git commit
→ Nur Klarnamen-Struktur wird committed!
```

## Neue Pfad-Logik

### get_team_working_path()
```python
def get_team_working_path(server: Server, team: Team) -> Path:
    """
    Returns: /app/data/ninox-cli/{server_name}/{team_name}/
    """
    base = Path('/app/data/ninox-cli')
    server_folder = sanitize_name(server.name)
    team_folder = sanitize_name(team.name)
    return base / server_folder / team_folder
```

### get_database_path()
```python
def get_database_path(server: Server, team: Team, db_name: str) -> Path:
    """
    Returns: /app/data/ninox-cli/{server}/{team}/{database}/
    """
    team_path = get_team_working_path(server, team)
    db_folder = sanitize_name(db_name)
    return team_path / db_folder
```

## Umstrukturierungs-Prozess

### Nach jedem ninox-cli download:

```python
def restructure_after_download(
    temp_download_path: Path,    # wo ninox-cli hinschreibt
    server: Server,
    team: Team,
    database_name: str,
    database_id: str
) -> Path:
    """
    Reorganizes ninox-cli output into clean name-based structure
    """
    # 1. Quelle: ninox-cli Standard-Struktur
    source = temp_download_path / 'src' / 'Objects' / f'database_{database_id}'

    if not source.exists():
        raise ValueError(f"Download failed: {source} not found")

    # 2. Ziel: Klarnamen-Struktur
    target_db_path = get_database_path(server, team, database_name)
    target_db_path.mkdir(parents=True, exist_ok=True)

    # 3. Verschieben
    target_objects = target_db_path / 'src' / 'Objects'

    # Wenn bereits existiert, löschen (für sauberen Re-Sync)
    if target_objects.exists():
        shutil.rmtree(target_objects)

    # Kopieren
    shutil.copytree(source, target_objects)

    # 4. Metadata-Datei erstellen (für ID-Mapping)
    metadata = {
        'server_id': server.id,
        'server_name': server.name,
        'team_id': team.team_id,
        'team_name': team.name,
        'database_id': database_id,
        'database_name': database_name,
        'last_sync': datetime.utcnow().isoformat()
    }

    metadata_file = target_db_path / '.ninox-metadata.json'
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)

    # 5. Temp-Ordner löschen
    shutil.rmtree(temp_download_path)

    return target_db_path
```

## Git-Repository Struktur

### Ein Git-Repo pro Server (im Team-Ordner)

```
/app/data/ninox-cli/
├── EFS-Server/
│   ├── .git                    ← Git-Repo für ganzen Server
│   ├── .gitignore
│   ├── README.md
│   ├── Dev/                    ← Team 1
│   │   ├── Buywatch/           ← DB 1
│   │   │   ├── .ninox-metadata.json
│   │   │   └── src/Objects/
│   │   └── CRM/                ← DB 2
│   │       └── ...
│   └── Production/             ← Team 2
│       └── ...
└── Cloud-Server/
    ├── .git                    ← Separates Git-Repo
    └── ...
```

## Änderungen an bestehenden Funktionen

### 1. get_team_cli_service() → get_database_working_path()
```python
# ALT:
team_path = base_path / f'team_{team.team_id}'

# NEU:
server_path = base_path / sanitize_name(server.name)
team_path = server_path / sanitize_name(team.name)
```

### 2. sync_database_async()
```python
# Nach download:
result = ninox_cli.download(...)

# NEU: Umstrukturieren!
if result.success:
    final_path = restructure_after_download(
        temp_path=ninox_cli.project_path,
        server=server,
        team=team,
        database_name=db_name,
        database_id=database_id
    )

    # Git operations auf final_path
    commit_changes(final_path.parent.parent)  # Server-Level
```

### 3. ERD/Docs Generator
```python
# Parser findet DB jetzt hier:
db_path = get_database_path(server, team, db_name)
parser = NinoxYAMLParser(str(db_path / 'src' / 'Objects'))
```

## Validierung

### Nach jedem Sync prüfen:
1. ✅ Struktur korrekt: `{server}/{team}/{database}/`
2. ✅ Metadata-Datei existiert
3. ✅ Keine `database_{id}` Ordner mehr
4. ✅ Git committed nur Klarnamen-Struktur

## Rückwärtskompatibilität

### Migration alter Daten:
```python
def migrate_old_structure():
    """
    Migriert alte team_{id}/database_{id} → neue Struktur
    """
    # Optional: Für bestehende Installationen
```

## Testing Checklist

- [ ] Download erstellt korrekte Struktur
- [ ] Re-Sync überschreibt korrekt
- [ ] Git enthält nur Klarnamen
- [ ] GitHub zeigt Klarnamen
- [ ] Parser findet Datenbanken
- [ ] ERD funktioniert
- [ ] AI-Doku funktioniert
- [ ] Changelog funktioniert

## Vorteile

1. ✅ Lesbare Ordnerstruktur
2. ✅ Konsistent bei jedem Download
3. ✅ Validierung eingebaut
4. ✅ Metadata für ID-Rückverfolgung
5. ✅ Git zeigt saubere History
6. ✅ GitHub ist navigierbar
