"""Canonical author incidence: one author can occur only once per paper event."""
import hashlib
import numpy as np

VERSION = 'unique-incidence-1'


def canonical_incidence(vertices, nverts, offsets):
    if len(offsets) != len(nverts) + 1 or offsets[0] != 0 or offsets[-1] != len(vertices):
        raise ValueError('Event offsets do not describe incidences')
    if np.any(np.diff(offsets) != nverts) or np.any(nverts < 1) or np.any(nverts > 25):
        raise ValueError('Unexpected event sizes')
    keep = np.ones(len(vertices), dtype=bool)
    affected = []
    # Batch same-size teams to avoid millions of Python set allocations. Stable
    # sorting identifies repeats; indexing keep retains original byline order.
    for width in range(2, 26):
        events = np.flatnonzero(nverts == width)
        for start in range(0, len(events), 100000):
            batch = events[start:start + 100000]
            indices = offsets[batch, None] + np.arange(width)
            values = vertices[indices]
            order = np.argsort(values, axis=1, kind='stable')
            sorted_values = np.take_along_axis(values, order, axis=1)
            duplicate = sorted_values[:, 1:] == sorted_values[:, :-1]
            sorted_indices = np.take_along_axis(indices, order, axis=1)
            keep[sorted_indices[:, 1:][duplicate]] = False
            affected.extend(batch[np.any(duplicate, axis=1)].tolist())
    sizes = np.add.reduceat(keep.astype(np.int16), offsets[:-1])
    cleaned = vertices[keep]
    new_offsets = np.r_[0, np.cumsum(sizes)]
    removed = np.flatnonzero(~keep).astype('<i8')
    return cleaned, sizes, new_offsets, {
        'version': VERSION, 'affected_events': len(affected),
        'removed_duplicate_incidences': len(removed),
        'removed_positions_sha256': hashlib.sha256(removed.tobytes()).hexdigest(),
        'policy': 'Keep first occurrence within each event; preserve every event ID, timestamp and distinct author ID.',
    }
