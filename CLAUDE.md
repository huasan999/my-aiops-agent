# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

AIOps 智能诊断代理:FastAPI + LangGraph 实现的 Plan-Execute-Replan 状态机,自动排查系统告警(CPU/内存/磁盘/服务不可用/响应慢)并生成诊断报告。

- **技术栈**:Python 3.13,`uv` 管理依赖,Milvus 向量库,Postgres 检查点持久化,Langfuse 追踪,Prometheus 告警,SSE 实时推送
- **入口**:`app/main.py` 挂 5 个路由(`/api` 前缀)+ static 前端,:9900
- **运行说明都在 `start-windows.bat` 里**(README.md 为空,勿依赖 README)

## 常用命令

```bash
uv sync                          # 安装依赖(勿用 pip 直装)

# 一键启动(Windows):Docker 基础设施 + LLM 网关 + 应用
start-windows.bat

# 手动起服务
python llm_gateway.py                                            # LLM 网关 :8006
uvicorn app.main:app --host 0.0.0.0 --port 9900                   # FastAPI 应用
docker compose -f vector-database.yml up -d                       # Milvus 栈 + Postgres 检查点
docker compose -f langfuse.yml up -d                              # Langfuse(可选)
docker start prometheus                                           # Prometheus(不在 compose 里)

# 冒烟测试(无 pytest,逐个跑)
python scripts/test_diagnosis_manager.py
python scripts/test_aiops_api.py
python scripts/test_aiops.py
python scripts/test_llm.py     # 需要 DEEPSEEK_API_KEY

# 其他
python scripts/index_docs.py        # aiops-docs → Milvus 入库
gitleaks detect --source . --config .gitleaks.toml   # 密钥扫描
curl http://localhost:9900/health   # 健康检查
```

## 架构

### 诊断主流程(核心)
`app/services/aiops_service.py` 组装三节点 LangGraph 状态机(`app/agent/aiops/`):
- `planner` 拆 4-6 步计划 → `executor` 执行 → `replanner` 决定继续/收尾,条件边回 executor 或 END
- 状态 `PlanExecuteState`(`state.py`):`input` / `plan` / `past_steps`(operator.add 追加)/ `step_count` / `response`
- 图**惰性编译**(首次调用才 build),`recursion_limit=25` 兜底防死循环
- 检查点:`CHECKPOINTER_DSN` 配 Postgres 时持久化,否则退化 `MemorySaver`

### 异步任务 + SSE(企业模式)
`POST /api/aiops` 立即返回 `task_id`(202),后台任务执行,`GET /api/aiops/{task_id}/events` SSE 订阅(先回放历史再实时推送)。实现见 `app/services/diagnosis_manager.py`(进程内 asyncio 任务,事件带 TTL 清理)。

### LLM 流量
**所有 LLM 调用必须经本地网关 `127.0.0.1:8006/v1`**(`llm_gateway.py` 做 DeepSeek→Ollama 故障转移)。唯一例外:多模态走 Ollama 原生 API `:11434/api/chat`。客户端封装在 `app/core/llm_client.py`,工具注册表 `AVAILABLE_TOOLS` 是 agent 唯一可见工具入口(新工具必须加进该列表)。

### 数据服务
- 向量库 Milvus(惰性初始化):`app/services/vector_store_manager.py` 管理集合,`knowledge`(故障知识)与 `memories`(对话记忆)两集合必须隔离
- 告警查询:`app/tools/query_metrics_alerts.py` 走 Prometheus
- 记忆存取:`app/services/memory_store.py`(向量记忆,跨会话召回)

## 关键约定(违反会踩坑)

- **Windows 事件循环**:psycopg async 不支持 ProactorEventLoop。`app/main.py` 在事件循环创建前强制 `WindowsSelectorEventLoopPolicy`;新脚本同样要在 `asyncio.run` 之前设置
- **懒初始化**:异步/向量/DB 资源禁止在模块 import 期创建(防事件循环污染),一律首次调用时初始化
- **配置走环境变量**(模板 `.env.example`):`DEEPSEEK_API_KEY`(必填)、`LLM_BASE_URL`、`PROMETHEUS_BASE_URL`、`CHECKPOINTER_DSN`、`LANGFUSE_*`
- **依赖硬钉**:核心库 `==` 精确锁定(langchain==1.2.10、langgraph==1.0.8、pymilvus==2.6.9 等),勿浮动
- **源码一律 UTF-8**(`config.py` 已有 GBK mojibake 事故现场,勿再引入)
- **测试用 `scripts/test_*.py` 冒烟脚本,不写 pytest**(项目无 pytest 依赖)
- **禁止**:LLM 编造数据/指标(报告必须基于实际数据)、Milvus `drop_old=True`(勿清存量)、提交 `.env`/`volumes/`/`uploads/`/`logs/`
- 上传文件名必须消毒(防路径注入),限 100MB + 扩展名白名单

## 深入阅读

- 根目录 `AGENTS.md` 是完整项目知识库(代码地图、WHERE TO LOOK、命令、坑位清单),修改涉及面广时先读它
- 分层 AGENTS.md:`app/AGENTS.md`(应用装配)、`app/agent/aiops/AGENTS.md`(状态机)、`app/api/AGENTS.md`(路由)、`app/services/AGENTS.md`(服务)

## 端口速查

应用 :9900 · LLM 网关 :8006 · MCP :8003 · Milvus :19530 · Attu :8000 · Ollama :11434 · Prometheus :9090 · Postgres :5432 · Langfuse :4000

> Windows 坑:Milvus 的 9091 落在系统保留区间(9080-9179),已映射到宿主 19091(`vector-database.yml`)。`prometheus/rules.yml` 含故意触发的 FakeServiceDown 演示告警(fake-service:9999 死目标),不是故障。
