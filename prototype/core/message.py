"""
消息 Schema 定义
"""
from dataclasses import dataclass, asdict
from typing import Literal, Optional, Any
from datetime import datetime
import json
import uuid


@dataclass
class Message:
    """Agent 间通信的消息对象"""
    message_id: str  # uuid-v4
    type: Literal["task", "result", "signal", "artifact"]
    sender: str
    receiver: str  # "" 表示广播到 bus
    timestamp: str
    priority: Literal["low", "normal", "high"]
    status: Literal["new", "processing", "done", "failed"]
    pid: int  # 处理进程 PID，用于崩溃检测
    payload: dict

    @classmethod
    def create_task(
        cls,
        sender: str,
        receiver: str,
        command: str,
        content: str,
        priority: str = "normal",
        file_refs: Optional[list] = None,
    ) -> "Message":
        """创建 Task 消息"""
        return cls(
            message_id=str(uuid.uuid4()),
            type="task",
            sender=sender,
            receiver=receiver,
            timestamp=datetime.utcnow().isoformat() + "Z",
            priority=priority,
            status="new",
            pid=0,  # 由发送者填充
            payload={
                "command": command,
                "content": content,
                "file_refs": file_refs or [],
            },
        )

    @classmethod
    def create_result(
        cls,
        sender: str,
        receiver: str,
        task_id: str,
        success: bool,
        result: str,
    ) -> "Message":
        """创建 Result 消息"""
        return cls(
            message_id=str(uuid.uuid4()),
            type="result",
            sender=sender,
            receiver=receiver,
            timestamp=datetime.utcnow().isoformat() + "Z",
            priority="normal",
            status="new",
            pid=0,
            payload={
                "task_id": task_id,
                "success": success,
                "result": result,
            },
        )

    def to_json(self) -> str:
        """序列化为 JSON"""
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """从 JSON 反序列化"""
        data = json.loads(json_str)
        return cls(**data)

    def filename(self) -> str:
        """生成文件名"""
        return f"msg_{self.message_id}.json"
