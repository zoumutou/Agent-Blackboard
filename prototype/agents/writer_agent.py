"""
Mock 写作 Agent
"""
from core.agent import BaseAgent
from core.message import Message


class WriterAgent(BaseAgent):
    """写作 Agent - 模拟进行文章写作和总结"""

    def get_capabilities(self) -> list:
        return ["write", "summarize", "generate", "compose"]

    def process(self, message: Message) -> str:
        """处理写作任务"""
        command = message.payload.get("command", "")
        content = message.payload.get("content", "")

        print(f"[WriterAgent] Processing: {command}")
        print(f"[WriterAgent] Content: {content}")

        # Mock 处理逻辑
        if "summarize" in command.lower():
            result = f"Summary of: {content}\n\n"
            result += "Executive Summary:\n"
            result += "This document provides a comprehensive overview of the key topics.\n"
            result += "Main takeaways:\n"
            result += "- Key insight 1\n"
            result += "- Key insight 2\n"
            result += "- Key insight 3\n"
            return result
        elif "write" in command.lower():
            result = f"Article on: {content}\n\n"
            result += "Introduction\n"
            result += "This article explores the topic in depth.\n\n"
            result += "Main Content\n"
            result += "Section 1: Background and context\n"
            result += "Section 2: Key findings\n"
            result += "Section 3: Implications\n\n"
            result += "Conclusion\n"
            result += "In summary, the topic is important and requires attention.\n"
            return result
        else:
            return f"Composed: {content}"
