# app/ — FastAPI 应用包

## OVERVIEW
AIOps 诊断代理的 FastAPI 应用本体(:9900),挂载 5 个 API 路由 + 静态前端 + 后台记忆清理任务。

## STRUCTURE
```
app/
├── main.py            # 入口:FastAPI 实例,挂路由 + /static + lifespan
├── config.py          # APP_NAME、PORT 常量(注意:docstring 是 mojibake 事故现场)
├── agent/aiops/       # LangGraph 状态机(见 agent/aiops/AGENTS.md)
├── api/               # 路由层(见 api/AGENTS.md)
├── services/          # 业务服务(见 services/AGENTS.md)
├── tools/             # LLM 可用工具:knowledge_tool / query_metrics_alerts / time_tool
├── core/llm_client.py # LLM 客户端:create_agent + AVAILABLE_TOOLS 注册表
├── mcp_servers/       # 独立 MCP 服务:clock_server.py(:8003)
└── uploads/           # 用户上传文件(消毒后存储)
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| 应用装配 | `main.py` | lifespan 启停 memory_cleanup_loop |
| 工具注册 | `core/llm_client.py` | AVAILABLE_TOOLS 是唯一入口 |
| 上传处理 | `api/file.py` | 文件名消毒 + 100MB + 扩展名白名单 |

## CONVENTIONS
- 路由都在 `api/`,经 `main.py` include_router 挂载(prefix="/api")
- 新工具必须先加进 `AVAILABLE_TOOLS` 才会被 agent 看到
- 异步/向量资源禁止模块导入期创建

## ANTI-PATTERNS
- 勿在 `__init__.py` 建任何资源
- 勿绕过 api/ 层直接暴露服务内部
- 勿用 pip 直装依赖(走根目录 uv)
