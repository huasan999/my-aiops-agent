"""Plan-Execute-Replan 状态定义"""

import operator
from typing import Annotated, List, TypedDict


class PlanExecuteState(TypedDict):
    """图的状态:所有节点共享读写"""

    # 用户输入(任务描述)
    input: str

    # 执行计划(步骤列表)
    plan: List[str]

    # 已执行的步骤历史 (步骤, 结果) 元组列表
    # operator.add = 追加式更新(和 add_messages 一个套路,只是换合并函数)
    past_steps: Annotated[List[tuple], operator.add]

    # 已执行步骤计数(硬性保险丝,防死循环)
    # 注意:与 len(past_steps) 等价,但显式计数让保险丝不依赖历史列表完整性
    step_count: int

    # 最终响应/诊断报告
    response: str