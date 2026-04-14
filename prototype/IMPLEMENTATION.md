# 原型实现完成

## 已实现的模块

✅ **core/message.py** — 消息 Schema（Task/Result/Signal/Artifact）
✅ **core/checkpoint.py** — 分层 Checkpoint 管理（步骤级/结果级）
✅ **core/agent.py** — BaseAgent 基类（inbox 监听 + write-then-move + 心跳）
✅ **core/router.py** — 智能路由（直投 + bus 兜底 + 置信度分级）
✅ **agents/research_agent.py** — Mock 研究 Agent
✅ **agents/writer_agent.py** — Mock 写作 Agent
✅ **dashboard/server.py** — 实时 Dashboard（Flask + watchdog + SSE）
✅ **run_demo.py** — 一键演示脚本

## 核心特性

1. **文件系统驱动通信**
   - Write-then-Move 原子操作
   - Watchdog 事件驱动
   - 无共享内存隔离

2. **分层 Checkpoint 机制**
   - 步骤级 checkpoint（Task 消息）
   - 结果级 checkpoint（Result 消息）
   - PID 检测和崩溃恢复

3. **智能路由**
   - 直投模式（已知目标）
   - Bus 兜底（未知目标）
   - 置信度分级（高信心直投，低信心走专家）
   - 行为沉淀记录

4. **可观测性 Dashboard**
   - 实时 Agent 状态展示
   - 消息队列深度监控
   - 错误统计和追踪
   - SSE 实时推送

## 预留接口

- `BaseAgent.call_llm()` — 预留 LLM 集成接口
- `Router._classify_message()` — 预留分类器升级接口
- 向量化索引（LanceDB）— 预留经验复用接口

## 运行方式

```bash
# 安装依赖
pip install -r requirements.txt

# 运行演示
python run_demo.py

# 打开 Dashboard
# http://localhost:5000
```

## 文件清单

```
prototype/
├── core/
│   ├── __init__.py
│   ├── message.py
│   ├── checkpoint.py
│   ├── agent.py
│   └── router.py
├── agents/
│   ├── __init__.py
│   ├── research_agent.py
│   └── writer_agent.py
├── dashboard/
│   ├── __init__.py
│   └── server.py
├── system_root/          # 运行时文件系统（gitignore）
├── requirements.txt
├── run_demo.py
└── README.md
```

## 验证清单

- [ ] 运行 `python run_demo.py`，观察消息流转
- [ ] 打开 Dashboard 查看实时状态
- [ ] 手动 kill Agent 进程，验证 checkpoint 恢复
- [ ] 发送 receiver 为空的消息，验证路由决策
