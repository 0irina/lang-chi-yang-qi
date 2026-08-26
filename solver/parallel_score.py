# -*- coding: utf-8 -*-
"""多核并行胜率评分(懒启动进程池)。

- 引擎把"每个候选走法的胜率评分"批量提交,各核心并行计算;
- 仅当显式 enable() 后才建池(GUI 启用;测试/脚本默认串行,
  避免 spawn 在无主函数保护的脚本里产生副作用);
- 建池或计算失败一律自动退回串行,保证永不因并行崩溃;
- 每个工作进程独立加载破解表(mmap,操作系统共享页缓存)与
  自己的胜率缓存,冻结版(exe)需在入口调用 freeze_support()。
"""
import os
import sys
import atexit

_ENABLED = False
_POOL = None
_MAX_WORKERS = max(2, min(8, (os.cpu_count() or 4)))
_ENG = None


def _shutdown_pool():
    global _POOL
    if _POOL is not None:
        try:
            _POOL.terminate()
            _POOL.join()
        except Exception:
            pass
        _POOL = None


atexit.register(_shutdown_pool)


def enable():
    global _ENABLED
    _ENABLED = True


def _init_worker():
    _dir = os.path.dirname(os.path.abspath(__file__))
    if _dir not in sys.path:
        sys.path.insert(0, _dir)
    import endgame
    endgame.load_tables()
    import engine as _engmod
    global _ENG
    _ENG = _engmod.Engine()
    _ENG.score_depth = 4


def _task(args):
    w, s, turn, depth = args
    import winrate
    return winrate.score_position(w, s, turn, eng=_ENG, depth=depth)[0]


def is_parallel_active():
    return _ENABLED and _POOL is not None


def batch_scores(items, depth, eng=None):
    """items: [(w, s, turn), ...] -> 并行评分列表。
    未启用 / 项数<=2 / 任何异常:退回串行(带调用方引擎)。"""
    global _POOL
    import winrate
    if not _ENABLED or len(items) <= 2:
        return [winrate.score_position(w, s, t, eng=eng, depth=depth)[0]
                for w, s, t in items]
    try:
        if _POOL is None:
            import multiprocessing as _mp
            ctx = _mp.get_context("spawn")
            _POOL = ctx.Pool(_MAX_WORKERS, initializer=_init_worker)
        return _POOL.map(_task, [(w, s, t, depth) for w, s, t in items])
    except Exception:
        return [winrate.score_position(w, s, t, eng=eng, depth=depth)[0]
                for w, s, t in items]
