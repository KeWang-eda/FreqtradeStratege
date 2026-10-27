"""Sticky source-write evidence, including writes later restored byte for byte.

Linux inotify(7) supplies queued inode/directory events, not sampled hashes.
Watch both inodes (hard-link writes) and parents (atomic replacement). Queue
overflow, removed watches and new source directories fail closed. Combined with
before/after SHA-256 this covers the full runner interval. It is local evidence,
not protection against a privileged process forging all artifacts.
"""

import ctypes
import os
import struct
from pathlib import Path

from quant.infrastructure.experiment_store import canonical_hash


class SourceMonitor:
    """Watch the same source scope as current_source_hashes without polling."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self._lib = ctypes.CDLL(None, use_errno=True)
        self._lib.inotify_init1.argtypes = [ctypes.c_int]
        self._lib.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        self.fd = self._lib.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), "Source monitoring unavailable; execution blocked")
        directories = {self.root}
        for name in ("quant", "tests", "tools"):
            base = self.root / name
            if base.is_dir():
                directories.add(base)
                directories.update(p for p in base.rglob("*") if p.is_dir())
        files = set(self.root.glob("*.py")) | {self.root / "pyproject.toml"}
        for name in ("quant", "tests", "tools"):
            files.update((self.root / name).rglob("*.py"))
        self.watches = {}
        try:
            # MODIFY, ATTRIB, CLOSE_WRITE, MOVE/CREATE/DELETE and SELF changes.
            for path in sorted(directories | files):
                wd = self._lib.inotify_add_watch(self.fd, os.fsencode(path), 0xFCE)
                if wd < 0:
                    raise OSError(ctypes.get_errno(), f"Cannot watch source: {path}")
                self.watches[wd] = path
        except BaseException:
            os.close(self.fd)
            raise

    def finish(self, before: dict, after: dict) -> dict:
        """Drain the kernel queue after final hashing; never clear a drift event."""
        events = []
        try:
            while True:
                try:
                    data = os.read(self.fd, 1024 * 1024)
                except BlockingIOError:
                    break
                if not data:
                    raise OSError("Source monitor ended unexpectedly")
                offset = 0
                while offset < len(data):
                    wd, mask, _, length = struct.unpack_from("iIII", data, offset)
                    name = os.fsdecode(data[offset + 16 : offset + 16 + length].split(b"\0")[0])
                    offset += 16 + length
                    path = self.watches.get(wd)
                    if path is None or mask & (0x4000 | 0x8000 | 0x2000 | 0xC00):
                        events.append({"path": None, "mask": mask, "reason": "lost coverage"})
                        continue
                    path = path / name if name else path
                    relative = path.relative_to(self.root)
                    source_tree = bool(relative.parts) and relative.parts[0] in {
                        "quant",
                        "tests",
                        "tools",
                    }
                    relevant = (
                        path.suffix == ".py"
                        or relative.as_posix() == "pyproject.toml"
                        or (source_tree and bool(mask & 0x40000000))
                    )
                    if relevant:
                        events.append({"path": relative.as_posix(), "mask": mask})
        finally:
            os.close(self.fd)
        return {
            "method": "linux-inotify-v1",
            "completed": True,
            "watch_count": len(self.watches),
            "watched_paths": sorted(
                p.relative_to(self.root).as_posix() for p in self.watches.values()
            ),
            "before_sha256": canonical_hash(before),
            "after_sha256": canonical_hash(after),
            "events": events,
        }
