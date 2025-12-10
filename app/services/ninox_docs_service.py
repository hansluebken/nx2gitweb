"""
Ninox Documentation Scraper Service

Lädt die komplette Ninox-Funktionsreferenz und API-Dokumentation vom Forum 
und speichert sie als Markdown. Kann auch eine kombinierte Datei erstellen 
und zu GitHub pushen.
"""

import os
import re
import time
import urllib.request
import urllib.error
import asyncio
from typing import Optional, Dict, List, Callable, Any
from datetime import datetime
from dataclasses import dataclass, field


# Ninox API-Dokumentation
NINOX_API_DOCS = {
    "01_Einführung in die Ninox-API": "/t/m1ylnsq/einfuhrung-in-die-ninox-api",
    "02_API-Endpunkte für Public Cloud": "/t/q6ylnsx/api-endpunkte-fur-public-cloud",
    "03_API-Endpunkte für Private Cloud/On-Premises": "/t/35ylns3/api-endpunkte-fur-private-cloudon-premises",
    "04_API-Calls im Ninox-Skript": "/t/y4ylnsy/api-calls-im-ninox-skript",
    "05_Tabellen, Felder und Datensätze": "/t/83ylnsh/tabellen-felder-und-datensatze",
    "06_Integrationen": "/t/q6yxs6j/integrationen",
}

# Ninox Drucken-Dokumentation
NINOX_PRINT_DOCS = {
    "01_Drucken": "/t/83y8p5a/drucken",
    "02_Druckeinstellungen ändern": "/t/q6y8p59/druckeinstellungen-andern",
    "03_Datensatz drucken": "/t/p8y806k/datensatz-drucken",
    "04_Druckoptionen": "/t/y4y80md/druckoptionen",
    "05_Druckansicht anpassen": "/t/35y80zk/druckansicht-anpassen",
    "06_Druckansicht erstellen": "/t/m1y80za/druckansicht-erstellen",
    "07_Druckanpassung": "/t/83yx9k3/druckanpassung",
    "08_Dynamische Drucklayouts - Einführung": "/t/83yldd5/dynamische-drucklayouts-einfuhrung",
    "09_Druckvorlage erstellen": "/t/35ylsgv/druckvorlage-erstellen",
    "10_Druckvorlage hochladen": "/t/q6ylsjt/druckvorlage-hochladen",
    "11_Option A - ohne benutzerdefiniertes Skript": "/t/x2ylsj1/option-a-ohne-ein-benutzerdefiniertes-skript",
    "12_Option B - mit benutzerdefiniertem Skript": "/t/y4ylsjg/option-b-mit-einem-benutzerdefinierten-skript",
    "13_Beispiel - Rechnung als PDF": "/t/35ylsjj/beispiel-rechnung-als-pdf",
    "14_Passwort-Verschlüsselung": "/t/p8ylsj2/passwort-verschlusselung",
    "15_Testdruck mit Wasserzeichen": "/t/g9ylsjb/testdruck-mit-wasserzeichen",
    "16_Bildbeispiel - Word-Dokument": "/t/p8ylw2j/bildbeispiel-word-dokument",
    "17_Bild aus einer Base64": "/t/y4ylw2k/bild-aus-einer-base64",
    "18_Bild aus einer base64-Daten-URI": "/t/60ylsj9/bild-aus-einer-base64-daten-uri",
    "19_Bild von einer öffentlichen URL": "/t/g9ylsj4/bild-von-einer-offentlichen-url",
}

# Alle Ninox-Funktionen mit ihren Forum-URLs
NINOX_FUNCTIONS = {
    "abs": "/t/60yhyhn/abs",
    "acos": "/t/h7yhym0/acos",
    "age": "/t/x2yhx5c/age",
    "alert": "/t/83yhx54/alert",
    "appendTempFile": "/t/q6yhzm4/appendtempfile",
    "appointment": "/t/83yhz5w/appointment",
    "array": "/t/83yhzrt/array",
    "asin": "/t/g9yhfs2/asin",
    "atan": "/t/x2yh1hc/atan",
    "atan2": "/t/h7yh1yz/atan2",
    "avg": "/t/g9yh1yf/avg",
    "barcodeScan": "/t/g9yh181/barcodescan",
    "cached": "/t/g9yh16z/cached",
    "capitalize": "/t/83yhg9p/capitalize",
    "ceil": "/t/q6yhg9j/ceil",
    "chosen": "/t/h7yhg95/chosen",
    "clientLang": "/t/83yhgvr/clientlang",
    "closeAllRecords": "/t/q6yhgvd/closeallrecords",
    "closeFullscreen": "/t/p8yhjhx/closefullscreen",
    "closeRecord": "/t/60yhjh6/closerecord",
    "color": "/t/h7yhjhl/color",
    "concat": "/t/h7yhjh2/concat",
    "contains": "/t/m1yhjhn/contains",
    "cos": "/t/y4yhj3m/cos",
    "count": "/t/35yhjx3/count-aka-cnt",
    "createCalendarEvent": "/t/x2yhjxr/createcalendarevent",
    "createCalendarReminder": "/t/y4yhjx4/createcalendarreminder",
    "createTempFile": "/t/60yhj8y/createtempfile",
    "createTextFile": "/t/g9yhjmh/createtextfile",
    "createXLSX": "/t/60ylw25/createxlsx",
    "createZipFile": "/t/g9yhjml/createzipfile",
    "databaseId": "/t/y4yhjmg/databaseid",
    "date": "/t/m1yhjmb/date",
    "datetime": "/t/83yhjmv/datetime",
    "day": "/t/q6yhjtf/day",
    "days": "/t/83yhjf4/days",
    "degrees": "/t/83yhjkj/degrees",
    "dialog": "/t/m1yhjkn/dialog",
    "duplicate": "/t/p8yhj1g/duplicate",
    "duration": "/t/m1yhj10/duration",
    "email": "/t/p8yhjph/email",
    "endof": "/t/g9yhjpf/endof",
    "even": "/t/p8yhjp2/even",
    "exp": "/t/83yhj25/exp",
    "extractx": "/t/60yhj2n/extractx",
    "fieldId": "/t/y4yl3kz/fieldid",
    "file": "/t/83yhj20/file",
    "fileMetadata": "/t/35yhj2c/filemetadata",
    "files": "/t/g9yhjbq/files",
    "fileUrl": "/t/m1yfplx/fileurl",
    "first": "/t/35yhjbx/first",
    "floor": "/t/g9yhjbt/floor",
    "format": "/t/y4yhjbk/format",
    "formatJSON": "/t/35yhjbw/formatjson",
    "formatXML": "/t/g9yhjb0/formatxml",
    "get": "/t/m1ylyv0/get",
    "html": "/t/g9yhjd3/html",
    "http": "/t/x2yhjd6/http",
    "icon": "/t/g9yhjdk/icon",
    "importFile": "/t/x2yhjdg/importfile",
    "index": "/t/p8yhjdb/index",
    "invalidate": "/t/y4yhjd0/invalidate",
    "iPad": "/t/x2yhg9v/ipad",
    "isAdminMode": "/t/g9yhjd9/isadminmode",
    "isDatabaseLocked": "/t/m1yhjwq/isdatabaselocked",
    "isDatabaseProtected": "/t/y4yhjw3/isdatabaseprotected",
    "item": "/t/q6yhjnq/item",
    "join": "/t/q6yhjnt/join",
    "last": "/t/x2yhjnp/last",
    "latitude": "/t/p8yhjn2/latitude",
    "length": "/t/m1yhjnw/length",
    "ln": "/t/83yhjn7/ln",
    "loadFileAsBase64": "/t/p8yhjnc/loadfileasbase64",
    "loadFileAsBase64URL": "/t/g9yhf5v/loadfileasbase64url",
    "location": "/t/x2yhfr4/location",
    "log": "/t/35yhf2q/log",
    "longitude": "/t/m1yhg9d/longitude",
    "lower": "/t/y4yhg97/lower",
    "max": "/t/35yhgvy/max",
    "min": "/t/m1yhgvs/min",
    "month": "/t/p8yh5ya/month",
    "monthIndex": "/t/x2yh5yv/monthindex",
    "monthName": "/t/p8yh53x/monthname",
    "ninoxApp": "/t/m1yh53m/ninoxapp",
    "now": "/t/q6yh53f/now",
    "number": "/t/x2yh535/number",
    "numbers": "/t/35yh53b/numbers",
    "odd": "/t/y4yh53a/odd",
    "openFullscreen": "/t/g9yh53v/openfullscreen",
    "openPage": "/t/60yxbs1/openpage",
    "openPrintLayout": "/t/y4yh5xx/openprintlayout",
    "openRecord": "/t/h7yh5xm/openrecord",
    "openTable": "/t/x2yh5xf/opentable",
    "openURL": "/t/m1yh5x2/openurl",
    "parseCSV": "/t/60yl310/parsecsv",
    "parseJSON": "/t/83yh5xd/parsejson",
    "parseXML": "/t/y4yh5xw/parsexml",
    "phone": "/t/q6yh5x7/phone",
    "popupRecord": "/t/y4yhr3f/popuprecord",
    "pow": "/t/p8yhr3g/pow",
    "printAndSaveRecord": "/t/y4yhr3b/printandsaverecord",
    "printRecord": "/t/p8yhr37/printrecord",
    "printTable": "/t/q6yhrxt/printtable",
    "quarter": "/t/h7yhrxz/quarter",
    "queryConnection": "/t/p8yhrxl/queryconnection",
    "radians": "/t/x2yhrxp/radians",
    "random": "/t/y4yhrxg/random",
    "range": "/t/35yhrxj/range",
    "raw": "/t/83yhgdx/raw",
    "record": "/t/y4yhgdp/record",
    "removeFile": "/t/x2yl3p8/removefile",
    "removeItem": "/t/m1yhg45/removeitem",
    "renameFile": "/t/h7yl3ph/renamefile",
    "replace": "/t/x2yhg4a/replace",
    "replacex": "/t/h7yhg9q/replacex",
    "round": "/t/83yhj55/round",
    "rpad": "/t/x2yhj50/rpad",
    "rsort": "/t/g9yhjrq/rsort",
    "sendCommand": "/t/h7yhjrm/sendcommand",
    "sendEmail": "/t/q6yhjrg/sendemail",
    "set": "/t/p8yly9c/set",
    "setItem": "/t/x2yhjrd/setitem",
    "shareFile": "/t/60yh5gq/sharefile",
    "shareView": "/t/g9yh5gt/shareview",
    "sign": "/t/x2yh5gb/sign",
    "sin": "/t/x2yh5g4/sin",
    "sleep": "/t/83yh5j6/sleep",
    "slice": "/t/60yh5j1/slice",
    "sort": "/t/35yh5j5/sort",
    "split": "/t/h7yh558/split",
    "splitx": "/t/m1yh55z/splitx",
    "sqr": "/t/60yh555/sqr",
    "sqrt": "/t/y4yh55d/sqrt",
    "start": "/t/q6yh5rq/start",
    "string": "/t/83yh5r6/string",
    "styled": "/t/m1yh5r1/styled",
    "substr": "/t/x2yh52q/substr",
    "substring": "/t/g9yh52m/substring",
    "sum": "/t/p8yhrjw/sum",
    "tableId": "/t/q6yhrj9/tableid",
    "tan": "/t/h7yhr5t/tan",
    "teamId": "/t/x2yhr5k/teamid",
    "testx": "/t/x2yhr5d/testx",
    "text": "/t/35yhrrh/text",
    "time": "/t/m1yhrrj/time",
    "timeinterval": "/t/x2yh1tl/timeinterval",
    "timestamp": "/t/83yh1t4/timestamp",
    "today": "/t/60yh1z1/today",
    "trim": "/t/q6yh1z0/trim",
    "unique": "/t/60yh1z9/unique",
    "unshareAllViews": "/t/y4yh1ly/unshareallviews",
    "unshareFile": "/t/83yh1ll/unsharefile",
    "unshareView": "/t/p8yh1f2/unshareview",
    "upper": "/t/m1yh1kt/upper",
    "url": "/t/g9yh1kg/url",
    "urlDecode": "/t/x2yh1ka/urldecode",
    "urlEncode": "/t/60yh11h/urlencode",
    "urlOf": "/t/h7yh11m/urlof",
    "user": "/t/q6yh11j/user",
    "userEmail": "/t/83yhjx2/useremail",
    "userFirstName": "/t/83yhjxc/userfirstname",
    "userFullName": "/t/h7yhj8q/userfullname",
    "userHasRole": "/t/35yhj8m/userhasrole",
    "userId": "/t/p8yhj8l/userid",
    "userIsAdmin": "/t/x2yhj81/userisadmin",
    "userLastName": "/t/35yhj8j/userlastname",
    "userName": "/t/35yhj8s/username",
    "userRole": "/t/h7yhj8a/userrole",
    "userRoles": "/t/35yhj6b/userroles",
    "users": "/t/p8yhj6n/users",
    "validateXML": "/t/g9yl31s/validatexml",
    "waitForSync": "/t/g9yhj67/waitforsync",
    "week": "/t/h7yhj6v/week",
    "weekday": "/t/83yhjm8/weekday",
    "weekdayIndex": "/t/60yhjmf/weekdayindex",
    "weekdayName": "/t/x2yhjm1/weekdayname",
    "workdays": "/t/35yhjmj/workdays",
    "year": "/t/60yhjm2/year",
    "yearmonth": "/t/g9yhjma/yearmonth",
    "yearquarter": "/t/h7yhjt3/yearquarter",
    "yearweek": "/t/83yhjtt/yearweek",
}

BASE_URL = "https://forum.ninox.de"


@dataclass
class ScrapeResult:
    """Result of a scraping operation"""
    success: bool
    total_functions: int = 0
    successful: int = 0
    failed: int = 0
    error_message: Optional[str] = None
    combined_file_path: Optional[str] = None
    github_url: Optional[str] = None


@dataclass
class ScrapeProgress:
    """Progress information during scraping"""
    current: int = 0
    total: int = 0
    current_function: str = ""
    status: str = "pending"  # pending, running, completed, failed
    errors: List[str] = field(default_factory=list)


class NinoxDocsService:
    """Service for scraping and managing Ninox documentation"""
    
    def __init__(self):
        self.base_url = BASE_URL
        self.functions = NINOX_FUNCTIONS
        self.api_docs = NINOX_API_DOCS
        self.print_docs = NINOX_PRINT_DOCS
        self.progress = ScrapeProgress()
    
    def get_function_count(self) -> int:
        """Returns the total number of documented functions"""
        return len(self.functions)
    
    def get_api_doc_count(self) -> int:
        """Returns the total number of API documentation pages"""
        return len(self.api_docs)
    
    def get_print_doc_count(self) -> int:
        """Returns the total number of Print documentation pages"""
        return len(self.print_docs)
    
    def get_total_doc_count(self) -> int:
        """Returns total number of all documentation items"""
        return len(self.functions) + len(self.api_docs) + len(self.print_docs)
    
    def _fetch_page(self, url: str) -> Optional[str]:
        """Fetches a web page and returns its content"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read().decode('utf-8')
        except urllib.error.URLError as e:
            return None
        except Exception as e:
            return None

    def _extract_content(self, html: str, function_name: str) -> str:
        """Extracts documentation content from HTML page"""
        md_parts = []
        
        # Extract title
        title_match = re.search(r'class="topic__title">([^<]+)</h1>', html)
        title = title_match.group(1).strip() if title_match else function_name
        md_parts.append(f"# {title}\n\n")
        
        # Extract main content
        content_match = re.search(
            r'<div class="cfa topic__text formatted">(.*?)</div>\s*(?:<ul class="topic-tags"|<div class="topic__actions)',
            html, 
            re.DOTALL
        )
        
        if content_match:
            content = content_match.group(1)
            content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
            content = re.sub(r'<div class=body-toc></div>', '', content)
            md_content = self._html_to_markdown(content)
            md_parts.append(md_content)
        
        return "".join(md_parts)

    def _html_to_markdown(self, html: str) -> str:
        """Converts HTML to Markdown"""
        text = html
        
        # Convert headings
        text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', text, flags=re.DOTALL)
        text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', text, flags=re.DOTALL)
        text = re.sub(r'<h4[^>]*>(.*?)</h4>', r'\n#### \1\n', text, flags=re.DOTALL)
        
        # Convert code blocks
        def convert_code_block(match):
            code = match.group(1)
            code = re.sub(r'<[^>]+>', '', code)
            code = self._decode_html_entities(code)
            code = code.replace('\xa0', ' ')
            code = code.replace('&nbsp;', ' ')
            return f"\n```ninox\n{code.strip()}\n```\n"
        
        text = re.sub(r'<pre[^>]*><code[^>]*>(.*?)</code></pre>', convert_code_block, text, flags=re.DOTALL)
        text = re.sub(r'<pre[^>]*>(.*?)</pre>', convert_code_block, text, flags=re.DOTALL)
        
        # Convert inline code
        text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.DOTALL)
        
        # Convert tables
        def convert_table(match):
            table_html = match.group(0)
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
            
            if not rows:
                return ""
            
            md_rows = []
            for i, row in enumerate(rows):
                cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)
                cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                
                if cells:
                    md_rows.append("| " + " | ".join(cells) + " |")
                    if i == 0:
                        md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
            
            return "\n" + "\n".join(md_rows) + "\n"
        
        text = re.sub(r'<table[^>]*>.*?</table>', convert_table, text, flags=re.DOTALL)
        
        # Convert blockquotes
        def convert_blockquote(match):
            content = match.group(1)
            content = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n', content, flags=re.DOTALL)
            content = re.sub(r'<[^>]+>', '', content)
            content = self._decode_html_entities(content)
            lines = [line.strip() for line in content.strip().split('\n') if line.strip()]
            return "\n" + "\n".join("> " + line for line in lines) + "\n"
        
        text = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', convert_blockquote, text, flags=re.DOTALL)
        
        # Convert lists
        text = re.sub(r'<li[^>]*>(.*?)</li>', r'\n- \1', text, flags=re.DOTALL)
        text = re.sub(r'</?[uo]l[^>]*>', '\n', text)
        
        # Convert formatting
        text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', text, flags=re.DOTALL)
        text = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', text, flags=re.DOTALL)
        text = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', text, flags=re.DOTALL)
        text = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', text, flags=re.DOTALL)
        
        # Convert links
        def convert_link(match):
            href = match.group(1)
            link_text = re.sub(r'<[^>]+>', '', match.group(2))
            link_text = self._decode_html_entities(link_text)
            if href.startswith('/'):
                href = BASE_URL + href
            if href.startswith('mailto:'):
                return link_text
            return f"[{link_text}]({href})"
        
        text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', convert_link, text, flags=re.DOTALL)
        
        # Convert paragraphs
        text = re.sub(r'<p[^>]*>(.*?)</p>', r'\n\1\n', text, flags=re.DOTALL)
        text = re.sub(r'<br\s*/?>', '\n', text)
        
        # Remove videos/iframes
        text = re.sub(r'<iframe[^>]*>.*?</iframe>', '', text, flags=re.DOTALL)
        text = re.sub(r'<span[^>]*class="video-inline"[^>]*>.*?</span>', '', text, flags=re.DOTALL)
        
        # Remove remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Decode entities
        text = self._decode_html_entities(text)
        
        # Clean whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r' +\n', '\n', text)
        text = re.sub(r'\n +', '\n', text)
        
        return text.strip()

    def _decode_html_entities(self, text: str) -> str:
        """Decodes HTML entities"""
        entities = {
            '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"',
            '&#39;': "'", '&apos;': "'", '&nbsp;': ' ', '&ndash;': '–',
            '&mdash;': '—', '&copy;': '©', '&reg;': '®', '&euro;': '€',
            '&pound;': '£', '&yen;': '¥', '&cent;': '¢', '&deg;': '°',
            '&plusmn;': '±', '&times;': '×', '&divide;': '÷',
            '&frac12;': '½', '&frac14;': '¼', '&frac34;': '¾',
            '&hellip;': '…', '&laquo;': '«', '&raquo;': '»',
            '&lsquo;': ''', '&rsquo;': ''', '&ldquo;': '"', '&rdquo;': '"',
            '&bull;': '•', '&middot;': '·',
        }
        
        for entity, char in entities.items():
            text = text.replace(entity, char)
        
        # Numeric entities
        def replace_numeric_entity(match):
            try:
                return chr(int(match.group(1)))
            except (ValueError, OverflowError):
                return match.group(0)
        
        text = re.sub(r'&#(\d+);', replace_numeric_entity, text)
        
        # Hex entities
        def replace_hex_entity(match):
            try:
                return chr(int(match.group(1), 16))
            except (ValueError, OverflowError):
                return match.group(0)
        
        text = re.sub(r'&#x([0-9a-fA-F]+);', replace_hex_entity, text)
        
        return text

    def scrape_all_functions(
        self, 
        progress_callback: Optional[Callable[[ScrapeProgress], None]] = None,
        delay: float = 1.0
    ) -> Dict[str, str]:
        """
        Scrapes all Ninox functions from the forum
        
        Args:
            progress_callback: Optional callback for progress updates
            delay: Delay between requests in seconds
            
        Returns:
            Dictionary mapping function names to their markdown content
        """
        self.progress = ScrapeProgress(
            total=len(self.functions),
            status="running"
        )
        
        results = {}
        
        for i, (func_name, path) in enumerate(self.functions.items(), 1):
            self.progress.current = i
            self.progress.current_function = func_name
            
            if progress_callback:
                progress_callback(self.progress)
            
            url = self.base_url + path
            html_content = self._fetch_page(url)
            
            if html_content:
                try:
                    markdown = self._extract_content(html_content, func_name)
                    results[func_name] = markdown
                except Exception as e:
                    self.progress.errors.append(f"{func_name}: {str(e)}")
            else:
                self.progress.errors.append(f"{func_name}: Konnte nicht geladen werden")
            
            if i < len(self.functions):
                time.sleep(delay)
        
        self.progress.status = "completed"
        if progress_callback:
            progress_callback(self.progress)
        
        return results

    def scrape_api_docs(
        self, 
        progress_callback: Optional[Callable[[ScrapeProgress], None]] = None,
        delay: float = 1.0
    ) -> Dict[str, str]:
        """
        Scrapes all Ninox API documentation pages from the forum
        
        Args:
            progress_callback: Optional callback for progress updates
            delay: Delay between requests in seconds
            
        Returns:
            Dictionary mapping doc names to their markdown content
        """
        self.progress = ScrapeProgress(
            total=len(self.api_docs),
            status="running"
        )
        
        results = {}
        
        for i, (doc_name, path) in enumerate(self.api_docs.items(), 1):
            # Remove sorting prefix for display
            display_name = doc_name.split('_', 1)[1] if '_' in doc_name else doc_name
            
            self.progress.current = i
            self.progress.current_function = display_name
            
            if progress_callback:
                progress_callback(self.progress)
            
            url = self.base_url + path
            html_content = self._fetch_page(url)
            
            if html_content:
                try:
                    markdown = self._extract_content(html_content, display_name)
                    results[doc_name] = markdown
                except Exception as e:
                    self.progress.errors.append(f"{display_name}: {str(e)}")
            else:
                self.progress.errors.append(f"{display_name}: Konnte nicht geladen werden")
            
            if i < len(self.api_docs):
                time.sleep(delay)
        
        self.progress.status = "completed"
        if progress_callback:
            progress_callback(self.progress)
        
        return results

    def scrape_print_docs(
        self, 
        progress_callback: Optional[Callable[[ScrapeProgress], None]] = None,
        delay: float = 1.0
    ) -> Dict[str, str]:
        """
        Scrapes all Ninox Print documentation pages from the forum
        
        Args:
            progress_callback: Optional callback for progress updates
            delay: Delay between requests in seconds
            
        Returns:
            Dictionary mapping doc names to their markdown content
        """
        self.progress = ScrapeProgress(
            total=len(self.print_docs),
            status="running"
        )
        
        results = {}
        
        for i, (doc_name, path) in enumerate(self.print_docs.items(), 1):
            # Remove sorting prefix for display
            display_name = doc_name.split('_', 1)[1] if '_' in doc_name else doc_name
            
            self.progress.current = i
            self.progress.current_function = display_name
            
            if progress_callback:
                progress_callback(self.progress)
            
            url = self.base_url + path
            html_content = self._fetch_page(url)
            
            if html_content:
                try:
                    markdown = self._extract_content(html_content, display_name)
                    results[doc_name] = markdown
                except Exception as e:
                    self.progress.errors.append(f"{display_name}: {str(e)}")
            else:
                self.progress.errors.append(f"{display_name}: Konnte nicht geladen werden")
            
            if i < len(self.print_docs):
                time.sleep(delay)
        
        self.progress.status = "completed"
        if progress_callback:
            progress_callback(self.progress)
        
        return results

    def scrape_all_documentation(
        self, 
        progress_callback: Optional[Callable[[ScrapeProgress], None]] = None,
        delay: float = 0.5
    ) -> Dict[str, Dict[str, str]]:
        """
        Scrapes ALL Ninox documentation (functions + API docs + Print docs)
        
        Args:
            progress_callback: Optional callback for progress updates
            delay: Delay between requests in seconds
            
        Returns:
            Dictionary with 'functions', 'api', and 'print' keys containing the scraped docs
        """
        total_items = len(self.functions) + len(self.api_docs) + len(self.print_docs)
        self.progress = ScrapeProgress(
            total=total_items,
            status="running"
        )
        
        results = {
            'functions': {},
            'api': {},
            'print': {}
        }
        
        current_item = 0
        
        # Scrape API docs first (smaller set)
        for doc_name, path in self.api_docs.items():
            current_item += 1
            display_name = doc_name.split('_', 1)[1] if '_' in doc_name else doc_name
            
            self.progress.current = current_item
            self.progress.current_function = f"API: {display_name}"
            
            if progress_callback:
                progress_callback(self.progress)
            
            url = self.base_url + path
            html_content = self._fetch_page(url)
            
            if html_content:
                try:
                    markdown = self._extract_content(html_content, display_name)
                    results['api'][doc_name] = markdown
                except Exception as e:
                    self.progress.errors.append(f"API/{display_name}: {str(e)}")
            else:
                self.progress.errors.append(f"API/{display_name}: Konnte nicht geladen werden")
            
            time.sleep(delay)
        
        # Scrape Print docs
        for doc_name, path in self.print_docs.items():
            current_item += 1
            display_name = doc_name.split('_', 1)[1] if '_' in doc_name else doc_name
            
            self.progress.current = current_item
            self.progress.current_function = f"Print: {display_name}"
            
            if progress_callback:
                progress_callback(self.progress)
            
            url = self.base_url + path
            html_content = self._fetch_page(url)
            
            if html_content:
                try:
                    markdown = self._extract_content(html_content, display_name)
                    results['print'][doc_name] = markdown
                except Exception as e:
                    self.progress.errors.append(f"Print/{display_name}: {str(e)}")
            else:
                self.progress.errors.append(f"Print/{display_name}: Konnte nicht geladen werden")
            
            time.sleep(delay)
        
        # Scrape functions
        for func_name, path in self.functions.items():
            current_item += 1
            self.progress.current = current_item
            self.progress.current_function = func_name
            
            if progress_callback:
                progress_callback(self.progress)
            
            url = self.base_url + path
            html_content = self._fetch_page(url)
            
            if html_content:
                try:
                    markdown = self._extract_content(html_content, func_name)
                    results['functions'][func_name] = markdown
                except Exception as e:
                    self.progress.errors.append(f"{func_name}: {str(e)}")
            else:
                self.progress.errors.append(f"{func_name}: Konnte nicht geladen werden")
            
            if current_item < total_items:
                time.sleep(delay)
        
        self.progress.status = "completed"
        if progress_callback:
            progress_callback(self.progress)
        
        return results

    def create_functions_markdown(self, function_docs: Dict[str, str]) -> str:
        """
        Creates a markdown file for NinoxScript functions only
        
        Args:
            function_docs: Dictionary mapping function names to markdown content
            
        Returns:
            Markdown string for functions
        """
        parts = [
            "# NinoxScript Funktionsreferenz\n\n",
            f"*Vollständige Dokumentation: {len(function_docs)} NinoxScript-Funktionen*\n\n",
            f"*Generiert am: {datetime.now().strftime('%d.%m.%Y %H:%M')}*\n\n",
            "---\n\n",
            "## Inhaltsverzeichnis\n\n",
        ]
        
        # Create table of contents grouped by letter
        by_letter: Dict[str, List[str]] = {}
        for func_name in sorted(function_docs.keys(), key=str.lower):
            letter = func_name[0].upper()
            if letter not in by_letter:
                by_letter[letter] = []
            by_letter[letter].append(func_name)
        
        for letter in sorted(by_letter.keys()):
            parts.append(f"**{letter}**: ")
            links = [f"[{fn}](#{fn.lower()})" for fn in by_letter[letter]]
            parts.append(" | ".join(links))
            parts.append("\n\n")
        
        parts.append("\n---\n\n")
        
        # Add all function documentation
        for func_name in sorted(function_docs.keys(), key=str.lower):
            content = function_docs[func_name]
            parts.append(f'<a name="{func_name.lower()}"></a>\n\n')
            parts.append(content)
            parts.append("\n\n---\n\n")
        
        parts.append(f"\n*Quelle: [Ninox Forum]({BASE_URL})*\n")
        
        return "".join(parts)

    def create_api_markdown(self, api_docs: Dict[str, str]) -> str:
        """
        Creates a markdown file for Ninox REST API documentation only
        
        Args:
            api_docs: Dictionary mapping API doc names to markdown content
            
        Returns:
            Markdown string for API docs
        """
        parts = [
            "# Ninox REST API Dokumentation\n\n",
            f"*Vollständige API-Dokumentation: {len(api_docs)} Artikel*\n\n",
            f"*Generiert am: {datetime.now().strftime('%d.%m.%Y %H:%M')}*\n\n",
            "---\n\n",
            "## Inhaltsverzeichnis\n\n",
        ]
        
        for doc_name in sorted(api_docs.keys()):
            display_name = doc_name.split('_', 1)[1] if '_' in doc_name else doc_name
            anchor = display_name.lower().replace(' ', '-').replace('/', '-')
            parts.append(f"- [{display_name}](#{anchor})\n")
        
        parts.append("\n---\n\n")
        
        # Add API documentation
        for doc_name in sorted(api_docs.keys()):
            display_name = doc_name.split('_', 1)[1] if '_' in doc_name else doc_name
            anchor = display_name.lower().replace(' ', '-').replace('/', '-')
            content = api_docs[doc_name]
            parts.append(f'<a name="{anchor}"></a>\n\n')
            parts.append(content)
            parts.append("\n\n---\n\n")
        
        parts.append(f"\n*Quelle: [Ninox Forum]({BASE_URL})*\n")
        
        return "".join(parts)

    def create_print_markdown(self, print_docs: Dict[str, str]) -> str:
        """
        Creates a markdown file for Ninox Print/Drucken documentation only
        
        Args:
            print_docs: Dictionary mapping print doc names to markdown content
            
        Returns:
            Markdown string for print docs
        """
        parts = [
            "# Ninox Drucken Dokumentation\n\n",
            f"*Vollständige Drucken-Dokumentation: {len(print_docs)} Artikel*\n\n",
            f"*Generiert am: {datetime.now().strftime('%d.%m.%Y %H:%M')}*\n\n",
            "---\n\n",
            "## Inhaltsverzeichnis\n\n",
        ]
        
        for doc_name in sorted(print_docs.keys()):
            display_name = doc_name.split('_', 1)[1] if '_' in doc_name else doc_name
            anchor = display_name.lower().replace(' ', '-').replace('/', '-')
            parts.append(f"- [{display_name}](#{anchor})\n")
        
        parts.append("\n---\n\n")
        
        # Add Print documentation
        for doc_name in sorted(print_docs.keys()):
            display_name = doc_name.split('_', 1)[1] if '_' in doc_name else doc_name
            anchor = display_name.lower().replace(' ', '-').replace('/', '-')
            content = print_docs[doc_name]
            parts.append(f'<a name="{anchor}"></a>\n\n')
            parts.append(content)
            parts.append("\n\n---\n\n")
        
        parts.append(f"\n*Quelle: [Ninox Forum]({BASE_URL})*\n")
        
        return "".join(parts)

    def create_combined_markdown(self, function_docs: Dict[str, str], api_docs: Optional[Dict[str, str]] = None) -> str:
        """
        Creates a single combined markdown file from all documentation (legacy method)
        
        Args:
            function_docs: Dictionary mapping function names to markdown content
            api_docs: Optional dictionary mapping API doc names to markdown content
            
        Returns:
            Combined markdown string
        """
        total_docs = len(function_docs) + (len(api_docs) if api_docs else 0)
        
        parts = [
            "# Ninox Dokumentation\n\n",
            f"*Vollständige Dokumentation: {len(function_docs)} NinoxScript-Funktionen",
        ]
        
        if api_docs:
            parts.append(f" + {len(api_docs)} API-Artikel")
        
        parts.append(f"*\n\n*Generiert am: {datetime.now().strftime('%d.%m.%Y %H:%M')}*\n\n")
        parts.append("---\n\n")
        
        # API Documentation section (if provided)
        if api_docs:
            parts.append("# Teil 1: Ninox REST API\n\n")
            parts.append("## API Inhaltsverzeichnis\n\n")
            
            for doc_name in sorted(api_docs.keys()):
                display_name = doc_name.split('_', 1)[1] if '_' in doc_name else doc_name
                anchor = display_name.lower().replace(' ', '-').replace('/', '-')
                parts.append(f"- [{display_name}](#{anchor})\n")
            
            parts.append("\n---\n\n")
            
            # Add API documentation
            for doc_name in sorted(api_docs.keys()):
                display_name = doc_name.split('_', 1)[1] if '_' in doc_name else doc_name
                anchor = display_name.lower().replace(' ', '-').replace('/', '-')
                content = api_docs[doc_name]
                parts.append(f'<a name="{anchor}"></a>\n\n')
                parts.append(content)
                parts.append("\n\n---\n\n")
            
            parts.append("\n\n")
            parts.append("# Teil 2: NinoxScript Funktionen\n\n")
        
        parts.append("## Funktionen Inhaltsverzeichnis\n\n")
        
        # Create table of contents grouped by letter
        by_letter: Dict[str, List[str]] = {}
        for func_name in sorted(function_docs.keys(), key=str.lower):
            letter = func_name[0].upper()
            if letter not in by_letter:
                by_letter[letter] = []
            by_letter[letter].append(func_name)
        
        for letter in sorted(by_letter.keys()):
            parts.append(f"**{letter}**: ")
            links = [f"[{fn}](#{fn.lower()})" for fn in by_letter[letter]]
            parts.append(" | ".join(links))
            parts.append("\n\n")
        
        parts.append("\n---\n\n")
        
        # Add all function documentation
        for func_name in sorted(function_docs.keys(), key=str.lower):
            content = function_docs[func_name]
            # Add anchor for linking
            parts.append(f'<a name="{func_name.lower()}"></a>\n\n')
            parts.append(content)
            parts.append("\n\n---\n\n")
        
        # Footer
        parts.append(f"\n*Quelle: [Ninox Forum]({BASE_URL})*\n")
        
        return "".join(parts)

    def upload_to_github(
        self, 
        combined_markdown: str,
        github_token: str,
        organization: Optional[str] = None,
        repo_name: str = "ninox-docs"
    ) -> Dict[str, Any]:
        """
        Uploads the combined markdown to a GitHub repository (legacy method)
        
        Args:
            combined_markdown: The combined markdown content
            github_token: GitHub access token
            organization: GitHub organization (optional)
            repo_name: Name of the repository
            
        Returns:
            Dict with success status and URL
        """
        try:
            from ..api.github_manager import GitHubManager
            
            manager = GitHubManager(github_token, organization)
            
            # Ensure repository exists
            repo = manager.ensure_repository(
                repo_name,
                description="NinoxScript Funktionsreferenz - Automatisch generierte Dokumentation"
            )
            
            # Upload the combined file
            commit_message = f"Update Ninox Dokumentation ({datetime.now().strftime('%d.%m.%Y %H:%M')})"
            manager.update_file(
                repo,
                "NINOX_FUNKTIONEN.md",
                combined_markdown,
                commit_message
            )
            
            # Create/update README
            readme_content = f"""# Ninox Dokumentation

Dieses Repository enthält die automatisch generierte Dokumentation aller NinoxScript-Funktionen.

## Dateien

- **[NINOX_FUNKTIONEN.md](NINOX_FUNKTIONEN.md)** - Komplette Funktionsreferenz ({len(NINOX_FUNCTIONS)} Funktionen)

## Verwendung mit Claude AI

Diese Dokumentation kann über die GitHub-Integration in Claude Projects eingebunden werden.
Claude kann dann alle NinoxScript-Funktionen nachschlagen und korrekten Ninox-Code generieren.

## Aktualisierung

Die Dokumentation kann jederzeit über das Admin-Panel von Ninox2Git neu generiert werden.

---

*Automatisch generiert von Ninox2Git*
*Letzte Aktualisierung: {datetime.now().strftime('%d.%m.%Y %H:%M')}*
"""
            
            manager.update_file(
                repo,
                "README.md",
                readme_content,
                "Update README"
            )
            
            return {
                "success": True,
                "url": repo.html_url,
                "file_url": f"{repo.html_url}/blob/main/NINOX_FUNKTIONEN.md"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def upload_separate_files_to_github(
        self, 
        functions_markdown: str,
        api_markdown: str,
        print_markdown: str,
        github_token: str,
        organization: Optional[str] = None,
        repo_name: str = "ninox-docs"
    ) -> Dict[str, Any]:
        """
        Uploads three separate markdown files (functions + API + Print) to a GitHub repository
        
        Args:
            functions_markdown: The functions markdown content
            api_markdown: The API documentation markdown content
            print_markdown: The Print documentation markdown content
            github_token: GitHub access token
            organization: GitHub organization (optional)
            repo_name: Name of the repository
            
        Returns:
            Dict with success status and URLs
        """
        try:
            from ..api.github_manager import GitHubManager
            
            manager = GitHubManager(github_token, organization)
            
            # Ensure repository exists
            repo = manager.ensure_repository(
                repo_name,
                description="Ninox Dokumentation - NinoxScript Funktionen, REST API & Drucken"
            )
            
            timestamp = datetime.now().strftime('%d.%m.%Y %H:%M')
            
            # Upload functions file
            manager.update_file(
                repo,
                "NINOX_FUNKTIONEN.md",
                functions_markdown,
                f"Update NinoxScript Funktionen ({timestamp})"
            )
            
            # Upload API file
            manager.update_file(
                repo,
                "NINOX_API.md",
                api_markdown,
                f"Update Ninox REST API ({timestamp})"
            )
            
            # Upload Print file
            manager.update_file(
                repo,
                "NINOX_DRUCKEN.md",
                print_markdown,
                f"Update Ninox Drucken ({timestamp})"
            )
            
            # Create/update README
            readme_content = f"""# Ninox Dokumentation

Dieses Repository enthält die automatisch generierte Dokumentation für Ninox.

## Dateien

- **[NINOX_FUNKTIONEN.md](NINOX_FUNKTIONEN.md)** - NinoxScript Funktionsreferenz ({len(NINOX_FUNCTIONS)} Funktionen)
- **[NINOX_API.md](NINOX_API.md)** - REST API Dokumentation ({len(NINOX_API_DOCS)} Artikel)
- **[NINOX_DRUCKEN.md](NINOX_DRUCKEN.md)** - Drucken & PDF-Export ({len(NINOX_PRINT_DOCS)} Artikel)

## Verwendung mit Claude AI

Diese Dokumentation kann über die GitHub-Integration in Claude Projects eingebunden werden.
Claude kann dann alle NinoxScript-Funktionen, API-Endpunkte und Druckfunktionen nachschlagen und korrekten Code generieren.

### Empfohlener System-Prompt:

```
Du bist ein Ninox-Experte und hilfst beim Schreiben von NinoxScript-Code und API-Integrationen.
Verwende die Ninox-Dokumentation aus dem Project Knowledge, um korrekten Code zu generieren.
- NINOX_FUNKTIONEN.md für NinoxScript-Funktionen
- NINOX_API.md für REST API und HTTP-Aufrufe
- NINOX_DRUCKEN.md für Drucklayouts und PDF-Export
Antworte auf Deutsch und erkläre den Code.
```

## Aktualisierung

Die Dokumentation kann jederzeit über das Admin-Panel von Ninox2Git neu generiert werden.

---

*Automatisch generiert von Ninox2Git*
*Letzte Aktualisierung: {timestamp}*
"""
            
            manager.update_file(
                repo,
                "README.md",
                readme_content,
                "Update README"
            )
            
            return {
                "success": True,
                "url": repo.html_url,
                "functions_url": f"{repo.html_url}/blob/main/NINOX_FUNKTIONEN.md",
                "api_url": f"{repo.html_url}/blob/main/NINOX_API.md",
                "print_url": f"{repo.html_url}/blob/main/NINOX_DRUCKEN.md"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# Singleton instance
_service_instance: Optional[NinoxDocsService] = None


def get_ninox_docs_service() -> NinoxDocsService:
    """Returns the singleton instance of NinoxDocsService"""
    global _service_instance
    if _service_instance is None:
        _service_instance = NinoxDocsService()
    return _service_instance
