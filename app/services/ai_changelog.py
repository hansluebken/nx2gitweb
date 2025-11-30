"""
AI Changelog Service - Multi-Provider KI-Service für Änderungsanalyse

Unterstützte Provider:
- Claude (Anthropic)
- OpenAI (GPT)
- Google Gemini

Alle Beschreibungen werden auf Deutsch generiert.
"""
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from ..database import get_db
from ..models.ai_config import AIConfig, AIProvider
from ..models.changelog import ChangeLog
from ..utils.encryption import get_encryption_manager


# System prompt for all providers (German)
SYSTEM_PROMPT = """Du bist ein Experte für Ninox-Datenbanken und analysierst Code-Änderungen.
Deine Aufgabe ist es, Änderungen in Ninox-Datenbankcode verständlich zu beschreiben.

Regeln:
1. Antworte IMMER auf Deutsch
2. Beschreibe Änderungen so, dass auch Nicht-Entwickler sie verstehen
3. Fokussiere auf den ZWECK der Änderung, nicht nur auf technische Details
4. Sei präzise und vermeide Fachbegriffe wo möglich
5. Wenn Code-Felder geändert wurden, erkläre was diese bewirken

Ninox Code-Typen Erklärung:
- fn: Berechnetes Feld (Formel)
- afterUpdate: Wird nach Änderungen ausgeführt
- afterCreate: Wird nach Erstellung eines Datensatzes ausgeführt
- beforeDelete: Wird vor dem Löschen ausgeführt
- canWrite/canRead: Berechtigungsregeln
- visibility: Sichtbarkeitsregeln
- globalCode: Globale Funktionen der Datenbank
- filter: Filterausdruck für Views/Reports"""


@dataclass
class AIAnalysisResult:
    """Result of AI analysis"""
    summary: str  # Short summary (1-2 sentences)
    details: str  # Detailed description (Markdown)
    provider: str  # Which provider was used
    model: str  # Which model was used
    success: bool = True
    error: Optional[str] = None
    input_tokens: Optional[int] = None  # Number of input tokens used
    output_tokens: Optional[int] = None  # Number of output tokens generated


class BaseAIProvider(ABC):
    """Abstract base class for AI providers"""
    
    def __init__(self, api_key: str, model: str, max_tokens: int = 1000, temperature: float = 0.3):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
    
    @abstractmethod
    def analyze(self, diff: str, context: Dict[str, Any]) -> AIAnalysisResult:
        """Analyze diff and generate description"""
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """Test if the API connection works"""
        pass
    
    def _build_user_prompt(self, diff: str, context: Dict[str, Any]) -> str:
        """Build the user prompt for analysis"""
        prompt_parts = ["Analysiere folgende Änderungen:\n"]
        
        # Add context
        if context.get('database_name'):
            prompt_parts.append(f"Datenbank: {context['database_name']}")
        
        if context.get('changed_items'):
            prompt_parts.append("\nGeänderte Elemente:")
            for item in context['changed_items']:
                table = item.get('table', 'Unbekannt')
                field = item.get('field', '')
                code_type = item.get('code_type', '')
                change_type = item.get('change_type', 'modified')
                
                change_type_de = {
                    'added': 'Hinzugefügt',
                    'modified': 'Geändert',
                    'removed': 'Entfernt',
                    'renamed': 'Umbenannt'
                }.get(change_type, change_type)
                
                prompt_parts.append(f"  - {table}.{field} ({code_type}): {change_type_de}")
        
        # Add diff
        prompt_parts.append(f"\nDiff:\n```\n{diff}\n```")
        
        # Request format
        prompt_parts.append("""
Bitte antworte im folgenden Format:

ZUSAMMENFASSUNG:
[1-2 Sätze, die die wichtigsten Änderungen beschreiben]

DETAILS:
[Ausführlichere Beschreibung in Markdown-Format mit Aufzählungspunkten]
""")
        
        return "\n".join(prompt_parts)
    
    def _parse_response(
        self, 
        response_text: str, 
        provider: str, 
        model: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None
    ) -> AIAnalysisResult:
        """Parse the AI response into structured format"""
        summary = ""
        details = ""
        
        # Try to parse structured response
        if "ZUSAMMENFASSUNG:" in response_text and "DETAILS:" in response_text:
            parts = response_text.split("DETAILS:")
            summary_part = parts[0].replace("ZUSAMMENFASSUNG:", "").strip()
            details_part = parts[1].strip() if len(parts) > 1 else ""
            
            summary = summary_part
            details = details_part
        else:
            # Fallback: Use first sentence as summary, rest as details
            sentences = response_text.split(". ")
            if sentences:
                summary = sentences[0] + "." if not sentences[0].endswith(".") else sentences[0]
                details = response_text
        
        return AIAnalysisResult(
            summary=summary.strip(),
            details=details.strip(),
            provider=provider,
            model=model,
            success=True,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )


class ClaudeProvider(BaseAIProvider):
    """Claude (Anthropic) AI Provider"""
    
    PROVIDER_NAME = "claude"
    
    def analyze(self, diff: str, context: Dict[str, Any]) -> AIAnalysisResult:
        try:
            import anthropic
            
            client = anthropic.Anthropic(api_key=self.api_key)
            
            message = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": self._build_user_prompt(diff, context)}
                ]
            )
            
            response_text = message.content[0].text
            
            # Extract token usage
            input_tokens = message.usage.input_tokens if hasattr(message, 'usage') else None
            output_tokens = message.usage.output_tokens if hasattr(message, 'usage') else None
            
            return self._parse_response(
                response_text, 
                self.PROVIDER_NAME, 
                self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
        except Exception as e:
            return AIAnalysisResult(
                summary="",
                details="",
                provider=self.PROVIDER_NAME,
                model=self.model,
                success=False,
                error=str(e)
            )
    
    def test_connection(self) -> bool:
        try:
            import anthropic
            
            client = anthropic.Anthropic(api_key=self.api_key)
            
            # Simple test message
            message = client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[
                    {"role": "user", "content": "Antworte mit 'OK'"}
                ]
            )
            
            return True
        except Exception:
            return False


class OpenAIProvider(BaseAIProvider):
    """OpenAI GPT Provider"""
    
    PROVIDER_NAME = "openai"
    
    def analyze(self, diff: str, context: Dict[str, Any]) -> AIAnalysisResult:
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=self.api_key)
            
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_user_prompt(diff, context)}
                ]
            )
            
            response_text = response.choices[0].message.content
            
            # Extract token usage
            input_tokens = response.usage.prompt_tokens if hasattr(response, 'usage') and response.usage else None
            output_tokens = response.usage.completion_tokens if hasattr(response, 'usage') and response.usage else None
            
            return self._parse_response(
                response_text, 
                self.PROVIDER_NAME, 
                self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
        except Exception as e:
            return AIAnalysisResult(
                summary="",
                details="",
                provider=self.PROVIDER_NAME,
                model=self.model,
                success=False,
                error=str(e)
            )
    
    def test_connection(self) -> bool:
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=self.api_key)
            
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=10,
                messages=[
                    {"role": "user", "content": "Antworte mit 'OK'"}
                ]
            )
            
            return True
        except Exception:
            return False


class GeminiProvider(BaseAIProvider):
    """Google Gemini Provider"""
    
    PROVIDER_NAME = "gemini"
    
    def analyze(self, diff: str, context: Dict[str, Any]) -> AIAnalysisResult:
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model)
            
            # Gemini combines system and user prompt
            full_prompt = f"{SYSTEM_PROMPT}\n\n{self._build_user_prompt(diff, context)}"
            
            response = model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=self.max_tokens,
                    temperature=self.temperature,
                )
            )
            
            response_text = response.text
            
            # Extract token usage from Gemini
            input_tokens = None
            output_tokens = None
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count
            
            return self._parse_response(
                response_text, 
                self.PROVIDER_NAME, 
                self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
        except Exception as e:
            return AIAnalysisResult(
                summary="",
                details="",
                provider=self.PROVIDER_NAME,
                model=self.model,
                success=False,
                error=str(e)
            )
    
    def test_connection(self) -> bool:
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model)
            
            response = model.generate_content("Antworte mit 'OK'")
            
            return True
        except Exception:
            return False


class AIChangelogService:
    """
    Main service for AI-powered changelog generation.
    Manages multiple providers and handles configuration from database.
    """
    
    PROVIDERS = {
        AIProvider.CLAUDE.value: ClaudeProvider,
        AIProvider.OPENAI.value: OpenAIProvider,
        AIProvider.GEMINI.value: GeminiProvider,
    }
    
    def __init__(self):
        self.encryption = get_encryption_manager()
        self._config_cache: Optional[AIConfig] = None
        self._provider_cache: Optional[BaseAIProvider] = None
    
    def _get_default_config(self) -> Optional[AIConfig]:
        """Get the default AI configuration from database"""
        db = get_db()
        try:
            config = db.query(AIConfig).filter(
                AIConfig.is_default == True,
                AIConfig.is_active == True,
                AIConfig.api_key_encrypted != None
            ).first()
            
            return config
        finally:
            db.close()
    
    def _get_config_by_provider(self, provider: str) -> Optional[AIConfig]:
        """Get AI configuration for a specific provider"""
        db = get_db()
        try:
            config = db.query(AIConfig).filter(
                AIConfig.provider == provider,
                AIConfig.is_active == True,
                AIConfig.api_key_encrypted != None
            ).first()
            
            return config
        finally:
            db.close()
    
    def _create_provider(self, config: AIConfig) -> Optional[BaseAIProvider]:
        """Create a provider instance from configuration"""
        provider_class = self.PROVIDERS.get(config.provider)
        if not provider_class:
            return None
        
        # Decrypt API key
        api_key = self.encryption.decrypt(config.api_key_encrypted)
        if not api_key:
            return None
        
        return provider_class(
            api_key=api_key,
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature
        )
    
    def get_provider(self, provider_name: Optional[str] = None) -> Optional[BaseAIProvider]:
        """
        Get an AI provider instance.
        Uses default provider if no specific provider is requested.
        """
        if provider_name:
            config = self._get_config_by_provider(provider_name)
        else:
            config = self._get_default_config()
        
        if not config:
            return None
        
        return self._create_provider(config)
    
    def is_configured(self) -> bool:
        """Check if at least one AI provider is configured"""
        config = self._get_default_config()
        return config is not None
    
    def get_available_providers(self) -> List[Dict[str, Any]]:
        """Get list of all configured providers with their status"""
        db = get_db()
        try:
            configs = db.query(AIConfig).all()
            
            result = []
            for config in configs:
                result.append({
                    'provider': config.provider,
                    'display_name': config.display_name,
                    'model': config.model,
                    'is_default': config.is_default,
                    'is_active': config.is_active,
                    'is_configured': config.is_configured,
                    'last_test_success': config.last_test_success,
                })
            
            return result
        finally:
            db.close()
    
    def analyze_diff(
        self, 
        diff: str, 
        context: Dict[str, Any],
        provider_name: Optional[str] = None
    ) -> AIAnalysisResult:
        """
        Analyze a diff and generate German description.
        
        Args:
            diff: The diff/patch content to analyze
            context: Additional context (database_name, changed_items, etc.)
            provider_name: Optional specific provider to use
        
        Returns:
            AIAnalysisResult with summary and details
        """
        provider = self.get_provider(provider_name)
        
        if not provider:
            return AIAnalysisResult(
                summary="",
                details="",
                provider="none",
                model="",
                success=False,
                error="Kein KI-Provider konfiguriert. Bitte konfigurieren Sie einen Provider im Admin-Panel."
            )
        
        return provider.analyze(diff, context)
    
    def test_provider(self, provider_name: str, api_key: str, model: str) -> Dict[str, Any]:
        """
        Test a provider connection with given credentials.
        
        Args:
            provider_name: Name of the provider (claude, openai, gemini)
            api_key: API key to test
            model: Model to use
        
        Returns:
            Dict with success status and optional error message
        """
        provider_class = self.PROVIDERS.get(provider_name)
        if not provider_class:
            return {
                'success': False,
                'error': f'Unbekannter Provider: {provider_name}'
            }
        
        provider = provider_class(
            api_key=api_key,
            model=model,
            max_tokens=100,
            temperature=0.3
        )
        
        try:
            success = provider.test_connection()
            return {
                'success': success,
                'error': None if success else 'Verbindungstest fehlgeschlagen'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def ask_question(
        self, 
        provider_name: str, 
        api_key: str, 
        model: str, 
        question: str,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        Ask a question to a specific provider.
        
        Args:
            provider_name: Name of the provider (claude, openai, gemini)
            api_key: API key to use
            model: Model to use
            question: The question to ask
            max_tokens: Maximum tokens in response
            temperature: Response creativity (0.0-1.0)
        
        Returns:
            Dict with success status, answer, and optional error message
        """
        provider_class = self.PROVIDERS.get(provider_name)
        if not provider_class:
            return {
                'success': False,
                'answer': '',
                'error': f'Unbekannter Provider: {provider_name}'
            }
        
        try:
            if provider_name == 'claude':
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                message = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "user", "content": question}
                    ]
                )
                answer = message.content[0].text
                
            elif provider_name == 'openai':
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "user", "content": question}
                    ]
                )
                answer = response.choices[0].message.content
                
            elif provider_name == 'gemini':
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                gemini_model = genai.GenerativeModel(model)
                response = gemini_model.generate_content(
                    question,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                    )
                )
                answer = response.text
            else:
                return {
                    'success': False,
                    'answer': '',
                    'error': f'Provider nicht implementiert: {provider_name}'
                }
            
            return {
                'success': True,
                'answer': answer,
                'error': None
            }
            
        except Exception as e:
            return {
                'success': False,
                'answer': '',
                'error': str(e)
            }
    
    def create_changelog_entry(
        self,
        database_id: int,
        commit_sha: str,
        commit_date: datetime,
        commit_message: str,
        commit_url: str,
        diff_data: Dict[str, Any],
        provider_name: Optional[str] = None
    ) -> Optional[ChangeLog]:
        """
        Create a complete changelog entry with AI analysis.
        
        Args:
            database_id: ID of the database
            commit_sha: Git commit SHA
            commit_date: Date of the commit
            commit_message: Original commit message
            commit_url: URL to the commit on GitHub
            diff_data: Dict containing files, full_patch, changed_items
            provider_name: Optional specific provider to use
        
        Returns:
            Created ChangeLog object or None on failure
        """
        # Perform AI analysis
        context = {
            'changed_items': diff_data.get('changed_items', []),
        }
        
        analysis = self.analyze_diff(
            diff=diff_data.get('full_patch', ''),
            context=context,
            provider_name=provider_name
        )
        
        # Calculate statistics
        files = diff_data.get('files', [])
        total_additions = sum(f.get('additions', 0) for f in files)
        total_deletions = sum(f.get('deletions', 0) for f in files)
        
        # Create changelog entry
        db = get_db()
        try:
            changelog = ChangeLog(
                database_id=database_id,
                commit_sha=commit_sha,
                commit_date=commit_date,
                commit_message=commit_message,
                commit_url=commit_url,
                files_changed=len(files),
                additions=total_additions,
                deletions=total_deletions,
                ai_summary=analysis.summary if analysis.success else None,
                ai_details=analysis.details if analysis.success else None,
                ai_provider=analysis.provider if analysis.success else None,
                ai_model=analysis.model if analysis.success else None,
                ai_generated_at=datetime.utcnow() if analysis.success else None,
                ai_error=analysis.error if not analysis.success else None,
                ai_input_tokens=analysis.input_tokens if analysis.success else None,
                ai_output_tokens=analysis.output_tokens if analysis.success else None,
                diff_patch=diff_data.get('full_patch', ''),
                changed_items=diff_data.get('changed_items', []),
            )
            
            db.add(changelog)
            db.commit()
            db.refresh(changelog)
            
            return changelog
            
        except Exception as e:
            db.rollback()
            print(f"Fehler beim Erstellen des ChangeLog-Eintrags: {e}")
            return None
        finally:
            db.close()


# Global service instance
_ai_changelog_service: Optional[AIChangelogService] = None


def get_ai_changelog_service() -> AIChangelogService:
    """Get global AI changelog service instance"""
    global _ai_changelog_service
    if _ai_changelog_service is None:
        _ai_changelog_service = AIChangelogService()
    return _ai_changelog_service
