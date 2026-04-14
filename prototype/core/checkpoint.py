"""
分层 Checkpoint 管理
"""
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class CheckpointManager:
    """管理 Agent 的分层 checkpoint"""

    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def save_step_checkpoint(
        self, task_id: str, step_n: int, state: Dict[str, Any]
    ) -> str:
        """保存步骤级 checkpoint"""
        checkpoint_file = (
            self.workspace_dir / f"{task_id}.step_{step_n}.checkpoint.json"
        )
        checkpoint_data = {
            "task_id": task_id,
            "step": step_n,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "state": state,
        }
        with open(checkpoint_file, "w") as f:
            json.dump(checkpoint_data, f, indent=2)
        return str(checkpoint_file)

    def save_result_checkpoint(
        self, task_id: str, progress: int, partial_result: str
    ) -> str:
        """保存结果级 checkpoint"""
        checkpoint_file = self.workspace_dir / f"{task_id}.result.checkpoint.json"
        checkpoint_data = {
            "task_id": task_id,
            "progress": progress,  # 0-100
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "partial_result": partial_result,
        }
        with open(checkpoint_file, "w") as f:
            json.dump(checkpoint_data, f, indent=2)
        return str(checkpoint_file)

    def load_latest_step_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """加载最新的步骤级 checkpoint"""
        checkpoints = sorted(
            self.workspace_dir.glob(f"{task_id}.step_*.checkpoint.json"),
            key=lambda p: int(p.stem.split("_")[1]),
            reverse=True,
        )
        if not checkpoints:
            return None
        with open(checkpoints[0]) as f:
            return json.load(f)

    def load_result_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """加载结果级 checkpoint"""
        checkpoint_file = self.workspace_dir / f"{task_id}.result.checkpoint.json"
        if not checkpoint_file.exists():
            return None
        with open(checkpoint_file) as f:
            return json.load(f)

    def scan_orphaned_tasks(self, current_pid: int) -> list:
        """扫描孤儿任务（.processing 文件对应的 PID 不存活）"""
        orphaned = []
        for processing_file in self.workspace_dir.glob("*.processing"):
            # 从文件名或内容中提取 PID（这里简化处理，实际应从消息内容读取）
            # 为了演示，我们假设 .processing 文件对应的消息已被读取
            orphaned.append(str(processing_file))
        return orphaned

    def cleanup_old_checkpoints(self, task_id: str, keep_latest: int = 3):
        """清理旧的 checkpoint，只保留最新的 N 个"""
        checkpoints = sorted(
            self.workspace_dir.glob(f"{task_id}.step_*.checkpoint.json"),
            key=lambda p: int(p.stem.split("_")[1]),
        )
        for checkpoint in checkpoints[:-keep_latest]:
            checkpoint.unlink()
