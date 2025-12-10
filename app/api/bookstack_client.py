"""
BookStack API Client
Handles communication with BookStack documentation platform
"""
import requests
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BookStackBook:
    """BookStack book representation"""
    id: int
    name: str
    slug: str
    description: str
    shelf_id: Optional[int] = None


@dataclass
class BookStackShelf:
    """BookStack shelf representation"""
    id: int
    name: str
    slug: str
    description: str


class BookStackClient:
    """
    Client for BookStack API

    API Documentation: https://demo.bookstackapp.com/api/docs
    """

    def __init__(self, base_url: str, api_token: str):
        """
        Initialize BookStack client

        Args:
            base_url: BookStack instance URL (e.g., https://docs.company.com)
            api_token: API token from BookStack settings
        """
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api"

        # BookStack uses "Token {token}" format
        self.headers = {
            'Authorization': f'Token {api_token}',
            'Content-Type': 'application/json'
        }

    def test_connection(self) -> tuple[bool, Optional[str]]:
        """
        Test connection to BookStack API

        Returns:
            (success, error_message)
        """
        try:
            response = requests.get(
                f"{self.api_url}/shelves",
                headers=self.headers,
                timeout=10
            )

            if response.status_code == 200:
                return True, None
            else:
                return False, f"HTTP {response.status_code}: {response.text[:200]}"

        except Exception as e:
            return False, str(e)

    def create_shelf(self, name: str, description: str = "") -> Optional[BookStackShelf]:
        """
        Create a new shelf

        Args:
            name: Shelf name
            description: Shelf description

        Returns:
            BookStackShelf or None if failed
        """
        try:
            payload = {
                'name': name,
                'description': description
            }

            response = requests.post(
                f"{self.api_url}/shelves",
                headers=self.headers,
                json=payload,
                timeout=30
            )

            if response.status_code in [200, 201]:
                data = response.json()
                return BookStackShelf(
                    id=data['id'],
                    name=data['name'],
                    slug=data['slug'],
                    description=data.get('description', '')
                )
            else:
                logger.error(f"Failed to create shelf: HTTP {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error creating shelf: {e}")
            return None

    def get_shelf_by_name(self, name: str) -> Optional[BookStackShelf]:
        """
        Get shelf by name

        Args:
            name: Shelf name to search for

        Returns:
            BookStackShelf or None if not found
        """
        try:
            response = requests.get(
                f"{self.api_url}/shelves",
                headers=self.headers,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                for shelf in data.get('data', []):
                    if shelf['name'] == name:
                        return BookStackShelf(
                            id=shelf['id'],
                            name=shelf['name'],
                            slug=shelf['slug'],
                            description=shelf.get('description', '')
                        )

            return None

        except Exception as e:
            logger.error(f"Error getting shelf: {e}")
            return None

    def ensure_shelf(self, name: str, description: str = "") -> Optional[BookStackShelf]:
        """
        Get shelf by name or create if not exists

        Args:
            name: Shelf name
            description: Shelf description (used if creating)

        Returns:
            BookStackShelf or None if failed
        """
        # Try to get existing shelf
        shelf = self.get_shelf_by_name(name)
        if shelf:
            logger.info(f"Shelf '{name}' already exists (ID: {shelf.id})")
            return shelf

        # Create new shelf
        logger.info(f"Creating new shelf: {name}")
        return self.create_shelf(name, description)

    def create_book(self, name: str, shelf_id: Optional[int] = None, description: str = "") -> Optional[BookStackBook]:
        """
        Create a new book

        Args:
            name: Book name
            shelf_id: Optional shelf ID to add book to
            description: Book description

        Returns:
            BookStackBook or None if failed
        """
        try:
            payload = {
                'name': name,
                'description': description
            }

            response = requests.post(
                f"{self.api_url}/books",
                headers=self.headers,
                json=payload,
                timeout=30
            )

            if response.status_code in [200, 201]:
                data = response.json()
                book = BookStackBook(
                    id=data['id'],
                    name=data['name'],
                    slug=data['slug'],
                    description=data.get('description', ''),
                    shelf_id=None
                )

                # Add to shelf if specified
                if shelf_id:
                    self.add_book_to_shelf(book.id, shelf_id)
                    book.shelf_id = shelf_id

                return book
            else:
                logger.error(f"Failed to create book: HTTP {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error creating book: {e}")
            return None

    def add_book_to_shelf(self, book_id: int, shelf_id: int) -> bool:
        """Add a book to a shelf"""
        try:
            # Get shelf details
            response = requests.get(
                f"{self.api_url}/shelves/{shelf_id}",
                headers=self.headers,
                timeout=30
            )

            if response.status_code != 200:
                return False

            shelf_data = response.json()
            books = shelf_data.get('books', [])
            book_ids = [b['id'] for b in books]

            # Add book if not already in shelf
            if book_id not in book_ids:
                book_ids.append(book_id)

                # Update shelf
                payload = {'books': book_ids}
                response = requests.put(
                    f"{self.api_url}/shelves/{shelf_id}",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )

                return response.status_code in [200, 204]

            return True

        except Exception as e:
            logger.error(f"Error adding book to shelf: {e}")
            return False

    def update_book_markdown(self, book_id: int, markdown_content: str, page_name: str = "Dokumentation") -> bool:
        """
        Create or update a page in a book with markdown content

        Args:
            book_id: Book ID
            markdown_content: Markdown content
            page_name: Page name (default: "Dokumentation")

        Returns:
            True if successful
        """
        try:
            # Get existing pages in book
            response = requests.get(
                f"{self.api_url}/books/{book_id}",
                headers=self.headers,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Failed to get book: HTTP {response.status_code}")
                return False

            book_data = response.json()
            pages = book_data.get('contents', [])

            # Delete ALL existing pages in book (clean slate for single-page documentation)
            for item in pages:
                if item.get('type') == 'page':
                    old_page_id = item['id']
                    logger.info(f"Deleting old page '{item.get('name')}' (ID: {old_page_id})")
                    try:
                        requests.delete(
                            f"{self.api_url}/pages/{old_page_id}",
                            headers=self.headers,
                            timeout=30
                        )
                    except Exception as e:
                        logger.warning(f"Could not delete old page {old_page_id}: {e}")

            # Create new page (always create, never update - we deleted all old pages)
            payload = {
                'book_id': book_id,
                'name': page_name,
                'markdown': markdown_content
            }

            response = requests.post(
                f"{self.api_url}/pages",
                headers=self.headers,
                json=payload,
                timeout=60
            )

            if response.status_code in [200, 201]:
                logger.info(f"Page '{page_name}' created in book {book_id}")
                return True
            else:
                logger.error(f"Failed to save page: HTTP {response.status_code} - {response.text[:200]}")
                return False

        except Exception as e:
            logger.error(f"Error updating book: {e}")
            return False

    def update_book_with_pages(self, book_id: int, pages: list[tuple[str, str]]) -> bool:
        """
        Create or update multiple pages in a book with markdown content

        Args:
            book_id: Book ID
            pages: List of (page_name, markdown_content) tuples

        Returns:
            True if successful
        """
        try:
            # Get existing pages in book
            response = requests.get(
                f"{self.api_url}/books/{book_id}",
                headers=self.headers,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Failed to get book: HTTP {response.status_code}")
                return False

            book_data = response.json()
            existing_pages = book_data.get('contents', [])

            # Delete ALL existing pages in book (clean slate)
            for item in existing_pages:
                if item.get('type') == 'page':
                    old_page_id = item['id']
                    logger.info(f"Deleting old page '{item.get('name')}' (ID: {old_page_id})")
                    try:
                        requests.delete(
                            f"{self.api_url}/pages/{old_page_id}",
                            headers=self.headers,
                            timeout=30
                        )
                    except Exception as e:
                        logger.warning(f"Could not delete old page {old_page_id}: {e}")

            # Create new pages in the SAME book
            logger.info(f"Creating {len(pages)} page(s) in book ID {book_id}")

            for idx, (page_name, markdown_content) in enumerate(pages, 1):
                payload = {
                    'book_id': book_id,
                    'name': page_name,
                    'markdown': markdown_content
                }

                logger.info(f"Creating page {idx}/{len(pages)}: '{page_name}' in book {book_id}")

                response = requests.post(
                    f"{self.api_url}/pages",
                    headers=self.headers,
                    json=payload,
                    timeout=60
                )

                if response.status_code in [200, 201]:
                    page_data = response.json()
                    page_id = page_data.get('id', 'unknown')
                    logger.info(f"✓ Page '{page_name}' created in book {book_id} (Page ID: {page_id})")
                else:
                    logger.error(f"✗ Failed to save page '{page_name}': HTTP {response.status_code} - {response.text[:200]}")
                    return False

            logger.info(f"✓ Successfully created {len(pages)} page(s) in book {book_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating book with pages: {e}")
            return False

    def get_book_by_name_in_shelf(self, book_name: str, shelf_id: int) -> Optional[BookStackBook]:
        """Find a book by name within a specific shelf"""
        try:
            response = requests.get(
                f"{self.api_url}/shelves/{shelf_id}",
                headers=self.headers,
                timeout=30
            )

            if response.status_code == 200:
                shelf_data = response.json()
                for book in shelf_data.get('books', []):
                    if book['name'] == book_name:
                        return BookStackBook(
                            id=book['id'],
                            name=book['name'],
                            slug=book['slug'],
                            description=book.get('description', ''),
                            shelf_id=shelf_id
                        )

            return None

        except Exception as e:
            logger.error(f"Error finding book: {e}")
            return None
