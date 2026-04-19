"""
Reciprocal Rank Fusion (RRF) — merges dense and sparse search results.

Formula: RRF(d) = Σ 1 / (k + rank(d))
Weights: 0.6 dense + 0.4 sparse
"""

from shared.constants import DENSE_WEIGHT, SPARSE_WEIGHT, RRF_K


def reciprocal_rank_fusion(
    dense_results: list[dict],
    sparse_results: list[dict],
    top_k: int = 20,
) -> list[dict]:
    """
    Merge dense and sparse results using weighted RRF.

    Each result must have: {"id": str, "score": float, "payload": dict}
    Returns merged list sorted by fused score, deduplicated by id.
    """
    scores: dict[str, float] = {}
    payloads: dict[str, dict] = {}

    for rank, result in enumerate(dense_results):
        rid = result["id"]
        scores[rid] = scores.get(rid, 0.0) + DENSE_WEIGHT * (1.0 / (RRF_K + rank + 1))
        payloads[rid] = result["payload"]

    for rank, result in enumerate(sparse_results):
        rid = result["id"]
        scores[rid] = scores.get(rid, 0.0) + SPARSE_WEIGHT * (1.0 / (RRF_K + rank + 1))
        if rid not in payloads:
            payloads[rid] = result["payload"]

    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        {"id": rid, "score": score, "payload": payloads[rid]}
        for rid, score in merged
    ]
