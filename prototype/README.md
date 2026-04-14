# Agent 通信系统原型

基于文件系统驱动的 Agent 间通信原型实现。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行演示

```bash
python run_demo.py
```

### 3. 查看 Dashboard

打开浏览器访问 `http://localhost:5000`

## 项目结构

```
prototype/
├── core/                    # 核心通信框架
│   ├── message.py          # 消息 Schema
│   ├── agent.py            # BaseAgent 基类
│   ├── checkpoint.py       # Checkpoint 管理
│   └── router.py           # 消息路由器
├── agents/                 # Agent 实现
│   ├── research_agent.py   # 研究 Agent
│   └── writer_agent.py     # 写作 Agent
├── dashboard/              # 可观测性 Dashboard
│   └── server.py           # Flask 服务器
├── system_root/            # 运行时文件系统
│   ├── registry/           # Agent 注册表
│   ├── agents/             # Agent 私有空间
│   ├── bus/                # 公共总线
│   ├── archive/            # 已完成消息归档
│   └── behavior_archive/   # 行为沉淀
├── run_demo.py             # 演示脚本
└── requirements.txt        # 依赖
```

## 核心特性

### 1. 文件系统驱动通信

- **Write-then-Move 原子操作**：确保消息完整性
- **Inbox 监听**：使用 watchdog 监听文件事件
- **无共享内存**：Agent 完全隔离

### 2. 分层 Checkpoint 机制

- **步骤级 Checkpoint**：Task 消息的每一步都可恢复
- **结果级 Checkpoint**：Result 消息的进度记录
- **PID 检测**：自动检测崩溃的 Agent 进程

### 3. 智能路由

- **直投模式**：已知目标直接投递
- **Bus 兜底**：未知目标走公共总线
- **置信度分级**：高信心直投，低信心走专家判定

### 4. 可观测性 Dashboard

- **实时状态展示**：Agent 状态、消息队列、错误统计
- **SSE 推送**：实时事件流
- **完整审计追踪**：所有消息流转记录

## 演示流程

1. 启动 `research_agent` 和 `writer_agent`
2. 发送 Task 消息给 `research_agent`
3. `research_agent` 处理后发送 Result 给 `writer_agent`
4. `writer_agent` 处理后归档消息
5. Dashboard 实时展示整个流程

## 预留接口

### LLM 集成

在 `BaseAgent.call_llm()` 中集成真实 LLM（如 Claude API）：

```python
def call_llm(self, prompt: str) -> str:
    # TODO: 接入 Claude API
    from anthropic import Anthropic
    client = Anthropic()
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text
```

### 向量化索引

在 `router.py` 中集成 LanceDB 进行经验复用：

```python
from lancedb import connect
db = connect("./vector_db")
table = db.create_table("experiences", data=[...])
results = table.search(query_embedding).limit(5).to_list()
```

## 测试场景

### 场景 1：正常流程

1. 发送 Task 消息
2. Agent 处理并返回 Result
3. 消息归档

### 场景 2：崩溃恢复

1. 启动 Agent
2. 发送 Task 消息
3. 手动 kill Agent 进程
4. 重启 Agent
5. 验证 checkpoint 恢复

### 场景 3：路由决策

1. 发送 receiver 为空的消息
2. 路由器根据 command 分类
3. 消息投递到匹配的 Agent 或 bus

## 下一步

- [ ] 集成真实 LLM（Claude API）
- [ ] 实现向量化索引（LanceDB）
- [ ] 添加更多 Agent 类型
- [ ] 实现分布式部署（跨进程/跨机器）
- [ ] 性能优化（批量处理、缓存）
- [ ] 完整的单元测试和集成测试
