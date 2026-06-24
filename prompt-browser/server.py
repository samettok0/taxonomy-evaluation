import os
import sys
import json
import csv
import io
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.config import PORT, DB_FILE, PROJECT_ROOT, BROWSER_DIR
import backend.db as db
import backend.gemini_client as gemini_client
import backend.batch_runner as batch_runner

if not os.path.exists(DB_FILE):
    print(f"❌ Database not found: {DB_FILE}")
    print(f"   Run 'python3 init_db.py' first to create it.")
    sys.exit(1)

app = FastAPI(title="AI4RSE Prompt Browser API")

# --- Pydantic Models ---

class SaveStateRequest(BaseModel):
    # dynamic dict
    model_config = {"extra": "allow"}

class SystemPromptCreate(BaseModel):
    name: str = "Untitled Prompt"
    content: str = ""

class SystemPromptId(BaseModel):
    id: int

class EvaluateSingleRequest(BaseModel):
    concept_index: int
    system_prompt_id: int
    count: int = 1

class EvalStartRequest(BaseModel):
    system_prompt_id: int
    run_mode: str = "full"
    max_batches: Optional[int] = None

class ExportCsvRequest(BaseModel):
    prompts: List[Dict[str, Any]] = []
    responses: Dict[str, Dict[str, Any]] = {}

# --- API Routes ---

@app.get("/api/prompts")
def get_prompts():
    try:
        return db.get_prompts_and_state()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/load")
def load_state():
    try:
        return db.load_app_state()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/save")
async def save_state(request: Request):
    try:
        data = await request.json()
        db.save_app_state(data)
        return {"status": "saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system-prompts")
def get_system_prompts():
    try:
        return {"prompts": db.get_system_prompts()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/system-prompts")
def create_system_prompt(req: SystemPromptCreate):
    try:
        new_id = db.create_system_prompt(req.name, req.content)
        return {"id": new_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/system-prompts/active")
def set_active_prompt(req: SystemPromptId):
    try:
        db.set_active_system_prompt(req.id)
        return {"status": "active", "id": req.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/system-prompts/delete")
def delete_system_prompt(req: SystemPromptId):
    try:
        success = db.delete_system_prompt(req.id)
        if success:
            return {"status": "deleted", "id": req.id}
        else:
            raise HTTPException(status_code=400, detail="Cannot delete the last system prompt.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/evaluate-single")
def evaluate_single(req: EvaluateSingleRequest):
    try:
        result = gemini_client.evaluate_range(req.concept_index, req.count, req.system_prompt_id)
        db.save_playground_history(req.system_prompt_id, req.concept_index, req.count, result)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/evaluation/start")
def eval_start(req: EvalStartRequest):
    try:
        batch_runner.start_evaluation(req.system_prompt_id, req.run_mode, req.max_batches)
        return {"status": "started", "run_mode": req.run_mode}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/evaluation/stop")
def eval_stop():
    stopped = batch_runner.stop_evaluation()
    if stopped:
        return {"status": "stopping"}
    else:
        return {"status": "not_running"}

@app.get("/api/evaluation/status")
def eval_status():
    return batch_runner.get_status()

@app.get("/api/evaluation/results")
def get_eval_results(system_prompt_id: int):
    try:
        return db.get_evaluation_results(system_prompt_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/evaluation/progress")
def get_eval_progress(system_prompt_id: int):
    try:
        return db.get_evaluation_progress(system_prompt_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/playground-history")
def get_playground_history():
    try:
        return {"history": db.get_playground_history()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/playground-history/clear")
def clear_playground_history():
    try:
        db.clear_playground_history()
        return {"status": "cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/export-csv")
def export_csv(req: ExportCsvRequest):
    try:
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "High level", "Middle level", "Low level",
            "Concept Name", "Concept Definition",
            "Decision", "Reason", "Issues", "New Taxonomy Path",
        ])

        for i, p in enumerate(req.prompts):
            idx_str = str(i)
            if idx_str in req.responses:
                r = req.responses[idx_str]
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
        
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="AI4RSE_Taxonomy_Decisions.csv"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Static Files ---

# Serve the index.html explicitly at the root
@app.get("/")
def serve_index():
    return FileResponse(os.path.join(BROWSER_DIR, "index.html"))

# Serve all other static files (js, css) from BROWSER_DIR
app.mount("/", StaticFiles(directory=BROWSER_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║   AI4RSE Prompt Browser (FastAPI)            ║")
    print(f"╠══════════════════════════════════════════════╣")
    print(f"║   Open: http://localhost:{PORT}                  ║")
    print(f"║   Database: taxonomy.db                      ║")
    print(f"║   Press Ctrl+C to stop                       ║")
    print(f"╚══════════════════════════════════════════════╝")
    print()
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=True)
