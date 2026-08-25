# -*- coding: utf-8 -*-
"""单独测试 _verify_full(定位崩溃)"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import endgame_full as EF
from index import (PLACEOFF_C, C22K, WOLF_MASKS, WR_OF_DENSE, FREECELLS,
                   FREELIST, CTAB_FLAT, WDEN, MIRROR_WR, MIRROR_CELL)

print("加载表...", flush=True)
tab = np.load(r'D:\狼吃羊棋\solver\tt_par\full_packed.npy')
print("表大小:", len(tab), flush=True)
print("开始复核...", flush=True)
bad = EF._verify_full(5, len(tab), tab, PLACEOFF_C, C22K, WOLF_MASKS,
                      WR_OF_DENSE, FREECELLS, FREELIST, CTAB_FLAT, WDEN,
                      MIRROR_WR, MIRROR_CELL, EF.NEIGH)
print("复核错误数:", bad, flush=True)
