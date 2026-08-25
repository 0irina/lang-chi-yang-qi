# -*- coding: utf-8 -*-
"""人类棋谱逐手回放诊断(人类执羊,AI 执狼,全破解表核对)。

对每一步:
- 前值: 走子方视角局面真实值(狼胜/羊胜/和棋)
- 走后值: 走这手之后的局面真实值
- 最佳可达: 走子方全部合法着法能取得的最好结果
- 判定: 完美 / 漏胜(有必胜着没走) / 败招(把更好结果走坏)
- 狼方附加 安全吃/毒吃 统计(检验"毒羊阵")
- 羊方附加 胜着/和着/败着 统计(检验陷阱形状与压力)
另外: 全程检测局面重复,以及最终局面的当前选项。
结果同时写入 replay_human_report.txt。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import endgame
from rules import (WOLF, SHEEP, WOLF_WIN, SHEEP_WIN, DRAW, ONGOING,
                   WIN_NAMES, pos_name, wolf_moves, sheep_moves,
                   apply_wolf_move, apply_sheep_move, popcount,
                   INIT_WOLVES, INIT_SHEEP)

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "game_human_20260824.txt")
OUT = SRC + ".report.txt"


def parse(path):
    moves = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = __import__("re").match(r"^(\d+)\.\s*(.*)$", line)
            if m:
                line = m.group(2)
            parts = line.split()
            if len(parts) < 2 or parts[0] not in ("狼", "羊"):
                continue
            who = parts[0]
            mv = parts[1].replace("->", "→")
            a, b = mv.split("→")

            def cell(s):
                col = ord(s[0]) - 65
                r0 = 5 - int(s[1])
                return r0 * 5 + col

            tag = "吃" in parts[2:]
            moves.append((who, cell(a), cell(b), tag))
    return moves


def rank_for(v, turn):
    if turn == WOLF:
        return {WOLF_WIN: 0, DRAW: 1, SHEEP_WIN: 2}.get(v, 9)
    return {SHEEP_WIN: 0, DRAW: 1, WOLF_WIN: 2}.get(v, 9)


def best_name(turn, r):
    if turn == WOLF:
        return {0: WOLF_WIN, 1: DRAW, 2: SHEEP_WIN}[r]
    return {0: SHEEP_WIN, 1: DRAW, 2: WOLF_WIN}[r]


def board_str(w, s):
    out = []
    for r in range(5):
        cells = []
        for c in range(5):
            p = r * 5 + c
            if (w >> p) & 1:
                cells.append("W")
            elif (s >> p) & 1:
                cells.append("S")
            else:
                cells.append(".")
        out.append("".join(cells))
    return "\n".join(out)


def main():
    lines = []
    moves = parse(SRC)
    lines.append(f"解析到 {len(moves)} 手")
    loaded = endgame.load_tables()
    lines.append("加载表: full" if endgame._FULL is not None
                 else f"加载表: k<={loaded}")

    w, s = INIT_WOLVES, INIT_SHEEP
    stats = {"狼": {"ok": 0, "bad": [], "miss": []},
             "羊": {"ok": 0, "bad": [], "miss": []}}
    seen = {}          # (w,s) -> [move numbers]
    tag_bad = []
    uniq = {"狼": 0, "羊": 0}   # 走子方"保持不败的着法数=1"的手数

    hdr = (f"{'手':>3} {'方':<2} {'招':<9} {'前值':<5} {'走后':<5} "
           f"{'最佳':<5} {'判定':<8} {'羊':>2}  备注")
    lines.append(hdr)
    lines.append("-" * 76)

    for i, (who, frm, to, tag) in enumerate(moves, 1):
        turn = WOLF if who == "狼" else SHEEP
        legal = False
        if who == "狼":
            for a, b, cap in wolf_moves(w, s):
                if (a, b) == (frm, to):
                    legal = True
                    break
        else:
            for a, b in sheep_moves(w, s):
                if (a, b) == (frm, to):
                    legal = True
                    break
        if not legal:
            lines.append(f"!! 第{i}手 {who} {pos_name(frm)}→{pos_name(to)} 非法!")
            break

        v0 = endgame.lookup(w, s, turn)
        d0 = endgame.lookup_dist(w, s, turn)

        ranks = []
        note = ""
        if who == "狼":
            csafe = cpoison = 0
            cnt = [0, 0, 0]
            for a, b, cap in wolf_moves(w, s):
                w2, s2 = apply_wolf_move(w, s, a, b)
                if popcount(s2) <= 3:
                    r = 0
                else:
                    vv = endgame.lookup(w2, s2, SHEEP)
                    r = rank_for(vv, WOLF)
                cnt[r] += 1
                ranks.append((r, a, b))
                if cap:
                    if popcount(s2) <= 3:
                        csafe += 1
                    elif endgame.lookup(w2, s2, SHEEP) == SHEEP_WIN:
                        cpoison += 1
                    else:
                        csafe += 1
            note = f"着:胜{cnt[0]}/和{cnt[1]}/败{cnt[2]} 吃:安全{csafe}/毒{cpoison}"
        else:
            cnt = [0, 0, 0]
            for a, b in sheep_moves(w, s):
                w2, s2 = apply_sheep_move(w, s, a, b)
                vv = endgame.lookup(w2, s2, WOLF)
                r = rank_for(vv, SHEEP)
                cnt[r] += 1
                ranks.append((r, a, b))
            note = f"着:胜{cnt[0]}/和{cnt[1]}/败{cnt[2]}"

        best_rank = min(r for r, _, _ in ranks)
        if cnt[0] + cnt[1] == 1:
            uniq[who] += 1

        if who == "狼":
            real_cap = bool((s >> to) & 1)
            if tag != real_cap:
                tag_bad.append(i)
            w2, s2 = apply_wolf_move(w, s, frm, to)
            v1 = endgame.lookup(w2, s2, SHEEP)
        else:
            w2, s2 = apply_sheep_move(w, s, frm, to)
            v1 = endgame.lookup(w2, s2, WOLF)

        played_rank = rank_for(v1, turn)
        bname = WIN_NAMES[best_name(turn, best_rank)]

        if played_rank > best_rank:
            flag = "漏胜!" if best_rank == 0 else "败招!"
            stats[who]["bad"].append((i, v0, v1))
        else:
            flag = "完美"
            stats[who]["ok"] += 1
        if best_rank == 0 and played_rank > 0:
            stats[who]["miss"].append(i)

        mv_str = pos_name(frm) + "→" + pos_name(to)
        if who == "狼" and real_cap:
            mv_str += "吃"
        d0s = f"({d0})" if v0 != DRAW else ""
        lines.append(f"{i:>3} {who:<2} {mv_str:<9} {WIN_NAMES[v0]:<5}{d0s:<5}"
                     f" {WIN_NAMES[v1]:<5} {bname:<5} {flag:<8} "
                     f"{popcount(s2):>2}  {note}")
        key = (w2, s2)
        seen.setdefault(key, []).append(i)
        w, s = w2, s2

    lines.append("-" * 76)
    for who in ("羊", "狼"):
        st = stats[who]
        lines.append(f"{who}方: 完美 {st['ok']} 手, "
                     f"败招/漏胜 {len(st['bad'])} 手")
        if st["bad"]:
            for i, v0, v1 in st["bad"]:
                lines.append(f"   第{i}手 {WIN_NAMES[v0]} → {WIN_NAMES[v1]}")
        if st["miss"]:
            lines.append(f"   漏胜手数: {st['miss']}")
    if tag_bad:
        lines.append(f"!! 吃标记与棋盘不符的手: {tag_bad}")
    lines.append("唯一正招统计(走子方保持不败的合法着法数恰为1的手数):")
    for who in ("狼", "羊"):
        lines.append(f"  {who}: {uniq[who]} 手 / 共 {len([m for m in moves if m[0] == who])} 手")

    # 局面重复检测
    reps = {k: v for k, v in seen.items() if len(v) >= 2}
    lines.append("")
    lines.append(f"局面重复检测: 共 {len(seen)} 个不同局面, "
                 f"出现>=2次的局面 {len(reps)} 个")
    for k, v in sorted(reps.items(), key=lambda kv: kv[1][0]):
        lines.append(f"  局面 {board_str(k[0], k[1]).replace(chr(10), ' | ')} "
                     f"出现在第 {v} 手后")

    # 终局
    lines.append("")
    lines.append("=" * 76)
    turn_now = SHEEP if len(moves) % 2 == 1 else WOLF
    lines.append(f"终局(第{len(moves)}手后): 轮到{('狼' if turn_now == WOLF else '羊')}"
                 f" · 羊剩 {popcount(s)} 只")
    lines.append(board_str(w, s))
    vnow = endgame.lookup(w, s, turn_now)
    lines.append(f"当前局面真实值: {WIN_NAMES[vnow]} "
                 f"(dist={endgame.lookup_dist(w, s, turn_now)})")

    # 当前走子方的选项
    lines.append("")
    if turn_now == SHEEP:
        win_m = []
        n_draw = n_lose = 0
        for a, b in sheep_moves(w, s):
            w2, s2 = apply_sheep_move(w, s, a, b)
            vv = endgame.lookup(w2, s2, WOLF)
            if vv == SHEEP_WIN:
                win_m.append((a, b))
            elif vv == DRAW:
                n_draw += 1
            else:
                n_lose += 1
        lines.append(f"羊方当前: 胜着 {len(win_m)} 手, 和着 {n_draw} 手, "
                     f"败着 {n_lose} 手")
        if win_m:
            lines.append("  胜着: " + ", ".join(
                pos_name(a) + "→" + pos_name(b) for a, b in win_m))
    else:
        n_win = n_draw = n_lose = 0
        win_m = []
        for a, b, cap in wolf_moves(w, s):
            w2, s2 = apply_wolf_move(w, s, a, b)
            if popcount(s2) <= 3:
                vv = WOLF_WIN
            else:
                vv = endgame.lookup(w2, s2, SHEEP)
            if vv == WOLF_WIN:
                n_win += 1
                win_m.append((a, b, s2))
            elif vv == DRAW:
                n_draw += 1
            else:
                n_lose += 1
        lines.append(f"狼方当前: 胜着 {n_win} 手, 和着 {n_draw} 手, "
                     f"败着 {n_lose} 手")
        for a, b, s2 in win_m:
            d = 0 if popcount(s2) <= 3 else endgame.lookup_dist(
                (w ^ (1 << a)) | (1 << b), s2, SHEEP)
            lines.append(f"  胜着: {pos_name(a)}→{pos_name(b)}"
                         f"{'吃' if (s >> b) & 1 else ''} (dist={d})")

    # 狼当前可吃子清单(棋盘层面,与先后手无关)
    lines.append("")
    caps = []
    for a, b, cap in wolf_moves(w, s):
        if not cap:
            continue
        w2, s2 = apply_wolf_move(w, s, a, b)
        if popcount(s2) <= 3:
            vv = WOLF_WIN
        else:
            vv = endgame.lookup(w2, s2, SHEEP)
        caps.append((a, b, vv))
    if caps:
        lines.append(f"狼当前可吃 {len(caps)} 处: " + ", ".join(
            f"{pos_name(a)}→{pos_name(b)}吃({WIN_NAMES[vv]})"
            for a, b, vv in caps))
    else:
        lines.append("狼当前无可吃之羊。")

    report = "\n".join(lines) + "\n"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
