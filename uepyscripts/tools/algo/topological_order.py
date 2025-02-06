from collections import defaultdict, deque

class Graph:
    def __init__(self):
        self.graph = defaultdict(list)
        self.nodes = set()

    def add_edge(self, u, v):
        self.graph[u].append(v)
        self.nodes.add(u)
        self.nodes.add(v)

    def calculate_in_degree(self):
        in_degree = {node: 0 for node in self.nodes}
        for node in self.graph:
            for neighbor in self.graph[node]:
                in_degree[neighbor] += 1
        return in_degree

    def topological_sort_with_hierarchy(
        self
    ) -> list[list[str]]:
        in_degree = self.calculate_in_degree()
        queue = deque([node for node in in_degree if in_degree[node] == 0])
        sorted_hierarchy = []

        while queue:
            level_size = len(queue)
            current_level_nodes = []

            for _ in range(level_size):
                node = queue.popleft()
                current_level_nodes.append(node)

                for neighbor in self.graph[node]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            sorted_hierarchy.append(current_level_nodes)

        if sum(len(level) for level in sorted_hierarchy) != len(self.nodes):
            return None  # Graph contains a cycle

        sorted_hierarchy.reverse()
        return sorted_hierarchy