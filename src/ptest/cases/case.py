from typing import Set
from .tag import Tag


class Case:
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
