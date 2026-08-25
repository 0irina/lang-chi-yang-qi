# -*- coding: utf-8 -*-
"""最终收尾:dist_pass 完成后一键验证 + 清理。

流程:
  1. 要求 tt\\dist_pass_done.flag 存在(否则拒绝)
  2. 阶段 A:穷举 k<=5 与独立顺序求解器交叉验证距离
  3. 阶段 B:40 万抽样局部一致性验证
  4. engine_check:初始局面/立即吃杀/150 步规则
  5. 全部通过才清理:删除 full_distq.dat(71.8GB 队列)、种子进度、存档水位、日志
  6. 输出总结

用法: python finalize.py [--keep-temps] [--force]
  --keep-temps: 验证通过后不删临时文件(手动清理)
  --force:      无完成标志也继续(危险,仅调试)
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TT = os.path.join(HERE, "tt")
FLAG = os.path.join(TT, "dist_pass_done.flag")

DEL_FILES = [
    "full_distq.dat", "dist_seed_pos.npy",
    "full_dist_meta.npy", "full_dist_meta.npy.prev",
]


def run(script, args=None):
    cmd = [sys.executable, "-u", os.path.join(HERE, script)] + (args or [])
    print(f"\n===== {script} {' '.join(args or [])} =====", flush=True)
    r = subprocess.run(cmd, cwd=os.path.dirname(HERE))
    return r.returncode


def cleanup():
    freed = 0
    for name in DEL_FILES:
        p = os.path.join(TT, name)
        if os.path.exists(p):
            try:
                sz = os.path.getsize(p)
                os.remove(p)
                freed += sz
                print(f"[cleanup] removed {name} ({sz/1e9:.1f}GB)")
            except PermissionError:
                print(f"[cleanup] {name} busy, will retry...")
                time.sleep(15)
                try:
                    sz = os.path.getsize(p)
                    os.remove(p)
                    freed += sz
                    print(f"[cleanup] removed {name} on retry ({sz/1e9:.1f}GB)")
                except PermissionError:
                    print(f"[cleanup] FAILED to remove {name} (still locked)")
    log = os.path.join(HERE, "dist_pass_log.txt")
    if os.path.exists(log):
        os.remove(log)
        print("[cleanup] removed dist_pass_log.txt")
    print(f"[cleanup] total freed = {freed/1e9:.1f}GB")


def main():
    args = sys.argv[1:]
    keep = "--keep-temps" in args
    force = "--force" in args
    if not os.path.exists(FLAG) and not force:
        print("REFUSED: dist_pass_done.flag not found; dist pass not finished.")
        return 2

    rc = 0
    rc |= run("dist_check.py", ["--phase", "a"])
    if rc:
        print("ABORT: phase A found mismatches; keeping all files for debugging")
        return rc
    rc |= run("dist_check.py", ["--phase", "b"])
    if rc:
        print("ABORT: phase B found mismatches; keeping all files for debugging")
        return rc
    rc |= run("engine_check.py")
    if rc:
        print("ABORT: engine check failed; keeping all files for debugging")
        return rc

    print("\nALL CHECKS PASSED.")
    if not keep:
        cleanup()
        print("FINAL TABLES READY: tt\\full_packed.npy + tt\\full_dist.dat "
              "(exact values + exact distances)")
    else:
        print("--keep-temps: temporary files left in place")
    return 0


if __name__ == "__main__":
    sys.exit(main())
