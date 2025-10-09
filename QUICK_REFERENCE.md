# Ninox2Git WebApp - Schnellreferenz

## 🚀 Quick Start (3 Schritte)

```bash
# 1. SMTP konfigurieren
nano /home/nx2git-go/webapp/.env
# → SMTP_USER und SMTP_PASSWORD eintragen

# 2. Starten
cd /home/nx2git-go/webapp
./start.sh

# 3. NPM konfigurieren (siehe NGINX_PROXY_MANAGER_CONFIG.md)
```

## 📋 Wichtige Befehle

### Container-Verwaltung
```bash
cd /home/nx2git-go/webapp

# Starten
docker-compose up -d

# Stoppen
docker-compose down

# Neu starten
docker-compose restart

# Logs
docker-compose logs -f webapp

# Status
docker-compose ps
```

### Backup
```bash
# Datenbank
docker exec nx2git-postgres pg_dump -U nx2git nx2git > backup_$(date +%Y%m%d).sql

# Verschlüsselungsschlüssel
cp data/keys/encryption.key backups/encryption.key.$(date +%Y%m%d)
```

### Troubleshooting
```bash
# Container neu bauen
docker-compose build --no-cache && docker-compose up -d

# Logs prüfen
docker-compose logs -f

# In Container-Shell
docker exec -it nx2git-webapp bash

# Datenbank-Shell
docker exec -it nx2git-postgres psql -U nx2git -d nx2git

# SMTP testen
docker exec -it nx2git-webapp python -c "from app.email_service import test_smtp_connection; test_smtp_connection()"
```

## 🔑 Zugangsdaten

**WebApp:**
- URL: `https://nx2git.netz-fabrik.net`
- User: `user500`
- Pass: `Quaternion1234____`

**PostgreSQL:**
- Host: `postgres` (im Docker-Netzwerk)
- Port: `5432`
- DB: `nx2git`
- User: `nx2git`
- Pass: `0miZqIj_iEhBPKJWphyn8DTACSJ5_YJQH1zDlWov-oQ`

## 📁 Wichtige Dateien

| Datei | Pfad |
|-------|------|
| Konfiguration | `/home/nx2git-go/webapp/.env` |
| Verschlüsselungsschlüssel | `/home/nx2git-go/webapp/data/keys/encryption.key` |
| Logs | `/home/nx2git-go/webapp/data/logs/` |
| Datenbank | `/home/nx2git-go/webapp/data/database/` |
| Backups | `/home/nx2git-go/webapp/backups/` |

## 🛠️ NGINX Proxy Manager

**Einstellungen:**
- Domain: `nx2git.netz-fabrik.net`
- Scheme: `http`
- Forward Host: `nx2git-webapp`
- Forward Port: `8765`
- SSL: Let's Encrypt
- Force SSL: ✅
- WebSockets: ✅

## 📧 SMTP (Gmail)

**Setup:**
1. Google-Konto → Sicherheit
2. 2FA aktivieren
3. App-Passwörter → Mail
4. Passwort kopieren
5. In `.env` eintragen:
   ```bash
   SMTP_USER=ihre-email@gmail.com
   SMTP_PASSWORD=abcdefghijklmnop
   ```

## 🔐 Sicherheit

**Berechtigungen:**
```bash
chmod 600 .env
chmod 600 data/keys/encryption.key
chmod 700 data/keys
```

**Passwörter ändern:**
1. Login als Admin
2. Benutzer-Icon → Einstellungen
3. Passwort ändern

## 📊 Monitoring

**Container-Status:**
```bash
docker stats nx2git-webapp nx2git-postgres
```

**Speicherplatz:**
```bash
du -sh data/*
```

**Audit-Logs:**
- WebApp → Admin → Audit Logs

## 🆘 Häufige Probleme

**502 Bad Gateway:**
```bash
docker-compose restart webapp
docker network connect proxy-network nx2git-webapp
```

**Datenbank-Fehler:**
```bash
docker-compose restart postgres
sleep 10
docker-compose restart webapp
```

**E-Mail funktioniert nicht:**
- Gmail App-Passwort prüfen
- 2FA muss aktiviert sein
- SMTP-Test ausführen

## 📚 Dokumentation

| Datei | Inhalt |
|-------|--------|
| `START_HIER.md` | Einstiegspunkt |
| `DEPLOYMENT_GUIDE.md` | Vollständige Anleitung |
| `NGINX_PROXY_MANAGER_CONFIG.md` | NPM-Setup |
| `SMTP_SETUP_GUIDE.md` | E-Mail-Konfiguration |
| `README.md` | Umfassende Docs |
| `QUICK_REFERENCE.md` | Diese Datei |

## 🎯 Workflow

### Neuer Benutzer
1. Admin → Benutzer → Hinzufügen
2. E-Mail wird automatisch gesendet
3. Benutzer erhält Zugangsdaten

### Neuer Server
1. Server → Server hinzufügen
2. Ninox URL & API-Key
3. GitHub Token (optional)
4. Verbindung testen
5. Speichern

### Team synchronisieren
1. Teams → Server wählen
2. Teams synchronisieren
3. Teams aktivieren

### Datenbanken syncen
1. Sync → Server & Team wählen
2. Datenbanken synchronisieren
3. Einzeln oder alle syncen
4. GitHub-Repo prüfen

## 💾 Backup-Strategie

**Täglich (Cron):**
```bash
# crontab -e
0 2 * * * cd /home/nx2git-go/webapp && docker exec nx2git-postgres pg_dump -U nx2git nx2git > backups/db_$(date +\%Y\%m\%d).sql
0 4 * * * find /home/nx2git-go/webapp/backups -name "*.sql" -mtime +30 -delete
```

**Wöchentlich:**
```bash
# Verschlüsselungsschlüssel
0 3 * * 0 cp /home/nx2git-go/webapp/data/keys/encryption.key /home/nx2git-go/webapp/backups/encryption.key.$(date +\%Y\%m\%d)
```

## 🔄 Updates

```bash
cd /home/nx2git-go/webapp

# Backup erstellen
docker exec nx2git-postgres pg_dump -U nx2git nx2git > backup_before_update.sql

# Images aktualisieren
docker-compose pull

# Neu bauen
docker-compose build --no-cache

# Neu starten
docker-compose up -d

# Logs prüfen
docker-compose logs -f webapp
```

## 📞 Support

- 📖 Dokumentation: `/home/nx2git-go/webapp/`
- 📧 E-Mail: admin@netz-fabrik.net
- 🔧 Logs: `docker-compose logs -f`
