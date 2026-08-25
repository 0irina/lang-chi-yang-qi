# -*- coding: utf-8 -*-
"""数据表打包/解包:用于软件分发。

格式:每个 .zst 文件 = 若干块,每块 = [8字节大端块长][一块独立的 lzma(.xz)帧]。
解包只用 Python 内置 lzma(打包版主程序零第三方依赖)。
"""
import lzma
import os


def _pack_chunk(args):
    """Windows spawn 子进程入口(顶层函数,可被 pickle)"""
    src, chunk, level, off = args
    with open(src, "rb") as f:
        f.seek(off)
        data = f.read(chunk)
    return lzma.compress(data, preset=level, format=lzma.FORMAT_XZ)


def pack(src, dst, chunk=32 << 20, level=9, jobs=None):
    """多进程并行压缩(每个块一个独立 .xz 帧,内存占用受控)"""
    from multiprocessing import Pool

    size = os.path.getsize(src)
    offsets = list(range(0, size, chunk))
    if jobs is None:
        jobs = min(20, os.cpu_count() or 4)
    with Pool(jobs) as p:
        frames = p.map(_pack_chunk,
                       [(src, chunk, level, off) for off in offsets],
                       chunksize=1)
    with open(dst, "wb") as out:
        for fr in frames:
            out.write(len(fr).to_bytes(8, "big"))
            out.write(fr)
    return len(frames)


def unpack(src, dst, chunk=32 << 20):
    tmp = dst + ".tmp"
    try:
        with open(src, "rb") as f, open(tmp, "wb") as out:
            while True:
                hdr = f.read(8)
                if not hdr:
                    break
                n = int.from_bytes(hdr, "big")
                frame = f.read(n)
                if len(frame) != n:
                    raise IOError(f"压缩包损坏: {os.path.basename(src)} "
                                  f"(块不完整,可能传输/下载时出错,请重新拷贝)")
                out.write(lzma.decompress(frame))
        os.replace(tmp, dst)
    except BaseException:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def ensure_tables(ttdir, progress=None):
    """首次运行:若 tt 目录缺 .npy/.dat 但存在同名 .zst,自动解压。
    progress(text):可选回调,用于显示解压进度。返回解压的文件列表。"""
    done = []
    if not os.path.isdir(ttdir):
        return done
    for name in sorted(os.listdir(ttdir)):
        if not name.endswith(".zst"):
            continue
        target = os.path.join(ttdir, name[:-4])
        if os.path.exists(target):
            continue
        src = os.path.join(ttdir, name)
        if progress:
            progress(f"首次安装:正在解压 {name[:-4]} …")
        unpack(src, target)
        done.append(target)
        if progress:
            progress(f"完成: {name[:-4]}")
    return done


if __name__ == "__main__":
    import sys
    import time

    # 用法: python tabpack.py pack <src> <dst> [level]
    #       python tabpack.py unpack <src> <dst>
    if len(sys.argv) >= 4 and sys.argv[1] == "pack":
        lvl = int(sys.argv[4]) if len(sys.argv) > 4 else 19
        t0 = time.time()
        n = pack(sys.argv[2], sys.argv[3], level=lvl)
        a, b = os.path.getsize(sys.argv[2]), os.path.getsize(sys.argv[3])
        print(f"压缩完成: {a/1e9:.2f}GB -> {b/1e9:.2f}GB "
              f"({a/max(1,b):.2f}:1), 块数={n}, 用时={time.time()-t0:.0f}s")
    elif len(sys.argv) >= 4 and sys.argv[1] == "unpack":
        t0 = time.time()
        unpack(sys.argv[2], sys.argv[3])
        print(f"解压完成, 用时={time.time()-t0:.0f}s")
    else:
        print(__doc__)
