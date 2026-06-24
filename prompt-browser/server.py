#!/usr/bin/env python3
"""
AI4RSE Prompt Browser — Local Server (SQLite-backed)
Serves the app and provides API endpoints backed by taxonomy.db.

Usage:
    python3 server.py
    Then open http://localhost:8080
"""

import http.server
import os
import sys

# Ensure backend package is discoverable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.config import PORT, DB_FILE
from backend.handlers import PromptBrowserHandler

def main():
    if not os.path.exists(DB_FILE):
        print(f"❌ Database not found: {DB_FILE}")
        print(f"   Run 'python3 init_db.py' first to create it.")
        sys.exit(1)

    print(f"╔══════════════════════════════════════════════╗")
    print(f"║   AI4RSE Prompt Browser (Modular SQLite)     ║")
    print(f"╠══════════════════════════════════════════════╣")
    print(f"║   Open: http://localhost:{PORT}/prompt-browser/  ║")
    print(f"║   Database: taxonomy.db                      ║")
    print(f"║   Press Ctrl+C to stop                       ║")
    print(f"╚══════════════════════════════════════════════╝")
    print()

    server = http.server.HTTPServer(("", PORT), PromptBrowserHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()

if __name__ == "__main__":
    main()
