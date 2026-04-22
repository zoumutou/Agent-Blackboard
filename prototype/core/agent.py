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

HEARTBEAT_TIMEOUT_SECONDS = 120


class InboxHandler(FileSystemEventHandler):
    """监听 inbox 目录的文件事件"""

    def __init__(self, agent: "BaseAgent"):
        self.agent = agent

    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(".json"):
            self.agent._on_message_arrived(event.src_path)

    def on_moved(self, event):
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

        for d in [
            self.inbox_dir, self.workspace_dir, self.outbox_dir,
            self.bus_pending_dir, self.bus_dead_letter_dir, self.archive_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        self.checkpoint_manager = CheckpointManager(str(self.workspace_dir))
        self.observer = None
        self.running = False
        self.pid = os.getpid()

    def register(self):
        self.system_root.joinpath("registry").mkdir(parents=True, exist_ok=True)
        registry_data = {
            "name": self.name,
            "pid": self.pid,
            "status": "running",
            "last_seen": datetime.utcnow().isoformat() + "Z",
            "capabilities": self.get_capabilities(),
        }
        with open(self.registry_file, "w") as f:
            json.dump(registry_data, f, indent=2)

    def unregister(self):
        if self.registry_file.exists():
            try:
                with open(self.registry_file) as f:
                    data = json.load(f)
                data["status"] = "stopped"
                data["last_seen"] = datetime.utcnow().isoformat() + "Z"
                with open(self.registry_file, "w") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

    def heartbeat(self):
        while self.running:
            time.sleep(30)
            try:
                if self.registry_file.exists():
                    with open(self.registry_file) as f:
                        data = json.load(f)
                    data["last_seen"] = datetime.utcnow().isoformat() + "Z"
                    data["status"] = "running"
                    with open(self.registry_file, "w") as f:
                        json.dump(data, f, indent=2)
            except Exception:
                pass

    def _recover_processing_files(self):
        """Recover .processing files left by a previous crash."""
        for p in self.workspace_dir.glob("*.processing"):
            try:
                target = self.inbox_dir / p.name.replace(".processing", ".json")
                shutil.move(str(p), str(target))
                print(f"[{self.name}] Recovered orphaned message: {p.name}")
            except Exception as e:
                print(f"[{self.name}] Failed to recover {p.name}: {e}")
        for p in self.inbox_dir.parent.glob("**/*.processing"):
            if p.parent == self.inbox_dir or p.parent == self.workspace_dir:
                try:
                    target = self.inbox_dir / p.name.replace(".processing", ".json")
                    shutil.move(str(p), str(target))
                    print(f"[{self.name}] Recovered orphaned message: {p.name}")
                except Exception:
                    pass

    def _process_existing_inbox(self):
        """Process any messages already in inbox at startup."""
        for msg_file in sorted(self.inbox_dir.glob("*.json")):
            self._on_message_arrived(str(msg_file))

    def start(self):
        self.running = True
        self.register()
        self._recover_processing_files()

        heartbeat_thread = threading.Thread(target=self.heartbeat, daemon=True)
        heartbeat_thread.start()

        handler = InboxHandler(self)
        self.observer = Observer()
        self.observer.schedule(handler, str(self.inbox_dir), recursive=False)
        self.observer.start()

        self._process_existing_inbox()
        print(f"[{self.name}] Agent started, PID={self.pid}")

    def stop(self):
        self.running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()
        self.unregister()
        print(f"[{self.name}] Agent stopped")

    def _on_message_arrived(self, file_path: str):
        """消息到达时的处理"""
        processing_path = file_path.replace(".json", ".processing")

        # Wait for file to be fully written (Windows file locking)
        message_data = None
        for attempt in range(8):
            try:
                if os.path.exists(file_path):
                    shutil.move(file_path, processing_path)
                if not os.path.exists(processing_path):
                    return
                with open(processing_path, encoding="utf-8") as f:
                    message_data = json.load(f)
                break
            except (PermissionError, OSError, json.JSONDecodeError):
                time.sleep(0.3 * (attempt + 1))

        if message_data is None:
            print(f"[{self.name}] Could not read message: {file_path}")
            return

        try:
            message = Message(**message_data)

            if message.type != "task":
                archive_path = self.archive_dir / message.filename()
                shutil.move(processing_path, str(archive_path))
                return

            message.pid = self.pid
            message.status = "processing"
            print(f"[{self.name}] Processing message {message.message_id}")

            result = self.process(message)

            result_message = Message.create_result(
                sender=self.name,
                receiver=message.sender,
                task_id=message.message_id,
                success=True,
                result=result,
            )
            self.send(result_message)

            archive_path = self.archive_dir / message.filename()
            shutil.move(processing_path, str(archive_path))
            print(f"[{self.name}] Message {message.message_id} completed")

        except Exception as e:
            print(f"[{self.name}] Error processing message: {e}")
            try:
                if os.path.exists(processing_path):
                    error_path = self.bus_dead_letter_dir / Path(processing_path).name
                    shutil.move(processing_path, str(error_path))
            except Exception:
                pass

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
        return []

    @staticmethod
    def check_agent_health(registry_dir: Path, timeout_seconds: int = HEARTBEAT_TIMEOUT_SECONDS) -> dict:
        """Check all registered agents and return their health status."""
        health = {}
        if not registry_dir.exists():
            return health
        now = time.time()
        for reg_file in registry_dir.glob("*.json"):
            try:
                with open(reg_file) as f:
                    data = json.load(f)
                name = data.get("name", reg_file.stem)
                last_seen = data.get("last_seen", "")
                status = data.get("status", "unknown")
                if last_seen and status == "running":
                    try:
                        ts = datetime.fromisoformat(last_seen.rstrip("Z")).timestamp()
                        age = now - ts
                        if age > timeout_seconds:
                            status = "timeout"
                    except (ValueError, OSError):
                        pass
                health[name] = {"status": status, "last_seen": last_seen, "pid": data.get("pid")}
            except Exception:
                pass
        return health

    _llm_client_cache: dict = {}

    def call_llm(
        self,
        prompt: str,
        *,
        tier: str = "cloud",
        system: str | None = None,
        json_mode: bool = False,
    ) -> str | None:
        """Call a real LLM via llm_client. Returns response content or None on failure."""
        try:
            import sys
            web_scripts = str(Path(__file__).resolve().parents[2] / "web" / "scripts")
            if web_scripts not in sys.path:
                sys.path.insert(0, web_scripts)
            from llm_client import create_client

            cache_key = tier
            if cache_key not in BaseAgent._llm_client_cache:
                client = create_client(tier)
                if client is None:
                    return None
                BaseAgent._llm_client_cache[cache_key] = client

            client = BaseAgent._llm_client_cache[cache_key]
            resp = client.chat(
                [{"role": "user", "content": prompt}],
                system=system,
                json_mode=json_mode,
            )
            return resp.content if resp else None
        except Exception as e:
            print(f"[{self.name}] LLM call failed: {e}")
            return None
