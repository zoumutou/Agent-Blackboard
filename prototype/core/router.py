"""
路由器 - 智能消息路由
"""
import json
import random
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from .message import Message


class Router:
    """消息路由器"""

    def __init__(self, system_root: str):
        self.system_root = Path(system_root)
        self.registry_dir = self.system_root / "registry"
        self.bus_pending_dir = self.system_root / "bus" / "pending"
        self.behavior_archive_dir = self.system_root / "behavior_archive"
        self.behavior_archive_dir.mkdir(parents=True, exist_ok=True)

    def get_available_agents(self) -> Dict[str, Dict[str, Any]]:
        """获取所有活跃的 Agent"""
        agents = {}
        if not self.registry_dir.exists():
            return agents

        for registry_file in self.registry_dir.glob("*.json"):
            try:
                with open(registry_file) as f:
                    agent_data = json.load(f)
                # 检查心跳是否超时（>2 分钟）
                last_seen = agent_data.get("last_seen", "")
                # 简化处理：假设都是活跃的
                agents[agent_data["name"]] = agent_data
            except Exception as e:
                print(f"Error reading registry {registry_file}: {e}")

        return agents

    def route(self, message: Message) -> str:
        """
        路由消息到目标 Agent 或 bus
        返回目标路径
        """
        # 如果 receiver 已知，直投
        if message.receiver:
            agents = self.get_available_agents()
            if message.receiver in agents:
                target_dir = (
                    self.system_root / "agents" / message.receiver / "inbox"
                )
                target_dir.mkdir(parents=True, exist_ok=True)
                target_file = target_dir / message.filename()
                return str(target_file)

        # receiver 未知或不可用，走 bus 兜底
        # 这里可以加入智能分类器逻辑
        confidence = self._classify_message(message)

        if confidence > 0.9:
            # 高信心：尝试直投到最匹配的 Agent
            best_agent = self._find_best_agent(message)
            if best_agent:
                target_dir = self.system_root / "agents" / best_agent / "inbox"
                target_dir.mkdir(parents=True, exist_ok=True)
                target_file = target_dir / message.filename()
                self._record_routing_decision(message, best_agent, confidence, True)
                return str(target_file)

        # 低信心或无匹配 Agent：写入 bus/pending
        message.payload["needs_expert"] = confidence < 0.6
        self.bus_pending_dir.mkdir(parents=True, exist_ok=True)
        target_file = self.bus_pending_dir / message.filename()
        self._record_routing_decision(message, "bus", confidence, False)
        return str(target_file)

    def _classify_message(self, message: Message) -> float:
        """
        分类消息，返回置信度 (0-1)
        原型中使用简单的关键词匹配
        """
        if message.type != "task":
            return 0.95  # Result/Signal 消息高信心

        command = message.payload.get("command", "").lower()

        # 简单的关键词匹配
        if "research" in command or "analyze" in command or "search" in command:
            return 0.85  # 中等信心，可能是 research_agent
        elif "write" in command or "summarize" in command or "generate" in command:
            return 0.85  # 中等信心，可能是 writer_agent
        else:
            return 0.5  # 低信心，需要专家判定

    def _find_best_agent(self, message: Message) -> Optional[str]:
        """找到最匹配的 Agent"""
        agents = self.get_available_agents()
        if not agents:
            return None

        command = message.payload.get("command", "").lower()

        # 简单的能力匹配
        for agent_name, agent_data in agents.items():
            capabilities = agent_data.get("capabilities", [])
            for cap in capabilities:
                if cap.lower() in command:
                    return agent_name

        # 如果没有精确匹配，随机选择一个
        return random.choice(list(agents.keys()))

    def _record_routing_decision(
        self,
        message: Message,
        target: str,
        confidence: float,
        success: bool,
    ):
        """记录路由决策到行为归档"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        archive_dir = self.behavior_archive_dir / today
        archive_dir.mkdir(parents=True, exist_ok=True)

        decision_file = archive_dir / f"routing_{message.message_id}.json"
        decision_data = {
            "message_id": message.message_id,
            "command": message.payload.get("command", ""),
            "target": target,
            "confidence": confidence,
            "success": success,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        with open(decision_file, "w") as f:
            json.dump(decision_data, f, indent=2)
