# Ninox2Git WebApp - Deployment Guide

Vollständige Schritt-für-Schritt-Anleitung zur Bereitstellung der Ninox2Git WebApp.

## Übersicht

Die Anwendung besteht aus:
- **NiceGUI WebApp** (Python) - Port 8765
- **PostgreSQL 16** (Datenbank)
- **NGINX Proxy Manager** (Reverse Proxy mit SSL)

## Voraussetzungen

✅ Docker und Docker Compose installiert
✅ NGINX Proxy Manager läuft
✅ `proxy-network` existiert
✅ Domain `nx2git.netz-fabrik.net` zeigt auf Server
✅ Ports 80 und 443 sind offen

## Deployment-Schritte

### Schritt 1: Verzeichnis vorbereiten

```bash
cd /home/nx2git-go/webapp
```

### Schritt 2: SMTP-Konfiguration anpassen

Bearbeiten Sie die `.env` Datei und tragen Sie Ihre Gmail-Zugangsdaten ein:

```bash
nano .env
```

Ändern Sie diese Zeilen:
```bash
SMTP_USER=ihre-email@gmail.com
SMTP_PASSWORD=ihr-google-app-passwort
```

**So erstellen Sie ein Google App-Passwort:**

1. Gehen Sie zu https://myaccount.google.com/security
2. Aktivieren Sie 2-Faktor-Authentifizierung
3. Gehen Sie zu "App-Passwörter"
4. Erstellen Sie ein neues Passwort für "Mail"
5. Kopieren Sie das 16-stellige Passwort
6. Tragen Sie es in `.env` ein

### Schritt 3: Verzeichnisse erstellen

```bash
mkdir -p data/database data/logs data/keys
chmod 700 data/keys
chmod 600 .env
```

### Schritt 4: Docker-Container starten

```bash
# Container bauen und starten
docker-compose up -d

# Logs überprüfen
docker-compose logs -f webapp
```

**Erwartete Ausgabe:**
```
✓ Database tables created successfully
✓ New encryption key generated at /app/data/keys/encryption.key
✓ Admin user created: user500
NiceGUI ready to go on http://0.0.0.0:8765
```

### Schritt 5: Container-Status prüfen

```bash
docker-compose ps
```

**Erwartete Ausgabe:**
```
NAME                 STATUS    PORTS
nx2git-postgres      Up        5432/tcp
nx2git-webapp        Up        8765/tcp
```

### Schritt 6: proxy-network Verbindung prüfen

```bash
# Prüfen, ob Container im proxy-network ist
docker network inspect proxy-network | grep nx2git-webapp
```

Sollte den Container zeigen. Falls nicht:

```bash
docker network connect proxy-network nx2git-webapp
```

### Schritt 7: NGINX Proxy Manager konfigurieren

Öffnen Sie NGINX Proxy Manager und erstellen Sie einen neuen Proxy Host mit **exakt** diesen Einstellungen:

#### Details Tab:
- **Domain Names**: `nx2git.netz-fabrik.net`
- **Scheme**: `http`
- **Forward Hostname/IP**: `nx2git-webapp`
- **Forward Port**: `8765`
- **Cache Assets**: ✅ aktiviert
- **Block Common Exploits**: ✅ aktiviert
- **Websockets Support**: ✅ aktiviert

#### SSL Tab:
- **SSL Certificate**: Request a new SSL Certificate with Let's Encrypt
- **Email**: `admin@netz-fabrik.net`
- **Force SSL**: ✅ aktiviert
- **HTTP/2 Support**: ✅ aktiviert
- **HSTS Enabled**: ✅ aktiviert
- **HSTS Subdomains**: ✅ aktiviert

#### Advanced Tab (Optional aber empfohlen):
```nginx
# Security Headers
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;

# WebSocket Support
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";

# Proxy Headers
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;

# Timeouts
proxy_connect_timeout 600s;
proxy_send_timeout 600s;
proxy_read_timeout 600s;

# Buffer sizes
client_max_body_size 100M;
```

Klicken Sie auf **Save**.

### Schritt 8: SSL-Zertifikat Verifizierung

Warten Sie 30-60 Sekunden, bis Let's Encrypt das Zertifikat ausgestellt hat.

Prüfen Sie dann:

```bash
curl -I https://nx2git.netz-fabrik.net
```

**Erwartete Antwort:**
```
HTTP/2 200
server: nginx
strict-transport-security: max-age=31536000; includeSubDomains
```

### Schritt 9: Erste Anmeldung

1. Öffnen Sie Browser: `https://nx2git.netz-fabrik.net`
2. Melden Sie sich an mit:
   - **Benutzername**: `user500`
   - **Passwort**: `Quaternion1234____`

3. **WICHTIG**: Ändern Sie sofort das Admin-Passwort:
   - Klicken Sie auf das Benutzer-Icon → Einstellungen
   - Wählen Sie "Passwort ändern"
   - Geben Sie ein neues, sicheres Passwort ein

### Schritt 10: Ersten Server hinzufügen

1. Gehen Sie zu **Server**
2. Klicken Sie auf **Server hinzufügen**
3. Geben Sie ein:
   - **Name**: z.B. "Production Ninox"
   - **URL**: z.B. "https://nx.nf1.eu"
   - **API-Key**: Ihr Ninox API-Key
   - **GitHub Token**: Ihr GitHub Personal Access Token
   - **GitHub Organisation**: Ihr GitHub Username oder Organisation
4. Klicken Sie auf **Verbindung testen**
5. Wenn erfolgreich, klicken Sie auf **Speichern**

## Verifizierung

### 1. Container-Logs prüfen

```bash
docker-compose logs -f webapp
```

### 2. Datenbank-Verbindung testen

```bash
docker exec -it nx2git-postgres psql -U nx2git -d nx2git -c "SELECT * FROM users;"
```

Sollte den user500 anzeigen.

### 3. Verschlüsselung prüfen

```bash
ls -la data/keys/
```

Sollte `encryption.key` mit Berechtigungen `600` zeigen.

### 4. E-Mail-Versand testen

In der WebApp:
1. Gehen Sie zu Login-Seite
2. Klicken Sie auf "Passwort vergessen"
3. Geben Sie Admin-E-Mail ein
4. Prüfen Sie Posteingang

## Backup-Strategie

### Automatisches Backup einrichten

Erstellen Sie ein Cron-Job für tägliche Backups:

```bash
crontab -e
```

Fügen Sie hinzu:

```bash
# Tägliches Backup um 2 Uhr morgens
0 2 * * * cd /home/nx2git-go/webapp && docker exec nx2git-postgres pg_dump -U nx2git nx2git > backups/db_$(date +\%Y\%m\%d).sql

# Wöchentliches Backup des Verschlüsselungsschlüssels (Sonntags)
0 3 * * 0 cp /home/nx2git-go/webapp/data/keys/encryption.key /home/nx2git-go/webapp/backups/encryption.key.$(date +\%Y\%m\%d)

# Alte Backups löschen (älter als 30 Tage)
0 4 * * * find /home/nx2git-go/webapp/backups -name "*.sql" -mtime +30 -delete
```

Erstellen Sie Backup-Verzeichnis:

```bash
mkdir -p backups
chmod 700 backups
```

### Manuelles Backup

```bash
# Datenbank
docker exec nx2git-postgres pg_dump -U nx2git nx2git > backup_$(date +%Y%m%d).sql

# Verschlüsselungsschlüssel
cp data/keys/encryption.key backups/encryption.key.$(date +%Y%m%d)
```

### Wiederherstellung

```bash
# Datenbank wiederherstellen
cat backup_20241009.sql | docker exec -i nx2git-postgres psql -U nx2git -d nx2git

# Verschlüsselungsschlüssel wiederherstellen
cp backups/encryption.key.20241009 data/keys/encryption.key
chmod 600 data/keys/encryption.key

# Container neu starten
docker-compose restart
```

## Wartung

### Container aktualisieren

```bash
cd /home/nx2git-go/webapp
docker-compose pull
docker-compose build --no-cache
docker-compose up -d
```

### Logs anzeigen

```bash
# Alle Logs
docker-compose logs -f

# Nur WebApp
docker-compose logs -f webapp

# Nur Datenbank
docker-compose logs -f postgres
```

### Container neu starten

```bash
# Alle Container
docker-compose restart

# Nur WebApp
docker-compose restart webapp
```

### Datenbank optimieren

```bash
docker exec nx2git-postgres psql -U nx2git -d nx2git -c "VACUUM ANALYZE;"
```

## Troubleshooting

### Problem: 502 Bad Gateway

**Diagnose:**
```bash
# Container-Status prüfen
docker-compose ps

# WebApp-Logs prüfen
docker-compose logs webapp

# Netzwerk prüfen
docker network inspect proxy-network | grep nx2git
```

**Lösung:**
```bash
# Container neu starten
docker-compose restart webapp

# Falls notwendig, Netzwerk neu verbinden
docker network connect proxy-network nx2git-webapp
```

### Problem: Datenbank-Verbindungsfehler

**Diagnose:**
```bash
# PostgreSQL-Status
docker-compose ps postgres

# PostgreSQL-Logs
docker-compose logs postgres

# Verbindung testen
docker exec -it nx2git-postgres psql -U nx2git -d nx2git -c "SELECT 1;"
```

**Lösung:**
```bash
# PostgreSQL neu starten
docker-compose restart postgres

# Warten und erneut versuchen
sleep 10
docker-compose restart webapp
```

### Problem: E-Mail-Versand fehlgeschlagen

**Diagnose:**
```bash
# SMTP-Konfiguration in .env prüfen
grep SMTP .env

# Test-E-Mail senden (in Container)
docker exec -it nx2git-webapp python -c "
from app.email_service import test_smtp_connection
test_smtp_connection()
"
```

**Lösung:**
- Prüfen Sie Gmail App-Passwort
- Stellen Sie sicher, dass 2FA aktiviert ist
- Verwenden Sie das 16-stellige App-Passwort, nicht Ihr normales Passwort

### Problem: Verschlüsselungsschlüssel fehlt

**Diagnose:**
```bash
ls -la data/keys/encryption.key
```

**Lösung:**
```bash
# Container neu starten - Key wird automatisch generiert
docker-compose restart webapp

# WICHTIG: Alte verschlüsselte Daten müssen neu verschlüsselt werden!
```

## Sicherheits-Checkliste

- [ ] Admin-Passwort geändert
- [ ] `.env` hat Berechtigungen 600
- [ ] `data/keys/encryption.key` hat Berechtigungen 600
- [ ] SSL/HTTPS ist aktiviert
- [ ] Force SSL ist aktiviert
- [ ] HSTS ist aktiviert
- [ ] Backups sind konfiguriert
- [ ] SMTP ist korrekt konfiguriert
- [ ] Firewall lässt nur 80/443 zu
- [ ] Regelmäßige Updates sind geplant

## Nützliche Befehle

```bash
# Status aller Container
docker-compose ps

# Alle Logs verfolgen
docker-compose logs -f

# Container stoppen
docker-compose down

# Container starten
docker-compose up -d

# Container neu bauen
docker-compose build --no-cache

# In Container-Shell
docker exec -it nx2git-webapp bash

# In PostgreSQL-Shell
docker exec -it nx2git-postgres psql -U nx2git -d nx2git

# Speicherverbrauch
docker stats nx2git-webapp nx2git-postgres

# Cleanup (VORSICHT!)
docker-compose down -v  # Löscht auch Volumes!
```

## Support

Bei Problemen:
1. Prüfen Sie die Logs: `docker-compose logs -f`
2. Konsultieren Sie `NGINX_PROXY_MANAGER_CONFIG.md`
3. Lesen Sie `README.md`
4. Kontaktieren Sie: admin@netz-fabrik.net
