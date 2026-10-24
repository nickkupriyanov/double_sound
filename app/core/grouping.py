"""Объединение файлов в группы дубликатов."""

from __future__ import annotations

from collections import defaultdict

from .models import AudioFile, DuplicateGroup
from .quality import rank_group


class UnionFind:
    def __init__(self, items):
        self._parent = {item: item for item in items}
        self._rank = {item: 0 for item in items}

    def find(self, item):
        parent = self._parent[item]
        while parent != self._parent[parent]:
            self._parent[parent] = self._parent[self._parent[parent]]
            parent = self._parent[parent]
        while item != parent:
            next_item = self._parent[item]
            self._parent[item] = parent
            item = next_item
        return parent

    def union(self, left, right) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        rank_left = self._rank[root_left]
        rank_right = self._rank[root_right]
        if rank_left < rank_right:
            root_left, root_right = root_right, root_left
        self._parent[root_right] = root_left
        if rank_left == rank_right:
            self._rank[root_left] += 1


def build_groups(
    files: list[AudioFile],
    sim_pairs: dict[tuple[str, str], float],
    sha_buckets: dict[str, list[AudioFile]],
) -> list[DuplicateGroup]:
    """Собирает группы из точных совпадений и пар с похожим отпечатком."""
    if not files:
        return []

    union = UnionFind([audio.path for audio in files])

    for bucket in sha_buckets.values():
        for audio in bucket[1:]:
            union.union(bucket[0].path, audio.path)

    for left, right in sim_pairs:
        union.union(left, right)

    # Представитель каждого содержимого: для точных копий отпечаток считается
    # один раз, поэтому все связи идут через него.
    rep_path: dict[str, str] = {}
    exact_size: dict[str, int] = {}
    for sha, bucket in sha_buckets.items():
        representative = bucket[0].path
        exact_size[sha] = len(bucket)
        for audio in bucket:
            rep_path[audio.path] = representative
    for audio in files:
        rep_path.setdefault(audio.path, audio.path)

    best_sim: dict[str, float] = {}
    for (left, right), score in sim_pairs.items():
        best_sim[left] = max(best_sim.get(left, 0.0), score)
        best_sim[right] = max(best_sim.get(right, 0.0), score)

    components: dict[str, list[AudioFile]] = defaultdict(list)
    for audio in files:
        components[union.find(audio.path)].append(audio)

    groups: list[DuplicateGroup] = []
    for members in components.values():
        if len(members) < 2:
            continue

        has_exact = False
        has_acoustic = False
        scores: list[float] = []

        for audio in members:
            exact = exact_size.get(audio.sha256, 0) > 1
            if exact:
                audio.match_type = "exact"
                audio.similarity = 1.0
                has_exact = True
            else:
                audio.match_type = "acoustic"
                audio.similarity = best_sim.get(rep_path.get(audio.path, audio.path), 0.0)
                has_acoustic = True
            scores.append(audio.similarity)

        if has_exact and not has_acoustic:
            kind = "exact"
            group_score = 1.0
        elif has_acoustic and not has_exact:
            kind = "acoustic"
            group_score = max(scores) if scores else 0.0
        else:
            kind = "mixed"
            group_score = max(scores) if scores else 1.0

        group = DuplicateGroup(files=members, kind=kind, similarity=group_score)
        group.keeper = rank_group(members)
        groups.append(group)

    groups.sort(key=lambda group: group.sort_key, reverse=True)
    for index, group in enumerate(groups, start=1):
        group.index = index
    return groups
