"""
Documentation Generator Service
Generates application documentation from Ninox database structure using Gemini AI
"""
import yaml
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def sanitize_for_ai(text: str) -> str:
    """
    Sanitize text for AI processing to avoid triggering safety filters
    
    Args:
        text: Input text that might contain problematic terms
        
    Returns:
        Sanitized text safe for AI processing
    """
    if not text:
        return text
    
    # Remove or replace potentially problematic characters/patterns
    # Keep it minimal - we don't want to lose meaningful information
    sanitized = text
    
    # Remove control characters and non-printable characters
    sanitized = ''.join(char for char in sanitized if char.isprintable() or char in '\n\t')
    
    return sanitized


# System prompt for documentation generation (using Markdown structure)
DOCUMENTATION_PROMPT = """You are a technical documentation assistant. Your task is to create comprehensive technical documentation for a Ninox database schema.

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
    DEFAULT_MODEL = "gemini-2.0-flash-exp"  # Less strict than gemini-3-pro-preview
    DEFAULT_MAX_TOKENS = 1000000  # Request maximum - Gemini will use what it can
    DEFAULT_TEMPERATURE = 0.3
    
    def __init__(self, api_key: str, model: str = None, max_tokens: int = None, temperature: float = None, custom_prompt: str = None):
        """
        Initialize the documentation generator

        Args:
            api_key: Google Gemini API key
            model: Gemini model to use (from config)
            max_tokens: Maximum output tokens (from config)
            temperature: Temperature setting (from config)
            custom_prompt: Custom prompt template from database (optional)
        """
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS
        self.temperature = temperature if temperature is not None else self.DEFAULT_TEMPERATURE
        self.custom_prompt = custom_prompt  # Use custom prompt if provided
    
    def generate(self, structure_dict: Dict[str, Any], db_name: str, retry_simplified: bool = True, progress_callback=None) -> DocumentationResult:
        """
        Generate documentation from Ninox database structure with automatic batching.

        Args:
            structure_dict: The database structure as dict (from YAML)
            db_name: Name of the database
            retry_simplified: Retry with simplified structure on error
            progress_callback: Optional callback(current_batch, total_batches) for progress updates

        Returns:
            DocumentationResult with generated markdown
        """
        tables = structure_dict.get('tables', [])
        table_count = len(tables)

        # Calculate optimal batch size based on complexity
        if table_count == 0:
            return DocumentationResult(content="# Keine Tabellen vorhanden", success=True, model=self.model)

        total_fields = sum(t.get('field_count', 0) for t in tables)
        avg_fields = total_fields / table_count if table_count > 0 else 0

        # Determine batch size based on complexity
        if avg_fields > 30:
            batch_size = 8  # Complex tables
        elif avg_fields > 15:
            batch_size = 12  # Medium complexity
        else:
            batch_size = 20  # Simple tables

        # Calculate number of batches
        import math
        batch_count = math.ceil(table_count / batch_size)

        logger.info(f"Documentation batching: {table_count} tables, avg {avg_fields:.1f} fields → {batch_count} batches of ~{batch_size} tables")

        # If only 1 batch, generate normally
        if batch_count == 1:
            return self._generate_single(structure_dict, db_name, retry_simplified)

        # Generate in batches
        return self._generate_batched(structure_dict, db_name, batch_size, batch_count, progress_callback)

    def _generate_single(self, structure_dict: Dict[str, Any], db_name: str, retry_simplified: bool = True) -> DocumentationResult:
        """Generate documentation in a single request (original method)"""
        try:
            import google.generativeai as genai
            
            # Configure Gemini
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model)
            
            # Convert structure to MARKDOWN format (like we did with JSON before!)
            # This avoids YAML/JSON syntax that triggers Gemini safety filters
            md_lines = []
            md_lines.append(f"# Datenbank: {sanitize_for_ai(structure_dict.get('name', 'Unknown'))}")
            md_lines.append(f"- Database ID: {sanitize_for_ai(str(structure_dict.get('database_id', 'N/A')))}")
            md_lines.append(f"- Anzahl Tabellen: {structure_dict.get('table_count', 0)}")
            md_lines.append(f"- Anzahl Code-Elemente: {structure_dict.get('code_count', 0)}")
            md_lines.append("")
            
            # Add global database code
            global_code = structure_dict.get('global_code', {})
            if global_code:
                md_lines.append("## Globaler Database-Code")
                md_lines.append("")
                for code_key, code_value in global_code.items():
                    if code_value:
                        code_preview = sanitize_for_ai(code_value[:300]) if len(code_value) > 300 else sanitize_for_ai(code_value)
                        md_lines.append(f"**{code_key}:**")
                        md_lines.append(f"```javascript")
                        md_lines.append(code_preview)
                        md_lines.append(f"```")
                        md_lines.append("")

            # Build table ID to name mapping for reference resolution
            tables = structure_dict.get('tables', [])
            table_id_to_name = {}
            for table in tables:
                # Try to extract table ID from the structure if available
                table_name = table.get('name', 'Unknown')
                table_id = table.get('id', '')
                if table_id:
                    table_id_to_name[table_id] = table_name

            # Count total fields and refs for statistics
            total_fields = 0
            total_refs = 0
            relationships = []

            # Add tables
            for table in tables:
                table_name = sanitize_for_ai(table.get('name', 'Unknown'))
                field_count = table.get('field_count', 0)
                total_fields += field_count

                md_lines.append(f"## Tabelle: {table_name}")
                md_lines.append(f"Anzahl Felder: {field_count}")

                # Add table-level code (triggers)
                table_code = table.get('code', {})
                if table_code:
                    md_lines.append("")
                    md_lines.append("**Tabellen-Trigger:**")
                    for code_key, code_value in table_code.items():
                        if code_value:
                            code_preview = code_value[:100] + '...' if len(code_value) > 100 else code_value
                            md_lines.append(f"- `{code_key}`: {sanitize_for_ai(code_preview)}")

                # Add fields as table with code info
                fields = table.get('fields', [])
                if fields:
                    md_lines.append("")
                    md_lines.append("| Feldname | Typ | Referenz/Details | Code |")
                    md_lines.append("|----------|-----|------------------|------|")
                    for field in fields:
                        name = sanitize_for_ai(field.get('name', '?'))
                        ftype = sanitize_for_ai(field.get('type', '?'))
                        ref_type_id = field.get('refTypeId', '')
                        db_id = field.get('dbId', '')
                        db_name = field.get('dbName', '')

                        # Build details column
                        details = '-'
                        if ftype == 'ref' and (ref_type_id or db_name):
                            # Show reference target
                            if db_name:
                                details = f"→ {db_name} (Cross-DB)"
                            else:
                                ref_name = table_id_to_name.get(ref_type_id, ref_type_id)
                                details = f"→ {ref_name}"
                            total_refs += 1
                            relationships.append(f"{table_name} → {db_name or ref_type_id} (via {name})")
                        elif field.get('required'):
                            details = "Pflichtfeld"

                        # Build code column (show what code exists)
                        code_parts = []
                        if field.get('fn'):
                            code_parts.append('fn')
                        if field.get('onClick'):
                            code_parts.append('onClick')
                        if field.get('constraint'):
                            code_parts.append('validation')
                        if field.get('visibility'):
                            code_parts.append('visibility')
                        if field.get('canRead') or field.get('canWrite'):
                            code_parts.append('permissions')

                        code_info = ', '.join(code_parts) if code_parts else '-'

                        md_lines.append(f"| {name} | {ftype} | {details} | {code_info} |")

                    # Add detailed code examples for fields with formulas
                    fields_with_code = [f for f in fields if f.get('fn') or f.get('onClick')]
                    if fields_with_code:
                        md_lines.append("")
                        md_lines.append("**Code-Beispiele:**")
                        for field in fields_with_code[:5]:  # Max 5 examples to keep size manageable
                            fname = sanitize_for_ai(field.get('name', '?'))
                            if field.get('fn'):
                                code_preview = sanitize_for_ai(field['fn'][:150]) if len(field['fn']) > 150 else sanitize_for_ai(field['fn'])
                                md_lines.append(f"- `{fname}` (Formel): `{code_preview}`")
                            elif field.get('onClick'):
                                code_preview = sanitize_for_ai(field['onClick'][:150]) if len(field['onClick']) > 150 else sanitize_for_ai(field['onClick'])
                                md_lines.append(f"- `{fname}` (onClick): `{code_preview}`")

                md_lines.append("")
            
            # Add relationship summary at the end
            if relationships:
                md_lines.append("---")
                md_lines.append("## Beziehungsübersicht")
                md_lines.append("")
                md_lines.append(f"Anzahl Verknüpfungen: {total_refs}")
                md_lines.append("")
                md_lines.append("```")
                for rel in relationships:
                    md_lines.append(rel)
                md_lines.append("```")
                md_lines.append("")
            
            # Add statistics
            md_lines.insert(4, f"- Gesamtzahl Felder: {total_fields}")
            md_lines.insert(5, f"- Anzahl Verknüpfungen: {total_refs}")
            
            structure_str = "\n".join(md_lines)

            # Build the full prompt (use custom prompt from DB or fallback to default)
            base_prompt = self.custom_prompt if self.custom_prompt else DOCUMENTATION_PROMPT
            full_prompt = f"{base_prompt}\n\n{structure_str}"
            
            # Log payload info
            payload_size = len(full_prompt)
            table_count = len(structure_dict.get('tables', []))
            logger.info(f"Generating documentation for '{db_name}' using {self.model}")
            logger.info(f"Payload: {payload_size} chars, {table_count} tables, max_tokens={self.max_tokens}, temp={self.temperature}")
            
            # Debug: Log first 1000 chars of structure to identify potential triggers
            structure_preview = structure_str[:1000]
            logger.info(f"Structure preview (first 1000 chars):\n{structure_preview}")
            
            # DEBUG: Save full prompt to file for analysis
            try:
                import os
                debug_dir = "/app/data/debug"
                # Ensure directory exists with proper permissions
                try:
                    os.makedirs(debug_dir, mode=0o755, exist_ok=True)
                except PermissionError:
                    logger.warning(f"No permission to create {debug_dir}, skipping debug output")
                    raise
                    
                debug_file = f"{debug_dir}/last_gemini_prompt.txt"
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(f"=== PROMPT FOR: {db_name} ===\n")
                    f.write(f"Model: {self.model}\n")
                    f.write(f"Tables: {table_count}\n")
                    f.write(f"Size: {payload_size} chars\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(full_prompt)
                logger.info(f"Full prompt saved to {debug_file} for debugging")
            except Exception as e:
                logger.warning(f"Could not save debug prompt: {e}")
            
            # Log table names to check for problematic names
            table_names = [t.get('name', '?') for t in structure_dict.get('tables', [])]
            logger.info(f"Table names: {', '.join(table_names[:10])}{'...' if len(table_names) > 10 else ''}")
            
            # Generate content with configured parameters and safety settings
            # Disable overly strict safety filters for technical documentation
            from google.generativeai.types import HarmCategory, HarmBlockThreshold
            
            # Set all safety filters to BLOCK_NONE for technical documentation
            # This is necessary because database field names might accidentally trigger filters
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            
            logger.info(f"Calling Gemini with safety_settings: BLOCK_NONE for all categories")
            
            response = model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=self.max_tokens,
                    temperature=self.temperature,
                ),
                safety_settings=safety_settings
            )
            
            # Log response metadata for debugging
            logger.info(f"Response received. Has candidates: {bool(response.candidates)}")
            if response.candidates:
                logger.info(f"Finish reason: {response.candidates[0].finish_reason}")
                logger.info(f"Number of candidates: {len(response.candidates)}")
                
                # Log full response for debugging
                if hasattr(response.candidates[0], 'safety_ratings'):
                    logger.info(f"Safety ratings: {response.candidates[0].safety_ratings}")
                if hasattr(response, 'prompt_feedback'):
                    logger.info(f"Prompt feedback: {response.prompt_feedback}")
            else:
                logger.error("No candidates in response!")
                if hasattr(response, 'prompt_feedback'):
                    logger.error(f"Prompt feedback: {response.prompt_feedback}")
            
            # Extract token usage
            input_tokens = None
            output_tokens = None
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count
            
            # Check if response was blocked by safety filters
            if not response.candidates or len(response.candidates) == 0:
                # Check prompt_feedback for block reason
                block_reason = "Unbekannt"
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                    if hasattr(response.prompt_feedback, 'block_reason'):
                        block_reason = str(response.prompt_feedback.block_reason)
                    if hasattr(response.prompt_feedback, 'safety_ratings'):
                        safety_ratings = response.prompt_feedback.safety_ratings
                        if safety_ratings:
                            block_reason += " | Safety: " + ", ".join([f"{r.category.name}: {r.probability.name}" for r in safety_ratings])
                
                # If retry_simplified is enabled, try again with a much simpler prompt
                if retry_simplified:
                    logger.warning(f"Input blocked. Retrying with simplified prompt (table names only)...")
                    
                    # Create a VERY minimal structure
                    simplified_structure = {
                        'name': structure_dict.get('name', 'Unknown'),
                        'database_id': 'DB',
                        'table_count': structure_dict.get('table_count', 0),
                        'code_count': structure_dict.get('code_count', 0),
                        'tables': []
                    }
                    
                    # Only include table names, NO field details at all
                    for table in structure_dict.get('tables', [])[:3]:  # Max 3 tables
                        simplified_structure['tables'].append({
                            'name': f"Tabelle_{len(simplified_structure['tables'])+1}",  # Generic names
                            'field_count': table.get('field_count', 0)
                        })
                    
                    # Retry with simplified structure
                    return self.generate(simplified_structure, db_name, retry_simplified=False)
                
                raise Exception(
                    f"Gemini hat die Anfrage blockiert (keine Kandidaten).\n"
                    f"Block-Grund: {block_reason}\n\n"
                    f"Dies deutet darauf hin, dass bereits der INPUT-Prompt blockiert wurde.\n"
                    f"Mögliche Lösungen:\n"
                    f"- Verwenden Sie ein anderes Gemini-Modell (z.B. gemini-1.5-flash)\n"
                    f"- Reduzieren Sie die Anzahl der Tabellen/Felder in der Datenbank\n"
                    f"- Prüfen Sie die Logs für Details"
                )
            
            # Check finish_reason
            # Gemini FinishReason enum values:
            # 0 = FINISH_REASON_UNSPECIFIED
            # 1 = STOP (normal completion)
            # 2 = MAX_TOKENS (output truncated - need more tokens!)
            # 3 = SAFETY (content blocked)
            # 4 = RECITATION (copyright concern)
            # 5 = OTHER
            finish_reason = response.candidates[0].finish_reason
            
            # Handle MAX_TOKENS - this means the output was truncated, not blocked!
            if finish_reason == 2:  # MAX_TOKENS
                logger.warning(f"Output truncated due to max_tokens limit ({self.max_tokens}). Extracting partial content...")
                # Try to get the partial content anyway
                try:
                    partial_content = response.text
                    if partial_content and len(partial_content) > 100:
                        logger.info(f"Got partial content: {len(partial_content)} chars")
                        # Add note about truncation
                        header = f"""# {db_name} - Anwendungsdokumentation

> **Automatisch generiert am:** {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}  
> **KI-Modell:** {self.model}  
> **Hinweis:** Die Ausgabe wurde bei {self.max_tokens} Tokens abgeschnitten. Erhöhen Sie max_tokens in der KI-Konfiguration für vollständige Dokumentation.

---

"""
                        return DocumentationResult(
                            content=header + partial_content + "\n\n---\n*[Dokumentation wurde abgeschnitten - erhöhen Sie max_tokens für vollständige Ausgabe]*",
                            success=True,
                            input_tokens=response.usage_metadata.prompt_token_count if hasattr(response, 'usage_metadata') and response.usage_metadata else None,
                            output_tokens=response.usage_metadata.candidates_token_count if hasattr(response, 'usage_metadata') and response.usage_metadata else None,
                            model=self.model,
                            generated_at=datetime.now()
                        )
                except Exception as e:
                    logger.warning(f"Could not extract partial content: {e}")
                
                # If we couldn't get partial content, raise a helpful error
                raise Exception(
                    f"Die Dokumentation wurde bei {self.max_tokens} Tokens abgeschnitten.\n\n"
                    f"LÖSUNG: Erhöhen Sie 'Max Tokens' in der Admin KI-Konfiguration auf mindestens 8000.\n"
                    f"Empfohlen: 16000 für vollständige Dokumentationen."
                )
            
            if finish_reason == 3:  # SAFETY
                safety_ratings = response.candidates[0].safety_ratings if hasattr(response.candidates[0], 'safety_ratings') else []
                safety_details = []
                for r in safety_ratings:
                    category = r.category.name if hasattr(r.category, 'name') else str(r.category)
                    probability = r.probability.name if hasattr(r.probability, 'name') else str(r.probability)
                    safety_details.append(f"{category}: {probability}")
                safety_info = ", ".join(safety_details) if safety_details else "Keine Details verfügbar"
                
                # Log the problematic table names for debugging
                logger.error(f"Safety block details: {safety_info}")
                logger.error(f"Table names in structure: {', '.join(table_names[:20])}")
                
                # If retry_simplified is enabled, try different strategies
                if retry_simplified:
                    # STRATEGY 1: Try with a different, less strict model
                    if self.model == "gemini-3-pro-preview":
                        logger.warning(f"Safety block with {self.model}. Retrying with gemini-2.0-flash-exp...")
                        fallback_gen = DocumentationGenerator(
                            api_key=self.api_key,
                            model="gemini-2.0-flash-exp",
                            max_tokens=self.max_tokens,
                            temperature=self.temperature
                        )
                        return fallback_gen.generate(structure_dict, db_name, retry_simplified=True)
                    
                    # STRATEGY 2: Simplify the structure
                    logger.warning(f"Safety block detected. Retrying with simplified prompt (fewer tables)...")
                    
                    # Create a MUCH simpler structure with only table names and counts
                    simplified_structure = {
                        'name': structure_dict.get('name', 'Unknown'),
                        'database_id': structure_dict.get('database_id', 'N/A'),
                        'table_count': structure_dict.get('table_count', 0),
                        'code_count': structure_dict.get('code_count', 0),
                        'tables': []
                    }
                    
                    # Only include table names and field counts (no field details!)
                    for table in structure_dict.get('tables', [])[:5]:  # Max 5 tables
                        simplified_structure['tables'].append({
                            'name': sanitize_for_ai(table.get('name', 'Unknown')),
                            'field_count': table.get('field_count', 0)
                        })
                    
                    # Retry with simplified structure
                    return self.generate(simplified_structure, db_name, retry_simplified=False)
                
                raise Exception(
                    f"Gemini hat die Antwort aus Sicherheitsgründen blockiert.\n"
                    f"Safety-Bewertung: {safety_info}\n\n"
                    f"Mögliche Ursachen:\n"
                    f"- Tabellen- oder Feldnamen könnten problematische Begriffe enthalten\n"
                    f"- Versuchen Sie, ein anderes Modell zu verwenden (z.B. gemini-2.0-flash-exp statt gemini-3-pro-preview)\n"
                    f"- Reduzieren Sie die Anzahl der Tabellen in der Datenbank\n"
                    f"- Prüfen Sie die Logs für Details zu blockierten Begriffen"
                )
            elif finish_reason == 3:  # RECITATION
                raise Exception("Gemini hat die Antwort wegen möglicher Urheberrechtsverletzung blockiert.")
            elif finish_reason not in [0, 1]:  # 0=UNSPECIFIED, 1=STOP (normal)
                raise Exception(f"Gemini hat die Generierung mit Grund {finish_reason} abgebrochen.")
            
            # Get the generated text
            try:
                content = response.text
            except Exception as e:
                raise Exception(f"Konnte generierten Text nicht extrahieren: {str(e)}")
            
            # Add header with metadata (NO # heading to avoid BookStack chapter creation)
            header = f"""**{db_name} - Anwendungsdokumentation**

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

    def _generate_batched(self, structure_dict: Dict[str, Any], db_name: str, batch_size: int, batch_count: int, progress_callback=None) -> DocumentationResult:
        """
        Generate documentation in batches to handle large databases.

        Args:
            structure_dict: Full database structure
            db_name: Database name
            batch_size: Number of tables per batch
            batch_count: Total number of batches
            progress_callback: Callback(current, total) for progress updates

        Returns:
            Combined DocumentationResult
        """
        try:
            tables = structure_dict.get('tables', [])
            all_docs = []
            total_input_tokens = 0
            total_output_tokens = 0

            logger.info(f"Starting batched documentation generation: {batch_count} batches")

            for batch_idx in range(batch_count):
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, len(tables))
                batch_tables = tables[start_idx:end_idx]

                logger.info(f"Generating batch {batch_idx + 1}/{batch_count}: Tables {start_idx + 1}-{end_idx} ({len(batch_tables)} tables)")

                # Call progress callback
                if progress_callback:
                    progress_callback(batch_idx + 1, batch_count)

                # Create batch structure
                batch_structure = {
                    'name': structure_dict.get('name'),
                    'database_id': structure_dict.get('database_id'),
                    'table_count': len(batch_tables),
                    'code_count': structure_dict.get('code_count'),
                    'global_code': structure_dict.get('global_code') if batch_idx == 0 else {},  # Only in first batch
                    'tables': batch_tables,
                    'batch_info': f"Batch {batch_idx + 1}/{batch_count}"
                }

                # Generate for this batch
                result = self._generate_single(batch_structure, db_name, retry_simplified=False)

                if not result.success:
                    logger.error(f"Batch {batch_idx + 1} failed: {result.error}")
                    return result  # Return error immediately

                all_docs.append(result.content)
                total_input_tokens += result.input_tokens or 0
                total_output_tokens += result.output_tokens or 0

                logger.info(f"✓ Batch {batch_idx + 1}/{batch_count} completed ({result.output_tokens} tokens)")

            # Combine all batch docs
            combined_content = self._combine_batch_docs(all_docs, db_name, batch_count)

            logger.info(f"✓ All batches completed. Total tokens: {total_input_tokens} input, {total_output_tokens} output")

            return DocumentationResult(
                content=combined_content,
                success=True,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                model=self.model,
                generated_at=datetime.now()
            )

        except Exception as e:
            logger.error(f"Error in batched generation: {e}")
            return DocumentationResult(
                content="",
                success=False,
                error=str(e),
                model=self.model
            )

    def _combine_batch_docs(self, batch_docs: list, db_name: str, batch_count: int) -> str:
        """Combine multiple batch documentations into one cohesive document"""
        header = f"""**{db_name} - Anwendungsdokumentation**

> **Automatisch generiert am:** {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}
> **KI-Modell:** {self.model}
> **Batch-Generierung:** {batch_count} Batches für vollständige Abdeckung

---

"""
        # Combine all batches (remove individual headers)
        combined = header
        for i, doc in enumerate(batch_docs):
            # Remove header from batch docs and combine
            # Find the first "##" heading to skip metadata
            lines = doc.split('\n')
            content_start = 0
            for j, line in enumerate(lines):
                if line.startswith('## '):
                    content_start = j
                    break

            batch_content = '\n'.join(lines[content_start:])
            combined += f"\n<!-- Batch {i + 1}/{batch_count} -->\n"
            combined += batch_content + "\n\n"

        return combined

    @staticmethod
    def extract_structure_summary(structure_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract a summary of the structure for preview (DEPRECATED - for old JSON format)
        
        Args:
            structure_dict: The database structure
            
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
            # Handle old JSON structures (deprecated)
            types = structure_dict.get("types", [])
            
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
    Uses the model, max_tokens, temperature and prompt from Admin KI-Konfiguration.

    Returns:
        DocumentationGenerator or None if not configured
    """
    try:
        from ..database import get_db
        from ..models.ai_config import AIConfig, AIProvider
        from ..models.prompt_template import PromptTemplate, PromptType
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

            # Get prompt template (from config or default)
            custom_prompt = None
            if config.doc_prompt_template_id:
                # Use linked prompt template
                prompt_template = db.query(PromptTemplate).filter(
                    PromptTemplate.id == config.doc_prompt_template_id,
                    PromptTemplate.is_active == True
                ).first()
                if prompt_template:
                    custom_prompt = prompt_template.prompt_text
                    logger.info(f"Using custom prompt: {prompt_template.name}")

            if not custom_prompt:
                # Use default prompt template for documentation
                default_template = db.query(PromptTemplate).filter(
                    PromptTemplate.prompt_type == PromptType.DOCUMENTATION.value,
                    PromptTemplate.is_default == True,
                    PromptTemplate.is_active == True
                ).first()

                if default_template:
                    custom_prompt = default_template.prompt_text
                    logger.info(f"Using default prompt template: {default_template.name}")
                else:
                    # Final fallback: use hardcoded prompt
                    custom_prompt = DOCUMENTATION_PROMPT
                    logger.info("Using hardcoded fallback prompt")

            # Use configuration from Admin panel
            # For documentation we request maximum tokens - Gemini will use what it supports
            doc_max_tokens = 1000000  # Request max - model will limit automatically

            logger.info(f"Creating DocumentationGenerator with model={config.model}, max_tokens={doc_max_tokens}, temp={config.temperature}")

            return DocumentationGenerator(
                api_key=api_key,
                model=config.model,
                max_tokens=doc_max_tokens,
                temperature=config.temperature,
                custom_prompt=custom_prompt
            )

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error creating DocumentationGenerator: {e}")
        return None
