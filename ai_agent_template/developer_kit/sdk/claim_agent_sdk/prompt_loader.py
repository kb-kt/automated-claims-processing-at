from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .template_loader import TemplateBundle


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    text: str
    path: Path


class PromptLoader:
    def __init__(self, template: TemplateBundle):
        self.template = template

    def load(self, relative_path: str | Path) -> PromptTemplate:
        path = self.template.require(relative_path)
        text = path.read_text(encoding="utf-8")
        return PromptTemplate(
            name=path.name,
            version=_extract_version(text),
            text=text,
            path=path,
        )

    def load_all(self) -> dict[str, PromptTemplate]:
        prompts_dir = self.template.require("prompts")
        return {
            path.name: self.load(path.relative_to(self.template.root))
            for path in sorted(prompts_dir.glob("*.md"))
        }


def _extract_version(text: str) -> str:
    match = re.search(r"Version:\s*([0-9]+\.[0-9]+\.[0-9]+)", text)
    return match.group(1) if match else "unknown"

