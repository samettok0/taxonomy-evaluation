import json
import csv
import io
from urllib.parse import urlparse, parse_qs
from http.server import SimpleHTTPRequestHandler
import os

from backend.config import PROJECT_ROOT
import backend.db as db
import backend.gemini_client as gemini_client
import backend.batch_runner as batch_runner

class PromptBrowserHandler(SimpleHTTPRequestHandler):
    """Custom handler that serves static files and handles API routes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PROJECT_ROOT, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        routes = {
            "/api/prompts": self._handle_get_prompts,
            "/api/load": self._handle_load,
            "/api/system-prompts": self._handle_get_system_prompts,
            "/api/evaluation/status": self._handle_eval_status,
            "/api/evaluation/results": self._handle_get_eval_results,
            "/api/evaluation/progress": self._handle_get_eval_progress,
            "/api/playground-history": self._handle_get_playground_history,
        }

        handler = routes.get(path)
        if handler:
            handler(qs)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        routes = {
            "/api/save": self._handle_save,
            "/api/system-prompts": self._handle_create_system_prompt,
            "/api/system-prompts/active": self._handle_set_active_prompt,
            "/api/system-prompts/delete": self._handle_delete_system_prompt,
            "/api/evaluate-single": self._handle_evaluate_single,
            "/api/evaluation/start": self._handle_eval_start,
            "/api/evaluation/stop": self._handle_eval_stop,
            "/api/export-csv": self._handle_export_csv,
            "/api/playground-history/clear": self._handle_clear_playground_history,
        }

        handler = routes.get(path)
        if handler:
            handler()
        else:
            self.send_error(404, "Not Found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ─── API Routes ─────────────────────────────────────────────────
    def _handle_get_prompts(self, qs):
        try:
            result = db.get_prompts_and_state()
            self._send_json(200, json.dumps(result))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_load(self, qs=None):
        try:
            result = db.load_app_state()
            self._send_json(200, json.dumps(result))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_save(self):
        try:
            data = json.loads(self._read_body())
            db.save_app_state(data)
            self._send_json(200, json.dumps({"status": "saved"}))
        except json.JSONDecodeError:
            self._send_json(400, json.dumps({"error": "Invalid JSON"}))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_get_system_prompts(self, qs=None):
        try:
            prompts = db.get_system_prompts()
            self._send_json(200, json.dumps({"prompts": prompts}))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_create_system_prompt(self):
        try:
            data = json.loads(self._read_body())
            name = data.get("name", "Untitled Prompt")
            content = data.get("content", "")
            new_id = db.create_system_prompt(name, content)
            self._send_json(200, json.dumps({"id": new_id, "status": "created"}))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_set_active_prompt(self):
        try:
            data = json.loads(self._read_body())
            prompt_id = data.get("id")
            db.set_active_system_prompt(prompt_id)
            self._send_json(200, json.dumps({"status": "active", "id": prompt_id}))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_delete_system_prompt(self):
        try:
            data = json.loads(self._read_body())
            prompt_id = data.get("id")
            success = db.delete_system_prompt(prompt_id)
            if success:
                self._send_json(200, json.dumps({"status": "deleted", "id": prompt_id}))
            else:
                self._send_json(400, json.dumps({"error": "Cannot delete the last system prompt."}))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_evaluate_single(self):
        try:
            data = json.loads(self._read_body())
            concept_index = data.get("concept_index")
            system_prompt_id = data.get("system_prompt_id")
            count = int(data.get("count", 1))
            
            result = gemini_client.evaluate_range(concept_index, count, system_prompt_id)
            db.save_playground_history(system_prompt_id, concept_index, count, result)
            self._send_json(200, json.dumps(result))
        except ValueError as e:
            self._send_json(404, json.dumps({"error": str(e)}))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_eval_start(self):
        try:
            data = json.loads(self._read_body())
            system_prompt_id = data.get("system_prompt_id")
            run_mode = data.get("run_mode", "full")
            max_batches = data.get("max_batches")
            
            batch_runner.start_evaluation(system_prompt_id, run_mode, max_batches)
            self._send_json(200, json.dumps({"status": "started", "run_mode": run_mode}))
        except RuntimeError as e:
            self._send_json(409, json.dumps({"error": str(e)}))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_eval_stop(self):
        stopped = batch_runner.stop_evaluation()
        if stopped:
            self._send_json(200, json.dumps({"status": "stopping"}))
        else:
            self._send_json(200, json.dumps({"status": "not_running"}))

    def _handle_eval_status(self, qs=None):
        status = batch_runner.get_status()
        self._send_json(200, json.dumps(status))

    def _handle_get_eval_results(self, qs=None):
        try:
            prompt_id = qs.get("system_prompt_id", [None])[0]
            if not prompt_id:
                self._send_json(400, json.dumps({"error": "system_prompt_id required"}))
                return
            
            result = db.get_evaluation_results(prompt_id)
            self._send_json(200, json.dumps(result))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_get_eval_progress(self, qs=None):
        try:
            prompt_id = qs.get("system_prompt_id", [None])[0]
            if not prompt_id:
                self._send_json(400, json.dumps({"error": "system_prompt_id required"}))
                return
            
            result = db.get_evaluation_progress(prompt_id)
            self._send_json(200, json.dumps(result))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_get_playground_history(self, qs=None):
        try:
            history = db.get_playground_history()
            self._send_json(200, json.dumps({"history": history}))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_clear_playground_history(self):
        try:
            db.clear_playground_history()
            self._send_json(200, json.dumps({"status": "cleared"}))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    def _handle_export_csv(self):
        try:
            data = json.loads(self._read_body())
            prompts_data = data.get("prompts", [])
            responses = data.get("responses", {})

            output = io.StringIO()
            writer = csv.writer(output)

            writer.writerow([
                "High level", "Middle level", "Low level",
                "Concept Name", "Concept Definition",
                "Decision", "Reason", "Issues", "New Taxonomy Path",
            ])

            for i, p in enumerate(prompts_data):
                idx_str = str(i)
                if idx_str in responses:
                    r = responses[idx_str]
                    writer.writerow([
                        p.get("high_level", ""),
                        p.get("middle_level", ""),
                        p.get("low_level", ""),
                        p.get("concept_name", ""),
                        p.get("concept_definition", ""),
                        r.get("decision", ""),
                        r.get("reason", ""),
                        r.get("issues", ""),
                        r.get("newPath", ""),
                    ])

            csv_data = output.getvalue()
            
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", 'attachment; filename="AI4RSE_Taxonomy_Decisions.csv"')
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(csv_data.encode("utf-8"))
        except Exception as e:
            self._send_json(500, json.dumps({"error": str(e)}))

    # ─── Helpers ────────────────────────────────────────────────────
    def _read_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(content_length).decode("utf-8")

    def _send_json(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        try:
            path = str(args[0]).split()[1] if args else ""
            if path.startswith("/api/"):
                print(f"  {args[0]}")
        except Exception:
            pass
