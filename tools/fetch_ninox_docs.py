#!/usr/bin/env python3
"""
Ninox Dokumentation Scraper

Dieses Script lädt die komplette Ninox-Funktionsreferenz vom Ninox-Forum
und speichert sie als Markdown-Dateien.

Verwendung:
    python fetch_ninox_docs.py [--output-dir OUTPUT_DIR]

Standardmäßig werden die Dateien in ./ninox-docs/ gespeichert.
"""

import argparse
import os
import re
import time
import urllib.request
import urllib.error
from typing import Optional, Dict, List


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


def fetch_page(url: str) -> Optional[str]:
    """Lädt eine Webseite und gibt den Inhalt zurück."""
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
        print(f"  Fehler beim Laden von {url}: {e}")
        return None
    except Exception as e:
        print(f"  Unerwarteter Fehler bei {url}: {e}")
        return None


def extract_content(html: str, function_name: str) -> str:
    """
    Extrahiert den Dokumentationsinhalt aus der HTML-Seite.
    """
    md_parts = []
    
    # Titel extrahieren (topic__title)
    title_match = re.search(r'class="topic__title">([^<]+)</h1>', html)
    title = title_match.group(1).strip() if title_match else function_name
    md_parts.append(f"# {title}\n\n")
    
    # Hauptinhalt aus topic__text formatted extrahieren
    content_match = re.search(
        r'<div class="cfa topic__text formatted">(.*?)</div>\s*<div class="topic__actions',
        html, 
        re.DOTALL
    )
    
    if content_match:
        content = content_match.group(1)
        
        # Script-Tags entfernen
        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
        
        # body-toc entfernen
        content = re.sub(r'<div class=body-toc></div>', '', content)
        
        # HTML zu Markdown konvertieren
        md_content = html_to_markdown(content)
        md_parts.append(md_content)
    
    # Quelle hinzufügen
    md_parts.append(f"\n\n---\n*Quelle: [Ninox Forum]({BASE_URL})*\n")
    
    return "".join(md_parts)


def html_to_markdown(html: str) -> str:
    """Konvertiert HTML zu Markdown."""
    text = html
    
    # Konvertiere Überschriften
    text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', text, flags=re.DOTALL)
    text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', text, flags=re.DOTALL)
    text = re.sub(r'<h4[^>]*>(.*?)</h4>', r'\n#### \1\n', text, flags=re.DOTALL)
    
    # Konvertiere Code-Blöcke (pre)
    def convert_code_block(match):
        code = match.group(1)
        # Entferne innere Tags
        code = re.sub(r'<[^>]+>', '', code)
        # Decode HTML entities
        code = decode_html_entities(code)
        # Ersetze &nbsp; durch normale Leerzeichen
        code = code.replace('\xa0', ' ')
        code = code.replace('&nbsp;', ' ')
        return f"\n```ninox\n{code.strip()}\n```\n"
    
    text = re.sub(r'<pre[^>]*><code[^>]*>(.*?)</code></pre>', convert_code_block, text, flags=re.DOTALL)
    text = re.sub(r'<pre[^>]*>(.*?)</pre>', convert_code_block, text, flags=re.DOTALL)
    
    # Konvertiere inline code
    text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.DOTALL)
    
    # Konvertiere Tabellen
    def convert_table(match):
        table_html = match.group(0)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        
        if not rows:
            return ""
        
        md_rows = []
        for i, row in enumerate(rows):
            # Extrahiere Zellen (th oder td)
            cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            
            if cells:
                md_rows.append("| " + " | ".join(cells) + " |")
                
                # Nach der ersten Zeile (Header) Trennlinie einfügen
                if i == 0:
                    md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
        
        return "\n" + "\n".join(md_rows) + "\n"
    
    text = re.sub(r'<table[^>]*>.*?</table>', convert_table, text, flags=re.DOTALL)
    
    # Konvertiere Blockquotes
    def convert_blockquote(match):
        content = match.group(1)
        # Entferne innere p-Tags aber behalte den Inhalt
        content = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n', content, flags=re.DOTALL)
        content = re.sub(r'<[^>]+>', '', content)
        content = decode_html_entities(content)
        lines = [line.strip() for line in content.strip().split('\n') if line.strip()]
        return "\n" + "\n".join("> " + line for line in lines) + "\n"
    
    text = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', convert_blockquote, text, flags=re.DOTALL)
    
    # Konvertiere Listen
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'\n- \1', text, flags=re.DOTALL)
    text = re.sub(r'</?[uo]l[^>]*>', '\n', text)
    
    # Konvertiere Formatierung
    text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'<u[^>]*>(.*?)</u>', r'\1', text, flags=re.DOTALL)
    
    # Konvertiere Links
    def convert_link(match):
        href = match.group(1)
        link_text = re.sub(r'<[^>]+>', '', match.group(2))
        link_text = decode_html_entities(link_text)
        # Relative Links zu absoluten machen
        if href.startswith('/'):
            href = BASE_URL + href
        # mailto: Links vereinfachen
        if href.startswith('mailto:'):
            return link_text
        return f"[{link_text}]({href})"
    
    text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', convert_link, text, flags=re.DOTALL)
    
    # Konvertiere Absätze
    text = re.sub(r'<p[^>]*>(.*?)</p>', r'\n\1\n', text, flags=re.DOTALL)
    
    # Konvertiere Zeilenumbrüche
    text = re.sub(r'<br\s*/?>', '\n', text)
    
    # Entferne Videos/iframes
    text = re.sub(r'<iframe[^>]*>.*?</iframe>', '', text, flags=re.DOTALL)
    text = re.sub(r'<span[^>]*class="video-inline"[^>]*>.*?</span>', '', text, flags=re.DOTALL)
    
    # Entferne übrige HTML-Tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Decode HTML entities
    text = decode_html_entities(text)
    
    # Bereinige Whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' +\n', '\n', text)
    text = re.sub(r'\n +', '\n', text)
    
    return text.strip()


def decode_html_entities(text: str) -> str:
    """Dekodiert HTML-Entities."""
    entities = {
        '&amp;': '&',
        '&lt;': '<',
        '&gt;': '>',
        '&quot;': '"',
        '&#39;': "'",
        '&apos;': "'",
        '&nbsp;': ' ',
        '&ndash;': '–',
        '&mdash;': '—',
        '&copy;': '©',
        '&reg;': '®',
        '&euro;': '€',
        '&pound;': '£',
        '&yen;': '¥',
        '&cent;': '¢',
        '&deg;': '°',
        '&plusmn;': '±',
        '&times;': '×',
        '&divide;': '÷',
        '&frac12;': '½',
        '&frac14;': '¼',
        '&frac34;': '¾',
        '&hellip;': '…',
        '&laquo;': '«',
        '&raquo;': '»',
        '&lsquo;': ''',
        '&rsquo;': ''',
        '&ldquo;': '"',
        '&rdquo;': '"',
        '&bull;': '•',
        '&middot;': '·',
    }
    
    for entity, char in entities.items():
        text = text.replace(entity, char)
    
    # Numerische Entities
    def replace_numeric_entity(match):
        try:
            code = int(match.group(1))
            return chr(code)
        except (ValueError, OverflowError):
            return match.group(0)
    
    text = re.sub(r'&#(\d+);', replace_numeric_entity, text)
    
    # Hex entities
    def replace_hex_entity(match):
        try:
            code = int(match.group(1), 16)
            return chr(code)
        except (ValueError, OverflowError):
            return match.group(0)
    
    text = re.sub(r'&#x([0-9a-fA-F]+);', replace_hex_entity, text)
    
    return text


def create_index(functions: Dict[str, str], output_dir: str) -> str:
    """Erstellt eine Index-Datei mit allen Funktionen."""
    md_parts = [
        "# Ninox Funktionsreferenz\n\n",
        "Vollständige Dokumentation aller NinoxScript-Funktionen.\n\n",
        "## Funktionen A-Z\n\n",
    ]
    
    # Nach Anfangsbuchstaben gruppieren
    by_letter: Dict[str, List[str]] = {}
    for func_name in sorted(functions.keys(), key=str.lower):
        letter = func_name[0].upper()
        if letter not in by_letter:
            by_letter[letter] = []
        by_letter[letter].append(func_name)
    
    for letter in sorted(by_letter.keys()):
        md_parts.append(f"### {letter}\n\n")
        for func_name in by_letter[letter]:
            md_parts.append(f"- [{func_name}](functions/{func_name}.md)\n")
        md_parts.append("\n")
    
    md_parts.append("\n---\n")
    md_parts.append(f"*{len(functions)} Funktionen dokumentiert*\n")
    md_parts.append("*Quelle: [Ninox Forum](https://forum.ninox.de/category/funktionen)*\n")
    
    return "".join(md_parts)


def main():
    parser = argparse.ArgumentParser(
        description="Lädt die Ninox-Funktionsdokumentation vom Forum"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./ninox-docs",
        help="Ausgabeverzeichnis (Standard: ./ninox-docs)"
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=1.0,
        help="Verzögerung zwischen Requests in Sekunden (Standard: 1.0)"
    )
    parser.add_argument(
        "--single", "-s",
        help="Nur eine einzelne Funktion laden (zum Testen)"
    )
    
    args = parser.parse_args()
    
    # Verzeichnisse erstellen
    output_dir = os.path.abspath(args.output_dir)
    functions_dir = os.path.join(output_dir, "functions")
    os.makedirs(functions_dir, exist_ok=True)
    
    print(f"Ninox Dokumentation wird nach {output_dir} heruntergeladen...")
    print(f"Anzahl Funktionen: {len(NINOX_FUNCTIONS)}")
    print()
    
    # Funktionen zum Laden bestimmen
    if args.single:
        if args.single in NINOX_FUNCTIONS:
            functions_to_fetch = {args.single: NINOX_FUNCTIONS[args.single]}
        else:
            print(f"Funktion '{args.single}' nicht gefunden!")
            return
    else:
        functions_to_fetch = NINOX_FUNCTIONS
    
    success_count = 0
    error_count = 0
    
    for i, (func_name, path) in enumerate(functions_to_fetch.items(), 1):
        url = BASE_URL + path
        print(f"[{i}/{len(functions_to_fetch)}] Lade {func_name}...", end=" ", flush=True)
        
        html_content = fetch_page(url)
        if html_content:
            try:
                markdown = extract_content(html_content, func_name)
                
                # Datei speichern
                file_path = os.path.join(functions_dir, f"{func_name}.md")
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(markdown)
                
                print("OK")
                success_count += 1
            except Exception as e:
                print(f"Parse-Fehler: {e}")
                error_count += 1
        else:
            print("FEHLER")
            error_count += 1
        
        # Pause zwischen Requests
        if i < len(functions_to_fetch):
            time.sleep(args.delay)
    
    # Index erstellen
    print("\nErstelle Index...")
    index_content = create_index(NINOX_FUNCTIONS, output_dir)
    index_path = os.path.join(output_dir, "README.md")
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_content)
    
    print()
    print("=" * 50)
    print(f"Fertig!")
    print(f"  Erfolgreich: {success_count}")
    print(f"  Fehler:      {error_count}")
    print(f"  Ausgabe:     {output_dir}")
    print("=" * 50)


if __name__ == "__main__":
    main()
