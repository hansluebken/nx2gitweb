# Ninox2Git WebApp - Deployment Dokumentation

## Systemanforderungen

### Server
- Docker & Docker Compose
- Min. 2GB RAM
- Min. 10GB Speicher
- Linux (Ubuntu 22.04+ empfohlen)

### Externe Services
- PostgreSQL 16+ (via Docker)
- GitHub Account mit Personal Access Token
- Ninox Server mit API-Zugriff

## Installation

### 1. Repository klonen
```bash
git clone <repository-url>
cd nx2git-go/webapp
```

### 2. Umgebungsvariablen konfigurieren
Erstellen Sie `.env` Datei:

```bash
# Database
DATABASE_URL=postgresql://nx2git:nx2git@nx2git-postgres:5432/nx2git
POSTGRES_PASSWORD=<sicheres-passwort>

# Security
JWT_SECRET_KEY=<generiere-mit: openssl rand -hex 32>
SESSION_SECRET=<generiere-mit: openssl rand -hex 32>
ENCRYPTION_KEY=<generiere-mit: openssl rand -hex 32>

# GitHub (Optional - wird im User-Profil konfiguriert)
GITHUB_DEPLOYMENT_TOKEN=<optional-für-deployment>

# App
APP_PORT=8765
APP_HOST=0.0.0.0
```

### 3. Build und Start
```bash
docker-compose build
docker-compose up -d
```

### 4. Zugriff
- Webapp: `http://localhost:8765`
- Standard-Admin: `user500` / `Quaternion1234____`

## Wichtige Features

### Authentication
- JWT-basierte Authentifizierung
- User-Preferences für Server/Team-Auswahl
- Session-Persistenz

### Datenbank-Synchronisation
- Manuelle Sync: "Sync Now" Button
- Bulk-Sync: "Sync All" Button
- Automatische Syncs: Cronjob-System

**WICHTIG:** Neue Datenbanken sind standardmäßig **EXCLUDED** und müssen manuell aktiviert werden!

### GitHub-Integration

**Repository-Struktur:**
- Ein Repository pro Server
- Repository-Name = Server-Hostname (z.B. `ninox.netz-fabrik.net`)
- Struktur: `Team/Database-structure.json`
- ERD: `Team/Database-erd.svg`

**Konfiguration:**
1. Im User-Profil GitHub Token hinterlegen
2. Organization: Ihr GitHub Username
3. Token braucht Rechte: `repo` (Full control of private repositories)

### ERD-Diagramme

**Layout (5 Spalten):**
| REV-Quelle | Feldname | Typ | ID | REF-Ziel |
|------------|----------|-----|-----|----------|

**Farben:**
- 🔑 Primary Key: Gelb
- 🔗 REF-Felder: Orange (Zeile + rechte Spalte grün)
- ↩️ REV-Felder: Grün (Zeile + linke Spalte orange)

**Features:**
- Pan & Zoom im Viewer (svg-pan-zoom library)
- Automatische Generierung beim Sync
- Kompaktes Layout (LR-Richtung, kurze Linien)

### Cronjobs

**Typen:**
- **Intervall:** Alle X Minuten/Stunden/Tage/Wochen (Minuten in 5er-Schritten)
- **Täglich:** Jeden Tag um HH:MM

**Scheduler:**
- Läuft automatisch im Hintergrund
- Prüft alle 30 Sekunden
- Synct nur nicht-excluded Datenbanken

## Wartung

### Logs ansehen
```bash
docker-compose logs -f webapp
docker-compose logs -f postgres
```

### Backup
Wichtige Verzeichnisse:
- `/app/data/keys` - Verschlüsselungsschlüssel
- PostgreSQL Datenbank

```bash
# Database backup
docker exec nx2git-postgres pg_dump -U nx2git nx2git > backup.sql

# Keys backup
docker cp nx2git-webapp:/app/data/keys ./backup_keys/
```

### Updates
```bash
git pull
docker-compose build
docker-compose up -d
```

### Rebuild (bei größeren Änderungen)
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Troubleshooting

### "Connection lost" beim Sync
- Normal bei langen Operationen
- Funktioniert im Hintergrund weiter
- Progress wird in Logs angezeigt
- Seite refresh (F5) um Ergebnisse zu sehen

### "Bad Gateway" / 502
- Container nicht gestartet: `docker-compose ps`
- Logs prüfen: `docker-compose logs webapp --tail=50`
- Neustart: `docker-compose restart webapp`

### SVG-Diagramme werden nicht generiert
- Prüfen: Graphviz installiert? `docker exec nx2git-webapp dot -V`
- Logs: `docker-compose logs webapp | grep "SVG\|ERD"`
- Neu syncen um neue ERDs zu generieren

### Browser-Cache Probleme
- Hard-Refresh: Strg+Shift+R / Cmd+Shift+R
- Neues Inkognito-Fenster
- Anderer Browser zum Testen

## Sicherheit

- Alle Passwörter verschlüsselt (Fernet)
- JWT-Tokens mit Expiration
- Audit-Logging aller Aktionen
- Private GitHub Repositories
- HTTPS via Reverse Proxy empfohlen (nginx/NPM)

## Performance

- SQLAlchemy mit Connection Pooling
- Async/Await für alle I/O-Operationen
- Thread-Pool für lange API-Calls
- Lazy-Loading von Datenbanken

## Bekannte Einschränkungen

1. **Volume-Mount:** Code-Änderungen erfordern Container-Restart
2. **Große Datenbanken:** ERD-Generierung kann 5-10 Sekunden dauern
3. **Browser-Cache:** Bei Updates manchmal Neubau nötig

## Support

- GitHub Issues: <repository-url>/issues
- Logs sind Ihr Freund: `docker-compose logs -f webapp`
