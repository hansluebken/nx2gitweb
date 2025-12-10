# ✅ Ninox2Git - Vollständige YAML-Migration

**Datum:** 8. Dezember 2024
**Status:** ✅ **ABGESCHLOSSEN**

---

## 📋 Übersicht der Änderungen

Alle JSON-Abhängigkeiten wurden entfernt. Das System arbeitet jetzt **komplett mit YAML**.

---

## ✅ Sprint 1: GitHub Initial Push

### Was wurde implementiert:
- **Neue Methode:** `_setup_github_remote_on_first_sync()` in `ninox_sync_service.py`
- **Automatische Erkennung:** Prüft ob git remote bereits konfiguriert
- **Beim ersten Sync:**
  1. Erstellt GitHub-Repository automatisch
  2. Konfiguriert `git remote` mit Token
  3. Pusht initial YAML-Struktur zu GitHub
  4. Zeigt Repository-URL im Log

### Geänderte Dateien:
- `app/services/ninox_sync_service.py` (Zeilen 161-268, 368-413)
- `app/services/background_sync.py` (Zeile 369)

### Wie es funktioniert:
```bash
# Erster Sync einer Datenbank:
1. YAML-Download von Ninox
2. Git commit (lokal)
3. GitHub-Repo erstellen
4. git push → GitHub ✅

# Alle weiteren Syncs:
1. YAML-Download
2. Git commit (lokal)
3. ℹ️  "Push manually when ready" → Benutzer pusht selbst
```

### Manuelle Pushes:
```bash
docker exec -it nx2git-webapp bash
cd /app/data/ninox-cli/team_<team_id>
git push
```

---

## ✅ Sprint 2: ERD Generator für YAML

### Was wurde geändert:
- **`svg_erd_generator.py`:** Komplette Umstellung
  - Neue Methode: `_parse_yaml_structure()` (direkt aus YAML)
  - Legacy: `_parse_json_structure()` (Abwärtskompatibilität)
  - Automatische Erkennung: YAML-Objekt vs. JSON-Dict

### Entfernte JSON-Konvertierungen:
- ❌ `ninox_sync_service.py:140` - `convert_yaml_to_json_structure()`
- ❌ `yaml_code_viewer.py:1213` - JSON-Konvertierung

### Vorher:
```python
json_structure = convert_yaml_to_json_structure(yaml_db)
svg_content = generate_svg_erd(json_structure)
```

### Nachher:
```python
svg_content = generate_svg_erd(yaml_db)  # Direkt YAML!
```

---

## ✅ Sprint 3: Google Drive Integration entfernt

### Komplett gelöscht:
1. **Database Model:**
   - ❌ `drive_document_id` Feld
   - ❌ `drive_last_upload` Feld
2. **UI:**
   - ❌ "Upload Drive" Button
   - ❌ `show_upload_drive_dialog()` Funktion (173 Zeilen)
3. **Service:**
   - ❌ `/app/services/drive_service.py` (komplett gelöscht)

### Geänderte Dateien:
- `app/models/database.py` (Zeilen 52-54 entfernt)
- `app/ui/sync.py` (Button + Dialog entfernt)

---

## ✅ Sprint 4: AI Dokumentation

### Status:
**War bereits auf YAML!** ✅ Keine Änderungen nötig.

Die AI-Dokumentation verwendet bereits:
```python
result = generator.generate(yaml_db, yaml_db.name)  # Direkt YAML
```

---

## ✅ Sprint 5: Changelog für YAML

### Komplette Neuimplementierung:
- **Vorher:** Las nicht-existierendes `structure.json` von GitHub
- **Nachher:** Liest YAML-Diff aus lokalem Git

### Neue Funktion `generate_ai_changelog()`:
```python
# Arbeitet mit lokalem Git:
1. Findet latest commit für database_<id> Ordner
2. Holt git diff (YAML-Änderungen)
3. Parsed commit info (Autor, Datum, Message)
4. Sendet YAML-Diff an AI
5. Speichert Changelog in DB
```

### Geänderte Dateien:
- `app/ui/sync.py` (Zeilen 525-738 komplett neu)

### Neue Parameter:
- ❌ `github_mgr`, `repo`, `github_path` (alt)
- ✅ `team_path` (neu) - Pfad zum lokalen Git

---

## ✅ Sprint 6: Cleanup

### Entfernt:
1. **Imports:**
   - `ninox_sync_service.py:60` - Import entfernt
   - `yaml_code_viewer.py` - Import entfernt
   - `sync.py` - Import entfernt

2. **Dateien:**
   - ❌ `sync.py.backup-before-removal` gelöscht
   - ❌ `drive_service.py` gelöscht

3. **Funktion bleibt (legacy):**
   - `convert_yaml_to_json_structure()` in `ninox_yaml_parser.py`
   - **Grund:** Wird nirgends mehr verwendet, aber für Abwärtskompatibilität belassen
   - **TODO:** Kann in Zukunft entfernt werden

---

## 📊 Gesamtübersicht: Was jetzt funktioniert

### ✅ Komplett YAML-basiert:
| Feature | Vorher (JSON) | Nachher (YAML) |
|---------|--------------|----------------|
| **Sync** | ninox-cli → YAML | ✅ Gleich (nur lokal) |
| **GitHub Push** | ❌ Kein Push | ✅ Initial Push automatisch |
| **ERD** | YAML→JSON→ERD | ✅ YAML→ERD direkt |
| **AI Doku** | YAML→JSON→AI | ✅ YAML→AI direkt |
| **Changelog** | GitHub JSON→AI | ✅ Git YAML-Diff→AI |
| **Google Drive** | GitHub JSON→Drive | ❌ Komplett entfernt |

### ❌ Keine JSON-Dateien mehr:
- ❌ `structure.json`
- ❌ `komplett.json`
- ❌ `views.json`
- ❌ `reports.json`
- ✅ Alles ist jetzt YAML!

---

## 🗂️ Datenfluss (neu)

### Beim ersten Sync:
```
Ninox Server
    ↓
ninox-cli download → YAML-Dateien (lokal)
    ↓
git commit (lokal)
    ↓
GitHub-Repo erstellen
    ↓
git push → GitHub ✅ (automatisch beim ersten Mal!)
    ↓
ERD aus YAML generieren → erd.svg
    ↓
AI-Doku aus YAML → APPLICATION_DOCS.md
    ↓
Git commit + push (optional)
```

### Bei weiteren Syncs:
```
Ninox Server
    ↓
ninox-cli download → YAML aktualisiert
    ↓
git commit (lokal)
    ↓
ℹ️  "Push manually when ready"
    ↓
ERD aus YAML generieren
    ↓
AI-Doku aus YAML (wenn aktiviert)
    ↓
Changelog aus Git-Diff
```

---

## 📁 GitHub Repository Struktur

Nach dem ersten Sync wird automatisch erstellt:

```
github.com/{organization}/{server-hostname}/
├── {team_name}/
│   └── {database_name}/
│       ├── .ninox-metadata.json        ← Metadata (ID tracking)
│       ├── APPLICATION_DOCS.md         ← AI Doku (direkt auf DB-Ebene!)
│       ├── SCRIPTS.md                  ← Alle Scripts (Format: "YAML-Code")
│       └── src/
│           └── Objects/
│               └── database_{db_name}/
│                   ├── database.yaml   ← Haupt-YAML
│                   ├── erd.svg         ← ERD Diagramm
│                   ├── Tables/         ← YAML pro Tabelle
│                   │   ├── Table1.yaml
│                   │   └── Table2.yaml
└── README.md                           ← Auto-generiert (optional)
```

---

## 🔧 Was Sie tun müssen

### 1. GitHub-Credentials konfigurieren (einmalig):
1. GitHub → Settings → Developer Settings → Personal Access Token
2. Scope: `repo` (Full control)
3. Token kopieren
4. In Ninox2Git WebApp → User Profile → GitHub Tab:
   - Token eintragen
   - Organization: Ihr GitHub-Username
   - Speichern

### 2. Erster Sync starten:
- Gehen Sie zur Sync-Seite
- Klicken Sie "Sync All YAML"
- **Automatisch passiert:**
  - GitHub-Repo wird erstellt
  - YAML-Struktur wird gepusht
  - Sie sehen Repository-URL im Log

### 3. Weitere Syncs:
- Klicken Sie "Sync All YAML"
- **Lokal:** Git commit erfolgt automatisch
- **GitHub:** Push manuell wenn gewünscht:
  ```bash
  docker exec -it nx2git-webapp bash
  cd /app/data/ninox-cli/team_<id>
  git push
  ```

---

## 🎯 Nächste Schritte (optional)

### Sofort verfügbar:
1. ✅ Sync mit automatischem GitHub-Push (erster Sync)
2. ✅ ERD aus YAML
3. ✅ AI-Dokumentation aus YAML
4. ✅ Changelog aus YAML-Diff

### Optional in Zukunft:
1. `convert_yaml_to_json_structure()` Funktion löschen (wird nicht mehr verwendet)
2. Migration-Skript für alte JSON-Dateien in GitHub (falls vorhanden)

---

## 📝 Migrationsanleitung für bestehende Installationen

Falls Sie bereits Daten haben:

### Ihre lokalen YAML-Dateien:
✅ **Keine Änderung nötig** - bleiben wo sie sind

### GitHub-Repositories:
- **Alte JSON-Dateien** (falls vorhanden):
  - Können gelöscht werden
  - Werden nicht mehr aktualisiert
- **Neue YAML-Struktur:**
  - Wird beim nächsten Sync automatisch gepusht

### Datenbank:
- **Google Drive Felder** (`drive_document_id`, `drive_last_upload`):
  - Werden nicht mehr verwendet
  - Bleiben in DB (für Abwärtskompatibilität)
  - Können manuell gelöscht werden mit Migration

---

## 🐛 Troubleshooting

### Problem: Repository wird nicht erstellt
**Lösung:**
1. Prüfen Sie GitHub-Token im Profil
2. Prüfen Sie Organization-Name
3. Log anschauen: `/app/data/logs/webapp.log`

### Problem: Push schlägt fehl
**Lösung:**
1. Token-Berechtigung prüfen (braucht `repo`)
2. Organisation/Username korrekt?
3. Repository existiert bereits? → OK, wird erkannt

### Problem: Changelog wird nicht generiert
**Lösung:**
1. AI-Provider konfiguriert? (Admin → AI Config)
2. Commits vorhanden? `git log` im team-Ordner
3. YAML-Dateien geändert? Ohne Diff kein Changelog

---

## ✅ Fertig!

Alle 6 Sprints abgeschlossen. Das System ist jetzt **100% YAML-basiert**!

**Genießen Sie Ihr Git-basiertes, YAML-natives Ninox-Backup-System!** 🎉
