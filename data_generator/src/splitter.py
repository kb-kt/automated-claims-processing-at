from __future__ import annotations

import random
from collections import defaultdict


def stratified_split(
    pairs: list[tuple[dict, dict]], dev_ratio: float, seed: int
) -> tuple[list[tuple[dict, dict]], list[tuple[dict, dict]]]:
    grouped: dict[tuple[str, str, str], list[tuple[dict, dict]]] = defaultdict(list)
    for claim, label in pairs:
        key = (
            label.get("expected_decision", ""),
            label.get("coverage_code", ""),
            claim.get("scenario_type", ""),
        )
        grouped[key].append((claim, label))

    rng = random.Random(seed)
    dev: list[tuple[dict, dict]] = []
    eval_: list[tuple[dict, dict]] = []
    for key in sorted(grouped):
        items = list(grouped[key])
        rng.shuffle(items)
        if len(items) == 1:
            eval_.extend(items)
            continue
        dev_count = round(len(items) * dev_ratio)
        dev_count = max(1, min(len(items) - 1, dev_count))
        dev.extend(items[:dev_count])
        eval_.extend(items[dev_count:])
    return dev, eval_
