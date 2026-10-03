"""
pairwise-graph-db-system - GraphDBSystem

A small in-memory graph database query system providing:

- Graph traversal (BFS / DFS) with visited marking and depth limits.
- Weighted shortest paths via bidirectional Dijkstra.
- Community detection (label propagation) with modularity scoring and
  convergence.
- Indexes: adjacency-list index plus property indexes, kept up to date on
  mutation.
- Query optimization: execution plans, predicate pushdown and result caching.
"""

from collections import deque
import heapq


def _sample_graph():
    """Small default weighted graph used when no graph is supplied."""
    return {
        "A": {"B": 1.0, "C": 4.0},
        "B": {"A": 1.0, "C": 2.0, "D": 5.0},
        "C": {"A": 4.0, "B": 2.0, "D": 1.0},
        "D": {"B": 5.0, "C": 1.0},
    }


class GraphDBSystem:
    def __init__(self):
        self.state = {}
        # Graph storage.
        self.nodes = {}            # node id -> property dict
        self.adjacency = {}        # adjacency-list index: node -> {neighbor: weight}
        # Property index: (key, value) -> set of node ids.
        self.property_index = {}
        # Query result cache: normalized query key -> result.
        self.query_cache = {}

    # ------------------------------------------------------------------
    # Graph mutation (keeps indexes up to date).
    # ------------------------------------------------------------------
    def add_node(self, node, **properties):
        self.nodes.setdefault(node, {}).update(properties)
        self.adjacency.setdefault(node, {})
        self._rebuild_property_index()
        return node

    def add_edge(self, source, target, weight=1.0):
        self.adjacency.setdefault(source, {})[target] = weight
        self.adjacency.setdefault(target, {})[source] = weight
        self.nodes.setdefault(source, {})
        self.nodes.setdefault(target, {})
        return (source, target, weight)

    def remove_edge(self, source, target):
        self.adjacency.get(source, {}).pop(target, None)
        self.adjacency.get(target, {}).pop(source, None)

    def _rebuild_property_index(self):
        self.property_index = {}
        for node, props in self.nodes.items():
            for key, value in props.items():
                self.property_index.setdefault((key, value), set()).add(node)

    def _graph(self, graph):
        if graph is not None:
            return graph
        if self.adjacency:
            return self.adjacency
        return _sample_graph()

    # ------------------------------------------------------------------
    # 1. Traversal: BFS / DFS with visited marking and depth limit.
    # ------------------------------------------------------------------
    def traverse_graph(self, start=None, method="bfs", max_depth=None,
                       graph=None):
        if isinstance(start, dict):
            graph, start = start, None
        graph = self._graph(graph)
        if start is None:
            start = next(iter(graph), None)
        if start is None:
            return []
        if max_depth is None:
            max_depth = len(graph)

        visited = {start}
        order = []
        if method == "dfs":
            stack = [(start, 0)]
            while stack:
                node, depth = stack.pop()
                order.append(node)
                if depth >= max_depth:
                    continue
                for neighbor in graph.get(node, {}):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        stack.append((neighbor, depth + 1))
        elif method == "bfs":
            queue = deque([(start, 0)])
            while queue:
                node, depth = queue.popleft()
                order.append(node)
                if depth >= max_depth:
                    continue
                for neighbor in graph.get(node, {}):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, depth + 1))
        else:
            raise ValueError("method must be 'bfs' or 'dfs'")
        return order

    # ------------------------------------------------------------------
    # 2. Shortest path: weighted, bidirectional Dijkstra.
    # ------------------------------------------------------------------
    def find_shortest_path(self, source=None, target=None, graph=None):
        if isinstance(source, dict):
            graph, source = source, None
        graph = self._graph(graph)
        nodes = list(graph)
        if source is None:
            source = nodes[0] if nodes else None
        if target is None:
            target = nodes[-1] if nodes else None
        if source is None or target is None or source not in graph \
                or target not in graph:
            return {"path": [], "distance": float("inf")}
        if source == target:
            return {"path": [source], "distance": 0.0}

        dist_f = {source: 0.0}
        dist_b = {target: 0.0}
        prev_f = {source: None}
        prev_b = {target: None}
        done_f, done_b = set(), set()
        heap_f = [(0.0, source)]
        heap_b = [(0.0, target)]
        best = float("inf")
        meeting = None

        while heap_f and heap_b:
            # Expand the smaller frontier (alternating bidirectional search).
            if sum(1 for _ in heap_f) <= sum(1 for _ in heap_b):
                dist, node = heapq.heappop(heap_f)
                if node in done_f:
                    continue
                done_f.add(node)
                if dist + (dist_b.get(node, float("inf"))) < best:
                    best = dist + dist_b[node]
                    meeting = node
                if dist_f[node] + dist_b.get(node, float("inf")) >= best and \
                        dist >= best:
                    break
                for neighbor, weight in graph.get(node, {}).items():
                    nd = dist + weight
                    if nd < dist_f.get(neighbor, float("inf")):
                        dist_f[neighbor] = nd
                        prev_f[neighbor] = node
                        heapq.heappush(heap_f, (nd, neighbor))
            else:
                dist, node = heapq.heappop(heap_b)
                if node in done_b:
                    continue
                done_b.add(node)
                if dist + (dist_f.get(node, float("inf"))) < best:
                    best = dist + dist_f[node]
                    meeting = node
                if dist >= best:
                    break
                for neighbor, weight in graph.get(node, {}).items():
                    nd = dist + weight
                    if nd < dist_b.get(neighbor, float("inf")):
                        dist_b[neighbor] = nd
                        prev_b[neighbor] = node
                        heapq.heappush(heap_b, (nd, neighbor))

        if meeting is None or best == float("inf"):
            return {"path": [], "distance": float("inf")}

        path = []
        node = meeting
        while node is not None:
            path.append(node)
            node = prev_f[node]
        path.reverse()
        node = prev_b[meeting]
        while node is not None:
            path.append(node)
            node = prev_b[node]
        return {"path": path, "distance": best}

    # ------------------------------------------------------------------
    # 3. Community detection: label propagation with modularity + convergence.
    # ------------------------------------------------------------------
    def detect_communities(self, graph=None, max_iterations=100,
                           tolerance=1e-9, seed=0):
        graph = self._graph(graph)
        nodes = list(graph)
        if not nodes:
            return {"communities": {}, "modularity": 0.0,
                    "iterations": 0, "converged": True}

        labels = {node: node for node in nodes}
        converged = False
        iterations = 0
        prev_modularity = float("-inf")

        for iterations in range(1, max_iterations + 1):
            changed = False
            for node in nodes:
                scores = {}
                for neighbor, weight in graph.get(node, {}).items():
                    label = labels[neighbor]
                    scores[label] = scores.get(label, 0.0) + weight
                if not scores:
                    continue
                best_label = max(scores,
                                 key=lambda l: (scores[l], str(l)))
                if best_label != labels[node]:
                    labels[node] = best_label
                    changed = True
            modularity = self._modularity(graph, labels)
            if not changed or abs(modularity - prev_modularity) <= tolerance:
                converged = True
                break
            prev_modularity = modularity

        communities = {}
        for node, label in labels.items():
            communities.setdefault(label, []).append(node)
        return {
            "communities": communities,
            "modularity": self._modularity(graph, labels),
            "iterations": iterations,
            "converged": converged,
        }

    @staticmethod
    def _modularity(graph, labels):
        m2 = 0.0
        degree = {}
        for node, neighbors in graph.items():
            degree[node] = sum(neighbors.values())
            m2 += degree[node]
        if m2 == 0:
            return 0.0
        q = 0.0
        for i, neighbors_i in graph.items():
            for j, w_ij in neighbors_i.items():
                if labels.get(i) == labels.get(j):
                    q += w_ij - degree[i] * degree[j] / m2
        return q / m2

    # ------------------------------------------------------------------
    # 4. Indexes: adjacency list + property index, kept up to date.
    # ------------------------------------------------------------------
    def create_index(self, graph=None, properties=None):
        if graph is not None:
            self.adjacency = {
                node: dict(neighbors) for node, neighbors in graph.items()
            }
            for node, neighbors in graph.items():
                self.nodes.setdefault(node, {})
                for neighbor in neighbors:
                    self.nodes.setdefault(neighbor, {})
        if properties:
            for node, props in properties.items():
                self.nodes.setdefault(node, {}).update(props)
                self.adjacency.setdefault(node, {})
        self._rebuild_property_index()
        return {
            "adjacency": self.adjacency,
            "property_index": self.property_index,
        }

    def neighbors(self, node):
        """O(1) neighbor lookup via the adjacency-list index."""
        return self.adjacency.get(node, {})

    def find_by_property(self, key, value):
        """O(1) property lookup via the property index."""
        return set(self.property_index.get((key, value), set()))

    # ------------------------------------------------------------------
    # 5. Query optimization: execution plan, predicate pushdown, caching.
    # ------------------------------------------------------------------
    def optimize_query(self, query=None):
        if query is None:
            query = {
                "scan": list(self._graph(None)),
                "filters": [],
                "joins": [],
            }

        cache_key = repr(sorted(query.items(),
                                key=lambda kv: kv[0])) \
            if isinstance(query, dict) else repr(query)
        if cache_key in self.query_cache:
            cached = self.query_cache[cache_key]
            return {**cached, "cached": True}

        filters = list(query.get("filters", []))
        joins = list(query.get("joins", []))
        scans = list(query.get("scan", []))

        # Execution plan: predicate pushdown -> filters run before joins.
        plan = []
        for source in scans:
            plan.append({"op": "scan", "source": source})
        for predicate in filters:
            plan.append({"op": "filter", "predicate": predicate,
                         "pushed_down": True})
        for join in joins:
            plan.append({"op": "join", "spec": join})

        result = {
            "plan": plan,
            "estimated_cost": self._estimate_cost(scans, filters, joins),
            "cached": False,
        }
        self.query_cache[cache_key] = result
        return result

    @staticmethod
    def _estimate_cost(scans, filters, joins):
        # Filtering first shrinks the input to the joins.
        selectivity = 0.5 ** len(filters)
        scan_cost = len(scans)
        join_cost = len(joins) * max(scan_cost, 1) * selectivity
        return scan_cost + join_cost
