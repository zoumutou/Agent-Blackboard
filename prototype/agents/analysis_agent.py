"""
Analysis Agent — Blackboard wrapper around the existing task_worker pipeline.

Receives analysis task messages via the Blackboard inbox, delegates to
task_worker.process_analysis_task, and sends back a result message.
"""
import json
import sys
from pathlib import Path

# Add web/scripts to path so we can import task_worker
WEB_SCRIPTS = Path(__file__).resolve().parents[3] / "web" / "scripts"
sys.path.insert(0, str(WEB_SCRIPTS))

from core.agent import BaseAgent
from core.message import Message


class AnalysisAgent(BaseAgent):
    def __init__(self, system_root: str):
        super().__init__("analysis_agent", system_root)

    def get_capabilities(self) -> list:
        return ["analyze", "extract", "research", "pdf", "marker", "pubmed"]

    def process(self, message: Message) -> str:
        payload = message.payload or {}
        command = payload.get("command", "")
        params = payload.get("params", {})

        pmid = params.get("pmid")
        pdf_path = params.get("pdfPath")
        title = params.get("title")
        doi = params.get("doi")
        journal = params.get("journal")
        engine = params.get("analysisEngine", "heuristic")

        # Build a task dict compatible with task_worker
        import uuid, time
        task_id = f"bb_{uuid.uuid4().hex[:12]}"
        task = {
            "id": task_id,
            "type": "analysis",
            "title": title or f"Blackboard analysis: {pmid or 'local-pdf'}",
            "status": "running",
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "input": {
                "pmid": pmid,
                "title": title,
                "journal": journal,
                "pdfPath": pdf_path,
                "doi": doi,
                "analysisEngine": engine,
            },
            "logs": [],
            "worker": {"id": f"bb-analysis-{self.name}", "mode": "blackboard"},
        }

        # Import and run the actual pipeline
        from task_worker import process_analysis_task, write_task, TASK_DIR
        TASK_DIR.mkdir(parents=True, exist_ok=True)

        try:
            process_analysis_task(task)
        except Exception as exc:
            task["status"] = "failed"
            task["error"] = f"Unhandled: {exc}"

        if task.get("status") == "running":
            task["status"] = "failed"
            task["error"] = "Pipeline ended without setting a final status."

        # Persist the task file so the web UI can see it
        task_file = TASK_DIR / f"{task_id}.json"
        task_file.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")

        result_summary = {
            "taskId": task_id,
            "status": task.get("status"),
            "result": task.get("result"),
            "error": task.get("error"),
        }
        return json.dumps(result_summary, ensure_ascii=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Blackboard Analysis Agent")
    parser.add_argument(
        "--system-root",
        default=str(Path(__file__).resolve().parent.parent / "prototype" / "system_root"),
        help="Path to the Blackboard system_root directory.",
    )
    args = parser.parse_args()

    agent = AnalysisAgent(args.system_root)
    agent.start()

    print(f"[analysis_agent] Listening for tasks. Press Ctrl+C to stop.")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
