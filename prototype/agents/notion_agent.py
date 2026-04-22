"""
Notion Agent — Blackboard wrapper around task_worker.process_notion_sync_task.
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


class NotionAgent(BaseAgent):
    def __init__(self, system_root: str):
        super().__init__("notion_agent", system_root)

    def get_capabilities(self) -> list:
        return ["notion-sync", "notion", "sync"]

    def process(self, message: Message) -> str:
        payload = message.payload or {}
        params = payload.get("params", {})

        task_id = payload.get("taskId") or f"bb_notion_{uuid.uuid4().hex[:8]}"
        task = {
            "id": task_id,
            "type": "notion-sync",
            "title": f"Notion sync: {params.get('pmid', 'unknown')}",
            "status": "running",
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "input": params,
            "logs": [],
            "worker": {"id": f"bb-notion-{self.name}", "mode": "blackboard"},
        }

        from task_worker import process_notion_sync_task, write_task, TASK_DIR
        TASK_DIR.mkdir(parents=True, exist_ok=True)

        try:
            process_notion_sync_task(task)
        except Exception as exc:
            task["status"] = "failed"
            task["error"] = f"Unhandled: {exc}"

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
    agent = NotionAgent(args.system_root)
    agent.start()
    print("[notion_agent] Listening. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
