"""
Ninox API Client
Kommuniziert mit dem Ninox Server über die REST API
"""

import requests
import json
from typing import Dict, List, Optional
from urllib.parse import urljoin


class NinoxClient:
    def __init__(self, base_url: str, api_key: str):
        """
        Initialisiert den Ninox Client
        
        Args:
            base_url: Basis-URL des Ninox Servers (z.B. https://nx.nf1.eu)
            api_key: API-Schlüssel für die Authentifizierung
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """
        Führt eine API-Anfrage aus
        
        Args:
            method: HTTP-Methode (GET, POST, PUT, DELETE)
            endpoint: API-Endpunkt
            **kwargs: Zusätzliche Parameter für requests
        
        Returns:
            JSON-Response als Dictionary
        
        Raises:
            requests.exceptions.HTTPError: Bei HTTP-Fehlern
        """
        url = urljoin(self.base_url, endpoint)
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            
            # Leere Responses behandeln
            if response.text:
                return response.json()
            return {}
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            raise requests.exceptions.HTTPError(error_msg)
        except requests.exceptions.RequestException as e:
            raise Exception(f"Netzwerkfehler: {str(e)}")
    
    def get_teams(self) -> List[Dict]:
        """
        Holt alle verfügbaren Teams/Arbeitsbereiche
        
        Returns:
            Liste der Teams
        """
        result = self._make_request('GET', '/v1/teams')
        # API könnte ein Dictionary mit Teams zurückgeben oder direkt eine Liste
        if isinstance(result, list):
            return result
        elif isinstance(result, dict) and 'teams' in result:
            return result['teams']
        return [result] if result else []
    
    def get_team(self, team_id: str) -> Dict:
        """
        Holt Details zu einem spezifischen Team
        
        Args:
            team_id: ID des Teams
        
        Returns:
            Team-Details
        """
        return self._make_request('GET', f'/v1/teams/{team_id}')
    
    def get_databases(self, team_id: str) -> List[Dict]:
        """
        Holt alle Datenbanken eines Teams
        
        Args:
            team_id: ID des Teams
        
        Returns:
            Liste der Datenbanken
        """
        result = self._make_request('GET', f'/v1/teams/{team_id}/databases')
        # API könnte ein Dictionary mit Datenbanken zurückgeben oder direkt eine Liste
        if isinstance(result, list):
            return result
        elif isinstance(result, dict) and 'databases' in result:
            return result['databases']
        return [result] if result else []
    
    def get_database_structure(self, team_id: str, database_id: str, format_scripts: bool = True) -> Dict:
        """
        Holt die komplette Struktur einer Datenbank inklusive aller Tabellen und Felder
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            format_scripts: Ob eingebettete Skripte formatiert werden sollen
        
        Returns:
            Datenbankstruktur mit allen Tabellen und Feldern
        """
        params = {}
        if format_scripts:
            params['formatScripts'] = 'T'
        
        return self._make_request(
            'GET', 
            f'/v1/teams/{team_id}/databases/{database_id}',
            params=params
        )
    
    def get_tables(self, team_id: str, database_id: str) -> List[Dict]:
        """
        Holt alle Tabellen einer Datenbank
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
        
        Returns:
            Liste der Tabellen
        """
        # Die Tabellen sind Teil der Datenbankstruktur
        db_structure = self.get_database_structure(team_id, database_id)
        return db_structure.get('tables', [])
    
    def get_table_structure(self, team_id: str, database_id: str, table_id: str) -> Dict:
        """
        Holt die Struktur einer spezifischen Tabelle
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            table_id: ID der Tabelle
        
        Returns:
            Tabellenstruktur
        """
        return self._make_request(
            'GET',
            f'/v1/teams/{team_id}/databases/{database_id}/tables/{table_id}'
        )
    
    def get_records(self, team_id: str, database_id: str, table_id: str, 
                   per_page: int = 100, page: int = 1, 
                   filters: Optional[str] = None, order: Optional[str] = None) -> Dict:
        """
        Holt Datensätze aus einer Tabelle
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            table_id: ID der Tabelle
            per_page: Anzahl der Datensätze pro Seite
            page: Seitennummer
            filters: NQL-Filter (optional)
            order: Sortierung (optional)
        
        Returns:
            Datensätze mit Paginierungsinformationen
        """
        params = {
            'perPage': str(per_page),
            'page': str(page)
        }
        
        if filters:
            params['filters'] = filters
        if order:
            params['order'] = order
        
        return self._make_request(
            'GET',
            f'/v1/teams/{team_id}/databases/{database_id}/tables/{table_id}/records',
            params=params
        )
    
    def get_record(self, team_id: str, database_id: str, table_id: str, record_id: str) -> Dict:
        """
        Holt einen einzelnen Datensatz
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            table_id: ID der Tabelle
            record_id: ID des Datensatzes
        
        Returns:
            Datensatz
        """
        return self._make_request(
            'GET',
            f'/v1/teams/{team_id}/databases/{database_id}/tables/{table_id}/records/{record_id}'
        )
    
    def create_record(self, team_id: str, database_id: str, table_id: str, fields: Dict) -> Dict:
        """
        Erstellt einen neuen Datensatz
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            table_id: ID der Tabelle
            fields: Feldwerte als Dictionary (Feldname -> Wert)
        
        Returns:
            Erstellter Datensatz
        """
        payload = {'fields': fields}
        
        return self._make_request(
            'POST',
            f'/v1/teams/{team_id}/databases/{database_id}/tables/{table_id}/records',
            json=payload
        )
    
    def update_record(self, team_id: str, database_id: str, table_id: str, 
                     record_id: str, fields: Dict) -> Dict:
        """
        Aktualisiert einen Datensatz
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            table_id: ID der Tabelle
            record_id: ID des Datensatzes
            fields: Zu aktualisierende Feldwerte
        
        Returns:
            Aktualisierter Datensatz
        """
        payload = {'fields': fields}
        
        return self._make_request(
            'PUT',
            f'/v1/teams/{team_id}/databases/{database_id}/tables/{table_id}/records/{record_id}',
            json=payload
        )
    
    def delete_record(self, team_id: str, database_id: str, table_id: str, record_id: str) -> None:
        """
        Löscht einen Datensatz
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            table_id: ID der Tabelle
            record_id: ID des Datensatzes
        """
        self._make_request(
            'DELETE',
            f'/v1/teams/{team_id}/databases/{database_id}/tables/{table_id}/records/{record_id}'
        )
    
    def batch_create_records(self, team_id: str, database_id: str, table_id: str, 
                           records: List[Dict]) -> List[Dict]:
        """
        Erstellt mehrere Datensätze gleichzeitig
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            table_id: ID der Tabelle
            records: Liste von Datensätzen mit Feldwerten
        
        Returns:
            Liste der erstellten Datensätze
        """
        payload = [{'fields': record} for record in records]
        
        result = self._make_request(
            'POST',
            f'/v1/teams/{team_id}/databases/{database_id}/tables/{table_id}/records',
            json=payload
        )
        
        # Ensure we return a list
        if isinstance(result, list):
            return result
        return [result] if result else []
    
    def test_connection(self) -> bool:
        """
        Testet die Verbindung zum Ninox-Server
        
        Returns:
            True wenn die Verbindung erfolgreich ist
        """
        try:
            self.get_teams()
            return True
        except Exception:
            return False
    
    # =========================================================================
    # Views API - Ansichten einer Datenbank
    # =========================================================================
    
    def get_views(self, team_id: str, database_id: str, full_view: bool = True, format_scripts: bool = True) -> List[Dict]:
        """
        Holt alle Views (Ansichten) einer Datenbank
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            full_view: Ob vollständige View-Daten geholt werden sollen (inkl. Konfiguration)
            format_scripts: Ob eingebettete Skripte formatiert werden sollen (Feldnamen statt IDs)
        
        Returns:
            Liste der Views mit allen Eigenschaften
        """
        params = {}
        if full_view:
            params['fullView'] = 'true'
        if format_scripts:
            params['formatScripts'] = 'T'
        
        result = self._make_request(
            'GET',
            f'/v1/teams/{team_id}/databases/{database_id}/views',
            params=params
        )
        
        if isinstance(result, list):
            return result
        return [result] if result else []
    
    def get_view(self, team_id: str, database_id: str, view_id: str) -> Dict:
        """
        Holt eine spezifische View
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            view_id: ID der View
        
        Returns:
            View-Details
        """
        return self._make_request(
            'GET',
            f'/v1/teams/{team_id}/databases/{database_id}/views/{view_id}'
        )
    
    # =========================================================================
    # Reports API - Berichte einer Datenbank
    # =========================================================================
    
    def get_reports(self, team_id: str, database_id: str, full_report: bool = True, format_scripts: bool = True) -> List[Dict]:
        """
        Holt alle Reports (Berichte) einer Datenbank
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            full_report: Ob vollständige Report-Daten geholt werden sollen
            format_scripts: Ob eingebettete Skripte formatiert werden sollen (Feldnamen statt IDs)
        
        Returns:
            Liste der Reports mit allen Eigenschaften
        """
        params = {}
        if full_report:
            params['fullReport'] = 'true'
        if format_scripts:
            params['formatScripts'] = 'T'
        
        result = self._make_request(
            'GET',
            f'/v1/teams/{team_id}/databases/{database_id}/reports',
            params=params
        )
        
        if isinstance(result, list):
            return result
        return [result] if result else []
    
    def get_report(self, team_id: str, database_id: str, report_id: str) -> Dict:
        """
        Holt einen spezifischen Report
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            report_id: ID des Reports
        
        Returns:
            Report-Details
        """
        return self._make_request(
            'GET',
            f'/v1/teams/{team_id}/databases/{database_id}/reports/{report_id}'
        )
    
    # =========================================================================
    # Report Files API - Dateien eines Reports (z.B. Word/Excel-Vorlagen)
    # =========================================================================
    
    def get_report_files(self, team_id: str, database_id: str, report_id: str) -> List[str]:
        """
        Listet alle Dateien eines Reports auf
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            report_id: ID des Reports
        
        Returns:
            Liste der Dateinamen
        """
        result = self._make_request(
            'GET',
            f'/v1/teams/{team_id}/databases/{database_id}/reports/{report_id}/files'
        )
        
        if isinstance(result, list):
            return result
        return [result] if result else []
    
    def get_report_file(self, team_id: str, database_id: str, report_id: str, 
                       file_name: str, as_base64: bool = True) -> str:
        """
        Holt eine spezifische Report-Datei
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            report_id: ID des Reports
            file_name: Name der Datei
            as_base64: Ob die Datei als Base64-URL zurückgegeben werden soll
        
        Returns:
            Dateiinhalt (als Base64-String wenn as_base64=True)
        """
        # Für Datei-Downloads müssen wir spezielle Header setzen
        url = f"{self.base_url}/v1/teams/{team_id}/databases/{database_id}/reports/{report_id}/files/{file_name}"
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Accept': '*/*'
        }
        
        if as_base64:
            headers['nx-file'] = 'base64url'
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            if as_base64:
                return response.text
            else:
                return response.content
                
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            raise requests.exceptions.HTTPError(error_msg)
    
    # =========================================================================
    # Database Schema API - Erweitert mit Views und Reports
    # =========================================================================
    
    def get_database_schema(self, team_id: str, database_id: str, 
                           include_views_reports: bool = True) -> Dict:
        """
        Holt das vollständige Datenbankschema (wie im Updatemanager)
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            include_views_reports: Ob Views und Reports inkludiert werden sollen
        
        Returns:
            Vollständiges Schema mit Types, Views, Reports
        """
        params = {}
        if include_views_reports:
            params['includeReportsAndViews'] = 'true'
        
        return self._make_request(
            'GET',
            f'/v1/teams/{team_id}/databases/{database_id}/schema',
            params=params
        )
    
    def get_complete_database_backup(self, team_id: str, database_id: str, 
                                     password: Optional[str] = None) -> Dict:
        """
        Erstellt ein vollständiges Backup einer Datenbank (wie im Updatemanager)
        Inkludiert: Schema, Views, Reports und Report-Dateien
        
        Args:
            team_id: ID des Teams
            database_id: ID der Datenbank
            password: Passwort für geschützte Datenbanken (optional)
        
        Returns:
            Vollständiges Backup mit allen Komponenten:
            {
                'schema': {...},
                'views': [...],
                'reports': [...],
                'report_files': {report_id: [file_names]}
            }
        """
        backup = {
            'schema': None,
            'views': [],
            'reports': [],
            'report_files': {}
        }
        
        # 1. Schema holen (mit Views und Reports wenn möglich)
        try:
            backup['schema'] = self.get_database_schema(team_id, database_id, include_views_reports=True)
        except Exception:
            # Fallback: Nur Struktur ohne Views/Reports
            backup['schema'] = self.get_database_structure(team_id, database_id)
        
        # 2. Views separat holen (für vollständige Daten)
        try:
            backup['views'] = self.get_views(team_id, database_id, full_view=True)
        except Exception as e:
            # Views könnten nicht verfügbar sein
            backup['views'] = []
            backup['views_error'] = str(e)
        
        # 3. Reports holen
        try:
            backup['reports'] = self.get_reports(team_id, database_id, full_report=True)
            
            # 4. Report-Dateien für jeden Report auflisten
            for report in backup['reports']:
                report_id = report.get('id')
                if report_id:
                    try:
                        files = self.get_report_files(team_id, database_id, report_id)
                        if files:
                            backup['report_files'][report_id] = files
                    except Exception:
                        pass  # Report hat keine Dateien
                        
        except Exception as e:
            backup['reports'] = []
            backup['reports_error'] = str(e)
        
        return backup