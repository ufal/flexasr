"""Clustering algorithms over L2-normalised embeddings (cosine similarity): agglomerative (fixed k or
threshold), spectral (eigengap, as in WeSpeaker), k-means, silhouette."""

from __future__ import annotations

import numpy as np

def _cluster(emb: np.ndarray, k: int) -> np.ndarray:
    """Average-linkage agglomerative clustering on cosine distance into ``k`` clusters."""
    n = len(emb)
    if k >= n:
        return np.arange(n)
    dist = 1.0 - emb @ emb.T
    np.fill_diagonal(dist, np.inf)
    size = np.ones(n)
    label = np.arange(n)
    active = np.ones(n, bool)
    for _ in range(n - k):
        sub = np.where(active[:, None] & active[None, :], dist, np.inf)
        a, b = np.unravel_index(np.argmin(sub), sub.shape)
        if a > b:
            a, b = b, a
        new = (dist[a] * size[a] + dist[b] * size[b]) / (size[a] + size[b])   # average linkage
        dist[a, :] = new
        dist[:, a] = new
        dist[a, a] = np.inf
        size[a] += size[b]
        active[b] = False
        dist[b, :] = dist[:, b] = np.inf
        label[label == b] = a
    _, out = np.unique(label, return_inverse=True)
    return out


def _cluster_threshold(emb: np.ndarray, min_sim: float, k_min: int = 1, k_max: int = 0) -> np.ndarray:
    """Average-linkage clustering that stops when the closest clusters' average cosine similarity
    falls below ``min_sim`` (the number of speakers follows from the threshold), kept within
    [k_min, k_max]."""
    n = len(emb)
    k_max = k_max or n
    sim = emb @ emb.T
    lab = np.arange(n)
    while True:
        ks = np.unique(lab)
        if len(ks) <= max(1, k_min):
            break
        best, pair = -np.inf, None
        for i, a in enumerate(ks):
            for b in ks[i + 1:]:
                v = sim[np.ix_(lab == a, lab == b)].mean()
                if v > best:
                    best, pair = v, (a, b)
        if best < min_sim and len(ks) <= k_max:
            break
        lab[lab == pair[1]] = pair[0]
    _, out = np.unique(lab, return_inverse=True)
    return out


def _kmeans(x: np.ndarray, k: int, iters: int = 30, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    cent = [x[rng.integers(len(x))]]
    for _ in range(1, k):                                   # k-means++ initialisation
        d = np.min(((x[:, None, :] - np.array(cent)[None]) ** 2).sum(-1), axis=1)
        cent.append(x[rng.choice(len(x), p=d / d.sum())] if d.sum() > 0 else x[rng.integers(len(x))])
    cent = np.array(cent)
    for _ in range(iters):
        lab = np.argmin(((x[:, None, :] - cent[None]) ** 2).sum(-1), axis=1)
        new = np.array([x[lab == j].mean(0) if (lab == j).any() else cent[j] for j in range(k)])
        if np.allclose(new, cent):
            break
        cent = new
    return lab


def _cluster_spectral(emb: np.ndarray, k_min: int = 1, k_max: int = 8, pval: float = 0.022,
                      fixed_k: int = 0) -> np.ndarray:
    """Spectral clustering as in WeSpeaker's diarization recipe: cosine affinity, keep each row's
    nearest neighbours (p-pruning), symmetrise, graph Laplacian, number of speakers from the largest
    eigengap (within [k_min, k_max]), k-means on the eigenvectors."""
    n = len(emb)
    if n < 3:
        return np.zeros(n, int)
    A = emb @ emb.T
    keep = max(2, int(round(n * pval)) if n < 1000 else int(round(n * 0.01)))
    order = np.argsort(-A, axis=1)
    pruned = np.zeros_like(A)
    rows = np.arange(n)[:, None]
    pruned[rows, order[:, :keep]] = A[rows, order[:, :keep]]
    A = np.maximum((pruned + pruned.T) / 2, 0.0)
    np.fill_diagonal(A, 0.0)
    L = np.diag(A.sum(1)) - A
    vals, vecs = np.linalg.eigh(L)
    if fixed_k:
        k = fixed_k
    else:
        k_max = max(k_min, min(k_max, n - 1))
        gaps = np.diff(vals[: k_max + 1])
        k = int(np.argmax(gaps[k_min - 1:]) + k_min) if len(gaps) >= k_min else k_min
    if k <= 1:
        return np.zeros(n, int)
    return _kmeans(vecs[:, :k], k)


def _silhouette(emb: np.ndarray, lab: np.ndarray) -> float:
    ks = np.unique(lab)
    if len(ks) < 2:
        return -1.0
    d = 1.0 - emb @ emb.T
    s = []
    for i in range(len(emb)):
        same = lab == lab[i]
        if same.sum() < 2:
            s.append(0.0)
            continue
        a = d[i, same].sum() / (same.sum() - 1)
        b = min(d[i, lab == k].mean() for k in ks if k != lab[i])
        s.append((b - a) / max(a, b, 1e-9))
    return float(np.mean(s))
