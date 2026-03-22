"""
Mock LangGraph-compatible HTTP server for frontend demo.
No LLM — simulates a lead agent spawning 10 subagents, then 3 more, then synthesizing.

Run: uv run uvicorn mock_server:app --port 2024 --reload
"""

import asyncio
import json
import random
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

app = FastAPI(title="DeerFlow Mock LangGraph Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory storage ────────────────────────────────────────────────────────

_threads: dict[str, dict] = {}
_artifacts: dict[str, dict[str, tuple[str, str]]] = {}  # thread_id → {path → (content, mime)}
_ASSISTANT_ID = "bee7d354-5df5-5f26-a978-10ea053f620d"
_GRAPH_ID = "lead_agent"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_thread(thread_id: str | None = None) -> dict:
    tid = thread_id or str(uuid.uuid4())
    thread = {
        "thread_id": tid,
        "created_at": _now(),
        "updated_at": _now(),
        "metadata": {},
        "status": "idle",
        "values": {"messages": [], "title": None},
    }
    _threads[tid] = thread
    return thread


# ── Artifact content generators ──────────────────────────────────────────────

_PLOTLY_CHART_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>纳斯达克走势预测</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body { margin: 0; background: #0f1117; color: #e0e0e0; font-family: sans-serif; }
    #chart { width: 100%; height: 100vh; }
    h2 { text-align: center; padding: 12px 0 0; margin: 0; font-size: 15px; color: #a0aec0; }
  </style>
</head>
<body>
  <h2>纳斯达克综合指数 — 历史走势 + 下周预测区间</h2>
  <div id="chart"></div>
  <script>
    const days = ['3/3','3/4','3/5','3/6','3/7','3/10','3/11','3/12','3/13','3/14','3/17','3/18','3/19','3/20','3/21'];
    const close = [18120,18340,18290,18510,18480,18650,18720,18690,18830,18900,18780,18950,19020,19180,19250];
    const vol   = [3.2,4.1,3.8,4.5,3.9,3.6,4.2,3.7,4.8,5.1,3.4,4.0,4.6,5.3,4.9];

    const forecast_days = ['3/24','3/25','3/26','3/27','3/28'];
    const fc_mid  = [19380,19450,19520,19600,19680];
    const fc_high = [19580,19700,19820,19950,20080];
    const fc_low  = [19180,19200,19220,19250,19280];

    const traces = [
      {
        x: days, y: close, type: 'scatter', mode: 'lines+markers',
        name: '历史收盘', line: { color: '#63b3ed', width: 2 },
        marker: { size: 5 }
      },
      {
        x: [...forecast_days, ...forecast_days.slice().reverse()],
        y: [...fc_high, ...fc_low.slice().reverse()],
        fill: 'toself', fillcolor: 'rgba(104,211,145,0.15)',
        line: { color: 'transparent' }, name: '预测区间', showlegend: true
      },
      {
        x: forecast_days, y: fc_mid, type: 'scatter', mode: 'lines+markers',
        name: '预测中枢', line: { color: '#68d391', width: 2, dash: 'dash' },
        marker: { size: 6, symbol: 'diamond' }
      },
      {
        x: days, y: vol, type: 'bar', name: '成交量(亿)',
        marker: { color: 'rgba(160,174,192,0.3)' },
        yaxis: 'y2'
      }
    ];

    const layout = {
      paper_bgcolor: '#0f1117', plot_bgcolor: '#0f1117',
      font: { color: '#a0aec0', size: 12 },
      xaxis: { gridcolor: '#2d3748', showgrid: true },
      yaxis: { title: '指数点位', gridcolor: '#2d3748', tickformat: ',d' },
      yaxis2: { title: '成交量', overlaying: 'y', side: 'right', showgrid: false },
      legend: { bgcolor: 'rgba(0,0,0,0)', bordercolor: '#2d3748', borderwidth: 1 },
      margin: { t: 20, b: 40, l: 60, r: 60 },
      hovermode: 'x unified',
      shapes: [{ type: 'line', x0: '3/21', x1: '3/21', y0: 0, y1: 1,
                 yref: 'paper', line: { color: '#fc8181', width: 1, dash: 'dot' } }],
      annotations: [{ x: '3/21', y: 1, yref: 'paper', text: '今日', showarrow: false,
                      font: { color: '#fc8181', size: 11 }, xanchor: 'left', xshift: 4 }]
    };

    Plotly.newPlot('chart', traces, layout, { responsive: true, displayModeBar: false });
  </script>
</body>
</html>"""

_ANALYSIS_REPORT_MD = """# 纳斯达克下周走势分析报告

**生成时间**：2026-03-22　**分析师**：DeerFlow AI

---

## 执行摘要

综合 13 个维度的数据分析，**下周纳斯达克指数大概率延续上行趋势**，目标区间 **19,380–20,080 点**，核心概率分布如下：

| 情景 | 概率 | 目标区间 |
|------|------|---------|
| 上涨（>+1%） | **52%** | 19,600–20,080 |
| 震荡（-1%~+1%） | **30%** | 19,100–19,600 |
| 下跌（<-1%） | **18%** | <19,100 |

---

## 多头因素

### 1. 宏观面：通胀下行，降息预期升温
- CPI 同比 **+3.1%**，连续 3 个月回落
- 美联储鸽派表态增多，市场隐含降息概率升至 **68%**
- 实际利率压力减轻，科技股估值有望修复

### 2. 技术面：多头格局完整
- 日线 **MACD 金叉**，柱状图由负转正
- RSI 处于 **55** 中性偏强区域，无超买压力
- 20/60/120 日均线多头排列，支撑有效

### 3. 资金面：机构持续净买入
- 过去两周科技 ETF 净流入 **42 亿美元**
- QQQ 持仓量创近 **6 个月新高**
- 空头回补压力明显，Short Interest 下降 12%

### 4. 基本面：财报季催化
- 下周 FAANG 等龙头财报，**73% 分析师上调预期**
- AI 资本开支超预期（微软 Q2: 320 亿美元）
- 半导体 PMI **52.4**，景气度回升

---

## 空头风险

| 风险因素 | 影响程度 | 概率 |
|---------|---------|------|
| 核心 PCE 高于目标，降息延迟 | 中 | 35% |
| 财报不及预期触发抛售 | 高 | 20% |
| 地缘政治黑天鹅 | 高 | 10% |
| 美元走强压制估值 | 低 | 25% |

---

## 关键观察节点

1. **周三（3/26）**：美联储主席讲话，可能确认降息时间表
2. **周四（3/27）**：Alphabet + Microsoft 财报
3. **周五（3/28）**：PCE 数据公布，为月末仓位调整提供方向

---

> ⚠️ 本报告仅供参考，不构成投资建议。
"""


def _store_artifact(thread_id: str, path: str, content: str, mime: str) -> None:
    _artifacts.setdefault(thread_id, {})[path] = (content, mime)


# ── SSE helpers ──────────────────────────────────────────────────────────────

def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _msg_tuple(message: dict) -> str:
    """messages-tuple stream mode: data = [msg_dict, metadata_dict]"""
    return _sse("messages", [message, {}])


def _custom(payload: dict) -> str:
    return _sse("custom", payload)


# ── Mock message factories ───────────────────────────────────────────────────

def _human_msg(content: str) -> dict:
    return {
        "type": "human",
        "id": f"hm-{uuid.uuid4().hex[:12]}",
        "content": content,
        "additional_kwargs": {},
        "response_metadata": {},
    }


def _ai_msg(content: str = "", tool_calls: list | None = None) -> dict:
    return {
        "type": "ai",
        "id": f"ai-{uuid.uuid4().hex[:12]}",
        "content": content,
        "tool_calls": tool_calls or [],
        "additional_kwargs": {},
        "response_metadata": {},
    }


def _tool_msg(tool_call_id: str, content: str) -> dict:
    return {
        "type": "tool",
        "id": f"tm-{uuid.uuid4().hex[:12]}",
        "tool_call_id": tool_call_id,
        "content": content,
        "additional_kwargs": {},
    }


def _task_call(description: str, prompt: str) -> dict:
    return {
        "name": "task",
        "id": f"tc-{uuid.uuid4().hex[:12]}",
        "args": {
            "description": description,
            "prompt": prompt,
            "subagent_type": "general-purpose",
        },
    }


# ── Progress phrases for subagents ───────────────────────────────────────────

_PROGRESS_PHRASES = [
    "正在搜索相关数据...",
    "分析历史走势中...",
    "汇总信息，提炼要点...",
    "查询最新市场报告...",
    "对比多个数据源...",
    "计算相关性指标...",
    "整理技术指标数据...",
    "评估机构持仓变化...",
    "核对信息准确性...",
]


def _subagent_progress_msg(phrase: str | None = None) -> dict:
    text = phrase or random.choice(_PROGRESS_PHRASES)
    return _ai_msg(content=text)


# ── Core mock stream ─────────────────────────────────────────────────────────

async def _mock_stream(thread_id: str, user_message: str) -> AsyncGenerator[str, None]:
    run_id = str(uuid.uuid4())
    all_messages: list[dict] = []

    # ── 1. metadata ──────────────────────────────────────────────────────────
    yield _sse("metadata", {"run_id": run_id, "attempt": 1})

    # ── 2. Echo human message ─────────────────────────────────────────────────
    human = _human_msg(user_message)
    all_messages.append(human)
    yield _msg_tuple(human)
    await asyncio.sleep(0.3)

    # ── 3. Lead agent opening text ────────────────────────────────────────────
    lead_open = _ai_msg(
        content=(
            "好的，这是一个需要多维度数据支撑的预测任务。"
            "我将并行启动多个专项调研 Agent，从宏观、技术面、情绪面等10个维度同步展开分析。"
        )
    )
    all_messages.append(lead_open)
    yield _msg_tuple(lead_open)
    await asyncio.sleep(0.8)

    # ── 4. Lead spawns 10 subagents ───────────────────────────────────────────
    batch1_specs = [
        ("宏观经济数据", "调研美国最新通胀数据、PMI、非农就业，分析对纳斯达克的宏观影响"),
        ("美联储政策动向", "搜集最新FOMC会议纪要和委员讲话，判断利率预期对科技股的传导"),
        ("技术面分析", "分析纳斯达克近30日K线、均线系统、MACD、RSI等技术指标"),
        ("机构资金流向", "调研最新13F持仓报告和ETF资金净流入/流出数据"),
        ("期权市场情绪", "分析纳斯达克相关期权put/call比率、隐含波动率曲面"),
        ("科技龙头财报预期", "汇总FAANG等龙头下周财报预期，评估超预期/不及预期风险"),
        ("地缘政治风险", "评估当前地缘冲突、中美关系对科技供应链的潜在冲击"),
        ("历史季节性规律", "分析近10年同期纳斯达克季节性表现规律和统计规律"),
        ("市场整体风险偏好", "评估VIX指数、信用利差、高收益债表现等风险情绪指标"),
        ("产业链景气度", "调研半导体、AI算力、云计算等核心板块最新景气度数据"),
    ]

    task_calls_1 = [_task_call(desc, prompt) for desc, prompt in batch1_specs]
    lead_dispatch1 = _ai_msg(tool_calls=task_calls_1)
    all_messages.append(lead_dispatch1)
    yield _msg_tuple(lead_dispatch1)
    await asyncio.sleep(0.2)

    # ── 5. task_started for all 10 ────────────────────────────────────────────
    for tc in task_calls_1:
        yield _custom({"type": "task_started", "task_id": tc["id"], "description": tc["args"]["description"]})
        await asyncio.sleep(0.05)

    # ── 6. Simulate concurrent subagent progress ──────────────────────────────
    # Randomly send progress events over ~8 seconds, then start completing

    active_tasks = list(task_calls_1)
    random.shuffle(active_tasks)

    # Send a few rounds of random progress updates
    for _round in range(4):
        await asyncio.sleep(random.uniform(1.2, 2.0))
        for tc in random.sample(active_tasks, k=min(4, len(active_tasks))):
            prog_msg = _subagent_progress_msg()
            yield _custom({
                "type": "task_running",
                "task_id": tc["id"],
                "message": prog_msg,
                "message_index": _round + 1,
                "total_messages": _round + 1,
            })
            await asyncio.sleep(0.08)

    # ── 7. First 5 subagents complete ─────────────────────────────────────────
    completing_first = task_calls_1[:5]
    still_running = task_calls_1[5:]

    result_snippets = [
        "通胀数据显示CPI同比+3.1%，核心PCE仍高于目标，但近3个月呈下行趋势，利好科技股估值修复。",
        "美联储官员鸽派表态增多，市场隐含降息概率上升至68%，利率敏感型科技股有望受益。",
        "纳斯达克日线MACD金叉信号出现，RSI处于55附近，均线多头排列，技术面偏乐观。",
        "过去两周机构资金净流入科技ETF达42亿美元，QQQ持仓量创近6个月新高。",
        "put/call比率降至0.72，隐含波动率小幅下行，期权市场显示投资者情绪偏乐观。",
    ]

    for i, tc in enumerate(completing_first):
        await asyncio.sleep(random.uniform(0.3, 0.7))
        result = result_snippets[i]
        yield _custom({"type": "task_completed", "task_id": tc["id"], "result": result})
        tool_msg = _tool_msg(tc["id"], f"Task Succeeded. Result: {result}")
        all_messages.append(tool_msg)
        yield _msg_tuple(tool_msg)

    # ── 8. While waiting for remaining 5, lead spawns 3 more ─────────────────
    await asyncio.sleep(1.5)

    # A couple more progress events from still-running tasks
    for tc in random.sample(still_running, k=3):
        prog_msg = _subagent_progress_msg("正在深度分析，汇总数据中...")
        yield _custom({
            "type": "task_running",
            "task_id": tc["id"],
            "message": prog_msg,
            "message_index": 3,
            "total_messages": 3,
        })
        await asyncio.sleep(0.1)

    # Lead decides to spawn 3 more based on partial results
    lead_intermediate = _ai_msg(
        content=(
            "前5个维度的结果已经返回，发现几个值得深挖的信号。"
            "我再补充启动3个专项调研来完善分析。"
        )
    )
    all_messages.append(lead_intermediate)
    yield _msg_tuple(lead_intermediate)
    await asyncio.sleep(0.5)

    batch2_specs = [
        ("AI资本开支跟踪", "追踪微软、谷歌、Meta等最新AI基础设施投资计划及执行进度"),
        ("散户情绪与社交媒体", "分析WallStreetBets、Twitter/X科技股相关讨论热度与情感"),
        ("跨市场相关性", "分析纳指与美债、美元指数、黄金近期相关性变化趋势"),
    ]
    task_calls_2 = [_task_call(desc, prompt) for desc, prompt in batch2_specs]
    lead_dispatch2 = _ai_msg(tool_calls=task_calls_2)
    all_messages.append(lead_dispatch2)
    yield _msg_tuple(lead_dispatch2)
    await asyncio.sleep(0.2)

    for tc in task_calls_2:
        yield _custom({"type": "task_started", "task_id": tc["id"], "description": tc["args"]["description"]})
        await asyncio.sleep(0.05)

    # ── 9. Remaining 5 from batch1 complete ───────────────────────────────────
    result_snippets_2 = [
        "下周财报季龙头超预期概率较高，分析师上调预期比例达73%，存在正向催化。",
        "当前地缘风险溢价处于近1年低位，对科技股影响有限，供应链压力缓解。",
        "近10年同期（3月末）纳斯达克上涨概率为70%，平均涨幅+1.8%，季节性偏有利。",
        "VIX跌破18，信用利差收窄，高收益债走强，整体风险偏好明显改善。",
        "半导体板块PMI回升至52.4，AI服务器出货量超预期，产业链景气度向好。",
    ]
    for i, tc in enumerate(still_running):
        await asyncio.sleep(random.uniform(0.4, 0.9))
        result = result_snippets_2[i]
        yield _custom({"type": "task_completed", "task_id": tc["id"], "result": result})
        tool_msg = _tool_msg(tc["id"], f"Task Succeeded. Result: {result}")
        all_messages.append(tool_msg)
        yield _msg_tuple(tool_msg)

    # ── 10. Batch2 (3 new) complete ───────────────────────────────────────────
    result_snippets_3 = [
        "微软Q2资本开支320亿美元超预期，谷歌TPU v5部署加速，AI基础设施投入不减反增。",
        "社交媒体科技股讨论热度上升34%，散户情绪指数回升至65（中性偏乐观区间）。",
        "纳指与10年美债收益率负相关性增强（-0.72），美元走弱将为纳指提供额外支撑。",
    ]
    for i, tc in enumerate(task_calls_2):
        await asyncio.sleep(random.uniform(0.5, 1.0))
        result = result_snippets_3[i]
        yield _custom({"type": "task_completed", "task_id": tc["id"], "result": result})
        tool_msg = _tool_msg(tc["id"], f"Task Succeeded. Result: {result}")
        all_messages.append(tool_msg)
        yield _msg_tuple(tool_msg)

    # ── 11. Lead final synthesis ──────────────────────────────────────────────
    await asyncio.sleep(1.2)

    final_text = """## 纳斯达克下周走势预测（综合13个维度分析）

### 核心判断：**短期偏乐观，目标区间上移**

---

### 多头因素（权重较高）

1. **宏观面**：CPI同比+3.1%，通胀下行趋势确立，美联储鸽派预期升温（降息概率68%），利率敏感型科技股估值压力减轻。

2. **技术面**：日线MACD金叉，RSI处于55中性偏强区域，均线多头排列，无明显超买压力。

3. **资金面**：机构两周净买入科技ETF 42亿美元，QQQ持仓量创6个月新高，大资金仍在主动加仓。

4. **财报催化**：下周财报季龙头超预期概率73%，正向催化窗口打开。

5. **产业链**：半导体PMI 52.4，AI资本开支持续超预期，基本面支撑逻辑完整。

6. **季节性**：历史同期上涨概率70%，平均+1.8%，统计规律偏有利。

---

### 空头因素（需关注）

- 核心PCE仍高于2%目标，降息时间表存在不确定性
- 美股整体估值偏高，若财报不及预期，回调风险较大
- 地缘政治黑天鹅风险无法完全排除

---

### 综合结论

**下周纳斯达克概率分布**：
- 上涨（>+1%）：**52%**
- 震荡（-1% ~ +1%）：**30%**
- 下跌（<-1%）：**18%**

建议关注周三财报数据和美联储官员讲话，作为阶段性方向确认的关键节点。

> ⚠️ 本分析仅供参考，不构成投资建议。市场存在不可预测风险，请结合个人风险承受能力决策。
"""

    final_msg = _ai_msg(content=final_text)
    all_messages.append(final_msg)
    yield _msg_tuple(final_msg)

    # ── 12. Generate artifacts ────────────────────────────────────────────────
    await asyncio.sleep(0.2)

    chart_path = "/mnt/user-data/outputs/nasdaq_forecast.html"
    report_path = "/mnt/user-data/outputs/analysis_report.md"
    _store_artifact(thread_id, chart_path, _PLOTLY_CHART_HTML, "text/html")
    _store_artifact(thread_id, report_path, _ANALYSIS_REPORT_MD, "text/markdown")

    artifact_paths = [chart_path, report_path]

    # Announce artifacts via present_files tool call + result
    present_call_id = f"tc-pf-{uuid.uuid4().hex[:8]}"
    present_ai = _ai_msg(tool_calls=[{
        "name": "present_files",
        "id": present_call_id,
        "args": {"paths": artifact_paths},
    }])
    all_messages.append(present_ai)
    yield _msg_tuple(present_ai)
    await asyncio.sleep(0.1)

    present_tool = _tool_msg(present_call_id, f"Files presented: {', '.join(artifact_paths)}")
    all_messages.append(present_tool)
    yield _msg_tuple(present_tool)

    # ── 13. values snapshot + title ───────────────────────────────────────────
    await asyncio.sleep(0.2)
    title = "纳斯达克下周走势预测分析"
    _threads[thread_id]["values"] = {"messages": all_messages, "title": title, "artifacts": artifact_paths}
    _threads[thread_id]["updated_at"] = _now()

    yield _sse("values", {"messages": all_messages, "title": title, "artifacts": artifact_paths})
    yield _sse("updates", {"lead_agent": {"title": title}})
    await asyncio.sleep(0.1)
    yield _sse("end", {})


# ── LangGraph-compatible endpoints ───────────────────────────────────────────

@app.get("/info")
async def info():
    return {
        "version": "mock-0.1.0",
        "graphs": {_GRAPH_ID: {"description": "Mock lead agent"}},
    }


@app.post("/assistants/search")
async def assistants_search():
    return [
        {
            "assistant_id": _ASSISTANT_ID,
            "graph_id": _GRAPH_ID,
            "name": "lead_agent",
            "metadata": {},
            "config": {},
            "created_at": _now(),
            "updated_at": _now(),
        }
    ]


@app.get("/assistants/{assistant_id}")
async def get_assistant(assistant_id: str):
    return {
        "assistant_id": assistant_id,
        "graph_id": _GRAPH_ID,
        "name": "lead_agent",
        "metadata": {},
        "config": {},
        "created_at": _now(),
        "updated_at": _now(),
    }


@app.post("/threads")
async def create_thread(request: Request):
    body = await request.json()
    thread_id = body.get("thread_id") or str(uuid.uuid4())
    thread = _make_thread(thread_id)
    return thread


@app.get("/threads/search")
@app.post("/threads/search")
async def search_threads(request: Request):
    limit = 20
    threads = sorted(_threads.values(), key=lambda t: t["updated_at"], reverse=True)
    return threads[:limit]


@app.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    if thread_id not in _threads:
        _make_thread(thread_id)
    return _threads[thread_id]


@app.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str):
    _threads.pop(thread_id, None)
    return {"status": "ok"}


@app.get("/threads/{thread_id}/state")
async def get_thread_state(thread_id: str):
    if thread_id not in _threads:
        _make_thread(thread_id)
    t = _threads[thread_id]
    return {
        "values": t["values"],
        "next": [],
        "checkpoint": {"thread_id": thread_id, "checkpoint_id": str(uuid.uuid4()), "checkpoint_ns": ""},
        "metadata": {},
        "created_at": t["created_at"],
        "parent_checkpoint": None,
    }


@app.api_route("/threads/{thread_id}/history", methods=["GET", "POST"])
async def get_thread_history(thread_id: str, request: Request, limit: int = 10):
    if thread_id not in _threads:
        _make_thread(thread_id)
    t = _threads[thread_id]
    if not t["values"]["messages"]:
        return []
    return [
        {
            "values": t["values"],
            "next": [],
            "checkpoint": {"thread_id": thread_id, "checkpoint_id": str(uuid.uuid4()), "checkpoint_ns": ""},
            "metadata": {},
            "created_at": t["created_at"],
            "parent_checkpoint": None,
        }
    ]


@app.post("/threads/{thread_id}/runs/stream")
async def stream_run(thread_id: str, request: Request):
    if thread_id not in _threads:
        _make_thread(thread_id)

    body = await request.json()

    # Extract user message
    user_message = "（无输入）"
    input_data = body.get("input") or {}
    messages = input_data.get("messages", [])
    if messages:
        last = messages[-1]
        content = last.get("content", "")
        if isinstance(content, str):
            user_message = content
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    user_message = part["text"]
                    break

    async def event_generator():
        async for chunk in _mock_stream(thread_id, user_message):
            yield chunk.encode("utf-8")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Gateway API mock endpoints ────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/models")
async def list_models():
    return {
        "models": [
            {
                "id": "mock-model",
                "name": "mock-model",
                "model": "mock-gpt-4o",
                "display_name": "Mock Model (Demo)",
                "description": "Mock model for demo — no LLM calls",
                "supports_thinking": False,
                "supports_reasoning_effort": False,
            }
        ]
    }


@app.get("/api/mcp/config")
async def get_mcp_config():
    return {"mcp_servers": {}}


@app.put("/api/mcp/config")
async def update_mcp_config(request: Request):
    return {"mcp_servers": {}}


@app.get("/api/skills")
async def list_skills():
    return {"skills": []}


@app.get("/api/memory")
async def get_memory():
    empty_ctx = {"summary": "", "updatedAt": _now()}
    return {
        "version": "1.0",
        "lastUpdated": _now(),
        "user": {
            "workContext": empty_ctx,
            "personalContext": empty_ctx,
            "topOfMind": empty_ctx,
        },
        "history": {
            "recentMonths": empty_ctx,
            "earlierContext": empty_ctx,
            "longTermBackground": empty_ctx,
        },
        "facts": [],
    }


@app.post("/api/threads/{thread_id}/suggestions")
async def get_suggestions(thread_id: str):
    return {"suggestions": []}


@app.get("/api/threads/{thread_id}/artifacts/{artifact_path:path}")
async def get_artifact(thread_id: str, artifact_path: str, download: bool = False):
    path = f"/{artifact_path}"
    thread_artifacts = _artifacts.get(thread_id, {})
    if path not in thread_artifacts:
        raise HTTPException(status_code=404, detail="Artifact not found")
    content, mime = thread_artifacts[path]
    headers = {}
    if download:
        filename = path.rsplit("/", 1)[-1]
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return Response(content=content.encode("utf-8"), media_type=mime, headers=headers)


# Stub run endpoints the SDK may call
@app.get("/threads/{thread_id}/runs")
async def list_runs(thread_id: str):
    return []


@app.post("/threads/{thread_id}/runs")
async def create_run(thread_id: str, request: Request):
    run_id = str(uuid.uuid4())
    return {"run_id": run_id, "thread_id": thread_id, "status": "pending"}


@app.get("/threads/{thread_id}/runs/{run_id}")
async def get_run(thread_id: str, run_id: str):
    return {"run_id": run_id, "thread_id": thread_id, "status": "success"}


@app.post("/threads/{thread_id}/runs/{run_id}/cancel")
async def cancel_run(thread_id: str, run_id: str):
    return {"status": "ok"}
