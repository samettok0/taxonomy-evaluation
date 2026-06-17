#!/usr/bin/env python3
"""
AI4RSE Prompt Browser — Local Server
Serves the app and saves/loads progress to a local JSON file.

Usage:
    python3 server.py
    Then open http://localhost:8080
"""

import http.server
import json
import os
import shutil
import csv
import io
from datetime import datetime
from urllib.parse import urlparse

PORT = 8080
# Paths relative to project root (one level up from prompt-browser)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "progress.json")
BROWSER_DIR = os.path.dirname(os.path.abspath(__file__))


class PromptBrowserHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler that serves static files and handles save/load API."""

    def __init__(self, *args, **kwargs):
        # Serve files from the project root so prompts.json is accessible
        super().__init__(*args, directory=PROJECT_ROOT, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/load":
            self._handle_load()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/save":
            self._handle_save()
        elif parsed.path == "/api/export-csv":
            self._handle_export_csv()
        else:
            self.send_error(404, "Not Found")

    def _handle_load(self):
        """Load progress from local file."""
        try:
            if os.path.exists(PROGRESS_FILE):
                with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                    data = f.read()
                self._send_json(200, data)
            else:
                self._send_json(200, json.dumps({"currentIndex": 0, "responses": {}, "completed": []}))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_save(self):
        """Save progress to local file with backup."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")

            # Validate JSON
            data = json.loads(body)

            # Create backup of existing file (keep last backup)
            if os.path.exists(PROGRESS_FILE):
                backup = PROGRESS_FILE.replace(".json", ".backup.json")
                shutil.copy2(PROGRESS_FILE, backup)

            # Write new progress
            with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            self._send_json(200, json.dumps({
                "status": "saved",
                "timestamp": datetime.now().isoformat(),
                "file": PROGRESS_FILE
            }))
        except json.JSONDecodeError:
            self._send_json(400, json.dumps({"error": "Invalid JSON"}))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_export_csv(self):
        """Generate and send CSV of decisions."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
            
            prompts = data.get("prompts", [])
            responses = data.get("responses", {})
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                "High level", "Middle level", "Low level", 
                "Concept Name", "Concept Definition", 
                "Decision", "Reason", "New Taxonomy Path"
            ])
            
            # Output in original order
            for i, p in enumerate(prompts):
                idx_str = str(i)
                if idx_str in responses:
                    r = responses[idx_str]
                    decision = r.get("decision", "")
                    reason = r.get("reason", "")
                    new_path = r.get("newPath", "")
                    writer.writerow([
                        p.get("high_level", ""),
                        p.get("middle_level", ""),
                        p.get("low_level", ""),
                        p.get("concept_name", ""),
                        p.get("concept_definition", ""),
                        decision,
                        reason,
                        new_path
                    ])
            
            csv_data = output.getvalue()
            
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", 'attachment; filename="AI4RSE_Taxonomy_Decisions.csv"')
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(csv_data.encode("utf-8"))
            
        except json.JSONDecodeError:
            self._send_json(400, json.dumps({"error": "Invalid JSON"}))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _send_json(self, status, body):
        """Send a JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        """Custom logging — suppress static file noise, show API calls."""
        try:
            path = str(args[0]).split()[1] if args else ""
            if path.startswith("/api/"):
                print(f"  {args[0]}")
        except Exception:
            pass


def main():
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║   AI4RSE Prompt Browser                      ║")
    print(f"╠══════════════════════════════════════════════╣")
    print(f"║   Open: http://localhost:{PORT}/prompt-browser/  ║")
    print(f"║   Progress file: progress.json               ║")
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
