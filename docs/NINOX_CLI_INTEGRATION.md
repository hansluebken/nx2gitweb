# Ninox-CLI Integration

Diese Dokumentation beschreibt die Integration von `ninox-dev-cli` in Ninox2Git.

## Übersicht

Die Integration ermöglicht:
- Download von Ninox-Datenbanken als YAML-Dateien
- KI-freundliche Darstellung des Ninox-Codes
- 3-Spalten Code-Viewer mit umfangreicher Filterung
- CLI-Tool für Automatisierung (OpenCode, Claude Code)
- Cronjob-Integration für automatische Synchronisation

## Architektur

```
webapp/
├── app/
│   ├── services/
│   │   ├── ninox_cli_service.py    # Wrapper für ninox-dev-cli
│   │   └── ninox_sync_service.py   # High-Level Sync-Service
│   ├── utils/
│   │   ├── ninox_yaml_parser.py    # YAML-Parser & Code-Extraktor
│   │   └── ninox_lexer.py          # Syntax-Highlighting
│   └── ui/
│       └── yaml_code_viewer.py     # 3-Spalten UI
├── tools/
│   └── ninox_cli.py                # CLI für externe Nutzung
├── package.json                     # npm-Abhängigkeiten
└── data/
    └── ninox-cli/                   # Heruntergeladene Datenbanken
        └── src/Objects/
            └── database_<id>/
```

## Installation

### In Docker (empfohlen)

Das Dockerfile enthält bereits alle Abhängigkeiten:
- Python 3.10+
- Node.js 18+
- ninox-dev-cli (via npm)

```bash
docker-compose up -d
```

### Lokal

1. Node.js 18+ installieren
2. npm-Pakete installieren:
   ```bash
   cd webapp
   npm install
   ```
3. Python-Abhängigkeiten installieren:
   ```bash
   pip install -r requirements.txt
   ```

## Web-UI: YAML Code Viewer

Zugriff über: **Entwicklung → YAML Code**

### 3-Spalten-Layout

1. **Linke Spalte - Datenbank-Browser**
   - Liste aller heruntergeladenen Datenbanken
   - Suche nach Datenbank-Namen
   - Zeigt Tabellen- und Code-Anzahl

2. **Mittlere Spalte - Code-Locations**
   - Hierarchische Darstellung: Tabelle → Feld/UI → Code-Typ
   - Filterung nach:
     - Text im Code
     - Kategorien (Trigger, Formeln, Buttons, etc.)
     - Code-Typen (fn, afterUpdate, onClick, etc.)
     - Tabellen

3. **Rechte Spalte - Code-Viewer**
   - Syntax-Highlighting für Ninox-Code
   - Zeilennummern
   - Metadaten (Kategorie, Typ, Zeilen)
   - Copy-to-Clipboard

### Unterstützte Code-Locations (24 Typen)

#### Datenbank-Ebene (3)
- `afterOpen` - Script beim Öffnen der DB
- `beforeOpen` - Script vor Öffnen der DB
- `globalCode` - Globale Funktionen

#### Tabellen-Ebene (4)
- `afterCreate` - Trigger nach Datensatz-Erstellung
- `afterUpdate` - Trigger nach Update
- `afterDelete` - Trigger nach Löschen
- `beforeDelete` - Trigger vor Löschen

#### Feld-Ebene (12)
- `fn` - Formel-Feld
- `afterUpdate` - Trigger nach Feld-Update
- `afterCreate` - Trigger nach Feld-Erstellung
- `constraint` - Validierungs-Constraint
- `dchoiceValues` - Dynamische Auswahl-Query
- `dchoiceCaption` - Anzeigeformat
- `dchoiceColor` - Farb-Expression
- `dchoiceIcon` - Icon-Expression
- `referenceFormat` - Referenz-Anzeigeformat
- `visibility` - Sichtbarkeits-Bedingung
- `onClick` - Klick-Handler
- `onDoubleClick` - Doppelklick-Handler

#### UI-Elemente (5)
- `fn` - Button-Script / View-Query
- `onClick` - Klick-Handler
- `beforeShow` - Tab vor Anzeige
- `afterShow` - Tab nach Anzeige
- `afterHide` - Tab nach Verbergen

## CLI-Tool

Das CLI-Tool ermöglicht Automatisierung und Integration mit externen Tools.

### Nutzung

```bash
cd webapp

# Verfügbare Server anzeigen
python tools/ninox_cli.py list-servers

# Heruntergeladene Datenbanken anzeigen
python tools/ninox_cli.py list-databases

# Alle Datenbanken eines Servers synchronisieren
python tools/ninox_cli.py sync-all --server-id 1

# Eine spezifische Datenbank synchronisieren
python tools/ninox_cli.py sync --server-id 1 --database-id abc123

# Code durchsuchen
python tools/ninox_cli.py search "let x"

# Statistiken anzeigen
python tools/ninox_cli.py stats

# Code als Dateien exportieren
python tools/ninox_cli.py export --database "MeinDB" --output ./export
```

### JSON-Ausgabe

Alle Befehle unterstützen `--json` für maschinenlesbare Ausgabe:

```bash
python tools/ninox_cli.py list-databases --json
```

## Cronjob-Integration

### In der Web-UI

1. Gehe zu **Einstellungen → Cronjobs**
2. Erstelle einen neuen Cronjob mit Typ "Ninox Sync"
3. Wähle Server und optional spezifische Datenbank
4. Definiere den Zeitplan (Cron-Syntax)

### Programmatisch

```python
from app.services.ninox_sync_service import cronjob_sync_server

# Alle Datenbanken eines Servers synchronisieren
result = await cronjob_sync_server(server_id=1)
print(result)
# {
#   'success': True,
#   'databases_synced': 5,
#   'databases_failed': 0,
#   'duration_seconds': 45.2
# }
```

## OpenCode / Claude Code Integration

Das CLI-Tool ist für die Nutzung mit KI-Coding-Assistenten optimiert:

### Beispiel-Workflow

1. **Datenbank synchronisieren:**
   ```bash
   python tools/ninox_cli.py sync-all --server-id 1
   ```

2. **Code suchen:**
   ```bash
   python tools/ninox_cli.py search "function"
   ```

3. **Code bearbeiten** (in YAML-Dateien unter `/app/data/ninox-cli/src/Objects/`)

4. **Manuell in Ninox übertragen** (da Upload bei Cross-DB-Referenzen fehlschlägt)

### YAML-Dateistruktur

Die Datenbanken werden als YAML-Dateien gespeichert:

```
data/ninox-cli/src/Objects/
└── database_abc123/
    ├── database.yaml       # DB-Metadaten und globalCode
    ├── tables/
    │   └── Kunden/
    │       ├── table.yaml  # Tabellen-Trigger
    │       ├── fields/
    │       │   ├── Name.yaml
    │       │   └── Berechnung.yaml  # enthält fn
    │       └── uis/
    │           └── Speichern.yaml   # Button mit onClick
    ├── views.yaml
    └── reports.yaml
```

## Bekannte Einschränkungen

1. **Upload nicht verfügbar**: `ninox dev database upload` funktioniert nicht bei Cross-Database-Referenzen. Code muss manuell in Ninox kopiert werden.

2. **Schema-Versioning**: Lokale Änderungen können bei erneutem Download überschrieben werden. Git-Versionierung wird empfohlen.

3. **Keine neuen Felder/Tabellen**: Das CLI kann nur bestehende Scripts bearbeiten, keine neuen Strukturen erstellen.

## Troubleshooting

### "ninox command not found"

Node.js und npm müssen installiert sein:
```bash
node --version  # sollte >= 18 sein
npx ninox --version
```

### "Database not found"

Prüfe die YAML-Verzeichnisstruktur:
```bash
ls -la /app/data/ninox-cli/src/Objects/
```

### Sync schlägt fehl

1. Prüfe API-Key und Workspace-ID in der Server-Konfiguration
2. Prüfe Netzwerkverbindung zu Ninox
3. Prüfe Logs: `docker-compose logs webapp`

## Weiterentwicklung

### Neue Code-Location hinzufügen

In `app/utils/ninox_yaml_parser.py`:

1. Code-Typ zum entsprechenden Dict hinzufügen (DATABASE_CODE_FIELDS, TABLE_CODE_FIELDS, etc.)
2. Kategorie zuweisen
3. Display-Name in CODE_TYPE_NAMES ergänzen
