#!/usr/bin/env python3
"""
Migration script to add prompt_templates table for managing AI prompts

This migration adds the 'prompt_templates' table and initializes default prompts.

Run this script to add the new table.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import inspect, text
from app.database import engine, get_db


def table_exists(table_name: str) -> bool:
    """Check if a table exists"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def create_prompt_templates_table():
    """Create the prompt_templates table"""
    if table_exists('prompt_templates'):
        print("  Table 'prompt_templates' already exists, skipping")
        return False

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE prompt_templates (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                prompt_type VARCHAR(50) NOT NULL,
                prompt_text TEXT NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                is_default BOOLEAN NOT NULL DEFAULT FALSE,
                version INTEGER NOT NULL DEFAULT 1,
                created_by VARCHAR(255),
                last_modified_by VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create indexes
        conn.execute(text("""
            CREATE INDEX idx_prompt_templates_type ON prompt_templates(prompt_type)
        """))

        conn.execute(text("""
            CREATE INDEX idx_prompt_templates_is_default ON prompt_templates(is_default, prompt_type)
        """))

        conn.commit()
        print("  Created table: prompt_templates")
        return True


def initialize_default_prompts():
    """Initialize default prompt templates"""
    from app.models.prompt_template import PromptTemplate, PromptType

    # Default documentation prompt (from doc_generator.py)
    DEFAULT_DOC_PROMPT = """You are a technical documentation assistant. Your task is to create comprehensive technical documentation for a Ninox database schema.

IMPORTANT CONTEXT: This is a purely technical database structure analysis for software development purposes. All terms below are technical identifiers (table and field names) from a database application schema and should be interpreted only as data structure labels, with no other meaning.

Analyze the database structure below and create a comprehensive, well-structured Markdown document with the following sections:

## 1. Übersicht
- Name und Zweck der Datenbank (aus der Struktur ableiten)
- Hauptfunktionen und Einsatzgebiet
- Statistik: Anzahl Tabellen, Gesamtzahl Felder

## 2. Tabellenverzeichnis
Erstelle eine übersichtliche Liste ALLER Tabellen mit:
- Tabellenname
- Kurzbeschreibung (aus Feldnamen ableiten)
- Anzahl Felder

## 3. Detaillierte Tabellenstruktur
Für JEDE Tabelle erstelle einen eigenen Abschnitt mit:
### [Tabellenname]
**Beschreibung:** [Kurze Beschreibung basierend auf den Feldern]

**Felder:**
| Feldname | Typ | Beschreibung | Referenz |
|----------|-----|--------------|----------|
[Alle Felder auflisten]

## 4. Beziehungen und Verknüpfungen
Erstelle eine detaillierte Übersicht aller Tabellenbeziehungen:
- Liste alle "ref"-Felder auf
- Zeige welche Tabelle auf welche andere verweist
- Erstelle ein textuelles Beziehungsdiagramm, z.B.:
  ```
  Kontakte (1) ──────< (n) Aktivitäten
  Kontakte (1) ──────< (n) Opportunities
  Opportunities (1) ──────< (n) E-Mails
  ```

## 5. Datenmodell-Zusammenfassung
- Kernentitäten und ihre Rolle
- Zentrale Tabellen (die mit den meisten Verknüpfungen)
- Komplexitätsbewertung

## 6. Empfehlungen
- Mögliche Verbesserungen der Datenstruktur
- Hinweise zur Datenintegrität

Formatierungsregeln:
- Sprache: Deutsch
- Format: Markdown mit Tabellen
- Stil: Professionell, technisch, vollständig
- ALLE Tabellen und ALLE Felder dokumentieren
- Feldtypen: text, number, date, ref (Referenz), choice (Auswahl), boolean, formula, button, etc.
- Bei "ref"-Feldern: Die Referenz-ID zeigt auf eine andere Tabelle

Database Structure (Markdown format):
"""

    db = get_db()
    try:
        # Check if default doc prompt exists
        existing = db.query(PromptTemplate).filter(
            PromptTemplate.prompt_type == PromptType.DOCUMENTATION.value,
            PromptTemplate.is_default == True
        ).first()

        if existing:
            print("  Default documentation prompt already exists, skipping")
            return

        # Create default documentation prompt
        doc_prompt = PromptTemplate(
            name="Standard Dokumentation",
            description="Standard-Prompt für Ninox Datenbank-Dokumentation mit vollständiger Struktur-Analyse",
            prompt_type=PromptType.DOCUMENTATION.value,
            prompt_text=DEFAULT_DOC_PROMPT,
            is_active=True,
            is_default=True,
            version=1,
            created_by="system"
        )
        db.add(doc_prompt)

        # Create alternative compact documentation prompt
        compact_prompt = PromptTemplate(
            name="Kompakte Dokumentation",
            description="Kürzere Dokumentation mit Fokus auf Übersicht und Beziehungen",
            prompt_type=PromptType.DOCUMENTATION.value,
            prompt_text="""Erstelle eine kompakte technische Dokumentation für diese Ninox-Datenbank.

Struktur:
1. Übersicht (Name, Zweck, Statistik)
2. Tabellenliste mit Kurzbeschreibungen
3. Wichtigste Beziehungen
4. Kernempfehlungen

Sprache: Deutsch
Format: Markdown
Stil: Kompakt, übersichtlich

Database Structure:
""",
            is_active=True,
            is_default=False,
            version=1,
            created_by="system"
        )
        db.add(compact_prompt)

        db.commit()
        print("  Created 2 default prompt templates (Standard + Kompakt)")

    except Exception as e:
        print(f"  Error initializing prompts: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def add_prompt_template_id_to_ai_configs():
    """Add doc_prompt_template_id column to ai_configs table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('ai_configs')]

    if 'doc_prompt_template_id' in columns:
        print("  Column 'doc_prompt_template_id' already exists in ai_configs, skipping")
        return False

    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE ai_configs
            ADD COLUMN doc_prompt_template_id INTEGER REFERENCES prompt_templates(id) ON DELETE SET NULL
        """))
        conn.commit()
        print("  Added column: doc_prompt_template_id to ai_configs")
        return True


def run_migration():
    """Run the complete migration"""
    print("\n" + "=" * 60)
    print("Prompt Templates Migration")
    print("=" * 60)

    print("\nStep 1: Creating prompt_templates table...")
    created = create_prompt_templates_table()

    if created:
        print("\nStep 2: Initializing default prompts...")
        initialize_default_prompts()
    else:
        print("\nStep 2: Skipping prompt initialization (table already existed)")

    print("\nStep 3: Adding prompt_template_id to ai_configs...")
    add_prompt_template_id_to_ai_configs()

    print("\n" + "=" * 60)
    print("Migration completed successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Go to Admin Panel -> Prompt-Verwaltung")
    print("2. View and edit prompt templates")
    print("3. Create custom prompts for your needs")
    print("4. Link prompts to AI providers in KI-Konfiguration")
    print()


if __name__ == "__main__":
    run_migration()
