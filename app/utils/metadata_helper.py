"""
Metadata Helper for Database ID Tracking
"""
import json
from pathlib import Path
from datetime import datetime

def create_database_metadata(db_path, server, team, database_id, database_name):
    metadata = {
        "server_id": server.id,
        "server_name": server.name,
        "team_id": team.team_id,
        "team_name": team.name,
        "database_id": database_id,
        "database_name": database_name,
        "last_sync": datetime.utcnow().isoformat(),
        "structure_version": "2.0-names"
    }
    metadata_file = db_path / ".ninox-metadata.json"
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

def read_database_metadata(db_path):
    metadata_file = db_path / ".ninox-metadata.json"
    if not metadata_file.exists():
        raise ValueError(f"Metadata not found: {metadata_file}")
    with open(metadata_file, "r", encoding="utf-8") as f:
        return json.load(f)
