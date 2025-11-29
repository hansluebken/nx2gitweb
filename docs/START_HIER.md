# 🚀 Ninox2Git WebApp - START HIER

## Willkommen!

Diese Datei führt Sie durch die ersten Schritte zur Inbetriebnahme der Ninox2Git WebApp.

---

## ✅ Was wurde bereits erledigt?

- ✅ Vollständige Webanwendung implementiert
- ✅ Docker-Container konfiguriert
- ✅ PostgreSQL-Datenbank eingerichtet
- ✅ Sicherheitsschlüssel generiert
- ✅ `.env` Datei vorbereitet
- ✅ Dokumentation erstellt

## ⚠️ Was müssen SIE noch tun?

Nur **2 Schritte** bis zur fertigen Anwendung:

### 📧 Schritt 1: SMTP konfigurieren (5 Minuten)

Öffnen Sie die `.env` Datei und tragen Sie Ihre Gmail-Zugangsdaten ein:

```bash
nano /home/nx2git-go/webapp/.env
```

Ändern Sie diese zwei Zeilen:

```bash
SMTP_USER=ihre-email@gmail.com          # ← Ihre Gmail-Adresse
SMTP_PASSWORD=ihr-app-passwort          # ← Ihr Google App-Passwort
```

**Wie bekomme ich ein App-Passwort?**
👉 Siehe `SMTP_SETUP_GUIDE.md` für detaillierte Anleitung

### 🚀 Schritt 2: Anwendung starten (1 Minute)

```bash
cd /home/nx2git-go/webapp
./start.sh
```

Das war's! Die Anwendung läuft jetzt.

---

## 🌐 NGINX Proxy Manager konfigurieren

Öffnen Sie NGINX Proxy Manager und erstellen Sie einen neuen Proxy Host:

**Quick Setup:**
- Domain: `nx2git.netz-fabrik.net`
- Forward to: `nx2git-webapp:8765`
- SSL: Let's Encrypt aktivieren
- Force SSL: ✅

**Detaillierte Anleitung:**
👉 Siehe `NGINX_PROXY_MANAGER_CONFIG.md`

---

## 🔐 Erste Anmeldung

Sobald NPM konfiguriert ist:

1. Öffnen Sie: **https://nx2git.netz-fabrik.net**
2. Melden Sie sich an:
   - **Benutzername**: `user500`
   - **Passwort**: `Quaternion1234____`
3. **WICHTIG**: Ändern Sie sofort das Passwort!

---

## 📚 Dokumentation

Alle wichtigen Dateien auf einen Blick:

| Datei | Zweck |
|-------|-------|
| `START_HIER.md` | 👈 Diese Datei - Ihr Einstiegspunkt |
| `DEPLOYMENT_GUIDE.md` | Vollständige Deployment-Anleitung |
| `NGINX_PROXY_MANAGER_CONFIG.md` | NPM-Konfiguration im Detail |
| `SMTP_SETUP_GUIDE.md` | E-Mail-Konfiguration |
| `README.md` | Umfassende Dokumentation |
| `PROJEKT_ZUSAMMENFASSUNG.md` | Projekt-Übersicht |

---

## 🛠️ Nützliche Befehle

```bash
# Anwendung starten
./start.sh

# Logs anzeigen
docker-compose logs -f webapp

# Status prüfen
docker-compose ps

# Anwendung stoppen
docker-compose down

# Neu starten
docker-compose restart
```

---

## ✅ Checkliste

Haken Sie ab, was Sie erledigt haben:

### Konfiguration
- [ ] `.env` Datei bearbeitet
- [ ] SMTP-Zugangsdaten eingetragen
- [ ] Anwendung gestartet (`./start.sh`)

### NGINX Proxy Manager
- [ ] Proxy Host erstellt
- [ ] Domain konfiguriert (`nx2git.netz-fabrik.net`)
- [ ] SSL-Zertifikat erhalten
- [ ] HTTPS funktioniert

### Erste Schritte
- [ ] Login erfolgreich
- [ ] Admin-Passwort geändert
- [ ] Ersten Server hinzugefügt
- [ ] Team synchronisiert
- [ ] E-Mail-Versand getestet

---

## 🆘 Probleme?

### Anwendung startet nicht

```bash
# Logs prüfen
docker-compose logs -f

# Container neu bauen
docker-compose build --no-cache
docker-compose up -d
```

### 502 Bad Gateway

```bash
# Container-Status prüfen
docker-compose ps

# Netzwerk prüfen
docker network inspect proxy-network | grep nx2git
```

### E-Mail funktioniert nicht

```bash
# SMTP-Verbindung testen
docker exec -it nx2git-webapp python -c "
from app.email_service import test_smtp_connection
test_smtp_connection()
"
```

👉 Weitere Lösungen in `DEPLOYMENT_GUIDE.md`

---

## 📞 Support

Bei Fragen:
- 📖 Lesen Sie `DEPLOYMENT_GUIDE.md`
- 📧 E-Mail: admin@netz-fabrik.net
- 📝 Alle Logs: `docker-compose logs -f`

---

## 🎯 Nächste Schritte nach Setup

1. **Backup einrichten**
   ```bash
   mkdir -p backups
   # Siehe DEPLOYMENT_GUIDE.md für Cron-Jobs
   ```

2. **Ersten Server hinzufügen**
   - Gehen Sie zu "Server"
   - Klicken Sie "Server hinzufügen"
   - Geben Sie Ninox-URL und API-Key ein
   - Konfigurieren Sie GitHub

3. **Teams synchronisieren**
   - Gehen Sie zu "Teams"
   - Wählen Sie Ihren Server
   - Klicken Sie "Teams synchronisieren"

4. **Datenbanken mit GitHub syncen**
   - Gehen Sie zu "Sync"
   - Wählen Sie Server und Team
   - Klicken Sie "Datenbanken synchronisieren"

---

## 🏁 Los geht's!

**Viel Erfolg mit Ihrer Ninox2Git WebApp!**

Beginnen Sie mit Schritt 1: SMTP konfigurieren 👆

---

*Erstellt: 2025-01-09*
*Status: Production Ready ✅*
