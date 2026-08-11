# my-aiops-agent

> AIOps 智能诊断代理 —— 收到 Prometheus 告警后,自动排查 CPU/内存/磁盘/服务不可用/响应慢五类故障,生成带证据链的诊断报告。

**状态**: v0.1.0 · 早期开发版 · 主要在 Windows + Docker Desktop 环境验证

---

## 它做了什么

把一段告警文本(例如 *"主机 web-01 的 CPU 使用率持续 5 分钟 > 90%"*)丢给 `/api/aiops`,Agent 会:

1. **规划** —— 拆成 4-6 步排查计划(查指标 → 定位进程 → 查知识库 → 验证假设 → 写报告)
2. **执行** —— 每步调用真实工具(Prometheus 查询、RAG 检索、时间、网页搜索),收集实际数据
3. **反思** —— 判断证据是否足够,不够就修订计划再来一轮(最多 6 步保险丝)
4. **汇报** —— 返回结构化诊断报告:现象、根因、证据、处置建议

整个过程通过 **SSE(Server-Sent Events)实时推送**给前端,用户可以在浏览器看 Agent 一边想一边干。

---

## 架构一览

```
┌──────────────┐  POST /api/aiops    ┌──────────────────────┐
│  浏览器/CLI  │ ──────────────────▶ │   FastAPI :9900      │
│  (static)    │ ◀────────────────── │  (app/main.py)       │
└──────────────┘  SSE 实时事件流     └──────────┬───────────┘
                                                │
                                ┌───────────────┴────────────────┐
                                ▼                                ▼
                    ┌──────────────────────┐         ┌──────────────────┐
                    │   LangGraph 状态机   │         │   LLM Gateway    │
                    │  planner→executor   │ ──────▶ │   :8006          │
                    │  →replanner (循环)  │         │  (DeepSeek→Ollama│
                    └──────────┬───────────┘         │   故障转移)      │
                               │                     └──────────────────┘
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ Milvus   │    │Prometheus│    │  其他工具 │
        │ :19530   │    │  :9090   │    │ 知识/OCR │
        │ 向量知识 │    │  告警查询 │    │  时间/搜索│
        └──────────┘    └──────────┘    └──────────┘

        Postgres :5432  ── LangGraph 检查点(崩溃恢复 + 历史回放)
        LangSmith(云) ── 全链路 LLM 追踪(可选,生产推荐开)
```

**关键设计**:
- **懒初始化** —— 异步资源(向量库、Postgres 连接池)在首次调用时才建,避免 import 期污染事件循环
- **双层防御幻觉** —— LLM 只做分析组织,事实数据全部来自工具;RAG 检索失败时如实回报,不编造
- **持久化检查点** —— 任务跑到一半服务挂了,重启后从 Postgres 恢复(session_id 找回)

---

## 技术栈

| 类别 | 选型 | 备注 |
|---|---|---|
| 语言 | Python 3.13+ | 强制版本要求 |
| Web 框架 | FastAPI 0.141+ | 5 个路由 + static |
| 状态机 | LangGraph 1.0.8 | 硬钉版本,plan-execute-replan 循环 |
| LLM 编排 | LangChain 1.2.10 | 硬钉版本 |
| LLM 入口 | 自建 LLM 微网关 :8006 | DeepSeek 主,Ollama 备 |
| 向量库 | Milvus 2.6.9 (pymilvus) | 知识库 + 长期记忆 |
| 检查点 | Postgres + langgraph-checkpoint-postgres | 空 DSN 则退化到内存 |
| 监控数据 | Prometheus :9090 | 告警 + 指标查询 |
| 可观测性 | LangSmith | 可选,云服务,环境变量自动追踪 |
| 前端 | 原生 HTML/CSS/JS | 无构建步骤 |
| 依赖管理 | uv (pyproject.toml + uv.lock) | 不要用 pip |

---

## 端口清单

| 端口 | 服务 | 备注 |
|---|---|---|
| **9900** | FastAPI 主应用 | Web UI + API |
| **8006** | LLM 微网关 | 唯一允许的 LLM 入口 |
| 9090 | Prometheus | 已有容器,docker start 启动 |
| 19530 | Milvus | 向量库 |
| 8000 | Attu | Milvus Web UI |
| 5432 | Postgres | LangGraph 检查点 |
| 11434 | Ollama | 本地 LLM 备选 |
| 8003 | MCP Server | 内置 clock_server |

> Windows 端口坑:9091 落在系统保留区间,Milvus 端口已映射到宿主 **19091**(详见 `vector-database.yml`)。

---

## 快速开始 (Windows)

### 1. 前置依赖

- **Python 3.13+**([python.org](https://www.python.org/downloads/))
- **uv**(`pip install uv` 或 [Astral 官方安装](https://docs.astral.sh/uv/))
- **Docker Desktop**(用于 Milvus/Postgres/Prometheus 容器)
- **Ollama**([ollama.com](https://ollama.com/))—— 本地备选 LLM

### 2. 克隆 & 装依赖

```powershell
git clone https://github.com/huasan999/my-aiops-agent.git
cd my-aiops-agent
uv sync
```

### 3. 配环境变量

```powershell
copy .env.example .env
# 编辑 .env,填入 DEEPSEEK_API_KEY(必填)
```

> 不要提交 `.env`。`.env.example` 列出全部可选项,留空的有合理默认值。

### 4. 启动基础设施

```powershell
# 一次性启动 Milvus 栈 + Postgres 检查点
docker compose -f vector-database.yml up -d

# 已有 Prometheus 容器(未在 compose 里)
docker start prometheus

# 可选:LangSmith 追踪 —— 在 .env 配置 LANGSMITH_API_KEY(云服务,无需本地容器)
```

### 5. 一键启动

```powershell
.\start-windows.bat
```

脚本自动检查 venv → 起 Docker 容器 → 启 LLM 网关 → 启 FastAPI → 健康检查。

启动后:
- Web UI: <http://localhost:9900>
- API 文档: <http://localhost:9900/docs>
- Milvus UI: <http://127.0.0.1:8000>

停止: `.\stop-windows.bat`

### 6. 验证

```powershell
curl http://localhost:9900/health
```

应返回 `{"status": "ok", ...}`。

---

## 5 分钟上手 API

### 提交诊断任务(异步)

```bash
curl -X POST http://localhost:9900/api/aiops \
  -H "Content-Type: application/json" \
  -d '{"alert": "主机 web-01 的 CPU 使用率持续 5 分钟 > 90%", "session_id": "demo-1"}'
```

返回 `202 Accepted` + `task_id`。

### 订阅实时事件(SSE)

```bash
curl -N http://localhost:9900/api/aiops/<task_id>/events
```

你会看到 Agent 一步步推流:规划 → 调工具 → 思考 → 修订计划 → 终态报告。

### 同步/历史查询

```bash
curl http://localhost:9900/api/aiops/<task_id>
curl http://localhost:9900/api/aiops/state/<session_id>   # 从 Postgres 恢复
```

完整接口见 <http://localhost:9900/docs>。

---

## 冒烟测试

无 pytest,逐个脚本验证(项目约定):

```powershell
# 不需要 LLM key 的基础检查
python scripts\test_diagnosis_manager.py
python scripts\test_aiops_api.py
python scripts\test_aiops.py

# 需要 DEEPSEEK_API_KEY
python scripts\test_llm.py
```

---

## 知识库

故障排查经验沉淀在 `aiops-docs/` 下五篇 Markdown:

- `cpu_high_usage.md`
- `memory_high_usage.md`
- `disk_high_usage.md`
- `service_unavailable.md`
- `slow_response.md`

首次使用前建议入库到 Milvus:

```powershell
python scripts\index_docs.py
```

---

## 目录速查

| 你想找 | 在哪 |
|---|---|
| 诊断主流程 | `app/services/aiops_service.py` |
| 异步任务 + SSE | `app/services/diagnosis_manager.py` |
| 状态机节点 | `app/agent/aiops/{planner,executor,replanner}.py` |
| HTTP 路由 | `app/api/aiops.py` 等 5 个文件 |
| LLM 调用 | `app/core/llm_client.py`(必须经网关) |
| 工具实现 | `app/tools/`(4 个工具) |
| 知识库脚本 | `scripts/index_docs.py` |
| 启动脚本 | `start-windows.bat` / `stop-windows.bat` |
| 详细 AGENTS 文档 | `AGENTS.md` / `app/AGENTS.md` / 各子目录 AGENTS.md |

> **README 不替代 AGENTS.md**。架构决策、约定、踩坑记录在 AGENTS.md 里。

---

## 已知约束

- **单实例设计** —— LangGraph 状态机绑在内存,水平扩展需引入 Redis 或外部 broker
- **Windows 优先** —— ProactorEventLoop 下 psycopg 异步驱动有兼容问题,启动方式有特定要求(详见 `app/main.py` 注释)
- **5 步封顶** —— 单次诊断计划 4-6 步,带 6 步保险丝,防死循环
- **不写 pytest** —— 测试走 `scripts/test_*.py` 模式,逐个 `python` 运行

---

## 安全

- 仓库 public,**任何推送前请扫描密钥**。运行 `gitleaks detect --source . --config .gitleaks.toml` 自检。
- `.env`、`volumes/`、`uploads/`、`logs/` 已在 `.gitignore` 忽略。
- 上传文件名必须消毒(防路径注入),限 100MB、白名单扩展名。
- LLM 流量强制经网关 :8006,**禁止**绕过。

---

## 许可

[MIT](LICENSE) — 允许商用、修改、私有化、再分发,只需保留版权声明。

Copyright (c) 2026 huasan999
