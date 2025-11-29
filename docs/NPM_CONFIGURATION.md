# NGINX Proxy Manager Konfiguration für Ninox2Git

## Zugriff auf NPM
- URL: http://localhost:81
- Standard Login: admin@example.com / changeme

## Proxy Host Konfiguration

### 1. Neuen Proxy Host anlegen
Gehen Sie zu "Hosts" → "Proxy Hosts" → "Add Proxy Host"

### 2. Details Tab
- **Domain Names**: `nx2git.netz-fabrik.net`
- **Scheme**: `http` (nicht https!)
- **Forward Hostname / IP**: `nx2git-webapp`
  - ⚠️ WICHTIG: NICHT localhost oder 127.0.0.1 verwenden!
  - Es muss der Container-Name sein: `nx2git-webapp`
- **Forward Port**: `8765`
- **Cache Assets**: ✓ (aktiviert)
- **Block Common Exploits**: ✓ (aktiviert)
- **Websocket Support**: ✓ (WICHTIG für NiceGUI!)
- **Access List**: Publicly Accessible

### 3. Custom Locations (optional)
Nicht erforderlich für Standard-Setup

### 4. SSL Tab (wenn HTTPS gewünscht)
- **SSL Certificate**: Request a new SSL Certificate
- **Force SSL**: ✓ (aktiviert)
- **Email Address**: Ihre Email
- **I Agree to the Let's Encrypt Terms**: ✓

### 5. Advanced Tab (optional)
Fügen Sie bei Bedarf zusätzliche Nginx-Konfiguration hinzu:
```nginx
# Größere Upload-Limits für Datei-Uploads
client_max_body_size 100M;

# Längere Timeouts für langsame Operationen
proxy_read_timeout 300;
proxy_connect_timeout 300;
proxy_send_timeout 300;
```

## Fehlerbehebung

### "Not Found" Fehler
- Prüfen Sie, ob Forward Hostname = `nx2git-webapp` (nicht localhost!)
- Container muss laufen: `docker ps | grep nx2git-webapp`
- Container muss im proxy-network sein

### Test der Verbindung
```bash
# Von NPM Container aus testen:
docker exec nginx-proxy-manager curl http://nx2git-webapp:8765

# Sollte HTTP 200 zurückgeben
```

### Container neu starten nach Änderungen
```bash
docker-compose restart webapp
```

## Aktuelle Container-Informationen
- Container Name: `nx2git-webapp`
- Interne IP im proxy-network: `10.0.1.48`
- Port: `8765`
- Networks: `proxy-network`, `webapp_nx2git-internal`

## DNS Konfiguration
Stellen Sie sicher, dass `nx2git.netz-fabrik.net` auf die IP Ihres Servers zeigt.