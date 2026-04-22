"""
Coordinator Agent — Routes incoming task messages to the appropriate worker agent.

Routing table:
  "analyze"           → analysis_agent
  "notion-sync"       → notion_agent
  "template-analyze"  → template_agent
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agent import BaseAgent
from core.message import Message


ROUTE_TABLE = {
    "analyze": "analysis_agent",
    "notion-sync": "notion_agent",
    "template-analyze": "template_agent",
}


class CoordinatorAgent(BaseAgent):
    def __init__(self, system_root: str):
        super().__init__("coordinator", system_root)

    def get_capabilities(self) -> list:
        return ["coordinate", "route", "dispatch"]

    def process(self, message: Message) -> str:
        payload = message.payload or {}
        command = payload.get("command", "")
        task_id = payload.get("taskId", "")

        target_agent = ROUTE_TABLE.get(command)
        if not target_agent:
            for key, agent in ROUTE_TABLE.items():
                if key in command.lower():
                    target_agent = agent
                    break

        if not target_agent:
            return json.dumps({"error": f"No agent found for command: {command}", "routed": False})

        health = BaseAgent.check_agent_health(self.system_root / "registry")
        agent_status = health.get(target_agent, {}).get("status", "unknown")
        if agent_status not in ("running",):
            print(f"[coordinator] Warning: {target_agent} status is '{agent_status}', dispatching anyway")

        forward = Message.create_task(
            sender=self.name,
            receiver=target_agent,
            command=command,
            content=payload.get("content", ""),
            priority=message.priority,
        )
        forward.payload["params"] = payload.get("params", {})
        forward.payload["taskId"] = task_id
        forward.payload["originalMessageId"] = message.message_id

        self.send(forward)

        return json.dumps({
            "routed": True,
            "target": target_agent,
            "forwardedMessageId": forward.message_id,
            "taskId": task_id,
        })


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Blackboard Coordinator Agent")
    parser.add_argument(
        "--system-root",
        default=str(Path(__file__).resolve().parent.parent / "system_root"),
    )
    args = parser.parse_args()

    agent = CoordinatorAgent(args.system_root)
    agent.start()

    print("[coordinator] Listening for tasks. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
