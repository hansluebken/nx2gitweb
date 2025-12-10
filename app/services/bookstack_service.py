"""
BookStack Service
Handles documentation export to BookStack
"""
import logging
from typing import Optional
from datetime import datetime
from pathlib import Path

from ..api.bookstack_client import BookStackClient
from ..database import get_db
from ..models.server import Server
from ..models.database import Database
from ..models.bookstack_config import BookstackConfig
from ..utils.encryption import get_encryption_manager

logger = logging.getLogger(__name__)


class BookStackService:
    """Service for syncing documentation to BookStack"""

    def sync_database_to_bookstack(
        self,
        database: Database,
        server: Server,
        documentation_content: str,
        scripts_content: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Sync database documentation and scripts to BookStack

        Args:
            database: Database model
            server: Server model
            documentation_content: Markdown documentation content
            scripts_content: Optional markdown scripts content

        Returns:
            (success, error_message)
        """
        try:
            # Get BookStack configuration for this server
            db = get_db()
            try:
                bookstack_config = db.query(BookstackConfig).filter(
                    BookstackConfig.server_id == server.id,
                    BookstackConfig.is_active == True
                ).first()

                if not bookstack_config or not bookstack_config.is_configured:
                    return False, "BookStack nicht für diesen Server konfiguriert"

                # Decrypt API token
                enc_manager = get_encryption_manager()
                api_token = enc_manager.decrypt(bookstack_config.api_token_encrypted)

                if not api_token:
                    return False, "Konnte API-Token nicht entschlüsseln"

                # Create BookStack client
                client = BookStackClient(bookstack_config.url, api_token)

                # Ensure shelf exists
                shelf_name = bookstack_config.default_shelf_name
                shelf = client.ensure_shelf(
                    shelf_name,
                    f"Automatisch generierte Dokumentationen von Ninox2Git für Server: {server.name}"
                )

                if not shelf:
                    return False, f"Konnte Shelf '{shelf_name}' nicht erstellen/finden"

                # Update config with shelf ID if it was just created
                if not bookstack_config.default_shelf_id:
                    bookstack_config.default_shelf_id = shelf.id
                    db.merge(bookstack_config)
                    db.commit()

                # Get or create book for this database
                book_name = f"{database.name}"
                book = client.get_book_by_name_in_shelf(book_name, shelf.id)

                if not book:
                    logger.info(f"Creating new book: {book_name}")
                    book = client.create_book(
                        book_name,
                        shelf.id,
                        f"Ninox Datenbank: {database.name} (ID: {database.database_id})"
                    )

                    if not book:
                        return False, "Konnte Buch nicht erstellen"

                    # Save book ID to database
                    database.bookstack_book_id = book.id
                    database.bookstack_shelf_id = shelf.id
                    db.merge(database)
                    db.commit()

                # Update book content with documentation and optional scripts
                logger.info(f"Updating book content: {book_name} (ID: {book.id})")

                # Prepare pages to create (book already has database name, so use simple page names)
                pages = [
                    ("Dokumentation", documentation_content)
                ]

                # Add scripts page if available
                if scripts_content:
                    pages.append(("Scripts", scripts_content))
                    logger.info(f"Including Scripts page in BookStack book {book.id}")

                logger.info(f"Creating {len(pages)} page(s) in book '{book_name}' (ID: {book.id})")
                success = client.update_book_with_pages(book.id, pages)

                if not success:
                    return False, "Konnte Buchinhalt nicht aktualisieren"

                # Update last sync time
                database.last_bookstack_sync = datetime.utcnow()
                db.merge(database)
                db.commit()

                logger.info(f"✓ Successfully synced {database.name} to BookStack")

                # Build URL to book (ensure no double slashes)
                base_url = bookstack_config.url.rstrip('/')
                book_url = f"{base_url}/books/{book.slug}"
                return True, book_url

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error syncing to BookStack: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, str(e)


# Singleton instance
_bookstack_service: Optional[BookStackService] = None


def get_bookstack_service() -> BookStackService:
    """Get or create singleton BookStack service"""
    global _bookstack_service
    if _bookstack_service is None:
        _bookstack_service = BookStackService()
    return _bookstack_service
