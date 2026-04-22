"""
Template Agent — Blackboard wrapper around template_analyzer.analyze_template.
"""
import json
import sys
import time
import uuid
from pathlib import Path

WEB_SCRIPTS = Path(__file__).resolve().parents[3] / "web" / "scripts"
sys.path.insert(0, str(WEB_SCRIPTS))

from core.agent import BaseAgent
from core.message import Message


class TemplateAgent(BaseAgent):
    def __init__(self, system_root: str):
        super().__init__("template_agent", system_root)

    def get_capabilities(self) -> list:
        return ["template-analyze", "template", "ppt"]

    def process(self, message: Message) -> str:
        payload = message.payload or {}
        params = payload.get("params", {})

        template_id = params.get("templateId", f"tpl_{int(time.time())}")
        pptx_path = params.get("filePath", "")
        output_dir = params.get("outputDir", "")
        use_cascade = params.get("cascade", False)

        task_id = payload.get("taskId") or f"bb_tpl_{uuid.uuid4().hex[:8]}"
        task = {
            "id": task_id,
            "type": "template-analysis",
            "title": f"Template analysis: {template_id}",
            "status": "running",
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "input": {"templateId": template_id, "filePath": pptx_path, "outputDir": output_dir},
            "logs": [],
            "worker": {"id": f"bb-template-{self.name}", "mode": "blackboard"},
        }

        from task_worker import write_task, add_log, set_progress, TASK_DIR
        TASK_DIR.mkdir(parents=True, exist_ok=True)

        try:
            from template_analyzer import analyze_template
            set_progress(task, phase="template-extract", label="Extracting template structure", percent=20)
            write_task(task)

            result = analyze_template(pptx_path, output_dir, use_cascade=use_cascade)

            task["status"] = "completed"
            task["result"] = result
            add_log(task, "info", f"Template analysis completed: {result.get('patterns', [])}")
        except Exception as exc:
            task["status"] = "failed"
            task["error"] = f"Template analysis failed: {exc}"
            add_log(task, "error", task["error"])

        if task.get("status") == "running":
            task["status"] = "failed"
            task["error"] = "Task ended without setting a final status."

        write_task(task)
        return json.dumps({"taskId": task_id, "status": task.get("status")}, ensure_ascii=False)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--system-root", default=str(Path(__file__).resolve().parent.parent / "system_root"))
    args = parser.parse_args()
    agent = TemplateAgent(args.system_root)
    agent.start()
    print("[template_agent] Listening. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
