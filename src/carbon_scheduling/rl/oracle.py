"""The perfect-foresight planner: the cheapest legal way to serve a demand stream.

This is the yardstick for every learned policy. It answers one question exactly:
given the realized carbon intensity at every (slot, site), the fleet's capacity
per slot, and each arrival's deadline, what is the lowest-carbon schedule that
serves the work?

It is not a policy -- it sees the future -- so it is an upper bound on what any
causal policy could achieve, and the gap between a learner and this plan is the
headroom the learner left on the table. It is solved as a min-cost flow, so the
number is a proven optimum rather than a heuristic's best effort.

Network, for ``T`` slots and ``N`` sites::

    source --(arrivals at t)--> slot t --(carry)--> slot t+1
                                  |
                                  +--(capacity, cost per GPU-s)--> sink   x N

Carrying work forward is free (the power model bills every site's idle floor in
every slot, so waiting costs no extra energy). The carry arc's capacity is the
work that could still be in flight legally -- everything that arrived in the
last ``deadline`` slots -- which is what enforces the deadline: work cannot wait
longer than its owner's window.
"""

from __future__ import annotations

import heapq

import numpy as np


def plan(
    cost: np.ndarray,
    demand: np.ndarray,
    capacity: float,
    deadline: int,
    volume: float | None = None,
) -> tuple[np.ndarray, float]:
    """Serve ``demand`` at minimum cost, subject to ``deadline`` and capacity.

    ``cost[t, i]`` is the carbon per GPU-second of running at site ``i`` in slot
    ``t``; ``demand[t]`` is the GPU-seconds arriving in slot ``t``; ``capacity``
    is the GPU-seconds one site can serve in one slot.

    ``volume`` pins how much work is served. Leave it out to serve as much as
    the fleet can hold; give it the volume a baseline serves to compare at
    matched service, because unserved work emits nothing and a carbon-only
    reading rewards doing less.

    Returns the allocation matrix (same shape as ``cost``) and the GPU-seconds
    left unserved: work the fleet could not hold, or work the requested volume
    did not cover.
    """
    cost = np.asarray(cost, dtype=np.float64)
    demand = np.asarray(demand, dtype=np.float64)
    if cost.ndim != 2:
        raise ValueError(f"cost must be 2-D, got shape {cost.shape}")
    if demand.shape != (cost.shape[0],):
        raise ValueError(f"demand shape {demand.shape} does not match {cost.shape[0]} slots")
    if deadline < 1:
        raise ValueError(f"deadline must be >= 1, got {deadline}")
    if capacity <= 0:
        raise ValueError(f"capacity must be positive, got {capacity}")
    if (demand < 0).any():
        raise ValueError("demand must be non-negative")
    if (cost < 0).any():
        raise ValueError("cost must be non-negative")

    slots, sites = cost.shape
    total = float(demand.sum())
    if total <= 0:
        return np.zeros_like(cost), 0.0

    # Carry capacity after slot t: work that can still be served in slot t+1.
    # An arrival at `a` may run in slots a .. a+deadline-1, so after serving slot
    # t the only work that may still be in flight arrived at t-deadline+2 or
    # later. Anything older has expired and must not be carried.
    carry = np.zeros(slots)
    for t in range(slots):
        carry[t] = float(demand[max(0, t - deadline + 2) : t + 1].sum())

    source = 0
    node = lambda t: 1 + t  # noqa: E731 - local, obvious
    sink = 1 + slots
    graph: list[list[list[float]]] = [[] for _ in range(sink + 1)]

    def add_edge(u: int, v: int, cap: float, price: float) -> None:
        graph[u].append([v, cap, price, len(graph[v])])
        graph[v].append([u, 0.0, -price, len(graph[u]) - 1])

    for t in range(slots):
        if demand[t] > 0:
            add_edge(source, node(t), float(demand[t]), 0.0)
        if t + 1 < slots and carry[t] > 0:
            add_edge(node(t), node(t + 1), carry[t], 0.0)
        for i in range(sites):
            add_edge(node(t), sink, float(capacity), float(cost[t, i]))

    want = total if volume is None else min(float(volume), total)
    if want < 0:
        raise ValueError(f"volume must be non-negative, got {volume}")
    flow = _min_cost_flow(graph, source, sink, want)
    alloc = np.zeros((slots, sites))
    # Read the served flow back off the site arcs: for slot t they are the last
    # `sites` arcs added, in site order.
    for t in range(slots):
        arcs = [arc for arc in graph[node(t)] if arc[0] == sink]
        for i, arc in enumerate(arcs[:sites]):
            served = capacity - arc[1]
            if served > 1e-9:
                alloc[t, i] = served
    return alloc, max(total - flow, 0.0)


def _min_cost_flow(graph: list[list[list[float]]], source: int, sink: int, want: float) -> float:
    """Min-cost max-flow by successive shortest paths (Dijkstra + potentials)."""
    n = len(graph)
    potential = [0.0] * n
    flow = 0.0
    while flow < want - 1e-12:
        dist = [float("inf")] * n
        prev_node = [-1] * n
        prev_edge = [-1] * n
        dist[source] = 0.0
        heap = [(0.0, source)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u] + 1e-15:
                continue
            for index, (v, cap, price, _rev) in enumerate(graph[u]):
                if cap <= 1e-12:
                    continue
                reduced = price + potential[u] - potential[v]
                if dist[v] > d + reduced + 1e-15:
                    dist[v] = d + reduced
                    prev_node[v] = u
                    prev_edge[v] = index
                    heapq.heappush(heap, (dist[v], v))
        if dist[sink] == float("inf"):
            break
        for v in range(n):
            if dist[v] < float("inf"):
                potential[v] += dist[v]
        push = want - flow
        v = sink
        while v != source:
            u = prev_node[v]
            push = min(push, graph[u][prev_edge[v]][1])
            v = u
        v = sink
        while v != source:
            u = prev_node[v]
            arc = graph[u][prev_edge[v]]
            arc[1] -= push
            graph[v][int(arc[3])][1] += push
            v = u
        flow += push
    return flow
