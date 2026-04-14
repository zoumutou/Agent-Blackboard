"""
Mock 研究 Agent
"""
from core.agent import BaseAgent
from core.message import Message


class ResearchAgent(BaseAgent):
    """研究 Agent - 模拟进行信息研究和分析"""

    def get_capabilities(self) -> list:
        return ["research", "analyze", "search", "investigate"]

    def process(self, message: Message) -> str:
        """处理研究任务"""
        command = message.payload.get("command", "")
        content = message.payload.get("content", "")

        print(f"[ResearchAgent] Processing: {command}")
        print(f"[ResearchAgent] Content: {content}")

        # Mock 处理逻辑
        if "research" in command.lower():
            result = f"Research findings on: {content}\n\n"
            result += "Key points:\n"
            result += "1. Point A - Supporting evidence\n"
            result += "2. Point B - Additional context\n"
            result += "3. Point C - Conclusion\n"
            return result
        elif "analyze" in command.lower():
            result = f"Analysis of: {content}\n\n"
            result += "Analysis results:\n"
            result += "- Aspect 1: Positive\n"
            result += "- Aspect 2: Neutral\n"
            result += "- Aspect 3: Needs attention\n"
            return result
        else:
            return f"Processed: {content}"
