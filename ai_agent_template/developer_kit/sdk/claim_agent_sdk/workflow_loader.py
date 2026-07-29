from __future__ import annotations

from dataclasses import dataclass

from .template_loader import TemplateBundle


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    type: str
    attributes: dict[str, str]


class WorkflowLoader:
    def __init__(self, template: TemplateBundle):
        self.template = template

    def load(self) -> dict[str, object]:
        text = self.template.read_text("workflows/claim_review_workflow.yaml")
        workflow: dict[str, object] = {"steps": []}
        steps: list[WorkflowStep] = []
        current: dict[str, str] | None = None
        in_steps = False

        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped == "steps:":
                in_steps = True
                continue
            if not in_steps and ":" in stripped:
                key, value = stripped.split(":", 1)
                workflow[key.strip()] = value.strip()
                continue
            if in_steps and stripped.startswith("- id:"):
                if current:
                    steps.append(
                        WorkflowStep(
                            id=current["id"],
                            type=current.get("type", ""),
                            attributes=dict(current),
                        )
                    )
                current = {"id": stripped.split(":", 1)[1].strip()}
                continue
            if current and ":" in stripped:
                key, value = stripped.split(":", 1)
                current[key.strip()] = value.strip()

        if current:
            steps.append(
                WorkflowStep(id=current["id"], type=current.get("type", ""), attributes=dict(current))
            )
        workflow["steps"] = steps
        return workflow

    def tool_names(self) -> list[str]:
        workflow = self.load()
        return [
            step.attributes["tool"]
            for step in workflow["steps"]  # type: ignore[index]
            if isinstance(step, WorkflowStep) and step.attributes.get("type") == "tool"
        ]

