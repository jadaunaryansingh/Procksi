# src/orchestrator/langgraph_adapter.py
from typing import Callable, Dict, Any, List, Set
from collections import defaultdict, deque
import traceback

class Node:
    def __init__(self, name: str, fn: Callable[..., Any]):
        self.name = name
        self.fn = fn
        self.inputs = []
        self.outputs = []
        self.result = None
        self.status = "PENDING"
        self.error = None

    def run(self, ctx: Dict[str, Any]):
        self.status = "RUNNING"
        try:
            # Node functions accept ctx and return dict to merge into ctx
            res = self.fn(ctx)
            if res and isinstance(res, dict):
                ctx.update(res)
            self.result = res
            self.status = "SUCCESS"
            return res
        except Exception as e:
            self.status = "FAILED"
            self.error = str(e) + "\n" + traceback.format_exc()
            raise

class SimpleLangGraph:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: Dict[str, Set[str]] = defaultdict(set)  # u -> set(v) (u must run before v)
        self.rev_edges: Dict[str, Set[str]] = defaultdict(set)

    def add_node(self, name: str, fn: Callable[..., Any]):
        if name in self.nodes:
            raise ValueError("Node exists: " + name)
        self.nodes[name] = Node(name, fn)

    def add_edge(self, from_node: str, to_node: str):
        if from_node not in self.nodes or to_node not in self.nodes:
            raise KeyError("Missing node")
        self.edges[from_node].add(to_node)
        self.rev_edges[to_node].add(from_node)

    def _toposort(self) -> List[str]:
        indeg = {n: len(self.rev_edges.get(n, [])) for n in self.nodes}
        q = deque([n for n, d in indeg.items() if d == 0])
        order = []
        while q:
            u = q.popleft()
            order.append(u)
            for v in self.edges.get(u, []):
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
        if len(order) != len(self.nodes):
            raise RuntimeError("Cycle detected or missing nodes")
        return order

    def run(self, initial_ctx: Dict[str, Any] = None, stop_on_error: bool = True) -> Dict[str, Any]:
        ctx = initial_ctx or {}
        order = self._toposort()
        for n in order:
            node = self.nodes[n]
            try:
                node.run(ctx)
            except Exception as e:
                node.error = str(e)
                if stop_on_error:
                    raise
                else:
                    continue
        return ctx
