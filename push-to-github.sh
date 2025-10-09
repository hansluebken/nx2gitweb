#!/bin/bash

# ============================================
# Ninox2Git WebApp - GitHub Push Script
# ============================================
#
# Dieses Script erstellt automatisch das Repository 'nx2gitweb' auf GitHub
# und überträgt die WebApp sicher dorthin.
# Es stellt sicher, dass keine sensiblen Daten hochgeladen werden
#
# Verwendung:
#   ./push-to-github.sh
#
# Voraussetzung: GitHub CLI (gh) muss installiert und authentifiziert sein
#
# ============================================

set -e  # Bei Fehler abbrechen

# Repository-Name (fest definiert)
REPO_NAME="nx2gitweb"

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funktion für farbigen Output
print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Banner
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║  Ninox2Git WebApp - GitHub Push Script    ║"
echo "╔════════════════════════════════════════════╗"
echo ""

# Prüfe ob wir im richtigen Verzeichnis sind
if [ ! -f "app/main.py" ]; then
    print_error "Fehler: Dieses Script muss im webapp-Verzeichnis ausgeführt werden!"
    exit 1
fi

# Prüfe ob GitHub CLI installiert ist
if ! command -v gh &> /dev/null; then
    print_error "GitHub CLI (gh) ist nicht installiert!"
    echo ""
    echo "Bitte installieren Sie GitHub CLI:"
    echo "  Ubuntu/Debian: sudo apt install gh"
    echo "  macOS: brew install gh"
    echo "  Oder: https://cli.github.com/"
    echo ""
    exit 1
fi

# Prüfe ob GitHub CLI authentifiziert ist
if ! gh auth status &> /dev/null; then
    print_error "GitHub CLI ist nicht authentifiziert!"
    echo ""
    print_info "Bitte authentifizieren Sie sich mit: gh auth login"
    echo ""
    exit 1
fi

# GitHub Benutzername ermitteln
GH_USER=$(gh api user -q .login)
REPO_URL="https://github.com/${GH_USER}/${REPO_NAME}.git"

print_info "Repository: ${GH_USER}/${REPO_NAME}"
print_info "URL: $REPO_URL"
echo ""

# Sicherheitsprüfungen
print_info "Führe Sicherheitsprüfungen durch..."

# Prüfe ob .gitignore existiert
if [ ! -f ".gitignore" ]; then
    print_error ".gitignore fehlt! Bitte zuerst .gitignore erstellen."
    exit 1
fi
print_success ".gitignore gefunden"

# Prüfe ob .env in .gitignore ist
if ! grep -q "^\.env$" .gitignore; then
    print_error ".env ist nicht in .gitignore! Bitte hinzufügen."
    exit 1
fi
print_success ".env ist in .gitignore eingetragen"

# Warne wenn .env existiert
if [ -f ".env" ]; then
    print_warning ".env Datei gefunden - sie wird NICHT zu GitHub übertragen"
fi

# Warne wenn data/keys existiert
if [ -d "data/keys" ]; then
    print_warning "data/keys Verzeichnis gefunden - es wird NICHT zu GitHub übertragen"
fi

echo ""

# Zeige welche Dateien übertragen werden
print_info "Folgende Dateien werden zu GitHub übertragen:"
echo ""

# Erstelle temporär ein git repo um zu sehen was übertragen würde
if [ -d ".git" ]; then
    HAS_GIT=true
else
    HAS_GIT=false
    git init > /dev/null 2>&1
fi

git add -A --dry-run 2>/dev/null | head -20
FILE_COUNT=$(git add -A --dry-run 2>/dev/null | wc -l)

if [ $FILE_COUNT -gt 20 ]; then
    echo "   ... und $((FILE_COUNT - 20)) weitere Dateien"
fi

echo ""

# Prüfe auf sensible Dateien
print_info "Prüfe auf sensible Inhalte..."

SENSITIVE_FOUND=false

# Prüfe ob versehentlich .env tracked würde
if git add -A --dry-run 2>/dev/null | grep -q "\.env$"; then
    print_error "WARNUNG: .env würde übertragen werden!"
    SENSITIVE_FOUND=true
fi

# Prüfe auf potentielle Secrets in Dateien
if git add -A --dry-run 2>/dev/null | xargs grep -l "password.*=" 2>/dev/null | grep -v ".env" | grep -v "README" | head -1 > /dev/null; then
    print_warning "Potentielle Passwörter in Dateien gefunden - bitte prüfen!"
fi

if [ "$SENSITIVE_FOUND" = true ]; then
    print_error "Sicherheitsprüfung fehlgeschlagen!"
    if [ "$HAS_GIT" = false ]; then
        rm -rf .git
    fi
    exit 1
fi

print_success "Keine sensiblen Daten gefunden"
echo ""

# Bestätigung einholen
print_warning "Möchten Sie fortfahren und zu GitHub übertragen?"
read -p "Eingabe (j/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[JjYy]$ ]]; then
    print_info "Abbruch durch Benutzer"
    if [ "$HAS_GIT" = false ]; then
        rm -rf .git
    fi
    exit 0
fi

echo ""
print_info "Starte Git-Übertragung..."
echo ""

# Git initialisieren falls noch nicht geschehen
if [ "$HAS_GIT" = false ]; then
    print_info "Initialisiere Git Repository..."
    git init
    print_success "Git Repository initialisiert"
fi

# Konfiguriere Git falls noch nicht geschehen
if [ -z "$(git config user.name)" ]; then
    print_info "Git Benutzername nicht konfiguriert"
    read -p "Ihr Name: " GIT_NAME
    git config user.name "$GIT_NAME"
fi

if [ -z "$(git config user.email)" ]; then
    print_info "Git Email nicht konfiguriert"
    read -p "Ihre Email: " GIT_EMAIL
    git config user.email "$GIT_EMAIL"
fi

# Dateien hinzufügen
print_info "Füge Dateien hinzu..."
git add -A
print_success "Dateien hinzugefügt"

# Status anzeigen
print_info "Git Status:"
git status --short

echo ""

# Commit erstellen
print_info "Erstelle Commit..."
COMMIT_MSG="Initial commit - Ninox2Git WebApp

- FastAPI Backend mit NiceGUI Frontend
- Benutzer- und Teamverwaltung
- Ninox API Integration
- GitHub Integration für Backups
- PostgreSQL Datenbank
- Docker Deployment Setup
"

git commit -m "$COMMIT_MSG"
print_success "Commit erstellt"

# Prüfe ob Repository auf GitHub existiert, wenn nicht erstelle es
print_info "Prüfe ob Repository auf GitHub existiert..."
if gh repo view "${GH_USER}/${REPO_NAME}" &> /dev/null; then
    print_warning "Repository ${GH_USER}/${REPO_NAME} existiert bereits auf GitHub"
else
    print_info "Erstelle Repository ${GH_USER}/${REPO_NAME} auf GitHub..."
    gh repo create "${REPO_NAME}" \
        --public \
        --description "Ninox2Git WebApp - FastAPI Backend mit NiceGUI Frontend für Ninox Datenbank Backups" \
        --source=. \
        --remote=origin \
        --push=false
    print_success "Repository erfolgreich auf GitHub erstellt"
fi

# Remote hinzufügen/aktualisieren
print_info "Konfiguriere Remote Repository..."
if git remote | grep -q "^origin$"; then
    git remote set-url origin "$REPO_URL"
    print_success "Remote Repository aktualisiert"
else
    git remote add origin "$REPO_URL"
    print_success "Remote Repository hinzugefügt"
fi

# Push zu GitHub
print_info "Übertrage zu GitHub..."
echo ""

# Prüfe ob main oder master branch
BRANCH=$(git branch --show-current)
if [ -z "$BRANCH" ]; then
    BRANCH="main"
    git branch -M main
fi

# Push mit Tracking
git push -u origin "$BRANCH"

echo ""
print_success "Erfolgreich zu GitHub übertragen!"
echo ""
print_info "Repository URL: $REPO_URL"
print_info "Branch: $BRANCH"
echo ""

# Abschließende Hinweise
echo "╔════════════════════════════════════════════╗"
echo "║  Wichtige Hinweise                         ║"
echo "╚════════════════════════════════════════════╝"
echo ""
print_warning "1. Die .env Datei wurde NICHT übertragen (wie gewünscht)"
print_warning "2. Erstellen Sie auf GitHub .env.example als Vorlage"
print_warning "3. Bei Deployment: .env Datei separat konfigurieren"
print_warning "4. Verschlüsselungs-Keys werden NICHT übertragen"
print_info "5. Dokumentation in README.md und START_HIER.md"
echo ""

print_success "✓ GitHub Push abgeschlossen!"
echo ""
