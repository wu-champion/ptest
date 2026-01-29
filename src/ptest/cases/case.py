from typing import Set, Dict, Any, Iterable, List       
from .tag import Tag

class Case:
    # TODO case的基础属性与管理。包括case基础信息、执行方法、状态管理等
    def __init__(self, name: str):
        self.name: str = str(name)
        self.tags: Set["Tag"] = set()

    def __repr__(self) -> str:
        return f"Case(name={self.name!r})"

    def add_tag(self, tag: "Tag") -> None:
        self.tags.add(tag)

    def remove_tag(self, tag: "Tag") -> None:
        self.tags.discard(tag)

    def get_tags(self) -> Set["Tag"]:
        return self.tags