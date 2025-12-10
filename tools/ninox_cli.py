#!/usr/bin/env python3
"""
Ninox CLI Tool for Ninox2Git
Command-line interface for syncing Ninox databases.

This script can be called from:
- Terminal
- OpenCode / Claude Code
- Cron jobs
- Other automation tools

Usage:
    python tools/ninox_cli.py list-servers
    python tools/ninox_cli.py list-databases
    python tools/ninox_cli.py sync-all --server-id 1
    python tools/ninox_cli.py sync --server-id 1 --database-id abc123
    python tools/ninox_cli.py search "function_name"
"""
import sys
import os
import json
import argparse
import asyncio
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'app'))

from services.ninox_sync_service import (
    cli_sync_database,
    cli_sync_all,
    cli_list_servers,
    cli_list_local_databases,
    get_ninox_sync_service
)
from utils.ninox_yaml_parser import (
    NinoxYAMLParser,
    search_code_locations,
    filter_code_locations,
    CodeCategory,
    CodeLevel
)
from services.ninox_cli_service import get_ninox_cli_service


def cmd_list_servers(args):
    """List available servers"""
    servers = cli_list_servers()
    
    if args.json:
        print(json.dumps(servers, indent=2))
    else:
        if not servers:
            print("No servers configured.")
            return 1
        
        print(f"\n{'ID':<5} {'Name':<30} {'URL':<40}")
        print("-" * 75)
        for s in servers:
            print(f"{s['id']:<5} {s['name']:<30} {s['url']:<40}")
        print(f"\nTotal: {len(servers)} server(s)")
    
    return 0


def cmd_list_databases(args):
    """List locally downloaded databases"""
    databases = cli_list_local_databases()
    
    if args.json:
        print(json.dumps(databases, indent=2))
    else:
        if not databases:
            print("No databases downloaded yet.")
            print("Use 'sync-all --server-id <ID>' to download databases.")
            return 1
        
        print(f"\n{'ID':<20} {'Name':<30} {'Tables':<8} {'Global':<8} {'Downloaded':<20}")
        print("-" * 90)
        for db in databases:
            global_code = "Yes" if db['has_global_code'] else "No"
            date = db['download_date'][:19]  # Truncate ISO timestamp
            print(f"{db['id']:<20} {db['name'][:28]:<30} {db['table_count']:<8} {global_code:<8} {date:<20}")
        print(f"\nTotal: {len(databases)} database(s)")
    
    return 0


def cmd_sync_all(args):
    """Sync all databases from a server"""
    server_id = args.server_id
    
    print(f"Syncing all databases from server {server_id}...")
    
    results = cli_sync_all(server_id)
    
    if not results:
        print("No databases synced. Check server configuration.")
        return 1
    
    success = sum(1 for v in results.values() if v)
    failed = len(results) - success
    
    if args.json:
        print(json.dumps({
            'server_id': server_id,
            'total': len(results),
            'success': success,
            'failed': failed,
            'results': results
        }, indent=2))
    else:
        print(f"\nSync completed:")
        print(f"  Total: {len(results)}")
        print(f"  Success: {success}")
        print(f"  Failed: {failed}")
        
        if failed > 0:
            print(f"\nFailed databases:")
            for db_id, ok in results.items():
                if not ok:
                    print(f"  - {db_id}")
    
    return 0 if failed == 0 else 1


def cmd_sync(args):
    """Sync a single database"""
    server_id = args.server_id
    database_id = args.database_id
    
    print(f"Syncing database {database_id} from server {server_id}...")
    
    success = cli_sync_database(server_id, database_id)
    
    if args.json:
        print(json.dumps({
            'server_id': server_id,
            'database_id': database_id,
            'success': success
        }, indent=2))
    else:
        if success:
            print("Sync successful!")
        else:
            print("Sync failed!")
    
    return 0 if success else 1


def cmd_search(args):
    """Search for code across all databases"""
    query = args.query
    
    # Load all databases
    cli_service = get_ninox_cli_service()
    parser = NinoxYAMLParser(str(cli_service.project_path))
    databases = parser.get_all_databases()
    
    if not databases:
        print("No databases downloaded yet.")
        return 1
    
    # Search across all databases
    results = []
    for db in databases:
        matches = search_code_locations(db.code_locations, query)
        for loc in matches:
            results.append({
                'database': db.name,
                'path': loc.path,
                'type': loc.code_type,
                'category': loc.category_name,
                'lines': loc.line_count,
                'preview': loc.code[:100].replace('\n', ' ') + ('...' if len(loc.code) > 100 else '')
            })
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        if not results:
            print(f"No results found for '{query}'")
            return 0
        
        print(f"\nSearch results for '{query}':")
        print(f"Found {len(results)} match(es)\n")
        
        for i, r in enumerate(results[:50], 1):  # Limit to 50 results
            print(f"{i}. [{r['database']}] {r['path']}")
            print(f"   Type: {r['type']} | Category: {r['category']} | Lines: {r['lines']}")
            print(f"   {r['preview']}")
            print()
        
        if len(results) > 50:
            print(f"... and {len(results) - 50} more results (use --json for full output)")
    
    return 0


def cmd_code_stats(args):
    """Show code statistics"""
    cli_service = get_ninox_cli_service()
    parser = NinoxYAMLParser(str(cli_service.project_path))
    databases = parser.get_all_databases()
    
    if not databases:
        print("No databases downloaded yet.")
        return 1
    
    stats = {
        'databases': len(databases),
        'total_code_locations': 0,
        'total_lines': 0,
        'by_database': {},
        'by_category': {},
        'by_type': {}
    }
    
    for db in databases:
        db_stats = {
            'tables': db.table_count,
            'code_locations': len(db.code_locations),
            'lines': sum(loc.line_count for loc in db.code_locations)
        }
        stats['by_database'][db.name] = db_stats
        stats['total_code_locations'] += db_stats['code_locations']
        stats['total_lines'] += db_stats['lines']
        
        for loc in db.code_locations:
            cat = loc.category_name
            stats['by_category'][cat] = stats['by_category'].get(cat, 0) + 1
            
            ct = loc.code_type
            stats['by_type'][ct] = stats['by_type'].get(ct, 0) + 1
    
    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print("\n=== Ninox Code Statistics ===\n")
        print(f"Databases: {stats['databases']}")
        print(f"Total Code Locations: {stats['total_code_locations']}")
        print(f"Total Lines of Code: {stats['total_lines']}")
        
        print("\n--- By Database ---")
        for name, s in sorted(stats['by_database'].items()):
            print(f"  {name}: {s['code_locations']} locations, {s['lines']} lines, {s['tables']} tables")
        
        print("\n--- By Category ---")
        for cat, count in sorted(stats['by_category'].items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count}")
        
        print("\n--- By Type ---")
        for ct, count in sorted(stats['by_type'].items(), key=lambda x: -x[1])[:15]:
            print(f"  {ct}: {count}")
    
    return 0


def cmd_export(args):
    """Export code to files"""
    database_name = args.database
    output_dir = Path(args.output or f"./ninox_export_{database_name}")
    
    cli_service = get_ninox_cli_service()
    parser = NinoxYAMLParser(str(cli_service.project_path))
    databases = parser.get_all_databases()
    
    # Find database
    db = None
    for d in databases:
        if d.name == database_name or d.database_id == database_name:
            db = d
            break
    
    if not db:
        print(f"Database '{database_name}' not found.")
        print("Available databases:")
        for d in databases:
            print(f"  - {d.name} ({d.database_id})")
        return 1
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Export each code location
    exported = 0
    for loc in db.code_locations:
        # Build file path
        parts = [loc.database_name]
        if loc.table_name:
            parts.append(loc.table_name.replace('/', '_').replace('\\', '_'))
        if loc.element_name:
            parts.append(loc.element_name.replace('/', '_').replace('\\', '_'))
        parts.append(f"{loc.code_type}.nx")
        
        file_path = output_dir
        for part in parts[:-1]:
            file_path = file_path / part
        file_path.mkdir(parents=True, exist_ok=True)
        file_path = file_path / parts[-1]
        
        # Write code with header
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"// Path: {loc.path}\n")
            f.write(f"// Type: {loc.type_display_name}\n")
            f.write(f"// Category: {loc.category_name}\n")
            f.write(f"// YAML: {loc.yaml_path}\n")
            f.write("// " + "=" * 50 + "\n\n")
            f.write(loc.code)
        
        exported += 1
    
    print(f"Exported {exported} code files to {output_dir}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Ninox CLI Tool for Ninox2Git',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list-servers                    List configured servers
  %(prog)s list-databases                  List downloaded databases
  %(prog)s sync-all --server-id 1          Sync all databases from server
  %(prog)s sync --server-id 1 -d abc123    Sync specific database
  %(prog)s search "let x"                  Search for code
  %(prog)s stats                           Show code statistics
  %(prog)s export -d MyDB -o ./export      Export database code to files
        """
    )
    
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # list-servers
    sub_ls = subparsers.add_parser('list-servers', help='List available servers')
    sub_ls.set_defaults(func=cmd_list_servers)
    
    # list-databases
    sub_ld = subparsers.add_parser('list-databases', help='List downloaded databases')
    sub_ld.set_defaults(func=cmd_list_databases)
    
    # sync-all
    sub_sa = subparsers.add_parser('sync-all', help='Sync all databases from a server')
    sub_sa.add_argument('--server-id', '-s', type=int, required=True, help='Server ID')
    sub_sa.set_defaults(func=cmd_sync_all)
    
    # sync
    sub_s = subparsers.add_parser('sync', help='Sync a single database')
    sub_s.add_argument('--server-id', '-s', type=int, required=True, help='Server ID')
    sub_s.add_argument('--database-id', '-d', required=True, help='Database ID')
    sub_s.set_defaults(func=cmd_sync)
    
    # search
    sub_search = subparsers.add_parser('search', help='Search code across databases')
    sub_search.add_argument('query', help='Search query')
    sub_search.set_defaults(func=cmd_search)
    
    # stats
    sub_stats = subparsers.add_parser('stats', help='Show code statistics')
    sub_stats.set_defaults(func=cmd_code_stats)
    
    # export
    sub_export = subparsers.add_parser('export', help='Export database code to files')
    sub_export.add_argument('--database', '-d', required=True, help='Database name or ID')
    sub_export.add_argument('--output', '-o', help='Output directory')
    sub_export.set_defaults(func=cmd_export)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
