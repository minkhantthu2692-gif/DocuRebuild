"""Small, dependency-free scoring helpers for figure-region evaluation.

The figure detector returns rectangles; a ground-truth case lists the rectangles
a person says are real figures. A proposal matches a truth box when their
intersection-over-union reaches a threshold, and each box may be matched at most
once. Precision and recall are then the usual definitions, so an accuracy claim
can be backed by a measured number instead of an assertion.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

Box = Mapping[str, float]


def iou(first: Box, second: Box) -> float:
    """Return intersection-over-union for two ``x/y/width/height`` boxes."""
    left = max(first["x"], second["x"])
    top = max(first["y"], second["y"])
    right = min(first["x"] + first["width"], second["x"] + second["width"])
    bottom = min(first["y"] + first["height"], second["y"] + second["height"])
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    union = (
        first["width"] * first["height"]
        + second["width"] * second["height"]
        - intersection
    )
    return intersection / union if union > 0 else 0.0


def match_boxes(
    proposed: Sequence[Box], truth: Sequence[Box], threshold: float = 0.5
) -> list[tuple[int, int, float]]:
    """Greedily match proposals to truth boxes by descending IoU.

    Returns ``(proposal_index, truth_index, iou)`` triples. Each proposal and
    each truth box is used at most once, so two overlapping proposals cannot
    both claim the same figure.
    """
    candidates: list[tuple[float, int, int]] = []
    for proposal_index, proposal in enumerate(proposed):
        for truth_index, target in enumerate(truth):
            score = iou(proposal, target)
            if score >= threshold:
                candidates.append((score, proposal_index, truth_index))
    candidates.sort(reverse=True)
    used_proposals: set[int] = set()
    used_truth: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for score, proposal_index, truth_index in candidates:
        if proposal_index in used_proposals or truth_index in used_truth:
            continue
        used_proposals.add(proposal_index)
        used_truth.add(truth_index)
        matches.append((proposal_index, truth_index, score))
    return matches


def score_boxes(
    proposed: Sequence[Box], truth: Sequence[Box], threshold: float = 0.5
) -> dict[str, Any]:
    """Return counts and precision/recall/F1 for one page."""
    matches = match_boxes(proposed, truth, threshold)
    true_positive = len(matches)
    false_positive = len(proposed) - true_positive
    false_negative = len(truth) - true_positive
    if proposed:
        precision = true_positive / len(proposed)
    else:
        precision = 1.0 if not truth else 0.0
    recall = true_positive / len(truth) if truth else 1.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def aggregate(scores: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Micro-average several per-page scores."""
    true_positive = sum(score["true_positive"] for score in scores)
    false_positive = sum(score["false_positive"] for score in scores)
    false_negative = sum(score["false_negative"] for score in scores)
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 1.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 1.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }
