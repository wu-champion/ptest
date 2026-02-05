from typing import Set, Dict, Any, Iterable, List

"""
Tag 类：用于管理测试用例的标签关系（级别 / 父 tag / 子 tag）及常用操作。

说明：
- 每个 Tag 通过 name 唯一标识（在同一测试集中请保证 name 唯一）。
- 支持双向维护父/子关系，提供防环检测（可选）。
"""


class Tag:
    def __init__(self, name: str, level: int = 0):
        self.name: str = str(name)
        self.level: int = int(level)
        self.parents: Set["Tag"] = set()
        self.children: Set["Tag"] = set()

    def __repr__(self) -> str:
        return f"Tag(name={self.name!r}, level={self.level})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Tag) and self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)

    # --- level 操作 ---
    def set_level(self, level: int) -> None:
        self.level = int(level)

    def get_level(self) -> int:
        return self.level

    # --- 父 / 子 操作 ---
    def add_parent(
        self, parent: "Tag", bidirectional: bool = True, prevent_cycle: bool = True
    ) -> None:
        if parent is self:
            raise ValueError("不能将自己设为自己的父 tag")
        if prevent_cycle and parent in self.find_descendants(include_self=True):
            raise ValueError("添加会导致环（cycle），已阻止")
        self.parents.add(parent)
        if bidirectional:
            parent.children.add(self)

    def remove_parent(self, parent: "Tag", bidirectional: bool = True) -> None:
        self.parents.discard(parent)
        if bidirectional:
            parent.children.discard(self)

    def add_child(
        self, child: "Tag", bidirectional: bool = True, prevent_cycle: bool = True
    ) -> None:
        if child is self:
            raise ValueError("不能将自己设为自己的子 tag")
        if prevent_cycle and child in self.find_ancestors(include_self=True):
            raise ValueError("添加会导致环（cycle），已阻止")
        self.children.add(child)
        if bidirectional:
            child.parents.add(self)

    def remove_child(self, child: "Tag", bidirectional: bool = True) -> None:
        self.children.discard(child)
        if bidirectional:
            child.parents.discard(self)

    # --- 查询辅助 ---
    def find_ancestors(self, include_self: bool = False) -> Set["Tag"]:
        seen: Set[Tag] = set()
        stack: List["Tag"] = [self] if include_self else list(self.parents)
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for p in cur.parents:
                if p not in seen:
                    stack.append(p)
        return seen

    def find_descendants(self, include_self: bool = False) -> Set["Tag"]:
        seen: Set[Tag] = set()
        stack: List["Tag"] = [self] if include_self else list(self.children)
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for c in cur.children:
                if c not in seen:
                    stack.append(c)
        return seen

    # --- 序列化 / 辅助输出 ---
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "level": self.level,
            "parents": sorted(p.name for p in self.parents),
            "children": sorted(c.name for c in self.children),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Tag":
        return cls(name=data.get("name", ""), level=data.get("level", 0))
