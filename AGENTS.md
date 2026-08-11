# PROJECT KNOWLEDGE BASE

**Generated:** 2026-08-10
**Branch:** master (no commits yet)
**Package:** my-aiops-agent v0.1.0

## OVERVIEW
AIOps 智能诊断代理:FastAPI + LangGraph 实现的 Plan-Execute-Replan 状态机,自动排查系统告警(CPU/内存/磁盘/服务不可用/响应慢)并生成诊断报告。Python 3.13,uv 管理,LLM 通过本地网关转发,向量知识库基于 Milvus。企业级特性:Postgres 持久化检查点、异步诊断任务(202+SSE 订阅)、LangSmith 追踪。

## STRUCTURE
```
my-aiops-agent/
├── app/               # FastAPI 应用(见 app/AGENTS.md)
│   ├── agent/aiops/   # LangGraph 状态机节点(见其 AGENTS.md)
│   ├── api/           # HTTP/SSE 路由(见其 AGENTS.md)
│   └── services/      # 向量/OCR/记忆/诊断任务基础设施(见其 AGENTS.md)
├── llm_gateway.py     # LLM 微网关 :8006(独立进程)
├── aiops-docs/        # 5 篇故障知识文档(RAG 语料)
├── scripts/           # index_docs.py + 13 个冒烟测试脚本
├── static/            # 前端页面(原生 HTML/CSS/JS)
├── prometheus/        # Prometheus 抓取 + 告警规则
├── vector-database.yml # Milvus 栈 + Postgres 检查点 docker-compose
├── .env.example       # 环境变量模板(复制为 .env)
├── .gitleaks.toml     # 密钥扫描配置
└── volumes/           # 运行数据(etcd/milvus/minio/postgres,勿提交)
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| 诊断主流程 | `app/services/aiops_service.py` | 状态机组装 + 异步任务 |
| 诊断任务管理 | `app/services/diagnosis_manager.py` | 202 提交 + SSE 订阅 |
| 崩溃恢复 | `GET /api/aiops/state/{session_id}` | 从 Postgres checkpointer 找回诊断进度 |
| 状态机节点 | `app/agent/aiops/` | planner→executor→replanner 循环 |
| HTTP 接口 | `app/api/` | POST /api/aiops + GET /api/aiops/{id}/events |
| LLM 调用 | `app/core/llm_client.py` | 统一经网关 :8006 |
| 可观测性 | `app/core/tracing.py` | LangSmith 自动追踪(环境变量) |
| 向量检索/索引 | `app/services/vector_*` | Milvus,懒初始化 |
| 文档入库 | `scripts/index_docs.py` | aiops-docs → Milvus |
| 告警查询 | `app/tools/query_metrics_alerts.py` | Prometheus |
| 运维启动 | `start-windows.bat` | 一键起全部服务 |

## CODE MAP
| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `app` | FastAPI 实例 | `app/main.py` | :9900 入口,挂 5 路由 + static |
| `aiops_service` | 单例 | `app/services/aiops_service.py` | 编译状态图,SSE 事件源 |
| `planner`/`executor`/`replanner` | 节点 | `app/agent/aiops/` | 状态机三节点 |
| `app.gateway` | FastAPI 实例 | `llm_gateway.py` | :8006,DeepSeek→Ollama 故障转移 |
| `vector_store_manager` | 单例 | `app/services/vector_store_manager.py` | Milvus 集合管理 |
| `llm_client` | 客户端 | `app/core/llm_client.py` | create_agent + AVAILABLE_TOOLS |

## CONVENTIONS
- **工具链**:uv(pyproject.toml + uv.lock + .python-version),勿用 pip 直装
- **依赖硬钉**:核心库用 `==` 精确锁定(langchain==1.2.10, langgraph==1.0.8, pymilvus==2.6.9),勿浮动
- **所有 LLM 流量必须经网关** `127.0.0.1:8006/v1`(llm_gateway.py 做供应商转发);唯一例外:多模态走 Ollama 原生 API
- **懒初始化**:异步/向量资源禁止在模块导入期创建(防事件循环污染);aiops_service 的 graph 惰性编译
- **配置走环境变量**:`DEEPSEEK_API_KEY`、`LLM_BASE_URL`(默认 :8006/v1)、`PROMETHEUS_BASE_URL`(默认 :9090)、`CHECKPOINTER_DSN`(Postgres,空则内存)、`LANGSMITH_*`;模板在 `.env.example`
- **Windows 事件循环**:psycopg async 不支持 ProactorEventLoop;必须用 `python -m app.main` 启动(uvicorn CLI 模式会在创建事件循环后才 import main.py,policy 来不及生效);新测试脚本同样需在 asyncio.run 前设置 policy
- **源码一律 UTF-8**(config.py 已有 mojibake 事故,GBK 读取会损坏注释)
- **测试无 pytest**:冒烟脚本在 scripts/test_*.py,直接 `python` 运行

## ANTI-PATTERNS (THIS PROJECT)
- **禁止 LLM 编造数据**:executor.py:41、llm_client.py:64、query_metrics_alerts.py:32 均注入"不要编造"规则;报告必须基于实际数据
- **禁止 import 期建资源**:vector_store_manager 懒初始化是硬性约定
- **禁止 drop_old=True**:不清空 Milvus 存量数据(vector_store_manager.py:67)
- **记忆集合 `memories` 与知识集合 `knowledge` 必须隔离**(memory_store.py:17)
- **计划 4-6 步封顶 + 6 步保险丝**:replanner.py:48 强制收尾防死循环;state 里 step_count 显式计数,recursion_limit=25 兜底
- **禁止提交**:`.env`(密钥)、`volumes/`、`uploads/`、`logs/`
- **上传文件名必须消毒**(防路径注入),限 100MB、白名单扩展名
- **不写 pytest**:项目无 pytest 依赖,新验证按 scripts/test_*.py 模式

## COMMANDS
```bash
# 安装依赖
uv sync

# 一键启动(Windows):Docker + 网关 + 应用
start-windows.bat

# 单独起 LLM 网关 :8006
python llm_gateway.py

# 起 FastAPI 应用 :9900
uvicorn app.main:app --host 0.0.0.0 --port 9900

# 起基础设施(Milvus 栈 + Postgres 检查点)
docker compose -f vector-database.yml up -d

# 起 LangSmith 追踪(可选):在 .env 配置 LANGSMITH_API_KEY 即可(云服务,无需本地容器)
# 参考 https://smith.langchain.com

# 冒烟测试(无 pytest,逐个跑)
python scripts/test_diagnosis_manager.py
python scripts/test_aiops_api.py
python scripts/test_aiops.py
python scripts/test_llm.py    # 需 DEEPSEEK_API_KEY

# 密钥扫描
gitleaks detect --source . --config .gitleaks.toml

# 文档入库
python scripts/index_docs.py

# 健康检查
curl http://localhost:9900/health
```

## NOTES
- **端口**:应用 :9900,网关 :8006,MCP :8003,Milvus :19530,Attu :8000,Ollama :11434,Prometheus :9090,Postgres :5432,LangSmith(云,无本地端口)
- **Windows 端口坑**:Milvus 9091 落在系统保留区间(9080-9179),已映射到宿主 19091(vector-database.yml:56)
- **Prometheus 容器不在 compose 里**:靠 `docker start prometheus` 启动(已手动创建过)
- **README.md 为空**:运行说明实际上全在 start-windows.bat 里,勿依赖 README
- **根 uploads/ 与 app/uploads/ 重复**,实际数据在 app/uploads/
- **prometheus/rules.yml 含故意触发的 FakeServiceDown 演示告警**(fake-service:9999 死目标),不是故障
- **镜像拉取失败时**用镜像源前缀拉取再 tag(docker pull docker.1ms.run/library/postgres:16 → docker tag)
