# Claude Code Prompt für Ninox2Git WebApp

## Projekt-Kontext

Du arbeitest an der **Ninox2Git WebApp**, einer professionellen Webanwendung zur Synchronisation von Ninox-Datenbanken mit GitHub. Die Anwendung ist in Python geschrieben und nutzt NiceGUI als Web-Framework, PostgreSQL als Datenbank und läuft vollständig in Docker-Containern.

---

## Technologie-Stack

### Core Technologies
- **Python**: 3.10-slim (Container-basiert)
- **Web Framework**: NiceGUI >= 3.0.0
- **API Framework**: FastAPI >= 0.109.1, < 0.123.5 (Version gepinnt wegen Coroutine-Bug)
- **Datenbank**: PostgreSQL 16-alpine
- **ORM**: SQLAlchemy >= 2.0.0 mit Alembic >= 1.13.0
- **Container**: Docker & Docker Compose

### Key Dependencies
```
# Web & API
nicegui>=3.0.0
fastapi>=0.109.1,<0.123.5  # WICHTIG: Version constraint beachten!

# Datenbank
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.9
alembic>=1.13.0

# Authentifizierung & Sicherheit
PyJWT>=2.8.0
passlib>=1.7.4
bcrypt>=4.1.0
cryptography>=41.0.0

# HTTP & API
requests>=2.31.0
PyGithub>=2.1.1
httpx>=0.25.0

# KI-Provider
anthropic>=0.18.0       # Claude
openai>=1.12.0          # OpenAI GPT
google-generativeai>=0.8.3  # Google Gemini

# E-Mail
aiosmtplib>=3.0.0
email-validator>=2.1.0

# Ninox CLI (Node.js)
# Wird über npm installiert (package.json)
```

### System-Dependencies (Dockerfile)
- gcc
- postgresql-client
- curl
- graphviz (für ERD-Generierung)
- gnupg
- git
- Node.js 18+ (für ninox-dev-cli)

---

## Projekt-Struktur

```
/home/nx2git-go/webapp/
├── docker-compose.yml          # Docker-Orchestrierung
├── docker-compose.host-nginx.yml  # Alternative für Host-NGINX
├── Dockerfile                  # Python 3.10-slim Container
├── requirements.txt            # Python Dependencies
├── package.json               # Node.js Dependencies (ninox-dev-cli)
├── .env                       # Umgebungsvariablen (NICHT committen!)
├── .env.example              # Template
├── start.sh                  # Quick-Start Script
├── README.md                 # Haupt-Dokumentation
│
├── app/                      # Haupt-Anwendung
│   ├── main.py              # NiceGUI Entry Point
│   ├── auth.py              # JWT-Authentifizierung
│   ├── database.py          # SQLAlchemy Setup
│   ├── email_service.py     # SMTP E-Mail Service
│   ├── dto.py               # Data Transfer Objects
│   │
│   ├── models/              # SQLAlchemy Models
│   │   ├── base.py         # Base Model & Mixins
│   │   ├── user.py         # User Model (JWT, OAuth)
│   │   ├── server.py       # Ninox Server Config
│   │   ├── team.py         # Team Model
│   │   ├── database.py     # Database Model
│   │   ├── audit_log.py    # Audit Logging
│   │   ├── password_reset.py
│   │   ├── ai_config.py    # KI-Provider Konfiguration
│   │   └── changelog.py    # Änderungsprotokoll
│   │
│   ├── services/           # Business Logic
│   │   ├── ninox_sync_service.py     # Kern-Sync-Logik
│   │   ├── ninox_cli_service.py      # YAML Discovery
│   │   ├── ai_changelog.py           # KI Changelog-Generierung
│   │   └── cronjob_scheduler.py      # Background Jobs
│   │
│   ├── api/                # External API Clients
│   │   ├── ninox_client.py    # Ninox REST API
│   │   └── github_manager.py  # GitHub Integration
│   │
│   ├── ui/                 # NiceGUI UI Components
│   │   ├── components.py       # Wiederverwendbare UI-Elemente
│   │   ├── login.py           # Login & OAuth
│   │   ├── dashboard.py       # Hauptübersicht
│   │   ├── servers.py         # Server-Verwaltung
│   │   ├── teams.py           # Team-Management
│   │   ├── sync.py            # Sync-Interface (135 KB!)
│   │   ├── admin.py           # Admin-Panel (95 KB!)
│   │   ├── cronjobs.py        # Cron-Job Verwaltung
│   │   ├── code_viewer.py     # Code-Viewer
│   │   ├── yaml_code_viewer.py # YAML Code-Viewer
│   │   ├── json_viewer.py     # JSON-Viewer
│   │   ├── changes.py         # Änderungshistorie
│   │   └── profile.py         # Benutzerprofil
│   │
│   ├── utils/              # Hilfsfunktionen
│   │   ├── encryption.py       # Fernet-Verschlüsselung
│   │   ├── helpers.py          # Allgemeine Helpers
│   │   ├── validators.py       # Input-Validierung
│   │   ├── path_resolver.py    # Pfad-Logik
│   │   ├── metadata_helper.py  # Metadata-Verwaltung
│   │   └── ninox_code_extractor.py
│   │
│   └── migrations/         # Datenbank-Migrationen
│       ├── migrate_add_ai_and_changelog.py
│       ├── migrate_add_ai_tokens.py
│       ├── migrate_add_oauth.py
│       └── migrate_add_drive.py
│
├── data/                   # Docker Volumes (persistente Daten)
│   ├── database/          # PostgreSQL Daten
│   ├── keys/              # Verschlüsselungsschlüssel (600 Permissions!)
│   ├── logs/              # Application Logs
│   ├── code/              # Ninox Code-Dateien
│   ├── ninox-cli/         # YAML-Dateien (Metadata-first)
│   └── debug/             # Debug Logs (z.B. Gemini API)
│
├── docs/                  # Dokumentation
│   ├── START_HIER.md
│   ├── PROJEKT_ZUSAMMENFASSUNG.md
│   ├── NGINX_PROXY_MANAGER_CONFIG.md
│   ├── SMTP_SETUP_GUIDE.md
│   ├── TROUBLESHOOTING.md
│   └── ...
│
├── tools/                 # Zusatz-Tools
└── backups/              # Backup-Verzeichnis
```

---

## Docker-Architektur

### Container
1. **nx2git-postgres** (postgres:16-alpine)
   - Datenbank: nx2git
   - User: nx2git
   - Port: 5432 (intern)
   - Volume: ./data/database

2. **nx2git-webapp** (Python 3.10-slim)
   - Port: 8765 (intern)
   - User: nx2git (UID 1000, non-root)
   - Volumes:
     - ./app → /app/app (live code updates)
     - ./data/keys → /app/data/keys
     - ./data/logs → /app/data/logs
     - ./data/code → /app/data/code
     - ./data/ninox-cli → /app/data/ninox-cli
     - ./data/debug → /app/data/debug

### Networks
- **nx2git-internal**: Bridge (PostgreSQL ↔ WebApp)
- **proxy-network**: External (NGINX Proxy Manager ↔ WebApp)

### Wichtige Umgebungsvariablen
```bash
# Datenbank
DATABASE_URL=postgresql://nx2git:${POSTGRES_PASSWORD}@nx2git-postgres:5432/nx2git

# Security Keys (generiert mit: openssl rand -hex 32)
SECRET_KEY=...
JWT_SECRET_KEY=...
ENCRYPTION_KEY_PATH=/app/data/keys/encryption.key

# SMTP (Gmail)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...  # App-spezifisches Passwort!

# App
APP_URL=https://nx2git.netz-fabrik.net
APP_PORT=8765
ADMIN_EMAIL=...

# Ninox CLI
NINOX_CLI_DATA_PATH=/app/data/ninox-cli
```

---

## Wichtige Architektur-Konzepte

### 1. Klarnamen-Struktur (Metadata-First)
Die Anwendung verwendet einen **Metadata-First-Ansatz**:
- Ninox-Datenbanken werden als YAML heruntergeladen (ninox-dev-cli)
- Struktur: `{Server}/{Team}/{Database}/`
- Metadata in `.nx-metadata.json` (Name, ID, Team, etc.)
- Code-Dateien in hierarchischer Struktur
- Fallback auf alte Struktur falls nötig

### 2. Synchronisations-Pipeline
```
1. Download (ninox-dev-cli) → _temp/
2. Umstrukturierung → {Server}/{Team}/{Database}/
3. Temp-Ordner löschen
4. Git commit (Server-Level)
5. GitHub push
6. ERD generieren (Graphviz)
7. Dokumentation generieren
8. KI-Changelog (optional)
```

### 3. Multi-Tenant-Architektur
- Jeder User sieht nur seine eigenen Daten
- Foreign Key Constraints für Datenisolation
- Admin kann alles sehen (is_admin Flag)
- Audit-Logging für alle kritischen Aktionen

### 4. Verschlüsselung
- **Fernet** (symmetrisch) für API-Keys und GitHub-Tokens
- Schlüssel in `/app/data/keys/encryption.key` (Permissions: 600)
- Automatische Generierung beim ersten Start

### 5. Authentifizierung
- **JWT-Tokens** mit konfigurierbarer Ablaufzeit
- **Bcrypt** Passwort-Hashing (Faktor 12)
- **Google OAuth2** (Single Sign-On, optional)
- Domain-basierte Zugriffskontrolle

---

## Bekannte Besonderheiten

### FastAPI Version Constraint
```python
# requirements.txt
fastapi>=0.109.1,<0.123.5  # WICHTIG: Coroutine-Bug in neueren Versionen
```
**Grund**: NiceGUI Issue #5535 - Coroutine serialization bug
**Lösung**: Version pinnen bis Bug gefixt ist

### NGINX Proxy Manager
**WICHTIG**: Forward Hostname muss `nx2git-webapp` sein, NICHT `localhost`!
- WebSocket Support MUSS aktiviert sein (NiceGUI Requirement)
- SSL via Let's Encrypt
- Force SSL aktivieren

### Container neu bauen
**IMMER** `--no-cache` verwenden bei Problemen:
```bash
docker-compose build --no-cache
docker-compose up -d
```

### Permissions
```bash
chmod 600 .env
chmod 600 data/keys/encryption.key
chmod 700 data/keys/
```

---

## Development-Workflow

### Code-Änderungen
1. Code in `./app/` bearbeiten
2. Container lädt automatisch neu (Volume-Mount!)
3. Bei Dependency-Änderungen:
   ```bash
   docker-compose build --no-cache
   docker-compose up -d
   ```

### Datenbank-Migrationen
```bash
# Migration erstellen
docker-compose exec webapp python -m app.migrations.migrate_xxx

# Oder manuell mit Alembic
docker-compose exec webapp alembic revision -m "description"
docker-compose exec webapp alembic upgrade head
```

### Logs
```bash
# Alle Logs
docker-compose logs -f

# Nur WebApp
docker-compose logs -f webapp

# Nur Postgres
docker-compose logs -f postgres
```

### Datenbank-Zugriff
```bash
# psql
docker exec -it nx2git-postgres psql -U nx2git -d nx2git

# Backup
docker exec nx2git-postgres pg_dump -U nx2git nx2git > backup.sql

# Restore
cat backup.sql | docker exec -i nx2git-postgres psql -U nx2git -d nx2git
```

---

## Best Practices für Claude Code

### 1. Dokumentation konsultieren
- **IMMER** zuerst die neueste Dokumentation prüfen:
  - NiceGUI: https://nicegui.io
  - SQLAlchemy 2.0: https://docs.sqlalchemy.org/en/20/
  - FastAPI: https://fastapi.tiangolo.com
  - Anthropic API: https://docs.anthropic.com
  - OpenAI API: https://platform.openai.com/docs
  - Google Gemini: https://ai.google.dev/docs

### 2. Neueste Versionen verwenden
- Bei Dependency-Updates **IMMER** auf neueste stabile Versionen updaten
- **AUSNAHME**: FastAPI Version-Constraint beachten!
- Changelogs/Migration Guides prüfen bei Major-Updates

### 3. Docker Best Practices
```bash
# Bei Problemen: Container ohne Cache neu bauen
docker-compose build --no-cache
docker-compose up -d

# Volumes prüfen
docker volume ls
docker volume inspect webapp_data

# Netzwerk prüfen
docker network inspect proxy-network
```

### 4. Code-Qualität
- **Type Hints** verwenden (Python 3.10+)
- **Async/Await** für I/O-Operationen
- **SQLAlchemy 2.0** Syntax (kein Legacy Mode!)
- **NiceGUI Reactive** pattern nutzen
- **Error Handling** mit try/except
- **Logging** statt print()

### 5. Sicherheit
- **NIEMALS** Secrets im Code
- **IMMER** `.env` für Konfiguration
- **Encryption** für sensitive Daten (API-Keys, Tokens)
- **Input Validation** für alle User-Inputs
- **SQL Injection** Prevention (SQLAlchemy ORM nutzen)
- **XSS** Prevention (NiceGUI sanitized inputs)

### 6. Testing
```bash
# Tests ausführen
docker-compose exec webapp pytest

# Mit Coverage
docker-compose exec webapp pytest --cov=app
```

---

## Häufige Aufgaben

### Neues Feature hinzufügen
1. Model erstellen/erweitern (`app/models/`)
2. Migration schreiben (`app/migrations/`)
3. Service-Logik implementieren (`app/services/`)
4. UI-Komponente erstellen (`app/ui/`)
5. Route in `app/main.py` registrieren
6. Tests schreiben
7. Dokumentation aktualisieren

### Dependency hinzufügen
```bash
# Python
echo "neue-library>=1.0.0" >> requirements.txt
docker-compose build --no-cache
docker-compose up -d

# Node.js (für ninox-dev-cli)
# In package.json eintragen, dann:
docker-compose build --no-cache
```

### Debugging
```bash
# Python Debugger
import pdb; pdb.set_trace()

# Oder mit IPython
import IPython; IPython.embed()

# Logs in Echtzeit
docker-compose logs -f webapp

# Container Shell
docker-compose exec webapp bash
```

### Performance-Optimierung
- **Async** für alle I/O (DB, HTTP, File)
- **Connection Pooling** (SQLAlchemy)
- **Caching** wo sinnvoll
- **Batch Operations** für DB
- **Lazy Loading** für große Datasets

---

## Wichtige Dateien zum Lesen

Bevor du Änderungen machst, lies:
1. `README.md` - Feature-Übersicht
2. `docs/START_HIER.md` - Quick Start
3. `docs/PROJEKT_ZUSAMMENFASSUNG.md` - Projekt-Status
4. `IMPLEMENTATION_STATUS.md` - Aktuelle Implementierung
5. `app/main.py` - Routing & App-Struktur
6. `.env.example` - Alle Konfigurationsoptionen

---

## Admin-Zugang

**Default Admin:**
- Username: `user500`
- Password: `Quaternion1234____`
- **WICHTIG**: Nach erstem Login ändern!

**Neue User anlegen:**
1. Via UI (Admin-Panel)
2. Via OAuth (automatisch bei erlaubter Domain)
3. Via Shell:
   ```bash
   docker-compose exec webapp python -c "
   from app.database import get_db
   from app.auth import create_user
   db = get_db()
   create_user(db, 'username', 'email@example.com', 'password', is_admin=False)
   "
   ```

---

## Troubleshooting

### Container startet nicht
```bash
# Logs prüfen
docker-compose logs webapp

# Syntax-Check
docker-compose exec webapp python -m py_compile app/main.py

# Komplett neu bauen
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Datenbank-Fehler
```bash
# Verbindung testen
docker exec nx2git-postgres pg_isready -U nx2git

# Logs
docker-compose logs postgres

# Permissions
ls -la data/database/
```

### NGINX 502 Bad Gateway
```bash
# Container läuft?
docker-compose ps

# Port erreichbar?
docker exec nx2git-webapp curl -f http://localhost:8765/

# Netzwerk OK?
docker network inspect proxy-network | grep nx2git
```

### E-Mail funktioniert nicht
```bash
# SMTP-Test
docker-compose exec webapp python -c "
from app.email_service import test_smtp_connection
test_smtp_connection()
"

# Logs prüfen
docker-compose logs webapp | grep -i smtp
```

---

## Wichtige Links

- **GitHub**: https://github.com/hansluebken/nx2gitweb
- **Production**: https://nx2git.netz-fabrik.net
- **Ninox API**: https://docs.ninox.com/en/api
- **NiceGUI Docs**: https://nicegui.io
- **SQLAlchemy 2.0**: https://docs.sqlalchemy.org/en/20/

---

## Zusammenfassung

Du arbeitest an einer **produktionsreifen Multi-User-Webanwendung** zur Synchronisation von Ninox-Datenbanken mit GitHub. Die App nutzt moderne Python-Technologien (NiceGUI, SQLAlchemy 2.0, FastAPI) und läuft vollständig in Docker.

**Wichtigste Prinzipien:**
1. **Neueste Versionen** verwenden (außer FastAPI!)
2. **Dokumentation** konsultieren vor Implementation
3. **Docker ohne Cache** neu bauen bei Problemen
4. **Sicherheit** ernst nehmen (Encryption, Validation, Auth)
5. **Async/Await** für I/O-Operationen
6. **Type Hints** und **Logging** verwenden
7. **Tests** schreiben

Bei Fragen zur Architektur: README.md und docs/ lesen!
