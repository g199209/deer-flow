# 目标系统架构愿景

> 基于 DeerFlow 二次开发，构建事件驱动的多 Agent 调度系统。

---

## 核心问题：当前 DeerFlow 的局限

| 问题 | 现状 | 目标 |
|------|------|------|
| Lead 阻塞等待 | `task_tool` 用 `while True + sleep(5)` 轮询，阻塞 LangGraph 节点 | 事件驱动，Lead 立即可响应 |
| 用户无法打断 | 流式期间无法注入新消息 | 随时可发送新指令给 Lead |
| 子任务完成无实时回调 | Lead 不知道子任务何时完成，只能轮询 | 子任务完成即通知 Lead，立即决策 |
| 模型固定 | 子 Agent 模型在配置文件里预设 | Lead 动态决定每个子 Agent 用什么模型 |
| 并发上限写死 | `MAX_CONCURRENT_SUBAGENTS = 3`，硬编码夹逼在 [2,4] | 可配置，支持 10+ 并发 |

---

## 目标架构：事件驱动 Actor 模型

### Lead Agent 状态机

```
                    ┌─────────────────────────────────────┐
                    │           Lead Agent                 │
                    │                                      │
  用户输入 ──────→  │  IDLE → PLANNING → DELEGATING       │
                    │              ↓           ↓           │
  用户打断 ──────→  │         INTERRUPTED   PARTIAL        │
                    │              ↓      RESULTS ↓        │
  子任务完成 ────→  │         RE-PLANNING ← ─ ─ ─ ┘       │
                    │              ↓                       │
                    │         SYNTHESIZING → DONE          │
                    └─────────────────────────────────────┘
```

### 关键特性

#### 1. 事件驱动调度（不阻塞）
Lead Agent 本身是一个事件循环：
- 收到 `user_message` → 规划并分发子任务
- 收到 `subagent_completed(id, result)` → 判断：够了就合成，不够就补发子任务
- 收到 `user_interrupted(new_instruction)` → 可以：中止部分子任务、调整计划、立即回应用户
- 收到 `subagent_failed(id, error)` → 决定重试或忽略

Lead 不阻塞等待，永远可响应。

#### 2. 用户随时可打断
流式输出过程中，用户可以：
- 发新消息追加指令（"再加一个维度分析一下XX"）
- 发新消息中止（"不用了，先给我个初步结论"）
- 这些消息作为事件注入 Lead 的事件队列

#### 3. 子任务完成即回调
子 Agent 运行在独立协程/线程，完成后：
- 立即发布 `subagent_completed` 事件到 Lead 的事件队列
- Lead 可在第一时间决策是否需要新的子任务
- 不再依赖轮询

#### 4. 动态模型分配
Lead 在分配子任务时，可以在 prompt 中指定：
```json
{
  "task": "分析美联储政策",
  "model": "claude-opus-4",        // Lead 动态决定
  "tools": ["web_search"],
  "max_turns": 5
}
```
支持按任务类型选择合适的模型（便宜快的用于数据收集，强力的用于深度分析）。

#### 5. 双向流通信
不仅 SubAgent → Lead，也支持 Lead → SubAgent 注入消息：
- Lead 发现某个子任务方向跑偏，可以中途注入修正指令
- 类似 Google ADK 的 `LiveRequestQueue`

---

## 理想的 SSE 事件流（从用户视角）

```
用户发送: "预测纳斯达克下周走势"

→ [Lead] 好的，我从10个维度展开分析...
→ [子任务1: 宏观数据] 启动
→ [子任务2: 技术面] 启动
→ ... (共10个)

→ [子任务3] 正在搜索美联储声明...
→ [子任务1] 完成: CPI 3.1%，通胀下行...
→ [子任务5] 完成: RSI 55，均线多头...

→ [Lead] 部分结果已回来，发现几个关键信号，追加3个专项...
→ [子任务11: AI资本开支] 启动
→ ...

         ↑ 用户此时可以发送: "重点分析一下AI板块"

→ [Lead] 收到，我调整了两个子任务的重点方向...

→ ... 所有子任务完成 ...
→ [Lead] [综合报告 Markdown]
```

---

## 技术选型分析

### 方案一：基于 LangGraph 改造
**可行但受限**：
- LangGraph 是图执行引擎，为 turn-based 设计
- 要实现事件驱动需要把 Lead 节点改成长轮询异步循环，违背框架设计
- `task_tool` 的 polling 模式难以根治
- 双向通信需要额外的 Queue 机制绕过 LangGraph

### 方案二：基于 Google ADK 重构核心引擎
**推荐**：
- `ParallelAgent`：asyncio.TaskGroup 真并行，事件合并
- `LiveRequestQueue`：内置双向通信 channel
- per-Agent model：每个 Agent 可独立指定模型
- 内置 HTTP/SSE 服务器，兼容前端现有协议

### 方案三：基于 AutoGen 0.4 Core
- 真正的 Actor 模型：`send_message` / `publish_message`
- `CancellationToken`：优雅中止
- 但 HTTP/SSE 层需要自己搭

---

## 可复用的 DeerFlow 资产（约 40-50%）

| 模块 | 复用价值 | 备注 |
|------|----------|------|
| 前端 (Next.js) | ✅ 高 | 已有完整的 SubtaskCard、流式渲染、线程管理 |
| Gateway API | ✅ 高 | Models/Skills/Memory/MCP/Uploads 接口完整 |
| 工具集 (tavily/jina/firecrawl 等) | ✅ 高 | 直接复用 |
| Memory 系统 | ✅ 中 | 异步更新队列 + 事实提取 |
| Sandbox 系统 | ✅ 中 | 本地/Docker 路径隔离 |
| Skills 系统 | ✅ 中 | .skill 格式、安装、加载 |
| 配置系统 | ✅ 中 | config.yaml mtime 热重载 |
| Nginx 路由 | ✅ 高 | 直接复用 |
| LangGraph Agent 执行核心 | ❌ 替换 | 替换为 ADK/AutoGen |
| Middleware chain | ⚠️ 部分 | 把有价值的逻辑移出到新框架 |
| SubagentExecutor (polling) | ❌ 替换 | 改为事件驱动 |

---

## 开发路线图（建议）

### Phase 0（已完成）：Mock Demo
在 `demo/mock-backend` 分支实现无 LLM 的 mock server，验证前后端协议。

### Phase 1：核心引擎替换
- 用 ADK `ParallelAgent` + `LiveRequestQueue` 替换 LangGraph 执行核心
- 实现事件驱动的 Lead Agent 调度循环
- 保持 SSE 协议不变（前端不动）

### Phase 2：双向通信
- 实现用户消息注入到运行中的 Lead
- 实现 Lead → SubAgent 的指令注入
- 前端添加"打断"按钮

### Phase 3：动态模型分配
- Lead prompt 中支持 `model` 字段
- SubAgent 工厂根据 Lead 指定的 model 动态创建

### Phase 4：生产化
- 持久化（见下方持久化设计）
- 多用户隔离
- 可观测性（tracing/metrics）

---

## 持久化设计：双存储分离

### 核心原则

对话状态需要服务两个不同目的，用一套存储难以兼顾：

| 需求 | 消费方 | 数据格式 |
|------|--------|---------|
| 向用户展示历史消息 | 前端 / LangGraph 兼容 API | LangGraph message dict 格式 |
| 恢复 Agent 上下文继续对话 | 执行引擎（ADK 等） | 引擎内部 Event 格式 |

### 两套存储各司其职

```
Display Store (SQLite)              ADK Store (SqliteSessionService)
──────────────────────              ────────────────────────────────
thread_id                           app_name + user_id + session_id
title                               ADK Event 列表
messages (LangGraph 格式 JSON)       state dict
created_at / updated_at             ADK 内部元数据
```

**Display Store**：自己建表，schema 完全自定义，只服务前端展示。
**ADK Store**：用 ADK 内置的 `SqliteSessionService`，ADK Runner 自动维护。

### 写入时机（流式过程中并行写）

```
ADK Event 产生
    ├── 转换为 LangGraph 消息格式 → 写 Display Store
    └── ADK SessionService 自动写 ADK Store
```
两个写入互相独立，无需事务。

### 恢复时机

```python
# 前端请求历史 → 从 Display Store 读（快，格式直接可用）
GET /threads/{id}/history
→ SELECT messages FROM display_threads WHERE id = ?

# 用户发新消息 → 从 ADK Store 恢复上下文
session = await adk_session_service.get_session(session_id=thread_id)
# ADK 加载完整 Event 历史，模型知道完整对话上下文
async for event in runner.run_async(session_id=thread_id, new_message=...):
    await update_display_store(thread_id, event)
    # ADK SessionService 同步更新自己
```

### 一致性策略

以 **ADK Store 为权威**（决定模型上下文），Display Store 只影响展示：
- 崩溃恢复：ADK Store 完整 → Agent 可正常续聊；Display Store 少几条 → 用户界面少几条消息，可接受
- 未来换执行引擎：替换 ADK Store 对应实现，Display Store 和前端完全不动

### 优势

- Display Store schema 不受任何框架约束，自由扩展（加标签、摘要、搜索索引等）
- 执行引擎可替换（ADK → 其他），Display Store / 前端零改动
- 两套存储可独立迁移到 Postgres
