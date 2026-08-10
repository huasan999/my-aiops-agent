import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""验证:普通字段覆盖 vs Annotated 字段追加"""

from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages


class StateA(TypedDict):
    messages: list  # 普通字段


class StateB(TypedDict):
    messages: Annotated[list, add_messages]  # 特殊字段


def node_a(state):
    return {"messages": ["节点A写入的消息"]}


def node_b(state):
    print("node_b 看到的 messages:", state["messages"])
    return {}


def run(state_cls, name):
    g = StateGraph(state_cls)
    g.add_node("a", node_a)
    g.add_node("b", node_b)
    g.set_entry_point("a")
    g.add_edge("a", "b")
    g.add_edge("b", END)
    g.compile().invoke({"messages": ["用户原始消息"]})
    print(f"--- {name} 跑完 ---")


print("======== 普通字段: ========")
run(StateA, "普通字段")

print("======== Annotated 字段: ========")
run(StateB, "Annotated字段")