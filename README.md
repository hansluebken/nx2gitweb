# Ninox2Git WebApp

Eine professionelle Webanwendung zur Synchronisation von Ninox-Datenbanken mit GitHub, gebaut mit NiceGUI, PostgreSQL und Docker.

## Features

### Kernfunktionalitäten
- **Multi-Server-Verwaltung**: Verwalten Sie mehrere Ninox-Server in einer Anwendung
- **Team-Synchronisation**: Synchronisieren Sie Teams und Datenbanken von Ninox
- **GitHub-Integration**: Automatische Versionierung in privaten GitHub-Repositories
- **Benutzerverwaltung**: Multi-User-System mit Admin- und Benutzerrollen
- **Verschlüsselte Credentials**: Sichere Speicherung von API-Keys und Tokens
- **KI-gestützte Changelogs**: Automatische Beschreibung von Änderungen (Claude, OpenAI, Gemini)
- **Code-Viewer**: Hierarchische Ansicht aller Ninox-Codefelder mit Syntax-Highlighting
- **Änderungshistorie**: Vollständige Nachverfolgbarkeit aller Datenbankänderungen

### Sicherheit
- **JWT-Token-Authentifizierung**: Sichere, zustandslose Authentifizierung
- **Bcrypt-Passwort-Hashing**: Industrie-Standard für Passwort-Sicherheit
- **Fernet-Verschlüsselung**: Verschlüsselte Speicherung von API-Keys und GitHub-Tokens
- **Audit-Logging**: Vollständige Nachverfolgbarkeit aller Benutzeraktionen
- **Benutzerisolation**: Jeder Benutzer sieht nur seine eigenen Daten
- **Admin-Berechtigungen**: Granulare Zugriffskontrolle

### Benutzeroberfläche
- **Modernes Design**: Gradient-Design mit responsivem Layout
- **Dashboard**: Übersicht mit Statistiken und Quick Actions
- **Server-Verwaltung**: CRUD-Operationen für Ninox-Server
- **Team-Management**: Teams synchronisieren und verwalten
- **Sync-Interface**: Datenbanken mit GitHub synchronisieren
- **Admin-Panel**: Benutzerverwaltung und Audit-Logs

## Technologie-Stack

- **Frontend**: NiceGUI (Python-basiertes Web-Framework)
- **Backend**: Python 3.10+
- **Datenbank**: PostgreSQL 16
- **ORM**: SQLAlchemy 2.0
- **Authentifizierung**: PyJWT, Bcrypt
- **Verschlüsselung**: Cryptography (Fernet)
- **Container**: Docker & Docker Compose
- **Proxy**: NGINX Proxy Manager Integration

## Architektur

```
webapp/
├── docker-compose.yml          # Docker-Orchestrierung
├── Dockerfile                  # Container-Definition
├── requirements.txt            # Python-Dependencies
├── .env.example               # Umgebungsvariablen-Template
├── app/
│   ├── main.py                # NiceGUI-Hauptanwendung
│   ├── auth.py                # Authentifizierungssystem
│   ├── database.py            # Datenbank-Konfiguration
│   ├── email_service.py       # E-Mail-Dienst
│   ├── models/                # SQLAlchemy-Models
│   │   ├── user.py
│   │   ├── server.py
│   │   ├── team.py
│   │   ├── database.py
│   │   ├── audit_log.py
│   │   ├── password_reset.py
│   │   ├── ai_config.py       # KI-Provider Konfiguration
│   │   └── changelog.py       # Änderungsprotokoll
│   ├── services/              # Business-Logik Services
│   │   ├── ai_changelog.py    # KI-gestützte Changelog-Generierung
│   │   └── cronjob_scheduler.py
│   ├── migrations/            # Datenbank-Migrationen
│   │   ├── migrate_add_ai_and_changelog.py
│   │   └── migrate_add_ai_tokens.py
│   ├── ui/                    # UI-Komponenten
│   │   ├── components.py      # Wiederverwendbare Komponenten
│   │   ├── login.py           # Login-Seite
│   │   ├── dashboard.py       # Dashboard
│   │   ├── servers.py         # Server-Verwaltung
│   │   ├── teams.py           # Team-Management
│   │   ├── sync.py            # Synchronisation
│   │   ├── admin.py           # Admin-Panel (inkl. KI-Konfiguration)
│   │   ├── changes.py         # Änderungshistorie
│   │   ├── code_viewer.py     # Ninox Code-Viewer
│   │   └── database_timeline.py  # Timeline-Dialog
│   ├── api/                   # API-Clients
│   │   ├── ninox_client.py
│   │   └── github_manager.py
│   └── utils/                 # Hilfsfunktionen
│       ├── encryption.py
│       ├── helpers.py
│       ├── validators.py
│       └── ninox_code_extractor.py
└── data/                      # Persistente Daten (Volumes)
    ├── database/              # PostgreSQL-Daten
    ├── keys/                  # Verschlüsselungsschlüssel
    ├── logs/                  # Anwendungs-Logs
    └── code/                  # Extrahierte Ninox-Code-Dateien
```

## ⚠️ Wichtige Hinweise

### Datenbank-Hostname
- Der PostgreSQL-Container heißt `nx2git-postgres`, nicht nur `postgres`
- In der DATABASE_URL muss `@nx2git-postgres:5432` stehen

### NGINX Proxy Manager Konfiguration
- **Forward Hostname muss `nx2git-webapp` sein** (NICHT localhost oder 127.0.0.1!)
- **Websocket Support muss aktiviert sein** für NiceGUI
- Der DNS A-Record muss auf die öffentliche Server-IP zeigen

### Bei Problemen
Siehe [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) für detaillierte Lösungen zu häufigen Problemen.

## Installation und Setup

### Voraussetzungen

- Docker und Docker Compose installiert
- NGINX Proxy Manager (optional, für SSL/HTTPS)
- Domain (optional): `nx2git.netz-fabrik.net` oder eigene Domain

### Proxy-Network erstellen (falls NGINX Proxy Manager verwendet wird)

```bash
# Prüfen ob das Netzwerk existiert
docker network ls | grep proxy-network

# Falls nicht, erstellen:
docker network create proxy-network
```

### Schritt 1: Repository klonen

```bash
# Repository klonen
git clone https://github.com/hansluebken/nx2gitweb.git
cd nx2gitweb

# Oder in ein spezifisches Verzeichnis
git clone https://github.com/hansluebken/nx2gitweb.git /home/nx2git/webapp
cd /home/nx2git/webapp
```

### Schritt 2: Umgebungsvariablen konfigurieren

```bash
cp .env.example .env
nano .env
```

**Wichtige Konfigurationen:**

```bash
# Datenbank-Passwort ändern
POSTGRES_PASSWORD=Ihr_sicheres_Passwort_hier

# Secret Keys generieren
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET_KEY=$(openssl rand -hex 32)
NICEGUI_STORAGE_SECRET=$(openssl rand -hex 32)

# SMTP für E-Mail konfigurieren
SMTP_USER=ihre-email@gmail.com
SMTP_PASSWORD=ihr-app-spezifisches-passwort

# Domain anpassen
APP_URL=https://nx2git.netz-fabrik.net
```

### Schritt 3: Verschlüsselungsschlüssel erstellen

```bash
mkdir -p data/keys data/logs data/database
chmod 700 data/keys
```

Der Verschlüsselungsschlüssel wird automatisch beim ersten Start generiert.

### Schritt 4: Docker Container starten

```bash
# Container bauen und starten
docker-compose up -d --build

# Alternativ bei Updates:
docker-compose build --no-cache
docker-compose up -d
```

### Schritt 5: Datenbank-Migrationen ausführen

Bei der ersten Installation werden die Tabellen automatisch erstellt.
Nach Updates mit neuen Features ggf. Migrationen ausführen:

```bash
# KI-Konfiguration und Changelog-Tabellen
docker-compose exec webapp python -m app.migrations.migrate_add_ai_and_changelog

# Token-Tracking (falls noch nicht vorhanden)
docker-compose exec webapp python -m app.migrations.migrate_add_ai_tokens
```

### Schritt 6: Logs überprüfen

```bash
docker-compose logs -f webapp
```

### Schritt 7: Reverse Proxy konfigurieren

Wählen Sie **eine** der folgenden Optionen:

---

#### Option A: NGINX Proxy Manager (Docker-basiert)

Für diese Option muss das `proxy-network` existieren (siehe Voraussetzungen).

1. In NGINX Proxy Manager einloggen
2. Neuen Proxy Host erstellen:
   - **Domain Names**: `nx2git.ihre-domain.de`
   - **Scheme**: `http`
   - **Forward Hostname/IP**: `nx2git-webapp` (Container-Name!)
   - **Forward Port**: `8765`
   - **Websockets Support**: ✅ Aktivieren (wichtig für NiceGUI!)
   - **SSL**: Let's Encrypt aktivieren
   - **Force SSL**: Ja

**Wichtig**: Der Forward Hostname muss `nx2git-webapp` sein, NICHT `localhost` oder `127.0.0.1`!

---

#### Option B: NGINX auf dem Host installiert

Falls Sie NGINX direkt auf dem Host installiert haben (nicht als Docker-Container):

1. **Alternative docker-compose verwenden**:

```bash
# Statt der Standard docker-compose.yml:
docker-compose -f docker-compose.host-nginx.yml up -d --build
```

Oder manuell in `docker-compose.yml` den Port freigeben:

```yaml
webapp:
  ports:
    - "127.0.0.1:8765:8765"  # Nur lokal erreichbar
```

2. **NGINX Konfiguration kopieren**:

```bash
# Beispielkonfiguration kopieren
sudo cp docs/nginx-host-example.conf /etc/nginx/sites-available/nx2git

# Domain anpassen
sudo nano /etc/nginx/sites-available/nx2git
# Ersetze "nx2git.ihre-domain.de" durch Ihre Domain
```

3. **Konfiguration aktivieren**:

```bash
# Symlink erstellen
sudo ln -s /etc/nginx/sites-available/nx2git /etc/nginx/sites-enabled/

# Konfiguration testen
sudo nginx -t

# NGINX neu laden
sudo systemctl reload nginx
```

4. **SSL-Zertifikat mit certbot erstellen**:

```bash
# Certbot installieren (falls nicht vorhanden)
sudo apt install certbot python3-certbot-nginx

# Zertifikat erstellen - certbot konfiguriert NGINX automatisch
sudo certbot --nginx -d nx2git.ihre-domain.de
```

Certbot wird automatisch:
- SSL-Zertifikate erstellen und einbinden
- HTTPS-Redirect konfigurieren
- Automatische Erneuerung einrichten

---

#### Option C: Direkter Zugriff (nur für Tests)

Für lokale Tests ohne Reverse Proxy:

1. **Port freigeben** in `docker-compose.yml`:

```yaml
webapp:
  ports:
    - "8765:8765"  # Öffentlich erreichbar
```

2. Zugriff über `http://server-ip:8765`

**Hinweis**: Nicht für Produktion empfohlen (kein HTTPS)!

---

### Schritt 8: Erste Anmeldung

1. Öffnen Sie `https://nx2git.netz-fabrik.net`
2. Melden Sie sich mit dem Admin-Account an:
   - **Benutzername**: `user500`
   - **Passwort**: `Quaternion1234____`
3. **WICHTIG**: Ändern Sie sofort das Admin-Passwort!

## Verwendung

### Neuen Server hinzufügen

1. Navigieren Sie zu **Server**
2. Klicken Sie auf **Server hinzufügen**
3. Geben Sie die Server-Details ein:
   - Name (z.B. "Production Server")
   - URL (z.B. "https://nx.nf1.eu")
   - Ninox API-Key
   - GitHub-Konfiguration (optional)
4. Klicken Sie auf **Verbindung testen**
5. Speichern Sie den Server

### Teams synchronisieren

1. Navigieren Sie zu **Teams**
2. Wählen Sie einen Server aus
3. Klicken Sie auf **Teams synchronisieren**
4. Aktivieren Sie die gewünschten Teams

### Datenbanken mit GitHub synchronisieren

1. Navigieren Sie zu **Sync**
2. Wählen Sie Server und Team aus
3. Klicken Sie auf **Datenbanken synchronisieren**
4. Wählen Sie die zu synchronisierenden Datenbanken aus
5. Klicken Sie auf **Alle synchronisieren**

### Benutzer verwalten (Admin)

1. Navigieren Sie zu **Admin**
2. Im Tab **Benutzer**:
   - Neue Benutzer erstellen
   - Benutzer aktivieren/deaktivieren
   - Benutzer löschen

### Audit-Logs einsehen (Admin)

1. Navigieren Sie zu **Admin**
2. Im Tab **Audit-Logs**:
   - Alle Benutzeraktionen anzeigen
   - Nach Aktion oder Benutzer filtern

## Sicherheits-Best-Practices

### Produktionsumgebung

1. **Starke Passwörter verwenden**:
   - Datenbank: Mindestens 16 Zeichen
   - Admin-Passwort sofort nach Setup ändern

2. **Secret Keys sichern**:
   ```bash
   chmod 600 .env
   chmod 600 data/keys/encryption.key
   ```

3. **HTTPS erzwingen**:
   - Let's Encrypt in NGINX Proxy Manager aktivieren
   - Force SSL aktivieren

4. **Regelmäßige Backups**:
   ```bash
   # Datenbank-Backup
   docker exec nx2git-postgres pg_dump -U nx2git nx2git > backup.sql

   # Verschlüsselungsschlüssel sichern
   cp data/keys/encryption.key backup/encryption.key.backup
   ```

5. **Updates durchführen**:
   ```bash
   docker-compose pull
   docker-compose up -d
   ```

## Backup und Wiederherstellung

### Backup erstellen

```bash
# Datenbank
docker exec nx2git-postgres pg_dump -U nx2git nx2git > backup_$(date +%Y%m%d).sql

# Verschlüsselungsschlüssel
cp data/keys/encryption.key backup/encryption.key.$(date +%Y%m%d)
```

### Wiederherstellung

```bash
# Datenbank wiederherstellen
cat backup_20241009.sql | docker exec -i nx2git-postgres psql -U nx2git -d nx2git

# Verschlüsselungsschlüssel wiederherstellen
cp backup/encryption.key.20241009 data/keys/encryption.key
chmod 600 data/keys/encryption.key

# Container neu starten
docker-compose restart
```

## Troubleshooting

### Problem: Container startet nicht

```bash
# Logs prüfen
docker-compose logs webapp

# Container neu bauen
docker-compose build --no-cache
docker-compose up -d
```

### Problem: Datenbank-Verbindungsfehler

```bash
# PostgreSQL-Status prüfen
docker-compose ps postgres

# PostgreSQL-Logs prüfen
docker-compose logs postgres

# Verbindung testen
docker exec -it nx2git-postgres psql -U nx2git -d nx2git -c "SELECT 1;"
```

### Problem: E-Mail-Versand schlägt fehl

1. SMTP-Konfiguration in `.env` überprüfen
2. Für Gmail: App-spezifisches Passwort verwenden
3. SMTP-Verbindung testen:
   ```bash
   docker exec -it nx2git-webapp python -c "from app.email_service import test_smtp_connection; test_smtp_connection()"
   ```

### Problem: JWT-Token ungültig

1. `JWT_SECRET_KEY` in `.env` überprüfen
2. Container neu starten:
   ```bash
   docker-compose restart webapp
   ```

## Development

### Lokale Entwicklung

```bash
# Virtuelle Umgebung erstellen
python3 -m venv venv
source venv/bin/activate

# Dependencies installieren
pip install -r requirements.txt

# Entwicklungsserver starten
cd app
python main.py
```

### Tests ausführen

```bash
pytest
```

## Wartung

### Logs rotieren

```bash
# Alte Logs archivieren
tar -czf logs_archive_$(date +%Y%m%d).tar.gz data/logs/*.log
rm data/logs/*.log
```

### Datenbank optimieren

```bash
# Vacuum und Analyze
docker exec nx2git-postgres psql -U nx2git -d nx2git -c "VACUUM ANALYZE;"
```

## Support und Kontakt

Bei Fragen oder Problemen:

- GitHub Issues: [Repository-URL]
- E-Mail: admin@netz-fabrik.net

## Lizenz

Proprietär - Alle Rechte vorbehalten

### KI-Konfiguration (optional)

Für automatische Changelog-Beschreibungen einen KI-Provider konfigurieren:

1. Navigieren Sie zu **Admin** → **KI-Konfiguration**
2. Wählen Sie einen Provider (Claude, OpenAI oder Gemini)
3. Geben Sie den API-Key ein
4. Testen Sie die Verbindung
5. Setzen Sie den Provider als Standard

Die Token-Nutzung wird automatisch getrackt und in der UI angezeigt.

## Changelog

### Version 1.1.0 (2025-11-30)
- KI-gestützte Changelog-Generierung (Claude, OpenAI, Gemini)
- Token-Tracking für Kostenüberwachung
- Neue Seite "Änderungen" mit Filter und Suche
- Database Timeline Dialog mit KI-Zusammenfassungen
- Erweiterter Code-Viewer mit Änderungshistorie
- Admin-Panel mit KI-Provider Konfiguration

### Version 1.0.0 (2025-01-09)
- Initiale Release
- Multi-User-System mit JWT-Authentifizierung
- Server- und Team-Verwaltung
- GitHub-Integration
- Admin-Panel mit Audit-Logs
- E-Mail-Benachrichtigungen
- Docker-Deployment mit PostgreSQL
