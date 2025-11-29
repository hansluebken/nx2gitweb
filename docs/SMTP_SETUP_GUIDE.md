# SMTP-Konfiguration für Gmail

## Schritt-für-Schritt Anleitung

### Schritt 1: Google-Konto vorbereiten

1. Gehen Sie zu https://myaccount.google.com/security
2. Scrollen Sie zu "Bei Google anmelden"
3. Klicken Sie auf "Bestätigung in zwei Schritten"
4. Falls noch nicht aktiviert, aktivieren Sie die 2-Faktor-Authentifizierung

### Schritt 2: App-Passwort erstellen

1. Gehen Sie zurück zu https://myaccount.google.com/security
2. Scrollen Sie zu "Bei Google anmelden"
3. Klicken Sie auf "App-Passwörter"
4. Wählen Sie:
   - **App**: Mail
   - **Gerät**: Anderes (benutzerdefinierter Name)
5. Geben Sie einen Namen ein: `Ninox2Git WebApp`
6. Klicken Sie auf "Generieren"
7. **Kopieren Sie das 16-stellige Passwort** (z.B. `abcd efgh ijkl mnop`)

### Schritt 3: .env konfigurieren

Bearbeiten Sie die `.env` Datei:

```bash
cd /home/nx2git-go/webapp
nano .env
```

Ändern Sie diese Zeilen:

```bash
# SMTP Credentials
SMTP_USER=ihre-email@gmail.com
SMTP_PASSWORD=abcdefghijklmnop    # 16-stelliges App-Passwort (ohne Leerzeichen!)
```

**Wichtig**: Entfernen Sie die Leerzeichen aus dem App-Passwort!

### Schritt 4: Testen

Starten Sie die Container:

```bash
./start.sh
```

Testen Sie den E-Mail-Versand:

```bash
docker exec -it nx2git-webapp python -c "
from app.email_service import test_smtp_connection
test_smtp_connection()
"
```

**Erwartete Ausgabe:**
```
✓ SMTP connection successful
```

### Schritt 5: In der WebApp testen

1. Öffnen Sie https://nx2git.netz-fabrik.net
2. Klicken Sie auf "Passwort vergessen"
3. Geben Sie Ihre E-Mail-Adresse ein
4. Prüfen Sie Ihren Posteingang

## Beispiel-Konfiguration

### Vollständige SMTP-Sektion in .env

```bash
# SMTP Server (für Gmail)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true

# SMTP Credentials
SMTP_USER=admin@netz-fabrik.net
SMTP_PASSWORD=abcdefghijklmnop

# Email sender information
SMTP_FROM=noreply@netz-fabrik.net
SMTP_FROM_NAME=Ninox2Git
```

## Alternative: Anderer E-Mail-Anbieter

### Outlook.com / Office 365

```bash
SMTP_HOST=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=ihre-email@outlook.com
SMTP_PASSWORD=ihr-passwort
```

### Eigener SMTP-Server

```bash
SMTP_HOST=mail.ihre-domain.de
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=noreply@ihre-domain.de
SMTP_PASSWORD=ihr-passwort
```

## Troubleshooting

### Problem: "Authentication failed"

**Lösung:**
- Stellen Sie sicher, dass 2FA aktiviert ist
- Verwenden Sie ein App-Passwort, nicht Ihr normales Passwort
- Entfernen Sie Leerzeichen aus dem App-Passwort

### Problem: "Connection timeout"

**Lösung:**
- Prüfen Sie Firewall-Einstellungen (Port 587 muss offen sein)
- Testen Sie mit: `telnet smtp.gmail.com 587`

### Problem: E-Mails kommen nicht an

**Lösung:**
- Prüfen Sie Spam-Ordner
- Stellen Sie sicher, dass `SMTP_FROM` eine gültige E-Mail ist
- Prüfen Sie Gmail-Konto auf Sicherheitswarnungen

## Sicherheitshinweise

1. **Niemals** das normale Google-Passwort verwenden
2. **Immer** App-Passwörter verwenden
3. `.env` Datei **niemals** in Git committen
4. Berechtigungen: `chmod 600 .env`
5. App-Passwort bei Kompromittierung widerrufen

## E-Mail-Templates

Die Anwendung sendet folgende E-Mails:

1. **Willkommens-E-Mail** bei Registrierung
2. **Passwort-Reset** bei vergessenen Passwort
3. **Passwort geändert** nach erfolgreicher Änderung
4. **Account deaktiviert** bei Deaktivierung durch Admin

Alle E-Mails haben:
- ✅ HTML-Version mit Logo und Styling
- ✅ Plain-Text-Fallback
- ✅ Responsive Design
- ✅ Professionelles Layout
