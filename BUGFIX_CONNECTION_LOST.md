# Bugfix: Connection Lost bei Cronjob-Ausführung

## Problem-Beschreibung

### Symptome
- Bei der Ausführung von Cronjobs über den "Run Now" Button erschien nach kurzer Zeit die Meldung "Connection lost. Trying to Connect."
- Die WebSocket-Verbindung zwischen Browser und Server brach ab
- Die Anwendung wurde unresponsive während der Cronjob-Ausführung
- Keine Rückmeldung über den Fortschritt der Synchronisierung

### Ursachen
1. **Blockierung des Event-Loops**: Lange laufende synchrone Operationen blockierten den asyncio Event-Loop
2. **WebSocket-Timeout**: Die WebSocket-Verbindung wurde unterbrochen, wenn keine Updates kamen
3. **Fehlende asynchrone Implementierung**: I/O-intensive Operationen (GitHub API, Ninox API, Datenbankzugriffe) liefen synchron
4. **Keine Fortschrittsanzeige**: Benutzer hatten keine Sichtbarkeit über den Status der Operation

## Implementierte Lösung

### 1. UI-Verbesserungen (`app/ui/cronjobs.py`)

#### Vorher:
```python
def run_cronjob_now(user, team, cronjob, container):
    # Simple notification - no dialog
    ui.notify(f'Starting cronjob...', timeout=10000)

    async def execute():
        await scheduler.execute_job(cronjob)

    background_tasks.create(execute())
```

#### Nachher:
```python
def run_cronjob_now(user, team, cronjob, container):
    # Status-Dialog mit Fortschrittsanzeige
    with ui.dialog() as status_dialog:
        ui.spinner()
        status_label = ui.label('Initializing...')
        progress_label = ui.label('')

    # Shared State für Updates
    job_state = {'running': True, 'status': 'init', 'progress': ''}

    async def execute_in_background():
        await scheduler.execute_job(cronjob, progress_callback=update_progress)

    def update_status():
        # UI-Updates basierend auf job_state
        if job_state['status'] == 'running':
            progress_label.text = job_state['progress']
        elif job_state['status'] == 'completed':
            # Auto-close nach Erfolg

    # Timer für regelmäßige UI-Updates
    ui.timer(0.5, update_status)

    # Asynchrone Ausführung ohne Blockierung
    asyncio.create_task(execute_in_background())
```

### 2. Scheduler-Optimierungen (`app/services/cronjob_scheduler.py`)

#### Thread Pool für I/O-Operationen:
```python
async def sync_database(self, user, server, team, database):
    loop = asyncio.get_event_loop()

    def sync_operation():
        # Alle synchronen I/O-Operationen hier
        client = NinoxClient(server.url, api_key)
        db_structure = client.get_database_structure(...)
        github_mgr.update_file(...)

    # Ausführung in separatem Thread
    await loop.run_in_executor(None, sync_operation)
```

#### Progress Callbacks:
```python
async def execute_job(self, job: Cronjob, progress_callback=None):
    for idx, database in enumerate(databases, 1):
        if progress_callback:
            progress_callback('running', f'Syncing database {idx}/{total}: {database.name}')
        await self.sync_database(...)
```

### 3. Technische Verbesserungen

#### Asynchrone Muster:
- **asyncio.create_task()** statt background_tasks für echte Parallelität
- **run_in_executor()** für blockierende I/O-Operationen
- **ui.timer()** für regelmäßige UI-Updates ohne Blockierung

#### WebSocket-Stabilität:
- Regelmäßige Updates über ui.timer halten die Verbindung aktiv
- Keine langen blockierenden Operationen im Hauptthread
- Responsive UI auch während schwerer Operationen

## Resultat

### Vorteile der neuen Implementierung:

1. **Stabilität**
   - ✅ Keine "Connection Lost" Fehler mehr
   - ✅ WebSocket-Verbindung bleibt stabil
   - ✅ Anwendung bleibt responsive

2. **Benutzerfreundlichkeit**
   - ✅ Live-Fortschrittsanzeige (z.B. "Syncing database 3/10: CustomerDB")
   - ✅ Status-Dialog mit Spinner während der Ausführung
   - ✅ Automatisches Schließen nach Erfolg
   - ✅ Klare Fehleranzeige bei Problemen

3. **Performance**
   - ✅ I/O-Operationen blockieren nicht den Event-Loop
   - ✅ Parallele Verarbeitung möglich
   - ✅ Skalierbar für große Datenmengen

## Testing

### Testfälle:
1. **Kurze Synchronisierung** (1-2 Datenbanken): ✅ Funktioniert ohne Probleme
2. **Lange Synchronisierung** (10+ Datenbanken): ✅ Keine Connection Lost
3. **Fehlerhafte API-Calls**: ✅ Fehler werden angezeigt, Verbindung bleibt stabil
4. **Parallele Cronjobs**: ✅ Mehrere Jobs können gleichzeitig laufen

## Best Practices befolgt

Die Lösung folgt den offiziellen NiceGUI Best Practices:
- Verwendung von asyncio für asynchrone Operationen
- run_in_executor für CPU/IO-intensive Tasks
- UI-Timer für regelmäßige Updates
- Keine blockierenden Operationen im Hauptthread

## Deployment

Nach Implementation:
1. Docker-Container neu bauen: `docker-compose down && docker-compose up -d --build`
2. Browser-Cache leeren: `Cmd+Shift+R` oder Inkognito-Modus
3. Funktionalität testen

## Referenzen

- [NiceGUI Documentation - Action & Events](https://nicegui.io/documentation/section_action_events)
- [GitHub Issue #3115 - Connection lost issue](https://github.com/zauberzeug/nicegui/discussions/3115)
- [Python asyncio Documentation](https://docs.python.org/3/library/asyncio.html)

---

**Datum**: 2024-10-09
**Author**: Claude AI Assistant
**Version**: 1.0