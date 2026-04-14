"""
演示脚本 - 一键启动完整的 Agent 通信演示
"""
import sys
import time
import threading
from pathlib import Path

# 添加 prototype 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from core.message import Message
from core.router import Router
from agents.research_agent import ResearchAgent
from agents.writer_agent import WriterAgent
from dashboard.server import DashboardServer


def run_demo():
    """运行演示"""
    system_root = Path(__file__).parent / "system_root"
    print(f"System root: {system_root}")

    # 初始化 Agent
    research_agent = ResearchAgent("research_agent", str(system_root))
    writer_agent = WriterAgent("writer_agent", str(system_root))
    router = Router(str(system_root))

    # 启动 Agent
    print("\n=== Starting Agents ===")
    research_agent.start()
    writer_agent.start()

    # 启动 Dashboard（在后台线程）
    print("\n=== Starting Dashboard ===")
    dashboard = DashboardServer(str(system_root), port=5000)
    dashboard_thread = threading.Thread(target=dashboard.start_in_thread, daemon=True)
    dashboard_thread.start()
    print("Dashboard available at http://localhost:5000")

    # 等待 Agent 启动
    time.sleep(2)

    # 发送第一条消息：research_agent 进行研究
    print("\n=== Sending Task 1: Research ===")
    task1 = Message.create_task(
        sender="writer_agent",  # 改为 writer_agent，这样 research_agent 会回复给它
        receiver="research_agent",
        command="research",
        content="Analyze the impact of AI on software development",
        priority="high",
    )
    print(f"Task 1 ID: {task1.message_id}")

    # 将消息写入 research_agent 的 inbox
    inbox_file = system_root / "agents" / "research_agent" / "inbox" / task1.filename()
    inbox_file.parent.mkdir(parents=True, exist_ok=True)
    with open(inbox_file, "w") as f:
        f.write(task1.to_json())
    print(f"Message written to {inbox_file}")

    # 等待 research_agent 处理
    print("\n=== Waiting for research_agent to process ===")
    time.sleep(3)

    # 检查 archive 中是否有完成的消息
    archive_dir = system_root / "archive"
    if archive_dir.exists():
        archived_messages = list(archive_dir.glob("*.json"))
        print(f"Archived messages: {len(archived_messages)}")
        if archived_messages:
            with open(archived_messages[0]) as f:
                archived_msg = Message.from_json(f.read())
            print(f"Archived message: {archived_msg.message_id}")

    # 检查 writer_agent 的 inbox 中是否有 Result 消息
    writer_inbox = system_root / "agents" / "writer_agent" / "inbox"
    if writer_inbox.exists():
        result_messages = list(writer_inbox.glob("*.json"))
        print(f"Result messages in writer_agent inbox: {len(result_messages)}")
        if result_messages:
            with open(result_messages[0]) as f:
                result_msg = Message.from_json(f.read())
            print(f"Result message type: {result_msg.type}")
            print(f"Result content preview: {result_msg.payload.get('result', '')[:100]}...")

    # 等待用户查看 Dashboard
    print("\n=== Demo Running ===")
    print("Open http://localhost:5000 to view the Dashboard")
    print("Demo will run for 30 seconds...")

    try:
        for i in range(30):
            time.sleep(1)
            if i % 5 == 0:
                print(f"Running... ({i}s)")
    except KeyboardInterrupt:
        pass
    finally:
        print("\n=== Stopping Demo ===")
        research_agent.stop()
        writer_agent.stop()
        if dashboard.observer:
            dashboard.observer.stop()
            dashboard.observer.join()
        print("Demo stopped")


if __name__ == "__main__":
    run_demo()
