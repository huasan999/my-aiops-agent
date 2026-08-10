# app/agent/aiops/ — LangGraph 状态机

## OVERVIEW
Plan-Execute-Replan 三节点状态机:planner 拆任务 → executor 执行 → replanner 决定继续/收尾。

## STRUCTURE
```
agent/aiops/
├── state.py      # PlanExecuteState:input/plan/past_steps(Annotated[add])/response
├── planner.py    # 任务 → 4-6 步计划(结构化 JSON 输出,json_mode)
├── executor.py   # 每步:调 LLM + 工具循环,结果入 past_steps
└── replanner.py  # 复盘:判断是否出报告;6 步保险丝强制收尾
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| 状态字段 | `state.py` | past_steps 用 operator.add 追加 |
| 图装配 | `app/services/aiops_service.py` | 条件边 replanner→executor/END |
| 工具集 | `app/core/llm_client.py` | executor 复用 AVAILABLE_TOOLS |

## CONVENTIONS
- 节点函数签名统一 `async def node(state: PlanExecuteState) -> Dict[str, Any]`,只返回增量字段
- 计划必须 4-6 步;replanner 新计划不得超过剩余步数
- 报告基于实际数据,Markdown 格式

## ANTI-PATTERNS
- **禁止 LLM 编造数据/指标**(executor.py:41 明确注入规则)
- 禁止超过 6 步执行(防死循环保险丝,replanner.py:48)
- 禁止把状态机逻辑写进路由层
