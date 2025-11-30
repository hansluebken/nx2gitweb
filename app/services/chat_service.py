"""
Chat Service for Ninox Database Assistant
Provides streaming chat functionality with Gemini AI
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Generator
from datetime import datetime

logger = logging.getLogger(__name__)

# System prompt for the Ninox Database Assistant
SYSTEM_PROMPT = """Du bist ein Experte für Ninox-Datenbanken und hilfst Benutzern bei Fragen zu ihrer Datenbank.

Du hast Zugriff auf die Struktur der Datenbank und kannst:
- Fragen zur Datenbankstruktur beantworten (Tabellen, Felder, Beziehungen)
- Ninox-Formeln schreiben und erklären
- Best Practices für Ninox empfehlen
- Bei der Fehlersuche in Formeln helfen
- Trigger und Automationen erklären
- Views und Reports analysieren

Wichtige Hinweise:
- Antworte auf Deutsch
- Verwende Markdown für Formatierung
- Nutze Code-Blöcke mit ```ninox für Ninox-Formeln
- Sei präzise und hilfreich
- Beziehe dich auf die konkrete Datenbankstruktur wenn relevant

Datenbankstruktur:
"""


@dataclass
class ChatMessage:
    """A single chat message"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    tokens_used: Optional[int] = None


@dataclass
class ChatSession:
    """A chat session with history"""
    database_name: str
    database_structure: Dict[str, Any]
    messages: List[ChatMessage] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    
    def add_message(self, role: str, content: str, tokens: int = None):
        """Add a message to the history"""
        self.messages.append(ChatMessage(role=role, content=content, tokens_used=tokens))
    
    def get_history_for_api(self) -> List[Dict[str, str]]:
        """Get message history in API format"""
        return [
            {"role": msg.role, "parts": [msg.content]}
            for msg in self.messages
        ]


class NinoxChatService:
    """Chat service for Ninox database questions using Gemini"""
    
    def __init__(self, api_key: str, model: str = "gemini-2.5-pro", temperature: float = 0.7):
        """
        Initialize the chat service
        
        Args:
            api_key: Gemini API key
            model: Model to use
            temperature: Creativity setting (higher = more creative)
        """
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.sessions: Dict[str, ChatSession] = {}
    
    def create_session(self, session_id: str, database_name: str, structure_json: Dict[str, Any]) -> ChatSession:
        """
        Create a new chat session for a database
        
        Args:
            session_id: Unique session identifier
            database_name: Name of the database
            structure_json: Database structure as dict
            
        Returns:
            ChatSession object
        """
        session = ChatSession(
            database_name=database_name,
            database_structure=structure_json
        )
        self.sessions[session_id] = session
        logger.info(f"Created chat session {session_id} for database '{database_name}'")
        return session
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Get an existing session"""
        return self.sessions.get(session_id)
    
    def _build_system_prompt(self, session: ChatSession) -> str:
        """Build the system prompt with database structure"""
        structure_str = json.dumps(session.database_structure, indent=2, ensure_ascii=False)
        return f"{SYSTEM_PROMPT}\n```json\n{structure_str}\n```"
    
    def chat(self, session_id: str, user_message: str) -> str:
        """
        Send a message and get a response (non-streaming)
        
        Args:
            session_id: Session ID
            user_message: User's message
            
        Returns:
            Assistant's response
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                self.model,
                system_instruction=self._build_system_prompt(session)
            )
            
            # Add user message to history
            session.add_message("user", user_message)
            
            # Start or continue chat
            chat = model.start_chat(history=session.get_history_for_api()[:-1])
            
            # Send message
            response = chat.send_message(user_message)
            
            # Extract response and tokens
            assistant_message = response.text
            input_tokens = None
            output_tokens = None
            
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count
                session.total_input_tokens += input_tokens or 0
                session.total_output_tokens += output_tokens or 0
            
            # Add assistant response to history
            session.add_message("assistant", assistant_message, output_tokens)
            
            logger.info(f"Chat response: {input_tokens} input, {output_tokens} output tokens")
            
            return assistant_message
            
        except Exception as e:
            logger.error(f"Chat error: {e}")
            raise
    
    def chat_stream(self, session_id: str, user_message: str) -> Generator[str, None, None]:
        """
        Send a message and stream the response
        
        Args:
            session_id: Session ID
            user_message: User's message
            
        Yields:
            Chunks of the response text
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                self.model,
                system_instruction=self._build_system_prompt(session)
            )
            
            # Add user message to history
            session.add_message("user", user_message)
            
            # Start or continue chat
            chat = model.start_chat(history=session.get_history_for_api()[:-1])
            
            # Send message with streaming
            response = chat.send_message(user_message, stream=True)
            
            full_response = ""
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    yield chunk.text
            
            # Get final token counts
            input_tokens = None
            output_tokens = None
            
            # After streaming, we can get usage from the response
            try:
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    input_tokens = response.usage_metadata.prompt_token_count
                    output_tokens = response.usage_metadata.candidates_token_count
                    session.total_input_tokens += input_tokens or 0
                    session.total_output_tokens += output_tokens or 0
            except:
                pass  # Token counting may not be available during streaming
            
            # Add assistant response to history
            session.add_message("assistant", full_response, output_tokens)
            
            logger.info(f"Streamed response complete: {len(full_response)} chars")
            
        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            yield f"\n\n**Fehler:** {str(e)}"


def get_chat_service() -> Optional[NinoxChatService]:
    """
    Get a NinoxChatService instance if Gemini is configured
    
    Returns:
        NinoxChatService or None if not configured
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
                logger.warning("Gemini not configured for chat")
                return None
            
            # Decrypt API key
            enc_manager = get_encryption_manager()
            api_key = enc_manager.decrypt(config.api_key_encrypted)
            if not api_key:
                logger.warning("Could not decrypt Gemini API key")
                return None
            
            logger.info(f"Creating NinoxChatService with model={config.model}, temp={config.temperature}")
            
            return NinoxChatService(
                api_key=api_key,
                model=config.model,
                temperature=config.temperature
            )
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error creating NinoxChatService: {e}")
        return None
