# app/services/ — 基础设施服务层

## OVERVIEW
业务服务层:向量库(Milvus)、OCR、长期记忆、状态机装配、后台清理。api/ 与 agent/ 都依赖这里。

## STRUCTURE
```
services/
├── aiops_service.py           # 编译 LangGraph 状态图(惰性)+ execute/stream_execute
├── diagnosis_manager.py       # 异步诊断任务:202 提交 + SSE 订阅回放
├── vector_store_manager.py    # Milvus 集合管理(懒初始化单例)
├── vector_embedding_service.py # 向量化(Ollama 嵌入)
├── vector_index_service.py    # 文档切分 + 入库 + 检索
├── memory_store.py            # 长期记忆集合(memories)
├── memory_cleaner.py          # 后台清理循环(main.py lifespan 启动)
└── ocr_service.py             # 图片 OCR(rapidocr)
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| 诊断编排 | `aiops_service.py` | 状态图唯一装配点;graph 惰性编译 |
| 异步任务 | `diagnosis_manager.py` | task_id 注册表 + 事件队列回放 |
| 向量集合 | `vector_store_manager.py` | 懒初始化硬性约定 |
| 记忆策略 | `memory_store.py` | 30 天保留期,集合隔离 |
| 文档检索 | `vector_index_service.py` | 知识库 knowledge 集合 |

## CONVENTIONS
- **懒初始化**:Milvus/异步客户端禁止在模块导入期创建;aiops_service 的 graph 首次调用才编译(async)
- **持久化 checkpointer**:`CHECKPOINTER_DSN` 配 Postgres → AsyncPostgresSaver(autocommit 连接池);空则 MemorySaver
- 集合命名:`knowledge`(知识库)与 `memories`(记忆)严格隔离
- auto_id=False(自管 id);metadata 走动态字段(metadata_field 已废弃)
- 诊断任务:POST 提交 → task_id,SSE 订阅先回放历史再实时(见 api/AGENTS.md)

## ANTI-PATTERNS
- **禁止 drop_old=True**:不清空存量数据(vector_store_manager.py:67)
- 禁止 import 期触碰事件循环(会污染 asyncio)
- 禁止 memory 与 knowledge 混用集合(memory_store.py:17)
- 禁止阻塞式等待分钟级诊断(必须 202 + 订阅,见 diagnosis_manager)
