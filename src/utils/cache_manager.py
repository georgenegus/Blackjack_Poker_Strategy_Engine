"""Hash-validated JSON cache. Every cached file records the hash of its source
code plus a caller-supplied key (e.g. a RuleSet's own identity); any mismatch --
including a pre-existing file with no manifest metadata at all -- triggers a
rebuild. There is deliberately NO grandfather clause: T20_Win_Probability_Model's
cache manager trusted a pre-existing file with no manifest entry blindly, which
let its team-Elo caches silently drift out of sync with their source code for a
long time before anyone caught it. See .agents/coding-standards.md's "Cache
Management" section.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict


def source_hash(*source_files: Path) -> str:
    """A short deterministic hash of one or more source files' current content,
    used as the cache-validity key -- editing any of them invalidates every
    cache built from them, forcing a rebuild on next use."""
    h = hashlib.sha256()
    for f in sorted(source_files):
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def load_or_compute(
    cache_path: Path, source_hash_value: str, cache_key: Dict[str, Any], compute_fn: Callable[[], Any]
) -> Any:
    """Returns compute_fn()'s result, using a hash-validated JSON cache at
    cache_path. Valid only if the cached file's recorded source hash AND
    cache_key both match exactly what's passed in now -- any mismatch, or any
    read/parse failure, triggers a full rebuild and overwrite. A pre-existing
    file with no '_source_hash'/'_cache_key' at all is treated as INVALID, not
    grandfathered in -- see the module docstring.
    """
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("_source_hash") == source_hash_value and cached.get("_cache_key") == cache_key:
                return cached["data"]
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    data = compute_fn()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({"_source_hash": source_hash_value, "_cache_key": cache_key, "data": data}, f, indent=2)
    return data
