#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
locking.py — qamaster Runtime 跨平台文件锁（仅 Python 标准库）

用于串行化共享可变资源的 read-modify-write（当前仅 MANIFEST.md 多需求协调）。
状态文件按 (workflow, req_id) 分区后无并发写者，不需要锁。

设计要点：
  - advisory lock（建议性锁），进程崩溃/退出自动释放（fd 关闭即解锁，崩溃安全）
  - POSIX: fcntl.flock(LOCK_EX | LOCK_NB) + 退避重试
  - Windows: msvcrt.locking(LK_NBLCK, 1) + 退避重试
  - 锁文件 = <被保护资源路径> + ".lock"（同目录）

仅用 Python 标准库（与 state_store.py:17 仓库策略一致）。
"""
import os
import time

try:
    import fcntl as _fcntl  # POSIX
except ImportError:
    _fcntl = None

try:
    import msvcrt as _msvcrt  # Windows
except ImportError:
    _msvcrt = None


class LockTimeout(TimeoutError):
    """文件锁在 timeout 秒内未获取到。"""


class FileLock:
    """跨平台 advisory 文件锁。

    用法：
        with FileLock(manifest_path, timeout=30):
            # 此区域内对 manifest_path 的 read-modify-write 串行化
            ...

    锁文件路径 = path + ".lock"。fd 关闭即释放（进程崩溃也释放）。
    """

    def __init__(self, path, timeout=30.0, poll=0.1):
        self.path = path
        self.timeout = timeout
        self.poll = poll
        self._lock_path = path + ".lock"
        self._fd = None

    def _acquire(self):
        d = os.path.dirname(self._lock_path) or "."
        if not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        # 以 'ab+' 打开：不存在则创建；fd 保留到 release
        self._fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        deadline = None
        # 仅在需要重试时计算 deadline（避免每次调用取系统时间）
        started = False
        while True:
            if self._try_lock():
                return
            if not started:
                import time as _t
                started = True
                deadline = _t.monotonic() + self.timeout
            if _t.monotonic() >= deadline:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None
                raise LockTimeout("文件锁获取超时（%s 秒）: %s" % (self.timeout, self._lock_path))
            time.sleep(self.poll)

    def _try_lock(self):
        if _fcntl is not None:
            try:
                _fcntl.flock(self._fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                return True
            except (OSError, IOError):
                return False
        if _msvcrt is not None:
            try:
                _msvcrt.locking(self._fd, _msvcrt.LK_NBLCK, 1)
                return True
            except (OSError, IOError):
                return False
        # 无 fcntl/msvcrt 平台（理论不应出现）：退化为临界区占位，每次 True（无锁）
        return True

    def _release(self):
        if self._fd is None:
            return
        try:
            if _fcntl is not None:
                try:
                    _fcntl.flock(self._fd, _fcntl.LOCK_UN)
                except (OSError, IOError):
                    pass
            elif _msvcrt is not None:
                try:
                    # 释放前须回到文件头并解锁 1 字节
                    os.lseek(self._fd, 0, os.SEEK_SET)
                    _msvcrt.locking(self._fd, _msvcrt.LK_UNLCK, 1)
                except (OSError, IOError):
                    pass
        finally:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def __enter__(self):
        self._acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._release()
        return False
