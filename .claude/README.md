# Claude Code Konfiguration für Ninox2Git WebApp

## Automatische Instruktionen

Die Datei `instructions.md` in diesem Verzeichnis wird automatisch von Claude Code geladen und berücksichtigt.

### Wie es funktioniert:

1. **Automatisches Laden**: Claude Code liest `.claude/instructions.md` beim Start im Projekt
2. **Projekt-spezifisch**: Gilt nur für dieses Projekt (/home/nx2git-go/webapp)
3. **Immer aktiv**: Muss nicht manuell aktiviert werden

### Alternative Methoden:

#### 1. Memory Command (persistent)
```bash
claude code /memory add "Wichtige Projekt-Info"
```
Gespeichert in: `~/.claude/projects/<project-hash>/memory.md`

#### 2. Custom Commands
Erstelle Dateien in `.claude/commands/`:
```bash
# Beispiel: .claude/commands/build.md
docker-compose build --no-cache
docker-compose up -d
```
Nutzung: `/build`

#### 3. Settings
Projekt-spezifische Settings in `.claude/settings.json`

## Aktueller Status:

- ✅ `instructions.md` - Vollständiges Projekt-Prompt (automatisch geladen)
- ✅ `.claude-code-prompt.md` - Backup im Root-Verzeichnis

## Wichtige Hinweise:

- Die `.claude/` Verzeichnis sollte in `.gitignore` wenn gewünscht
- `instructions.md` wird bei jedem Claude Code Start neu geladen
- Änderungen an `instructions.md` erfordern keinen Neustart

## Datei-Struktur:

```
webapp/
├── .claude/
│   ├── instructions.md      # ← Haupt-Prompt (auto-load)
│   ├── README.md           # ← Diese Datei
│   └── commands/           # ← Custom Slash Commands (optional)
│       ├── build.md
│       └── deploy.md
└── .claude-code-prompt.md  # ← Backup
```
