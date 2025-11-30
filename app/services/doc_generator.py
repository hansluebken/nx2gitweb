"""
Documentation Generator Service
Generates application documentation from Ninox database structure using Gemini AI
"""
import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# System prompt for documentation generation
DOCUMENTATION_PROMPT = """Du bist ein Experte für Ninox-Datenbanken und technische Dokumentation.

Analysiere die folgende Ninox-Datenbankstruktur und erstelle eine ausführliche, 
gut strukturierte Dokumentation auf Deutsch im Markdown-Format.

Die Dokumentation soll folgende Abschnitte enthalten:

## 1. Übersicht
- Name und Zweck der Anwendung (aus der Struktur ableiten)
- Kurze Zusammenfassung der Hauptfunktionen

## 2. Datenmodell
Für jede Tabelle:
- Tabellenname und Beschreibung
- Alle Felder mit Typ und Bedeutung
- Besondere Felder (Formeln, Berechnungen)

## 3. Beziehungen
- Übersicht aller Tabellenbeziehungen
- Textuelle Darstellung der Verknüpfungen (z.B. "Kunde 1:n Aufträge")
- Mermaid-Diagramm des Datenmodells (falls sinnvoll)

## 4. Geschäftslogik
- Wichtige Formeln und deren Bedeutung
- Berechnete Felder
- Trigger und Automationen (falls vorhanden)

## 5. Benutzeroberfläche
- Views und deren Zweck
- Reports (falls vorhanden)
- Print-Layouts (falls vorhanden)

## 6. Technische Zusammenfassung
- Anzahl Tabellen
- Anzahl Felder gesamt
- Komplexitätsbewertung (einfach/mittel/komplex)
- Besondere Merkmale der Anwendung

Wichtige Hinweise:
- Schreibe auf Deutsch
- Verwende klare, verständliche Sprache
- Strukturiere mit Markdown-Überschriften
- Verwende Tabellen für Feldübersichten
- Füge Mermaid-Diagramme ein wo sinnvoll

JSON-Struktur der Datenbank:
"""


@dataclass
class DocumentationResult:
    """Result of documentation generation"""
    content: str  # Generated Markdown content
    success: bool = True
    error: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    model: str = ""
    generated_at: Optional[datetime] = None


class DocumentationGenerator:
    """Generates application documentation from Ninox database structure"""
    
    # Default values (can be overridden by config)
    DEFAULT_MODEL = "gemini-2.5-pro"
    DEFAULT_MAX_TOKENS = 1000000  # Request maximum - Gemini will use what it can
    DEFAULT_TEMPERATURE = 0.3
    
    def __init__(self, api_key: str, model: str = None, max_tokens: int = None, temperature: float = None):
        """
        Initialize the documentation generator
        
        Args:
            api_key: Google Gemini API key
            model: Gemini model to use (from config)
            max_tokens: Maximum output tokens (from config)
            temperature: Temperature setting (from config)
        """
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS
        self.temperature = temperature if temperature is not None else self.DEFAULT_TEMPERATURE
    
    def generate(self, structure_json: Dict[str, Any], db_name: str) -> DocumentationResult:
        """
        Generate documentation from Ninox database structure
        
        Args:
            structure_json: The database structure as dict
            db_name: Name of the database
            
        Returns:
            DocumentationResult with generated markdown
        """
        try:
            import google.generativeai as genai
            
            # Configure Gemini
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model)
            
            # Prepare the structure JSON
            structure_str = json.dumps(structure_json, indent=2, ensure_ascii=False)
            
            # Build the full prompt
            full_prompt = f"{DOCUMENTATION_PROMPT}\n\n```json\n{structure_str}\n```"
            
            logger.info(f"Generating documentation for '{db_name}' using {self.model} (max_tokens={self.max_tokens}, temp={self.temperature})")
            
            # Generate content with configured parameters
            response = model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=self.max_tokens,
                    temperature=self.temperature,
                )
            )
            
            # Extract token usage
            input_tokens = None
            output_tokens = None
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count
            
            # Get the generated text
            content = response.text
            
            # Add header with metadata
            header = f"""# {db_name} - Anwendungsdokumentation

> **Automatisch generiert am:** {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}  
> **KI-Modell:** {self.model}  
> **Max Tokens:** {self.max_tokens}  
> **Token-Verbrauch:** {input_tokens or '?'} Input / {output_tokens or '?'} Output

---

"""
            content = header + content
            
            logger.info(f"Documentation generated successfully: {input_tokens} input, {output_tokens} output tokens")
            
            return DocumentationResult(
                content=content,
                success=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=self.model,
                generated_at=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error generating documentation: {str(e)}")
            return DocumentationResult(
                content="",
                success=False,
                error=str(e),
                model=self.model
            )
    
    @staticmethod
    def extract_structure_summary(structure_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract a summary of the structure for preview
        
        Args:
            structure_json: The database structure
            
        Returns:
            Dict with summary information
        """
        summary = {
            "tables": [],
            "total_fields": 0,
            "has_views": False,
            "has_reports": False,
        }
        
        try:
            # Handle different JSON structures
            types = structure_json.get("types", [])
            
            for table in types:
                table_name = table.get("caption", table.get("name", "Unknown"))
                fields = table.get("fields", [])
                field_count = len(fields)
                
                summary["tables"].append({
                    "name": table_name,
                    "field_count": field_count
                })
                summary["total_fields"] += field_count
                
                # Check for views
                if table.get("views"):
                    summary["has_views"] = True
                    
                # Check for reports
                if table.get("reports"):
                    summary["has_reports"] = True
                    
        except Exception as e:
            logger.warning(f"Error extracting structure summary: {e}")
        
        return summary


def get_documentation_generator() -> Optional[DocumentationGenerator]:
    """
    Get a DocumentationGenerator instance if Gemini is configured.
    Uses the model, max_tokens, and temperature from Admin KI-Konfiguration.
    
    Returns:
        DocumentationGenerator or None if not configured
    """
    try:
        from ..database import get_db
        from ..models.ai_config import AIConfig, AIProvider
        from ..utils.encryption import get_encryption_manager
        
        db = get_db()
        try:
            # Get Gemini config
            config = db.query(AIConfig).filter(
                AIConfig.provider == AIProvider.GEMINI.value,
                AIConfig.is_active == True
            ).first()
            
            if not config or not config.api_key_encrypted:
                logger.warning("Gemini not configured for documentation generation")
                return None
            
            # Decrypt API key using EncryptionManager
            enc_manager = get_encryption_manager()
            api_key = enc_manager.decrypt(config.api_key_encrypted)
            if not api_key:
                logger.warning("Could not decrypt Gemini API key")
                return None
            
            # Use configuration from Admin panel
            # For documentation we request maximum tokens - Gemini will use what it supports
            doc_max_tokens = 1000000  # Request max - model will limit automatically
            
            logger.info(f"Creating DocumentationGenerator with model={config.model}, max_tokens={doc_max_tokens}, temp={config.temperature}")
            
            return DocumentationGenerator(
                api_key=api_key,
                model=config.model,
                max_tokens=doc_max_tokens,
                temperature=config.temperature
            )
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error creating DocumentationGenerator: {e}")
        return None
