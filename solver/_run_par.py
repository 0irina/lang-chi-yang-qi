# -*- coding: utf-8 -*-
"""并行回归启动器:启用多核评分池后运行指定测试脚本。
用法: python _run_par.py <测试脚本.py>
子进程(spawn)重新导入本模块时,__main__ 守卫保证测试代码不会在
子进程中重复执行。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import parallel_score

parallel_score.enable()

if __name__ == "__main__":
    src = sys.argv[1]
    code = compile(open(src, encoding="utf-8").read(), src, "exec")
    exec(code, {"__name__": "__main__", "__file__": src})
