# Troubleshooting Guide

## PostgreSQL Authentication Failed

### Problem
Nach dem Start der Container erhält die webapp den Fehler:
```
FATAL: password authentication failed for user "nx2git"
```

### Ursache
Das Problem hatte mehrere Ursachen:

1. **DNS-Auflösung**: Der Hostname "postgres" konnte nicht aufgelöst werden
2. **Container-Naming**: Der korrekte Hostname ist "nx2git-postgres" (der Container-Name), nicht "postgres"
3. **Passwort-Encoding**: Spezielle Zeichen im Passwort können Probleme verursachen

### Lösung

#### 1. DATABASE_URL korrigieren
In `docker-compose.yml` oder `.env`:
```yaml
DATABASE_URL: postgresql://nx2git:PASSWORT@nx2git-postgres:5432/nx2git
# NICHT: @postgres:5432
# SONDERN: @nx2git-postgres:5432
```

#### 2. Passwort vereinfachen
Verwenden Sie ein Passwort ohne Sonderzeichen wie `-`, `_`, oder Base64-Zeichen:
```bash
# Schlecht: 0miZqIj_iEhBPKJWphyn8DTACSJ5_YJQH1zDlWov-oQ
# Gut: nx2gitSecurePassword2024
```

#### 3. Bei bestehendem Container: Passwort zurücksetzen
Falls die Datenbank bereits mit einem anderen Passwort initialisiert wurde:
```bash
# Passwort direkt im PostgreSQL Container ändern
docker exec nx2git-postgres psql -U nx2git -d nx2git -c "ALTER USER nx2git WITH PASSWORD 'NEUES_PASSWORT';"

# Webapp neu starten
docker-compose restart webapp
```

#### 4. Kompletter Reset (wenn nichts hilft)
```bash
# Alles stoppen und löschen
docker-compose down -v
sudo rm -rf data/database

# Neu starten
docker-compose up -d
```

### Debugging-Befehle

#### Verbindung testen
```bash
# Von außen testen
docker run --rm --network webapp_nx2git-internal postgres:16-alpine \
  sh -c "PGPASSWORD='PASSWORT' psql -h nx2git-postgres -U nx2git -d nx2git -c 'SELECT 1'"

# Aus webapp Container testen
docker-compose run --rm webapp sh -c \
  "PGPASSWORD='PASSWORT' psql -h nx2git-postgres -U nx2git -d nx2git -c 'SELECT 1'"
```

#### Logs prüfen
```bash
# PostgreSQL Logs
docker-compose logs postgres | grep -E "(authentication|FATAL)"

# Webapp Logs
docker-compose logs webapp | grep -E "(ERROR|password)"
```

#### Netzwerk prüfen
```bash
# Container im Netzwerk
docker network inspect webapp_nx2git-internal

# DNS-Auflösung testen
docker-compose run --rm webapp sh -c "ping -c 1 nx2git-postgres"
```

## NGINX Proxy Manager "Not Found" Error

### Problem
Die Domain zeigt "Not Found", obwohl die webapp läuft.

### Ursache
1. Forward Hostname war auf "localhost" statt Container-Name gesetzt
2. DNS-Eintrag fehlte oder zeigte auf falsche IP

### Lösung

#### 1. NPM Konfiguration korrigieren
Im NGINX Proxy Manager (Port 81):
- **Forward Hostname**: `nx2git-webapp` (NICHT localhost!)
- **Forward Port**: `8765`
- **Websocket Support**: Aktiviert (wichtig für NiceGUI!)

#### 2. DNS konfigurieren
A-Record anlegen:
```
nx2git.netz-fabrik.net → Server-IP (z.B. 87.106.232.128)
```

#### 3. Verbindung testen
```bash
# Von NPM aus testen
docker exec nginx-proxy-manager curl http://nx2git-webapp:8765

# Mit Host-Header testen
curl -H "Host: nx2git.netz-fabrik.net" http://localhost
```

## Port-Konflikte

### Problem
Port 8765 ist bereits belegt.

### Lösung
In `docker-compose.yml` den Port ändern:
```yaml
ports:
  - "8766:8765"  # Host-Port 8766, Container-Port bleibt 8765
```

## SQLAlchemy Session Binding Error

### Problem
Beim Login erscheint der Fehler:
```
Instance <User at 0x...> is not bound to a Session; attribute refresh operation cannot proceed
```

### Ursache
Das User-Objekt ist nach `db.close()` nicht mehr an die SQLAlchemy Session gebunden, aber die UI-Komponenten versuchen auf User-Attribute zuzugreifen.

### Lösung
In `app/auth.py` die Funktionen `login_user` und `get_user_from_token` anpassen:

```python
# In login_user() nach dem commit:
db.refresh(user)  # User wieder an Session binden
# ... weitere Operationen ...
db.expunge(user)  # User von Session trennen vor return

# In get_user_from_token() vor return:
db.expunge(user)  # User von Session trennen
```

Dies stellt sicher, dass das User-Objekt unabhängig von der Session verwendet werden kann.

## Container startet nicht

### Problem
Container bleibt im Status "Restarting".

### Debugging
```bash
# Logs anschauen
docker-compose logs --tail=50 webapp

# Manuell starten für bessere Fehlermeldungen
docker-compose run --rm webapp

# Health-Check Status
docker inspect nx2git-webapp --format='{{json .State.Health}}'
```

## Backup und Wiederherstellung

### Datenbank-Backup
```bash
# Backup erstellen
docker exec nx2git-postgres pg_dump -U nx2git nx2git > backup.sql

# Backup wiederherstellen
docker exec -i nx2git-postgres psql -U nx2git nx2git < backup.sql
```

### Vollständiges Backup
```bash
# Alle Daten sichern
tar -czf nx2git-backup.tar.gz data/ .env

# Wiederherstellen
tar -xzf nx2git-backup.tar.gz
docker-compose up -d
```