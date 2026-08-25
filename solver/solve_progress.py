# -*- coding: utf-8 -*-
"""查看 tt_new 求解进度:断点水位、处理速率、预计剩余时间。"""
import os
import sys
import time

import numpy as np

TT = r"D:\狼吃羊棋\solver\tt_new"
meta = os.path.join(TT, "full_meta.npy")
tab = os.path.join(TT, "full_packed.npy")
done = os.path.join(TT, "full_done.flag")

print("done.flag:", os.path.exists(done))
print("packed:", os.path.exists(tab),
      f"({os.path.getsize(tab)/1e9:.2f}GB)" if os.path.exists(tab) else "")
if not os.path.exists(meta):
    print("no checkpoint yet")
    sys.exit(0)
m = np.load(meta)
head, tail = int(m[0]), int(m[1])
mt = os.path.getmtime(meta)
now = time.time()
print(f"head={head:,} tail={tail:,} remaining={tail - head:,}")
print(f"checkpoint_age={now - mt:.0f}s")
print(f"progress={head / 9640000000 * 100:.1f}% of ~96.4亿")
# 估算速率:读取本目录下上一代水位(如有)
prev = meta + ".prev"
if os.path.exists(prev):
    try:
        mp = np.load(prev)
        hp, tp = int(mp[0]), int(mp[1])
        pt = os.path.getmtime(prev)
        dt = max(mt - pt, 1e-9)
        rate = (head - hp) / dt
        print(f"pop_rate={rate:,.0f}/s (上一代 {dt/60:.1f}min 前)")
        # 假设总处理量 ~84亿(小规模试验 88% 被定值):剩余处理 = 84亿 - head
        est_total = 8400000000
        rem_pops = max(est_total - head, 0)
        eta_h = rem_pops / max(rate, 1) / 3600
        print(f"ETA_propagation(按总处理84亿估算)={eta_h:.1f}h")
    except Exception as e:
        print("prev meta read fail:", e)
