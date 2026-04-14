# Agent 间通信黑板模式系统

> 将 Agent 间的通信完全从"内存上下文传递"转为"文件系统驱动"，实现基于黑板模式的分布式 Agent 协作框架。

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 📋 目录

- [项目概述](#项目概述)
- [核心特性](#核心特性)
- [快速开始](#快速开始)
- [系统架构](#系统架构)
- [通信协议](#通信协议)
- [关键机制](#关键机制)
- [行业验证](#行业验证)
- [优缺点对比](#优缺点对比)
- [项目结构](#项目结构)
- [预留接口](#预留接口)

---

## 项目概述

本项目探索一种新的 Agent 协作范式：**不依赖内存上下文共享，而是通过文件系统作为通信总线**。

这种设计特别适合：
- 🔄 **超长任务**：支持断点恢复，系统宕机后能从中断点继续
- 📊 **高可观测性**：所有通信都是文件，支持完整审计追踪和回放
- 🔗 **跨语言协作**：任何能读写文件的语言都能参与
- 🛡️ **安全隔离**：OS 级权限控制，支持 PII 脱敏

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **黑板模式** | Agent 通过共享文件系统通信，无内存耦合 |
| **分层 Checkpoint** | 支持步骤级、结果级、轻量级三层恢复粒度 |
| **智能路由** | 基于置信度的自适应分流 + 行为学习 |
| **向量化索引** | 归档消息自动生成 Embedding，支持经验复用 |
| **完整生命周期** | Agent 注册/注销、心跳检测、僵尸恢复 |
| **可观测性** | 实时 Dashboard + 完整审计日志 |
| **安全隔离** | 目录权限隔离 + 敏感数据脱敏 |

---

## 快速开始

### 前置要求

- Python 3.8+
- pip

### 安装与运行

```bash
# 进入原型目录
cd prototype

# 安装依赖
pip install -r requirements.txt

# 运行演示
python run_demo.py

# 打开浏览器访问 Dashboard
# http://localhost:5000
```

### 演示流程

1. 启动 `research_agent` 和 `writer_agent`
2. 发送 Task 消息给 research_agent（command: research）
3. research_agent 处理后发送 Result 给 writer_agent
4. writer_agent 收到 Result 后归档
5. Dashboard 实时展示整个流程

---

## 系统架构

### 核心目录结构

```
/system_root
│
├── /registry             # 注册表：所有活跃 Agent 的元数据
│   └── agent_a.json
│
├── /agents               # Agent 私有空间
│   ├── /agent_a
│   │   ├── /inbox        # 待处理任务（只读）
│   │   ├── /outbox       # 已外发消息（备份）
│   │   └── /workspace    # 运行时临时草稿
│   └── /agent_b
│
├── /bus                  # 公共总线（核心通信区）
│   ├── /pending          # 提交后等待路由的消息
│   └── /dead_letter      # 无法解析或超时的消息
│
├── /archive              # 已完成任务归档 + 向量化索引
│
└── /shared_storage       # 大规模数据参考区（PDF、数据库镜像等）
```

### 消息生命周期

```
[Agent A 产生任务]
      │
      ▼
┌──────────┐   write-then-move    ┌──────────────┐
│ workspace │ ─────────────────► │  bus/pending  │  (目标未知时)
│  (草稿)   │                    └──────┬───────┘
└──────────┘                           │ Router 分流
      │                                ▼
      │ 目标已知，直投          ┌──────────────┐
      └───────────────────────► │  Agent B     │
                                │   /inbox     │
                                └──────┬───────┘
                                       │
                        ┌──────────────┼──────────────┐
                        │              │              │
                        ▼              ▼              ▼
                  [崩溃/中断]      [执行中]        [完成]
                        │              │              │
                        ▼              ▼              ▼
                 ┌────────────┐  ┌──────────┐  ┌──────────────┐
                 │ checkpoint │  │workspace │  │  成功 Result  │
                 │  恢复断点  │  │ 中间产物  │  │  → 目标inbox │
                 └─────┬──────┘  └──────────┘  └──────┬───────┘
                       │                               │
                       └──────────────┬────────────────┘
                                      │
                            ┌─────────┴──────────┐
                            │                    │
                            ▼                    ▼
                     [任务失败]            [任务成功]
                            │                    │
                            ▼                    ▼
                  ┌──────────────────┐   ┌──────────────────────────┐
                  │  bus/dead_letter │   │  /archive + 向量化索引    │
                  │  (错误日志回发)   │   │  (Summary + Embedding)   │
                  └──────────────────┘   └──────────────────────────┘
```

---

## 通信协议

### 消息类型分层

| 消息类型 | 说明 | Checkpoint 粒度 |
|---------|------|----------------|
| **Task** | 请求执行一个任务 | 步骤级：`{task_id}.step_{n}.checkpoint.json` |
| **Result** | 任务执行结果 | 结果级：`{task_id}.result.checkpoint.json` |
| **Signal** | 轻量级信号（心跳、取消等） | 轻量标记：`{signal_id}.ack` |
| **Artifact** | 大文件引用 | 无需 checkpoint |

### 消息格式示例

```json
{
  "metadata": {
    "message_id": "uuid-v4",
    "type": "task",
    "sender": "research_agent",
    "receiver": "writer_agent",
    "timestamp": "2026-04-12T09:49:00Z",
    "priority": "high",
    "status": "new",
    "pid": 12345
  },
  "payload": {
    "command": "summarize",
    "file_refs": ["/shared_storage/report_v1.pdf"],
    "content": "请根据该文件生成 500 字摘要。"
  }
}
```

---

## 关键机制

### A. 原子写入（Write-then-Move）

防止读到残缺文件：
1. Agent 在自己的 `/workspace` 下写完临时文件
2. 使用 `rename()` 原子操作将文件移动到目标 Agent 的 `/inbox`

### B. 事件驱动监听

- **Linux**: `inotify` 驱动
- **跨平台**: Python `watchdog` 库

### C. 分层 Checkpoint 恢复

**Task 消息** → 步骤级 checkpoint
- 记录已完成的步骤序号、中间结果、当前状态
- 重启后快速定位到最后一个有效步骤

**Result 消息** → 结果级 checkpoint
- 记录结果生成的进度

**Signal 消息** → 轻量级标记
- 只需确认已收到

### D. 智能路由与自学习

```
高信心 (>0.9)  ──► 本地 SLM 直接路由
                   
低信心 (<0.6)  ──► /bus/pending + needs_expert 标签
                   ↓
                   高参数量模型判定
                   ↓
                   结果写回训练集
```

### E. Agent 生命周期管理

- **注册**: 启动时在 `/registry/{agent_name}.json` 写入元数据
- **心跳**: 定期更新 `last_seen` 时间戳
- **僵尸检测**: 监控系统检查超期 Agent，自动重新路由任务
- **能力声明**: Agent Card 中声明支持的 command 类型

### F. 可观测性设计

- **审计日志**: `/audit` 目录按时间分桶存储已完成消息
- **实时 Dashboard**: 基于文件系统 watch 的 Web UI
- **回放能力**: 完整重现任务流程用于调试
- **向量化索引**: 自动生成 Embedding，支持语义搜索和经验复用

### G. 安全与隔离

- **目录权限**: OS 级权限控制，限制 Agent 访问范围
- **PII 脱敏**: Privacy Agent 在消息进入 `/bus` 前进行敏感数据清洗

---

## 行业验证

### 竞品对比

| 框架 | 通信模型 | 核心特点 |
|------|---------|---------|
| **AutoGen v0.4** | Actor 模型 + 异步消息 | 内存驱动，支持 gRPC 分布式 |
| **CrewAI** | 任务链 + 委托 | 隐式通信，通过 Task 输出传递 |
| **LangGraph** | 共享状态图 | 有状态图，所有 Node 共享 State |
| **Google A2A** | HTTP + JSON-RPC | 跨组织协议，基于 HTTP |
| **MCP** | Tool/Resource 接口 | Agent 与工具连接，非 Agent 间通信 |

### 学术与工业验证

- **arxiv 2603.16021**: "Folder Structure as Agent Architecture" - 用文件夹结构作为 Agent 编排架构
- **1Password 博客**: "Agents are making filesystems cool again" - 文件系统是原生协作基础设施
- **Claude Code**: 实际采用文件驱动的 Agent 协作模式

### 协议栈定位

```
┌─────────────────────────────────────┐
│  A2A (跨组织 Agent 发现与协作)       │  ← HTTP/JSON-RPC
├─────────────────────────────────────┤
│  本方案 (同系统内 Agent 通信)        │  ← 文件系统
├─────────────────────────────────────┤
│  MCP (Agent 与工具/数据源连接)       │  ← Tool/Resource 接口
└─────────────────────────────────────┘
```

---

## 优缺点对比

| 维度 | 文件系统通信 | 内存/上下文传递 |
|------|------------|----------------|
| **持久化** | ⭐⭐⭐⭐⭐ 极强，支持断点恢复 | ⭐ 弱，进程崩溃丢失上下文 |
| **调试性** | ⭐⭐⭐⭐⭐ 极佳，直观查看通信历史 | ⭐⭐ 难，需复杂日志系统 |
| **延迟** | ⭐⭐⭐ 较高，受磁盘 I/O 限制 | ⭐⭐⭐⭐⭐ 极低，纳秒级 |
| **扩展性** | ⭐⭐⭐⭐⭐ 跨语言、跨容器容易 | ⭐⭐ 耦合度高，框架限制 |
| **可观测性** | ⭐⭐⭐⭐⭐ 极强，支持回放和审计 | ⭐⭐ 弱，需额外追踪系统 |
| **安全隔离** | ⭐⭐⭐⭐⭐ 强，OS 级权限控制 | ⭐⭐ 弱，内存共享易越权 |

---

## 项目结构

```
探索交互/
├── README.md                    # 本文件
├── 探索交互.md                  # 详细设计文档
├── 记忆体.md                    # 项目沟通记录
│
└── prototype/                   # 可运行原型
    ├── core/
    │   ├── message.py          # 消息 Schema
    │   ├── agent.py            # BaseAgent 基类
    │   ├── checkpoint.py       # 分层 Checkpoint 管理
    │   └── router.py           # 路由器
    ├── agents/
    │   ├── research_agent.py   # Mock 研究 Agent
    │   └── writer_agent.py     # Mock 写作 Agent
    ├── dashboard/
    │   └── server.py           # Flask Dashboard
    ├── system_root/            # 运行时文件系统
    ├── run_demo.py             # 一键演示脚本
    └── requirements.txt        # 依赖列表
```

---

## 预留接口

| 接口 | 位置 | 说明 | 优先级 |
|------|------|------|--------|
| LLM 集成 | `core/agent.py` → `call_llm()` | 接入 Claude API | 高 |
| 分类器升级 | `core/router.py` → `_classify_message()` | sklearn/LLM 分类 | 中 |
| 向量化索引 | `core/agent.py` → 归档时 | LanceDB 经验复用 | 中 |
| 安全隔离 | 未实现 | OS 权限控制 + PII 脱敏 | 中 |
| 崩溃恢复演示 | `core/checkpoint.py` | 手动 kill 进程验证 | 低 |

---

## 进阶建议

### 虚拟化文件系统

如果对物理磁盘寿命有顾虑，可使用内存文件系统：

```bash
# Linux
sudo mount -t tmpfs -o size=1G tmpfs /mnt/ramdisk

# macOS
diskutil secureErase freespace 0 -secureRandom 1G /Volumes/RAMDisk
```

这样既保留"一切皆文件"的设计逻辑，又获得接近内存传递的速度。

---

## 设计总结

这种模式将 Agent 视为一个**处理文件的流水线工人**。它不关心谁给的任务，只关心自己的 `/inbox` 文件夹里出现了什么，并把处理完的结果丢进下一个人的文件夹。

通过分层 checkpoint、智能路由、行为沉淀、向量化索引和安全隔离，这个系统可以支持：

✅ 超长任务的可靠执行（通过 checkpoint 恢复）  
✅ 自适应的路由决策（通过本地分类器 + 行为学习）  
✅ 经验复用（通过向量化索引）  
✅ 完整的可观测性和审计追踪（通过文件系统的天然特性）  
✅ 跨语言、跨容器的互操作（通过文件作为通用接口）

---

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 联系方式

如有问题或建议，欢迎提交 Issue 或 Pull Request。
