"""
pairwise-graph-db-system - GraphDBSystem

This module contains a deliberately broken implementation.
Fix all bugs so that tests pass.
"""


class GraphDBSystem:
    def __init__(self):
        self.state = {}

    def traverse_graph(self, *args, **kwargs):
        """BUG: 图遍历不做BFS/DFS，随机走"""
        return None

    def find_shortest_path(self, *args, **kwargs):
        """BUG: 最短路径不做Dijkstra，暴力枚举"""
        return None

    def detect_communities(self, *args, **kwargs):
        """BUG: 社区发现不做算法，随机分组"""
        return None

    def create_index(self, *args, **kwargs):
        """BUG: 索引不做邻接表，查询邻居全表扫描"""
        return None

    def optimize_query(self, *args, **kwargs):
        """BUG: 查询优化不做执行计划，永远按顺序执行"""
        return None

