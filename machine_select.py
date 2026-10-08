# -*- coding: utf-8 -*-
"""
印刷機選定ロジック

仕様（色数・加工の要否・サイズ）から、machines_data.py の一覧を絞り込み、
対応できる機種の候補と、対応できない機種＋その理由を返す。

最終判断は人（担当者）が行う前提。ここでは「候補を絞り込んで見せる」ところまでを担う。
"""

import copy
import re

from machines_data import DEFAULT_MACHINES

_TIER_RE = re.compile(r"([\d,]+)枚以上/(\d+)面付")


def menzuke_hint(machine, qty):
    """面付目安（「5,000枚以上/2面付」形式の表記がある機種のみ）。数量に当てはまる面付数を返す。無ければ None。"""
    tiers = sorted((int(a.replace(",", "")), int(b)) for a, b in _TIER_RE.findall(machine.get("menzuke_note") or ""))
    if not tiers:
        return None
    n = 1
    for limit, count in tiers:
        if qty >= limit:
            n = count
    return n


def _fits(m, colors, width, height, need_half_cut, need_full_cut, need_emboss,
          need_back_print, need_variable, need_seamless):
    reasons = []
    if m["max_colors"] is not None and colors and colors > m["max_colors"]:
        reasons.append(f"色数{colors}色に対して対応{m['max_colors']}色まで")
    if need_half_cut and not m["half_cut"]:
        reasons.append("ハーフカット非対応")
    if need_full_cut and not m["full_cut"]:
        reasons.append("全抜き非対応")
    if need_emboss and not m["emboss"]:
        reasons.append("エンボス非対応")
    if need_back_print and not m["back_print"]:
        reasons.append("裏面印刷非対応")
    if need_variable and not m["variable"]:
        reasons.append("可変印刷（シリアル等）非対応")
    if need_seamless and not m["seamless"]:
        reasons.append("シームレス印刷非対応")
    if width and m["max_w"] and width > m["max_w"]:
        reasons.append(f"幅{width:g}mmが最大{m['max_w']}mmを超過")
    if height and m["max_h"] and height > m["max_h"]:
        reasons.append(f"高さ{height:g}mmが最大{m['max_h']}mmを超過")
    return reasons


def suggest_machines(colors=1, width=0, height=0, need_half_cut=False, need_full_cut=False,
                      need_emboss=False, need_back_print=False, need_variable=False,
                      need_seamless=False, need_haku=False, machines=None):
    """
    印刷本体の候補・対象外、および（need_hakuがTrueなら）箔押し加工機の候補を返す。
    戻り値: (candidates, excluded, haku_candidates)  ※各要素は machines_data の1件＋reasons
    """
    machines = machines or DEFAULT_MACHINES
    candidates, excluded, haku_candidates = [], [], []

    for m in machines:
        if m["category"] == "箔押し加工機":
            continue
        reasons = _fits(m, colors, width, height, need_half_cut, need_full_cut, need_emboss,
                        need_back_print, need_variable, need_seamless)
        item = copy.deepcopy(m)
        item["exclude_reasons"] = reasons
        (excluded if reasons else candidates).append(item)

    if need_haku:
        for m in machines:
            if m["category"] != "箔押し加工機":
                continue
            reasons = []
            if need_full_cut and not m["full_cut"]:
                reasons.append("全抜き非対応")
            if need_emboss and not m["emboss"]:
                reasons.append("エンボス非対応")
            if width and m["max_w"] and width > m["max_w"]:
                reasons.append(f"幅{width:g}mmが最大{m['max_w']}mmを超過")
            if height and m["max_h"] and height > m["max_h"]:
                reasons.append(f"高さ{height:g}mmが最大{m['max_h']}mmを超過")
            item = copy.deepcopy(m)
            item["exclude_reasons"] = reasons
            if not reasons:
                haku_candidates.append(item)

    return candidates, excluded, haku_candidates
