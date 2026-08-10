# app/api/ — HTTP/SSE 路由层

## OVERVIEW
FastAPI 路由层:5 个路由,统一挂载在 main.py(prefix="/api")。AI 诊断走 SSE 流式。

## STRUCTURE
```
api/
├── aiops.py    # POST /api/aiops 提交诊断(202+task_id);GET /{id}/events SSE 订阅;GET /{id} 状态
├── chat.py     # 聊天/agent 会话
├── file.py     # 文件上传(消毒 + 100MB + 扩展名白名单)
├── health.py   # GET /health 健康检查
└── memory.py   # 长期记忆读写
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| SSE 事件格式 | `aiops.py` | 5 种事件类型,前端按 type 分发 |
| 异步任务流 | `aiops.py` + `services/diagnosis_manager.py` | 提交即 202,订阅先回放再实时 |
| 上传校验 | `file.py` | 防路径注入是硬性要求 |
| 记忆接口 | `memory.py` | 走 services/memory_store.py |

## CONVENTIONS
- 每个路由一个文件,APIRouter 导出 `router`
- 业务逻辑全部下沉 services/,路由只做参数校验 + 响应序列化
- SSE 用 sse_starlette EventSourceResponse,中文 ensure_ascii=False
- **长任务异步化**:诊断类接口必须 202 提交 + task_id,禁止同步占连接

## ANTI-PATTERNS
- 禁止在路由里直接 new LangGraph/向量客户端(用 services 单例)
- 禁止裸传用户文件名(必须消毒)
- 禁止把服务端内部异常明文透出(统一 error 事件)
- 禁止同步等待分钟级诊断
