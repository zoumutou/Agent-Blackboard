"""
BaseAgent 基类 - 文件系统驱动的 Agent
"""
import os
import json
import time
import threading
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Optional, Callable
from datetime import datetime
import shutil

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

from .message import Message
from .checkpoint import CheckpointManager


class InboxHandler(FileSystemEventHandler):
    """监听 inbox 目录的文件事件"""

    def __init__(self, agent: "BaseAgent"):
        self.agent = agent

    def on_created(self, event):
        """文件被创建时触发"""
        if event.is_directory:
            return
        if event.src_path.endswith(".json"):
            self.agent._on_message_arrived(event.src_path)

    def on_moved(self, event):
        """文件被移动到 inbox 时触发"""
        if event.is_directory:
            return
        if event.dest_path.endswith(".json"):
            self.agent._on_message_arrived(event.dest_path)


class BaseAgent(ABC):
    """Agent 基类"""

    def __init__(self, name: str, system_root: str):
        self.name = name
        self.system_root = Path(system_root)
        self.inbox_dir = self.system_root / "agents" / name / "inbox"
        self.workspace_dir = self.system_root / "agents" / name / "workspace"
        self.outbox_dir = self.system_root / "agents" / name / "outbox"
        self.registry_file = self.system_root / "registry" / f"{name}.json"
        self.bus_pending_dir = self.system_root / "bus" / "pending"
        self.bus_dead_letter_dir = self.system_root / "bus" / "dead_letter"
        self.archive_dir = self.system_root / "archive"

        # 创建必要的目录
        for d in [
            self.inbox_dir,
            self.workspace_dir,
            self.outbox_dir,
            self.bus_pending_dir,
            self.bus_dead_letter_dir,
            self.archive_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        self.checkpoint_manager = CheckpointManager(str(self.workspace_dir))
        self.observer = None
        self.running = False
        self.pid = os.getpid()

    def register(self):
        """在 registry 中注册自己"""
        registry_data = {
            "name": self.name,
            "pid": self.pid,
            "status": "running",
            "last_seen": datetime.utcnow().isoformat() + "Z",
            "capabilities": self.get_capabilities(),
        }
        with open(self.registry_file, "w") as f:
            json.dump(registry_data, f, indent=2)

    def heartbeat(self):
        """定期更新心跳"""
        while self.running:
            time.sleep(30)
            if self.registry_file.exists():
                with open(self.registry_file) as f:
                    data = json.load(f)
                data["last_seen"] = datetime.utcnow().isoformat() + "Z"
                with open(self.registry_file, "w") as f:
                    json.dump(data, f, indent=2)

    def start(self):
        """启动 Agent"""
        self.running = True
        self.register()

        # 启动心跳线程
        heartbeat_thread = threading.Thread(target=self.heartbeat, daemon=True)
        heartbeat_thread.start()

        # 启动文件监听
        handler = InboxHandler(self)
        self.observer = Observer()
        self.observer.schedule(handler, str(self.inbox_dir), recursive=False)
        self.observer.start()

        print(f"[{self.name}] Agent started, PID={self.pid}")

    def stop(self):
        """停止 Agent"""
        self.running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()
        print(f"[{self.name}] Agent stopped")

    def _on_message_arrived(self, file_path: str):
        """消息到达时的处理"""
        try:
            # 原子操作：rename 为 .processing
            processing_path = file_path.replace(".json", ".processing")
            shutil.move(file_path, processing_path)

            # 读取消息
            with open(processing_path) as f:
                message_data = json.load(f)
            message = Message(**message_data)

            # 只处理 Task 消息，Result/Signal 消息直接归档
            if message.type != "task":
                print(f"[{self.name}] Received {message.type} message {message.message_id}, archiving")
                archive_path = self.archive_dir / message.filename()
                shutil.move(processing_path, archive_path)
                return

            # 更新 PID
            message.pid = self.pid
            message.status = "processing"

            print(f"[{self.name}] Processing message {message.message_id}")

            # 调用子类的处理逻辑
            result = self.process(message)

            # 生成 Result 消息
            result_message = Message.create_result(
                sender=self.name,
                receiver=message.sender,
                task_id=message.message_id,
                success=True,
                result=result,
            )

            # 发送结果
            self.send(result_message)

            # 移动原消息到 archive
            archive_path = self.archive_dir / message.filename()
            shutil.move(processing_path, archive_path)

            print(f"[{self.name}] Message {message.message_id} completed")

        except Exception as e:
            print(f"[{self.name}] Error processing message: {e}")
            # 移动到 dead_letter
            if os.path.exists(processing_path):
                error_path = self.bus_dead_letter_dir / Path(processing_path).name
                shutil.move(processing_path, error_path)

    def send(self, message: Message):
        """发送消息"""
        message.pid = self.pid
        message.sender = self.name

        # 在 workspace 中写临时文件
        temp_file = self.workspace_dir / f"temp_{message.message_id}.json"
        with open(temp_file, "w") as f:
            f.write(message.to_json())

        # 确定目标目录
        if message.receiver:
            # 直投到目标 Agent 的 inbox
            target_dir = self.system_root / "agents" / message.receiver / "inbox"
        else:
            # 广播到 bus
            target_dir = self.bus_pending_dir

        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / message.filename()

        try:
            # write-then-move（原子操作）
            if target_file.exists():
                target_file.unlink()
            os.rename(str(temp_file), str(target_file))

            # 备份到 outbox（直接写入，不复制）
            outbox_file = self.outbox_dir / message.filename()
            with open(outbox_file, "w") as f:
                f.write(message.to_json())

            print(f"[{self.name}] Sent message {message.message_id} to {message.receiver or 'bus'}")
        except Exception as e:
            print(f"[{self.name}] Error sending message: {e}")
            # 清理临时文件
            if temp_file.exists():
                temp_file.unlink()

    @abstractmethod
    def process(self, message: Message) -> str:
        """处理消息，返回结果字符串"""
        pass

    def get_capabilities(self) -> list:
        """返回 Agent 的能力列表"""
        return []

    def call_llm(self, prompt: str) -> str:
        """调用 LLM（预留接口，原型中 mock 实现）"""
        # TODO: 接入真实 LLM（如 Claude API）
        return f"[Mock LLM Response] {prompt[:50]}..."
