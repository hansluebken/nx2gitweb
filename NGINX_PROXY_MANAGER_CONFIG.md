# NGINX Proxy Manager Konfiguration für Ninox2Git WebApp

## Proxy Host Einrichtung

### 1. Neuen Proxy Host erstellen

Navigieren Sie in NGINX Proxy Manager zu **Hosts** → **Proxy Hosts** → **Add Proxy Host**

### 2. Details Tab

**Domain Names:**
```
nx2git.netz-fabrik.net
```

**Scheme:**
```
http
```

**Forward Hostname / IP:**
```
nx2git-webapp
```
*(Dies ist der Container-Name aus docker-compose.yml)*

**Forward Port:**
```
8765
```

**Optionen:**
- ☑ Cache Assets
- ☑ Block Common Exploits
- ☑ Websockets Support

### 3. SSL Tab

**SSL Certificate:**
- ☑ Request a new SSL Certificate with Let's Encrypt

**Email Address for Let's Encrypt:**
```
admin@netz-fabrik.net
```

**Optionen:**
- ☑ Force SSL
- ☑ HTTP/2 Support
- ☑ HSTS Enabled
- ☑ HSTS Subdomains

### 4. Advanced Tab (Optional)

Fügen Sie folgende Custom Nginx Configuration hinzu für bessere Sicherheit:

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
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Port $server_port;

# Timeouts
proxy_connect_timeout 600s;
proxy_send_timeout 600s;
proxy_read_timeout 600s;
send_timeout 600s;

# Buffer sizes
client_max_body_size 100M;
```

## Zusammenfassung der Einstellungen

| Einstellung | Wert |
|------------|------|
| Domain | nx2git.netz-fabrik.net |
| Scheme | http |
| Forward Host | nx2git-webapp |
| Forward Port | 8765 |
| SSL | Let's Encrypt |
| Force SSL | Ja |
| HTTP/2 | Ja |
| HSTS | Ja |
| WebSockets | Ja |

## Verifizierung

Nach der Konfiguration:

1. Speichern Sie den Proxy Host
2. Warten Sie auf SSL-Zertifikat (ca. 30-60 Sekunden)
3. Testen Sie den Zugriff:
   ```bash
   curl -I https://nx2git.netz-fabrik.net
   ```

4. Erwartete Antwort:
   ```
   HTTP/2 200
   server: nginx
   content-type: text/html; charset=utf-8
   strict-transport-security: max-age=31536000; includeSubDomains
   x-frame-options: SAMEORIGIN
   x-content-type-options: nosniff
   ```

## Troubleshooting

### Problem: 502 Bad Gateway

**Lösung:**
1. Prüfen Sie, ob der Container läuft:
   ```bash
   docker ps | grep nx2git-webapp
   ```

2. Prüfen Sie, ob der Container im proxy-network ist:
   ```bash
   docker network inspect proxy-network | grep nx2git-webapp
   ```

3. Testen Sie die Verbindung vom NPM-Container:
   ```bash
   docker exec -it nginx-proxy-manager curl http://nx2git-webapp:8765
   ```

### Problem: SSL-Zertifikat fehlgeschlagen

**Lösung:**
1. DNS überprüfen:
   ```bash
   nslookup nx2git.netz-fabrik.net
   ```

2. Port 80 und 443 müssen offen sein
3. Domain muss auf die Server-IP zeigen

### Problem: WebSocket-Verbindung fehlgeschlagen

**Lösung:**
- Stellen Sie sicher, dass "Websockets Support" aktiviert ist
- Custom Nginx Config aus Schritt 4 hinzufügen
