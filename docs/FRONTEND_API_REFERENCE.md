# DeerFlow 前后端接口参考

> 本文档覆盖前端与两个后端服务的完整交互协议，以及调试 mock server 过程中发现的重要陷阱。

---

## 架构概览

```
前端 (Next.js :3000)
    │
    ├─ /api/langgraph/*  → nginx → LangGraph Server (:2024)
    └─ /api/*            → nginx → Gateway API (:8001)

环境变量覆盖（直连，跳过 nginx）：
    NEXT_PUBLIC_LANGGRAPH_BASE_URL=http://localhost:2024
    NEXT_PUBLIC_BACKEND_BASE_URL=http://localhost:2024
```

---

## 一、LangGraph Server API（:2024）

前端通过 `@langchain/langgraph-sdk` 的 `Client` 和 `useStream` hook 调用。

### 1.1 `POST /assistants/search`

**触发时机**：页面加载，`getAPIClient()` 初始化时
**作用**：获取 `assistant_id`，后续所有流式调用都用它
**请求体**：`{}` 或 `{graph_id: "lead_agent"}`
**响应**：
```json
[{
  "assistant_id": "bee7d354-...",
  "graph_id": "lead_agent",
  "name": "lead_agent",
  "metadata": {},
  "config": {},
  "created_at": "...",
  "updated_at": "..."
}]
```

---

### 1.2 `POST /threads`

**触发时机**：用户发起新对话
**请求体**：`{"thread_id": "可选，SDK 会自动生成"}` 或 `{}`
**响应**：
```json
{
  "thread_id": "uuid",
  "created_at": "ISO datetime",
  "updated_at": "ISO datetime",
  "metadata": {},
  "status": "idle",
  "values": {"messages": [], "title": null}
}
```

---

### 1.3 `POST /threads/search`

**触发时机**：页面加载、对话完成后（刷新侧边栏线程列表）
**请求体**：`{"limit": 50, "offset": 0, "sort_by": "updated_at", "sort_order": "desc", "select": ["thread_id", "updated_at", "values"]}`
**响应**：线程对象数组（同 1.2 结构）

---

### 1.4 `GET /threads/{thread_id}`

**触发时机**：导航到某个线程时
**响应**：单个线程对象

---

### 1.5 `DELETE /threads/{thread_id}`

**触发时机**：用户删除对话
**响应**：`{"status": "ok"}`

---

### 1.6 `POST /threads/{thread_id}/history` ⚠️ 陷阱

**触发时机**：进入已有线程时，`useStream(fetchStateHistory: {limit: 1})` 触发
**陷阱**：SDK 的 `client.threads.getHistory()` 用的是 **POST**，不是 GET！实现时若只注册 GET 会返回 405。
**请求体**：`{"limit": 1, "before": null, "metadata": null, "checkpoint": null}`
**响应**：状态快照数组：
```json
[{
  "values": {"messages": [...], "title": "..."},
  "next": [],
  "checkpoint": {
    "thread_id": "uuid",
    "checkpoint_id": "uuid",
    "checkpoint_ns": ""
  },
  "metadata": {},
  "created_at": "...",
  "parent_checkpoint": null
}]
```
历史为空时返回 `[]`。

---

### 1.7 `GET /threads/{thread_id}/state`

**触发时机**：`fetchStateHistory: false` 时，或 SDK 内部需要当前状态
**响应**：同 1.6 中的单个快照对象

---

### 1.8 `POST /threads/{thread_id}/runs/stream` ← 核心端点

**触发时机**：用户发送消息，`thread.submit()` 调用
**请求体**：
```json
{
  "input": {
    "messages": [{
      "type": "human",
      "content": [{"type": "text", "text": "用户输入"}],
      "additional_kwargs": {}
    }]
  },
  "config": {
    "recursion_limit": 1000,
    "configurable": {}
  },
  "context": {
    "thinking_enabled": true,
    "is_plan_mode": false,
    "subagent_enabled": true,
    "model_name": "...",
    "thread_id": "uuid"
  },
  "stream_mode": ["messages-tuple", "values", "updates", "custom"],
  "stream_subgraphs": true,
  "stream_resumable": true
}
```

**响应**：`Content-Type: text/event-stream`，SSE 格式。
详见下方 SSE 事件规范。

---

### 1.9 其他 Run 管理端点（Stub 即可）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/threads/{id}/runs` | GET | 列出 runs，返回 `[]` |
| `/threads/{id}/runs` | POST | 创建 run，返回 `{run_id, status: "pending"}` |
| `/threads/{id}/runs/{run_id}` | GET | 返回 `{run_id, status: "success"}` |
| `/threads/{id}/runs/{run_id}/cancel` | POST | 返回 `{status: "ok"}` |

---

## 二、SSE 事件规范 ⚠️ 关键

所有事件格式：
```
event: <event_type>
data: <json>

```
（每个事件以空行结束）

### ⚠️ 最大陷阱：messages 事件格式

SDK `useStream` hook 内部处理的是 **`event: messages`**（messages-tuple 模式），
**不是** `event: messages/complete`！

`matchEventType("messages", event)` 只匹配：
- `event === "messages"`（精确匹配）
- `event.startsWith("messages|")`（子图命名空间，如 `messages|subgraph_ns`）

`messages/complete` 会被完全忽略，所有消息只在最后的 `values` 事件时才一起渲染。

**正确格式**：
```
event: messages
data: [{"type": "ai", "id": "msg-xxx", "content": "...", "tool_calls": []}, {}]
```
Data 是二元组 `[message_dict, metadata_dict]`，`metadata` 可为空对象 `{}`。

---

### 2.1 `event: metadata`

```json
{"run_id": "uuid", "attempt": 1}
```
第一个事件，SDK 用于记录本次 run 的 ID。

---

### 2.2 `event: messages`（messages-tuple 模式）

数据格式：`[message_dict, metadata_dict]`

**Human 消息**（echo 用户输入）：
```json
[{
  "type": "human",
  "id": "hm-xxx",
  "content": "用户输入文本",
  "additional_kwargs": {},
  "response_metadata": {}
}, {}]
```

**AI 消息（纯文本）**：
```json
[{
  "type": "ai",
  "id": "ai-xxx",
  "content": "助手回复文本",
  "tool_calls": [],
  "additional_kwargs": {},
  "response_metadata": {}
}, {}]
```

**AI 消息（带 task tool_calls）** → 触发 SubtaskCard 渲染：
```json
[{
  "type": "ai",
  "id": "ai-xxx",
  "content": "",
  "tool_calls": [{
    "name": "task",
    "id": "tc-xxx",
    "args": {
      "description": "子任务标题",
      "prompt": "子任务详细 prompt",
      "subagent_type": "general-purpose"
    }
  }],
  "additional_kwargs": {},
  "response_metadata": {}
}, {}]
```
每个 `tool_calls` 中的 `task` 条目对应一个 SubtaskCard。

**Tool 消息（子任务结果）** → 更新 SubtaskCard 状态：
```json
[{
  "type": "tool",
  "id": "tm-xxx",
  "tool_call_id": "tc-xxx",  // 与 task tool_call 的 id 对应
  "content": "Task Succeeded. Result: 具体结果文本",
  "additional_kwargs": {}
}, {}]
```
`content` 以 `"Task Succeeded. Result: "` 开头 → SubtaskCard 变为 completed。

---

### 2.3 `event: custom`

SDK 通过 `onCustomEvent` 回调处理。

**task_started**：通知子任务启动
```json
{"type": "task_started", "task_id": "tc-xxx", "description": "子任务描述"}
```

**task_running**：子任务进度更新（更新 SubtaskCard 的 latestMessage）
```json
{
  "type": "task_running",
  "task_id": "tc-xxx",
  "message": {"type": "ai", "id": "...", "content": "正在搜索...", "tool_calls": []},
  "message_index": 1,
  "total_messages": 1
}
```
`message` 字段是一个 AI 消息对象，显示在 SubtaskCard 的展开详情里。

**task_completed**：
```json
{"type": "task_completed", "task_id": "tc-xxx", "result": "结果文本"}
```

**task_failed**：
```json
{"type": "task_failed", "task_id": "tc-xxx", "error": "错误信息"}
```

---

### 2.4 `event: values`

发送完整状态快照，触发 `setStreamValues(data)`：
```json
{
  "messages": [...],
  "title": "对话标题"
}
```
推荐在流结束前发送一次，作为最终状态。SDK 会用它覆盖本次流式积累的状态。

---

### 2.5 `event: updates`

发送节点更新差量，触发 `onUpdateEvent` 回调：
```json
{"lead_agent": {"title": "对话标题"}}
```
前端 `hooks.ts` 在这里提取 `title` 字段并更新侧边栏。

---

### 2.6 `event: end`

```json
{}
```
流结束信号。

---

### SubtaskCard 完整渲染逻辑

`message-list.tsx` 处理流程：
1. 遇到 AI 消息 + `tool_calls[{name:"task"}]` → 为每个 tool_call 创建 `Subtask` 对象（`status: "in_progress"`）
2. `task_started` custom event → 激活 SubtaskCard 显示
3. `task_running` custom event → 更新 `latestMessage`（进度文字）
4. 遇到 tool 消息 + `tool_call_id` 匹配 → 更新状态
   - content 含 `"Task Succeeded."` → `status: "completed"`
   - 否则 → `status: "failed"`

---

## 三、Gateway API（:8001）

FastAPI 应用，前端通过 `getBackendBaseURL()` 直接 fetch。

### 3.1 `GET /api/models` ⚠️ 必须可用

**触发时机**：聊天工作区加载时（InputBox 组件），是**页面级 eager load**
**响应**：
```json
{
  "models": [{
    "id": "model-id",
    "name": "model-name",
    "model": "gpt-4o",
    "display_name": "显示名称",
    "description": "描述（可 null）",
    "supports_thinking": false,
    "supports_reasoning_effort": false
  }]
}
```
此接口若返回错误，输入框的模型选择器无法渲染。

---

### 3.2 `GET /api/skills`

**触发时机**：用户打开 Skills 设置面板（按需加载）
**响应**：`{"skills": [...]}`

---

### 3.3 `GET /api/mcp/config`

**触发时机**：用户打开 Tools 设置面板（按需加载）
**响应**：`{"mcp_servers": {}}`

---

### 3.4 `PUT /api/mcp/config`

**触发时机**：用户保存 MCP 配置
**响应**：更新后的 config

---

### 3.5 `GET /api/memory`

**触发时机**：用户打开 Memory 设置面板（按需加载）
**响应**：
```json
{
  "version": "1.0",
  "lastUpdated": "ISO datetime",
  "user": {
    "workContext": {"summary": "", "updatedAt": "..."},
    "personalContext": {"summary": "", "updatedAt": "..."},
    "topOfMind": {"summary": "", "updatedAt": "..."}
  },
  "history": {
    "recentMonths": {"summary": "", "updatedAt": "..."},
    "earlierContext": {"summary": "", "updatedAt": "..."},
    "longTermBackground": {"summary": "", "updatedAt": "..."}
  },
  "facts": []
}
```

---

### 3.6 `POST /api/threads/{thread_id}/suggestions`

**触发时机**：流结束后，生成跟进问题建议
**响应**：`{"suggestions": ["问题1", "问题2"]}`
空数组也可，UI 会隐藏该区域。

---

### 3.7 `GET /health`

**触发时机**：健康检查
**响应**：`{"status": "ok"}`

---

## 四、Mock Server 快速搭建 Checklist

实现一个能跑通前端的最小 mock server 需要：

- [ ] `POST /assistants/search` → 返回固定 assistant
- [ ] `POST /threads` → 创建线程，存内存
- [ ] `POST /threads/search` → 返回线程列表
- [ ] `GET /threads/{id}` → 返回线程
- [ ] `DELETE /threads/{id}` → 删除线程
- [ ] `POST /threads/{id}/history` ← **必须是 POST，否则 405**
- [ ] `GET /threads/{id}/state`
- [ ] `POST /threads/{id}/runs/stream` → SSE 流，见第二节
- [ ] `GET /api/models` ← **必须成功，否则 InputBox 崩溃**
- [ ] `GET /api/mcp/config`
- [ ] `GET /api/skills`
- [ ] `GET /api/memory`
- [ ] `POST /api/threads/{id}/suggestions`
- [ ] `GET /health`

---

## 五、SSE 流正确顺序模板

```
event: metadata
data: {"run_id": "...", "attempt": 1}

event: messages
data: [{"type": "human", "id": "hm-1", "content": "用户输入", ...}, {}]

event: messages
data: [{"type": "ai", "id": "ai-1", "content": "我来分析...", "tool_calls": []}, {}]

event: messages
data: [{"type": "ai", "id": "ai-2", "content": "", "tool_calls": [
  {"name": "task", "id": "tc-1", "args": {"description": "...", "prompt": "..."}},
  {"name": "task", "id": "tc-2", "args": {"description": "...", "prompt": "..."}}
]}, {}]

event: custom
data: {"type": "task_started", "task_id": "tc-1", "description": "..."}

event: custom
data: {"type": "task_started", "task_id": "tc-2", "description": "..."}

event: custom
data: {"type": "task_running", "task_id": "tc-1", "message": {"type": "ai", "content": "进行中..."}, ...}

event: custom
data: {"type": "task_completed", "task_id": "tc-1", "result": "结果"}

event: messages
data: [{"type": "tool", "tool_call_id": "tc-1", "content": "Task Succeeded. Result: 结果"}, {}]

event: messages
data: [{"type": "ai", "id": "ai-3", "content": "综合结论：...", "tool_calls": []}, {}]

event: values
data: {"messages": [...所有消息...], "title": "对话标题"}

event: updates
data: {"lead_agent": {"title": "对话标题"}}

event: end
data: {}
```
