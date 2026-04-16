"""
Export the OpenAPI spec to a static JSON file for version control.

Usage:
    python scripts/export_openapi.py [output_path]

Default output: docs/openapi.json (relative to repo root)
"""

import json
import sys
import os

# Ensure backend directory is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set required env vars to allow import without a running database
os.environ.setdefault("DATABASE_URL", "sqlite:///dummy.db")
os.environ.setdefault("JWT_SECRET_KEY", "export-only")


def main():
    from app import app

    spec = app.openapi()

    output_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "docs",
        "openapi.json",
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)

    print(f"OpenAPI spec exported to {output_path}")
    print(f"  Title: {spec.get('info', {}).get('title')}")
    print(f"  Version: {spec.get('info', {}).get('version')}")
    print(f"  Paths: {len(spec.get('paths', {}))}")
    print(f"  Schemas: {len(spec.get('components', {}).get('schemas', {}))}")


if __name__ == "__main__":
    main()
