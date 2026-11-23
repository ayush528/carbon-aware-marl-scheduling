"""The perfect-foresight planner: the cheapest legal way to serve a demand stream.

This is the yardstick for every learned policy. It answers one question exactly:
given the realized carbon intensity at every (slot, site), the fleet's capacity
per slot, and each arrival's deadline, what is the lowest-carbon schedule that
serves the work?

It is not a policy -- it sees the future -- so it is a lower bound on the carbon
any causal policy could emit, and the gap between a learner and this plan is the
headroom the learner left on the table. It is solved as a min-cost flow, so the
number is a proven optimum rather than a heuristic's best effort.

Work may arrive in several **classes** with different deadlines (an interactive
request and a batch job are both work, but only one of them may wait). The
network, for ``T`` slots, ``N`` sites and ``K`` classes::

    source --(arrivals at t, class k)--> class(k, t) --(carry)--> class(k, t+1)
                                            |
                                            +--(cost per GPU-s)--> site(t, i) --> sink
                                                                      (capacity)

Carrying work forward is free (the power model bills every site's idle floor in
every slot, so waiting costs no extra energy). A carry arc's capacity is the
work of that class that could still be in flight legally, which is what enforces
the deadline: work cannot wait longer than its class's window. Site capacity is
shared, so classes compete for the same clean slots.

A lower bound assumes the schedule can move work between regions at will, so it
is optimistic about placement *and* timing. Both are exactly known to the
planner and only partly observable to a policy; that gap is the point of the
measurement.
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
    """Serve one deadline class at minimum cost (see :func:`plan_multi`).

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
    demand = np.asarray(demand, dtype=np.float64)
    if demand.ndim != 1:
        raise ValueError(f"demand must be 1-D, got shape {demand.shape}")
    alloc, unserved = plan_multi(cost, demand[None, :], capacity, [deadline], volume=volume)
    return alloc[0], unserved


def plan_multi(
    cost: np.ndarray,
    demand: np.ndarray,
    capacity: float,
    deadlines: list[int] | tuple[int, ...],
    volume: float | None = None,
) -> tuple[np.ndarray, float]:
    """Serve every class at minimum cost, sharing the fleet's capacity.

    ``demand[k, t]`` is the GPU-seconds of class ``k`` arriving in slot ``t`` and
    ``deadlines[k]`` is how many slots (including its own) that class may wait --
    a deadline of 1 means "this slot or never".

    ``volume`` applies to the *total*: it asks for the cheapest ``volume``
    GPU-seconds across all classes, leaving the rest unserved. ``None`` serves
    everything the fleet can hold.

    Returns ``alloc`` (shape ``(K, T, N)``) and the GPU-seconds left unserved.
    """
    cost = np.asarray(cost, dtype=np.float64)
    demand = np.asarray(demand, dtype=np.float64)
    deadlines = [int(d) for d in deadlines]
    if cost.ndim != 2:
        raise ValueError(f"cost must be 2-D, got shape {cost.shape}")
    if demand.ndim != 2:
        raise ValueError(f"demand must be 2-D (classes, slots), got shape {demand.shape}")
    slots, sites = cost.shape
    if demand.shape[1] != slots:
        raise ValueError(f"demand has {demand.shape[1]} slots, cost has {slots}")
    if len(deadlines) != demand.shape[0]:
        raise ValueError(f"{len(deadlines)} deadlines for {demand.shape[0]} demand classes")
    if any(d < 1 for d in deadlines):
        raise ValueError(f"every deadline must be >= 1, got {deadlines}")
    if capacity <= 0:
        raise ValueError(f"capacity must be positive, got {capacity}")
    if (demand < 0).any():
        raise ValueError("demand must be non-negative")
    if (cost < 0).any():
        raise ValueError("cost must be non-negative")
    if volume is not None and volume < 0:
        raise ValueError(f"volume must be non-negative, got {volume}")

    classes = demand.shape[0]
    total = float(demand.sum())
    if total <= 0:
        return np.zeros((classes, slots, sites)), 0.0
    want = total if volume is None else min(float(volume), total)

    source = 0
    class_node = lambda k, t: 1 + k * slots + t  # noqa: E731 - local, obvious
    site_node = lambda t, i: 1 + classes * slots + t * sites + i  # noqa: E731
    sink = 1 + classes * slots + slots * sites
    graph: list[list[list[float]]] = [[] for _ in range(sink + 1)]

    def add_edge(u: int, v: int, cap: float, price: float) -> int:
        graph[u].append([v, cap, price, len(graph[v])])
        graph[v].append([u, 0.0, -price, len(graph[u]) - 1])
        return len(graph[u]) - 1

    served_arcs: list[tuple[int, int, int, int, int]] = []
    for k in range(classes):
        horizon = deadlines[k]
        for t in range(slots):
            if demand[k, t] > 0:
                add_edge(source, class_node(k, t), float(demand[k, t]), 0.0)
            if t + 1 < slots:
                # After serving slot t, class-k work may still be in flight only
                # if it arrived at t - horizon + 2 or later: an arrival at a may
                # run in slots a .. a+horizon-1.
                carry = float(demand[k, max(0, t - horizon + 2) : t + 1].sum())
                if carry > 0:
                    add_edge(class_node(k, t), class_node(k, t + 1), carry, 0.0)
            for i in range(sites):
                arc = add_edge(class_node(k, t), site_node(t, i), total, float(cost[t, i]))
                served_arcs.append((k, t, i, class_node(k, t), arc))
    for t in range(slots):
        for i in range(sites):
            add_edge(site_node(t, i), sink, float(capacity), 0.0)

    flow = _min_cost_flow(graph, source, sink, want)

    alloc = np.zeros((classes, slots, sites))
    # Flow along a class -> site arc is the capacity its reverse arc now holds.
    for k, t, i, u, arc in served_arcs:
        reverse = graph[u][arc][3]
        alloc[k, t, i] = graph[site_node(t, i)][reverse][1]
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
