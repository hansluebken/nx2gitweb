# ✅ Ordnerstruktur-Umstellung ABGESCHLOSSEN

**Datum:** 8. Dezember 2024
**Status:** ✅ **KOMPLETT**

---

## Was wurde umgesetzt

### Ziel erreicht: NUR Klarnamen, KEINE IDs!

**VORHER:**
```
/app/data/ninox-cli/
└── team_ulnxwg3q4bcolh3ho/        ❌ Team-ID
    └── src/Objects/
        └── database_jz79ok8wdsbd/  ❌ DB-ID
```

**NACHHER:**
```
/app/data/ninox-cli/
└── EFS-Server/                     ✅ Server-Name
    └── Dev/                        ✅ Team-Name
        └── Buywatch/               ✅ DB-Name
            ├── .ninox-metadata.json
            └── src/Objects/
```

---

## Neue Dateien

### 1. app/utils/path_resolver.py (78 Zeilen)
```python
get_server_path(server) → {base}/{server_name}/
get_team_path(server, team) → {base}/{server_name}/{team_name}/
get_database_path(server, team, db_name) → {base}/{server}/{team}/{db_name}/
```

### 2. app/utils/metadata_helper.py (95 Zeilen)
```python
create_database_metadata(db_path, server, team, db_id, db_name)
read_database_metadata(db_path) → Dict mit IDs
update_last_sync(db_path)
```

---

## Geänderte Dateien

### services/ninox_sync_service.py (Kern-Änderungen)
- ✅ `_restructure_download()` - Nutzt metadata_helper
- ✅ `sync_database_async()` - KOMPLETT neu (140 Zeilen)
- ✅ `_generate_and_save_erd_new_structure()` - NEU (54 Zeilen)
- ✅ `_generate_and_save_docs_new_structure()` - NEU (73 Zeilen)
- ✅ Git/GitHub auf Server-Level

### ui/yaml_code_viewer.py (3 Änderungen)
- ✅ Line 85: `change_team()` - get_team_path()
- ✅ Line 229: `has_git_changes()` - Pattern: {db_name}/
- ✅ Line 1054: `show_download_dialog()` - get_team_path()

### ui/sync.py (6 Änderungen)
- ✅ Line 149: `get_database_dependencies()` - Neue Pfade
- ✅ Line 565: `show_database_details()` - get_database_path()
- ✅ Line 1085: **HARDCODED PATH** entfernt - get_database_path()
- ✅ Line 1180: `show_erd_viewer_from_sync()` - Neue Pfade

### services/ninox_cli_service.py (Discovery)
- ✅ Line 434: `get_downloaded_databases()` - Metadata-First Ansatz
- ✅ Fallback auf alte Struktur für Kompatibilität

---

## Workflow (NEU)

### Bei jedem Sync:

```
1. ninox-cli download
   → _temp_{team_id}/src/Objects/database_{id}/

2. UMSTRUKTURIERUNG ✨
   → {server}/{team}/{database}/src/Objects/
   → Metadata erstellt

3. TEMP LÖSCHEN
   → _temp_* Ordner gelöscht

4. GIT (Server-Level)
   → init (einmalig)
   → commit auf Server-Repo

5. GITHUB (erster Sync)
   → repo erstellen
   → git push --force

6. ERD + DOCS
   → Auf neuer Struktur
   → Parser auf Team-Level

ERGEBNIS: Nur Klarnamen lokal + GitHub! ✅
```

---

## Garantien

### Struktur-Garantien:
- ✅ **Lokal:** Nur `{Server}/{Team}/{Database}/`
- ✅ **Git:** Committed nur Klarnamen-Struktur
- ✅ **GitHub:** Zeigt nur Klarnamen (main Branch)
- ❌ **Keine** `team_{id}` oder `database_{id}` Ordner mehr
- ✅ **IDs** nur in `.ninox-metadata.json`

### Konsistenz-Garantien:
- ✅ **Jeder Download:** Automatische Umstrukturierung
- ✅ **Temp-Ordner:** Werden immer gelöscht
- ✅ **Metadata:** Wird immer erstellt
- ✅ **Git-Repo:** Ein Repo pro Server (alle Teams)

---

## Metadata-Format

```json
{
  "server_id": 1,
  "server_name": "EFS-Server",
  "team_id": "ulnxwg3q4bcolh3ho",
  "team_name": "Dev",
  "database_id": "jz79ok8wdsbd",
  "database_name": "Buywatch",
  "last_sync": "2024-12-08T10:30:00.000000",
  "structure_version": "2.0-names"
}
```

---

## Jetzt testen!

### Schritt 1: GitHub-Repo löschen
```
https://github.com/hansluebken/efs.ninoxdb.de
→ Settings → Delete
```

### Schritt 2: Sync starten
```
WebApp → Sync-Seite → "Sync All YAML"
```

### Schritt 3: Erwartetes Ergebnis

**Lokal im Container:**
```bash
docker exec nx2git-webapp ls -la /app/data/ninox-cli/
# Sollte zeigen:
# EFS-Server/
```

**In GitHub:**
```
https://github.com/hansluebken/efs.ninoxdb.de
Branch: main
Struktur:
├── Dev/
│   └── Buywatch/
│       ├── .ninox-metadata.json
│       ├── APPLICATION_DOCS.md          ← AI-generierte Doku
│       ├── SCRIPTS.md                   ← Alle Scripts (Format: "YAML-Code")
│       └── src/Objects/
│           └── database_Buywatch/
│               ├── database.yaml
│               ├── erd.svg
│               └── table_Artikel/
└── ...
```

---

## Features die funktionieren sollten

- ✅ Download & Umstrukturierung
- ✅ Git Commit (Server-Level)
- ✅ GitHub Push (Initial automatisch)
- ✅ ERD-Generierung (aus YAML, Team-Level Parser)
- ✅ AI-Dokumentation (aus YAML, Team-Level Parser)
- ✅ Code-Viewer (Team-Level Parser)
- ✅ Dependencies (neue Pfade)
- ✅ Changelog (lokales Git)

---

## Alle Änderungen im Überblick

| Kategorie | Dateien | Zeilen | Status |
|-----------|---------|--------|--------|
| **Neue Helper** | 2 | 173 | ✅ Erstellt |
| **Core Sync** | 1 | 267 | ✅ Komplett neu |
| **UI Updates** | 2 | 35 | ✅ Angepasst |
| **Discovery** | 1 | 20 | ✅ Metadata-First |
| **Cleanup** | - | - | ✅ Alte Ordner gelöscht |

**Gesamt:** 5 Dateien geändert/erstellt, ~495 Zeilen Code

---

## BEREIT ZUM TESTEN! 🚀

Die komplette Umstrukturierung ist fertig.
Alle Ordner nutzen jetzt Klarnamen.
Starten Sie einen Sync und sehen Sie die neue Struktur!
