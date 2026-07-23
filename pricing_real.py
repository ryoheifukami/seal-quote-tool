# -*- coding: utf-8 -*-
"""
シール堂印刷 実見積計算エンジン（実際のExcel計算フォーマットを忠実に移植）

対象3方式：
  hiraatsu … 平圧・間欠印刷（凸版シール）
  masking  … マスキングテープ
  konica   … コニカミノルタ オンデマンド（デジタル）

各Excelの「計算」シートの数式をそのまま再現している。
末尾の verify() で、Excelにキャッシュされた計算結果と1円単位まで一致することを確認する。

Excel関数の対応：
  ROUNDUP(x, n) … 0から遠い方向へ切り上げ（n=-2は百の位、n=2は小数2位）
  CEILING(x, s) … s の倍数へ切り上げ
  ROUNDDOWN(x,0)… 切り捨て
"""

import math

import masters

EPS = 1e-9


def roundup(x, digits=0):
    if x == 0:
        return 0.0
    f = 10 ** digits
    s = 1 if x > 0 else -1
    return s * math.ceil(abs(x) * f - EPS) / f


def ceiling(x, sig):
    if sig == 0:
        return 0.0
    return math.ceil(x / sig - EPS) * sig


def rounddown0(x):
    return math.floor(x + EPS)


# =====================================================================
# 平圧・間欠印刷
# =====================================================================
# 予備(調子出し)ショット：色数→ショット（E91:F96）
HIRA_YOBI_SHOT = {1: 1000, 2: 2000, 3: 3000, 4: 4000, 5: 5000}
# 版型セット代原価（E99:H104）col G=No.2大型(平圧)、H=No.3光(間欠) ※元金額×0.8済
HIRA_HANGATA = {
    "G": {1: 4000, 2: 5200, 3: 6400},
    "H": {1: 5200, 2: 6400, 3: 7600, 4: 8800, 5: 10000},
}
# 通し工賃原価（E107:H112）※元金額×0.8済
HIRA_TOOSHI = {
    "G": {1: 1.2, 2: 1.44, 3: 1.68},
    "H": {1: 1.44, 2: 1.68, 3: 1.92, 4: 2.16, 5: 2.4},
}

HIRA_DEFAULTS = dict(
    width=0, height=0,            # D13 寸法ヨコ, D14 寸法タテ（空欄=0）
    colors=1,                     # D15 色数(1-5)
    machine=2,                    # D16 機種：平圧2, 間欠3
    genshi_tanka=0,               # D17 原紙 平米単価
    pp_tanka=0,                   # D18 PP 平米単価
    haku_tanka=0,                 # D19 箔 平米単価
    numbering=0,                  # D20 シリアル・ナンバリング（ありは1、空欄=0）
    menzuke_w=1,                  # D21 面付ヨコ
    menzuke_p=1,                  # D22 面付タテ
    plate_change=0,               # D23 版替回数
    color_change=0,               # D24 色替回数
    soryo=1000,                   # D25 送料（1箱原価）
    nuki=2,                       # D26 全抜き=1 / ハーフカット=2
    finish=1,                     # D27 シート=1 / ロール=2
    roll_per=500,                 # D28 ロール1巻あたり枚数
    shikan=10,                    # D29 ロール紙管原価
    margin_material=30,           # D30 材料粗利率
    margin_other=20,              # D31 セット・工賃等粗利率
    margin_outsource=30,          # D32 外注費・色校正粗利率
    ura_print=0,                  # D33 ウラ(セパ)印刷（ありは1）
    half_lami=0,                  # D34 ハーフラミ（ありは1）
    emboss=0,                     # D35 エンボス（ありは1）
    add_process=0,                # D36 追加工程数
    hanshita_cost=0,              # H33 版下原価
    han_cost=0,                   # H34 版代原価
    kata_cost=0,                  # H35 型代原価
    seihan_cost=0,                # H36 色校正原価
    unit_price_manual=None,       # D78 印刷代 単価入力（手入力。Noneなら参考単価を採用）
)

# 定数（H列）
HIRA_C = dict(
    dobu_w=3,        # H13 ドブ ヨコ
    dobu_p=3,        # H14 ドブ タテ
    haku_toshi=1.2,  # H21 箔押し通し工賃
    num_tanka=60,    # H22 シリアル・ナンバリング平米単価
    add_hira_set=4000,   # H23 追加加工 平圧 セット
    add_hira_shot=1.2,   # H24 追加加工 平圧 ショット
    add_kan_set=5200,    # H25 追加加工 間欠 セット
    add_kan_shot=1.44,   # H26 追加加工 間欠 ショット
    set_pp=1600,         # H27 加工セット(PP)原価
    set_haku=4000,       # H28 加工セット(箔)原価
    set_num=4800,        # H29 加工セット(ナンバリング)原価
    slitter=4,           # H30 スリッター代(1m原価)
)


def estimate_hiraatsu(inp=None, qty=1000, rates=None):
    p = dict(HIRA_DEFAULTS)
    if inp:
        p.update(inp)
    R = (rates or masters.get_rates()).get("hiraatsu", {})
    c = {**HIRA_C, **{k: R[k] for k in HIRA_C if k in R}}
    _yobi = {int(k): v for k, v in R.get("yobi_shot", {}).items()} or HIRA_YOBI_SHOT
    _hangata = {"G": {int(k): v for k, v in R.get("hangata_G", {}).items()},
                "H": {int(k): v for k, v in R.get("hangata_H", {}).items()}}
    _tooshi = {"G": {int(k): v for k, v in R.get("tooshi_G", {}).items()},
               "H": {int(k): v for k, v in R.get("tooshi_H", {}).items()}}

    colors = int(p["colors"])
    machine = int(p["machine"])                     # 2平圧 / 3間欠
    mw, mp = p["menzuke_w"], p["menzuke_p"]

    menzuke = mw * mp                                # H15 面付数
    # H16 予備ショット
    yobi_shot = _yobi[colors] + p["plate_change"] * 300 + p["color_change"] * 1000
    # H17 原紙幅
    base = ceiling(p["width"] * mw + 15 + c["dobu_w"] * (mw - 1), 5)
    if base < 30:
        genshi_w = 30
    elif machine == 2:
        genshi_w = base
    else:
        genshi_w = base + 5
    # H18 原紙送り
    okuri = p["height"] * mp + 3 + c["dobu_p"] * (mp - 1)
    # H19 版型セット列 / 参照列
    col = "G" if machine == 2 else "H"              # 平圧→G(No.2大型), 間欠→H(No.3光)
    # H20 通し工賃
    toshi = _tooshi[col][colors]
    # H31 追加工程
    add_proc = p["add_process"] * 1000

    def has(v):
        # Excelの「空欄」は 0 or None。0 は「未入力」として扱う項目がある
        return v not in ("", None, 0)

    def col_calc(q):
        if q in ("", None) or q == 0:
            return None
        shot = q / menzuke                                        # 41 ショット数
        need_mm = okuri * (shot + yobi_shot + add_proc)           # 42 必要mm
        need_m = need_mm / 1000                                   # 43 必要m
        yobi_m = 0 if machine == 2 else 30                        # 44 予備メーター
        final_m = need_m + yobi_m                                 # 45 最終m
        buy_m = roundup(final_m, -2)                              # 46 購入m
        roll_maki = None if p["finish"] == 1 else roundup(q / p["roll_per"], 0)  # 47

        genshi = p["genshi_tanka"] * (genshi_w / 10) * buy_m / 100        # 48 原紙代
        pp = p["pp_tanka"] * ((genshi_w - 5) / 10) * buy_m / 100          # 49 PP代
        haku = p["haku_tanka"] * (genshi_w / 10) * buy_m / 100           # 50 箔代
        hangata = _hangata[col][colors]                                 # 51 版型セット
        toshi_cost = shot * toshi                                        # 52 通し工賃
        haku_toshi = shot * c["haku_toshi"] if has(p["haku_tanka"]) else 0   # 53
        set_pp = c["set_pp"] if has(p["pp_tanka"]) else 0                # 54 加工セット(PP)
        set_haku = c["set_haku"] if has(p["haku_tanka"]) else 0          # 55 加工セット(箔)
        set_num = c["set_num"] if has(p["numbering"]) else 0            # 56 加工セット(ナンバ)
        set_ura = c["add_kan_set"] if has(p["ura_print"]) else 0        # 57 ウラ印刷セット(間欠5200)
        set_half = c["add_hira_set"] if has(p["half_lami"]) else 0      # 58 ハーフラミセット(平圧4000)
        set_emb = c["add_hira_set"] if has(p["emboss"]) else 0          # 59 エンボスセット(平圧4000)
        set_plate = p["plate_change"] * 1000 if has(p["plate_change"]) else 0  # 60 版替
        set_color = p["color_change"] * 3000 if has(p["color_change"]) else 0  # 61 色替
        num_toshi = c["num_tanka"] * (genshi_w / 10) * buy_m / 100 if has(p["numbering"]) else 0  # 62
        ura_toshi = shot * c["add_kan_shot"] if has(p["ura_print"]) else 0    # 63 ウラ印刷通し(間欠1.44)
        half_toshi = shot * c["add_hira_shot"] if has(p["half_lami"]) else 0  # 64 ハーフラミ通し(平圧1.2)
        emb_toshi = shot * c["add_hira_shot"] if has(p["emboss"]) else 0      # 65 エンボス通し(平圧1.2)
        slitter = 0 if p["finish"] == 1 else (shot * okuri / 1000) * c["slitter"] * (mw + 1)  # 66
        shikan = 0 if p["finish"] == 1 else roll_maki * p["shikan"]      # 67 紙管代
        soryo = p["soryo"] if q < 10000 else roundup(q / 10000, 0) * p["soryo"]  # 68 送料
        mushiri = q * 2 if p["nuki"] == 1 else 0                         # 69 全抜きムシリ

        items_material = [genshi, pp, haku]                             # 48-50
        items_other = [hangata, toshi_cost, haku_toshi, set_pp, set_haku, set_num,
                       set_ura, set_half, set_emb, set_plate, set_color,
                       num_toshi, ura_toshi, half_toshi, emb_toshi, slitter, shikan,
                       soryo, mushiri]                                   # 51-69
        cost_total = sum(items_material) + sum(items_other)             # 73 原価合計
        material_after = sum(items_material) / ((100 - p["margin_material"]) / 100)  # 74
        other_after = sum(items_other) / ((100 - p["margin_other"]) / 100)          # 75
        print_total = material_after + other_after                     # 76 印刷代合計
        ref_unit = print_total / q                                     # 77 参考単価
        breakdown = [
            ("原紙代", genshi), ("PP代", pp), ("箔代", haku),
            ("版型セット", hangata), ("通し工賃", toshi_cost), ("箔押通し工賃", haku_toshi),
            ("加工セット(PP)", set_pp), ("加工セット(箔)", set_haku), ("加工セット(ﾅﾝﾊﾞﾘﾝｸﾞ)", set_num),
            ("加工セット(ｳﾗ印刷)", set_ura), ("加工セット(ﾊｰﾌﾗﾐ)", set_half), ("加工セット(ｴﾝﾎﾞｽ)", set_emb),
            ("加工セット(版替)", set_plate), ("加工セット(色替)", set_color),
            ("ﾅﾝﾊﾞﾘﾝｸﾞ通し工賃", num_toshi), ("ｳﾗ印刷通し工賃", ura_toshi),
            ("ﾊｰﾌﾗﾐ通し工賃", half_toshi), ("ｴﾝﾎﾞｽ通し工賃", emb_toshi),
            ("スリッター代", slitter), ("紙管代", shikan or 0), ("送料", soryo), ("全抜きムシリ", mushiri),
        ]
        return dict(shot=shot, need_m=need_m, buy_m=buy_m, cost_total=cost_total,
                    material_after=material_after, other_after=other_after,
                    print_total=print_total, ref_unit=ref_unit, genshi_w=genshi_w, okuri=okuri,
                    breakdown=breakdown)

    r = col_calc(qty)
    proto = col_calc(10)   # 試作代（N列 数量10）

    # 提出用（手入力単価 D78。未指定なら参考単価）
    unit = p["unit_price_manual"] if p["unit_price_manual"] is not None else r["ref_unit"]
    print_submit = qty * unit                                          # 79
    m_out = (100 - p["margin_outsource"]) / 100
    hanshita = roundup(p["hanshita_cost"] / m_out, -2)                 # 81
    han = roundup(p["han_cost"] / m_out, -2)                           # 82
    kata = roundup(p["kata_cost"] / m_out, -2)                         # 83
    # 色校正原価 H36：未指定なら「色校正代 H32」または試作代（原価合計）を使う想定
    seihan_cost = p["seihan_cost"]
    seihan = roundup(seihan_cost / m_out, -2)                          # 84
    total = print_submit + hanshita + han + kata + seihan             # 86 合計

    r.update(dict(
        qty=qty, menzuke=menzuke, yobi_shot=yobi_shot, toshi=toshi,
        ref_unit_disp=round(r["ref_unit"], 2), unit=unit,
        print_submit=print_submit, hanshita=hanshita, han=han, kata=kata, seihan=seihan,
        total=total, proto_cost_total=proto["cost_total"], proto_ref_unit=proto["ref_unit"],
    ))
    return r


# =====================================================================
# マスキングテープ
# =====================================================================
MASK_DEFAULTS = dict(
    width=15,          # D3 製品の幅(mm)
    dobu=3,            # D4 ドブ幅(mm)
    maki_m=5,          # D6 巻きメーター(m)
    data_cost=3000,    # D10 印刷用データ作成(3000-6000)
    proof=20000,       # D11 色校正(一律)
    genshi_tanka=49,   # D12 原紙 平米単価
    nenchaku=7,        # D13 粘着剤 単価
    nis=26.4,          # D14 シリコンニス 単価
    ink=24,            # D15 インク 単価
    pj_set=6900,       # D16 PJセット代
    pj_print=5.8,      # D17 PJ印刷 単価
    emul_set=6900,     # D18 エマルジョンセット
    emul_print=8,      # D19 エマルジョン印刷 単価
    komaki=51.5,       # D20 小巻 単価
    cut=51.5,          # D21 カット単価(30φ)
    shikan=31.8,       # D22 紙管単価(30φ)
    pp_naishoku=8,     # D23 PPシート＋内職 単価
    soryo=1500,        # D24 送料(1箱)
    eigyo_rieki=0,     # D27 営業利益率(%)
)


_MASK_TOME_DEFAULT = [[1000, 24000], [2000, 29600], [3000, 32400], [4000, 35200], [5000, 38000],
                      [6000, 43800], [7000, 46200], [8000, 48800], [10000, 58000], [20000, 90000]]


def _mask_tome(q, tiers):
    # 止めシール（D25 数量帯）
    for lim, val in tiers:
        if q <= lim:
            return val
    return q * 4.5


def estimate_masking(inp=None, qty=1000, rates=None):
    R = (rates or masters.get_rates()).get("masking", {})
    p = dict(MASK_DEFAULTS)
    for k in ("genshi_tanka", "nenchaku", "nis", "ink", "pj_set", "pj_print", "emul_set",
              "emul_print", "komaki", "cut", "shikan", "pp_naishoku", "proof", "data_cost", "soryo"):
        if k in R:
            p[k] = R[k]
    if inp:
        p.update(inp)
    tiers = R.get("tome_tiers", _MASK_TOME_DEFAULT)
    retsu = rounddown0(180 / (p["width"] + p["dobu"]))          # D5 印刷列数
    shikan_hon = roundup(qty / retsu, 0)                        # 8 紙管本数
    use_m = roundup((p["maki_m"] * shikan_hon / 0.8) + 200, -2)  # 9 原紙使用m

    data = p["data_cost"]                                       # 10
    proof = p["proof"]                                          # 11
    genshi = roundup(21 * (use_m / 100) * p["genshi_tanka"] / 0.7, -2)  # 12 原紙代
    nenchaku = roundup(use_m * p["nenchaku"] / 0.7, -2)         # 13 粘着剤
    nis = roundup(use_m * p["nis"] / 0.7, -2)                   # 14 シリコンニス
    ink = roundup(use_m * p["ink"] / 0.7, -2)                   # 15 インク
    pj_set = p["pj_set"]                                        # 16
    pj_print = roundup(use_m * p["pj_print"], -2)               # 17
    emul_set = p["emul_set"]                                    # 18
    emul_print = roundup(use_m * p["emul_print"], -2)           # 19
    komaki = roundup(p["komaki"] * shikan_hon, -2)             # 20
    cut = roundup(p["cut"] * shikan_hon, -2)                    # 21
    shikan = roundup(p["shikan"] * shikan_hon / 0.7, -2)       # 22
    pp = roundup(p["pp_naishoku"] * qty / 0.7, -2)             # 23
    soryo = roundup(p["soryo"] * roundup(qty / (30 * retsu), 0), -2)   # 24 送料
    tome = _mask_tome(qty, tiers)                              # 25 止めシール

    subtotal = (data + proof + genshi + nenchaku + nis + ink + pj_set + pj_print +
                emul_set + emul_print + komaki + cut + shikan + pp + soryo + tome)  # 26 小計
    eigyo = subtotal / ((100 - p["eigyo_rieki"]) / 100) - subtotal   # 27 営業利益
    sub_plus = subtotal + eigyo                                       # 28
    unit = roundup(sub_plus / qty, 2)                                # 29 単価
    total = qty * unit                                              # 30 合計
    breakdown = [
        ("印刷用データ作成", data), ("色校正", proof), ("原紙代", genshi),
        ("粘着剤", nenchaku), ("シリコンニス", nis), ("インク", ink),
        ("PJセット代", pj_set), ("PJ印刷", pj_print), ("エマルジョンセット", emul_set),
        ("エマルジョン印刷", emul_print), ("小巻", komaki), ("カット", cut),
        ("紙管", shikan), ("PPシート＋内職", pp), ("送料", soryo), ("止めシール", tome),
    ]
    return dict(qty=qty, retsu=retsu, shikan_hon=shikan_hon, use_m=use_m,
                subtotal=subtotal, eigyo=eigyo, unit=unit, total=total, breakdown=breakdown)


# =====================================================================
# コニカミノルタ オンデマンド
# =====================================================================
KONI_DEFAULTS = dict(
    width=0, height=0,            # D13/D14 寸法（例では空欄=0）
    types=1,                      # D15 種類（同一型同一仕上の種類数）
    genshi_tanka=0,               # D16 原紙 平米単価
    pp_tanka=0,                   # D17 PP 平米単価
    version=3,                    # D18 新版1/改版2/再版3
    print_w=1,                    # D19 印刷面付ヨコ
    nuki_w=1,                     # D20 抜き面付ヨコ
    nuki_p=1,                     # D21 抜き面付タテ
    slitter_hon=1,                # D22 スリッター本数
    soryo=1000,                   # D23 送料
    nuki=2,                       # D24 全抜き=1 / ハーフカット=2
    finish=1,                     # D25 シート=1 / ロール=2
    roll_per=500,                 # D26 ロール1巻あたり枚数
    shikan=10,                    # D27 ロール紙管原価
    add_process=0,                # D28 追加工程数
    margin_material=30,           # D30
    margin_other=20,              # D31
    margin_outsource=30,          # D32
    hanshita_cost=0,              # D33 版下原価
    kata_cost=0,                  # D34 型代原価
    seihan_cost=0,                # D35 色校正原価
    unit_price_manual=None,       # D69 単価入力（手入力）
)
KONI_C = dict(
    dobu_p=3,        # H13 ドブ タテ
    genshi_w=25,     # H18 原紙幅 25cm固定
    nuki_yobi=1000,  # H19 抜き予ショット固定
    onde_choshi=20000,   # H20 オンデ調子出し 20m固定
    iroawase=20000,      # H21 色合せ 20m固定
    loss_pct=10,         # H24 ロス分％
    ink_tanka=38,        # H25 インク単価
    onde_set=4800,       # H26 オンデセット
    onde_koching=10.9,   # H27 オンデ工賃
    nuki_half=1.2,       # H28 抜き工賃(ハーフ)
    nuki_all=1.44,       # H29 抜き工賃(全)
    set_pp=1600,         # H30 加工セット(PP)
    slitter=4,           # H31 スリッター代(1m)
    cooldown=8,          # H32 クールダウン(円/m)
)


def estimate_konica(inp=None, qty=1000, rates=None):
    p = dict(KONI_DEFAULTS)
    if inp:
        p.update(inp)
    R = (rates or masters.get_rates()).get("konica", {})
    c = {**KONI_C, **{k: R[k] for k in KONI_C if k in R}}

    print_menzuke = p["print_w"]                       # H14 印刷面付数 = D19
    nuki_menzuke = p["nuki_w"] * p["nuki_p"]           # H15 抜き面付数
    okuri = p["height"] + c["dobu_p"]                  # H17 実送り = 寸法タテ+ドブタテ
    add_proc = p["add_process"] * 1000                 # H22 追加工程
    same_add = (p["types"] - 1) * c["onde_choshi"]     # H23 同種追加

    def has(v):
        return v not in ("", None, 0)

    def col_calc(q):
        if q in ("", None) or q == 0:
            return None
        shot = q / print_menzuke                                       # 39 印刷ショット数
        need_mm = okuri * (shot + c["nuki_yobi"] + add_proc) + c["onde_choshi"] + c["iroawase"] + same_add  # 40
        need_m = need_mm / 1000                                        # 41 必要m
        loss = need_m * (c["loss_pct"] / 100)                          # 42 ロス分追加
        final_m = need_m + loss                                       # 43 最終m
        buy_m = roundup(final_m, -2)                                  # 44 購入m
        nuki_shot = q / nuki_menzuke                                  # 45 抜きショット数
        roll_maki = None if p["finish"] == 1 else roundup(q / p["roll_per"], 0)  # 46

        genshi = p["genshi_tanka"] * c["genshi_w"] * buy_m / 100      # 47 原紙代
        pp = p["pp_tanka"] * c["genshi_w"] * buy_m / 100             # 48 PP代
        ink = final_m * c["ink_tanka"]                               # 49 インク代
        onde_set = c["onde_set"]                                     # 50 オンデセット
        onde_ko = final_m * c["onde_koching"]                       # 51 オンデ工賃
        half = (4000 + nuki_shot * c["nuki_half"]) if p["nuki"] == 2 else 0   # 52 ハーフカット代
        allnuki = (5200 + nuki_shot * c["nuki_all"]) if p["nuki"] == 1 else 0  # 53 全抜き代
        slitter = (shot * okuri / 1000) * c["slitter"] * p["slitter_hon"]     # 54 スリッター代
        set_pp = c["set_pp"] if has(p["pp_tanka"]) else 0            # 55 PPセット
        add_type = 0 if p["version"] == 3 else (p["types"] - 1) * 1200   # 56 追加種類（新版/改版時のみ）
        shikan = 0 if p["finish"] == 1 else roll_maki * p["shikan"]  # 57 紙管代
        soryo = p["soryo"] if q < 10000 else roundup(q / 10000, 0) * p["soryo"]  # 58 送料
        cooldown = roundup(final_m, -2) * c["cooldown"]             # 59 クールダウン（購入m×8）
        mushiri = q * 2 if p["nuki"] == 1 else 0                    # 60 全抜きムシリ

        items_material = [genshi, pp, ink]                          # 47-49
        items_other = [onde_set, onde_ko, half, allnuki, slitter, set_pp,
                       add_type, shikan, soryo, cooldown, mushiri]  # 50-63
        cost_total = sum(items_material) + sum(items_other)         # 64 原価合計
        material_after = sum(items_material) / ((100 - p["margin_material"]) / 100)  # 65
        other_after = sum(items_other) / ((100 - p["margin_other"]) / 100)           # 66
        print_total = material_after + other_after                 # 67 印刷代合計
        ref_unit = print_total / q                                 # 68 参考単価
        breakdown = [
            ("原紙代", genshi), ("PP代", pp), ("インク代", ink),
            ("オンデセット", onde_set), ("オンデ工賃", onde_ko),
            ("ハーフカット代", half), ("全抜き代", allnuki), ("スリッター代", slitter),
            ("加工セット(PP)", set_pp), ("追加種類", add_type), ("紙管代", shikan or 0),
            ("送料", soryo), ("クールダウン", cooldown), ("全抜きムシリ", mushiri),
        ]
        return dict(shot=shot, need_m=need_m, final_m=final_m, buy_m=buy_m,
                    cost_total=cost_total, material_after=material_after,
                    other_after=other_after, print_total=print_total, ref_unit=ref_unit,
                    breakdown=breakdown)

    r = col_calc(qty)
    unit = p["unit_price_manual"] if p["unit_price_manual"] is not None else r["ref_unit"]
    print_submit = qty * unit                                       # 70
    m_out = (100 - p["margin_outsource"]) / 100
    hanshita = roundup(p["hanshita_cost"] / m_out, -2)             # 72
    kata = roundup(p["kata_cost"] / m_out, -2)                     # 73
    seihan = roundup(p["seihan_cost"] / m_out, -2)                # 74
    total = print_submit + hanshita + kata + seihan               # 76 合計
    r.update(dict(qty=qty, unit=unit, print_submit=print_submit,
                  hanshita=hanshita, kata=kata, seihan=seihan, total=total))
    return r


# =====================================================================
# 検証（Excelキャッシュ値と一致するか）
# =====================================================================
def _approx(a, b, tol=0.01):
    if a is None or b is None:
        return a == b
    return abs(a - b) <= tol


def verify():
    ok = True

    def check(name, got, exp, tol=0.01):
        nonlocal ok
        good = _approx(got, exp, tol)
        ok = ok and good
        print(f"  [{'OK ' if good else 'NG!'}] {name}: got={got!r} exp={exp!r}")

    print("=== 平圧・間欠（例：空欄テンプレ, 色数1, 平圧, 面付1×1, 送料1000, 手入力単価7.8）===")
    h = estimate_hiraatsu(dict(unit_price_manual=7.8), qty=1000)
    check("原価合計(D73)", h["cost_total"], 6200)
    check("その他粗利後(D75)", h["other_after"], 7750)
    check("参考単価(D77)", round(h["ref_unit"], 2), 7.75)
    check("提出用(D79)", h["print_submit"], 7800)
    check("合計(D86)", h["total"], 7800)
    check("試作 原価合計(N73)", h["proto_cost_total"], 5012)
    check("試作 参考単価(N77)", round(h["proto_ref_unit"], 2), 626.5)

    print("=== マスキング（例：15mm×5m, 4色相当, 全原価あり）===")
    for q, exp_unit, exp_sub in [(1000, 193, 193000), (2000, 147.7, 295400), (3000, 131.77, 395300)]:
        m = estimate_masking(qty=q)
        check(f"小計(q={q})", m["subtotal"], exp_sub)
        check(f"単価(q={q})", m["unit"], exp_unit)

    print("=== コニカミノルタ（例：空欄寸法, 種類1, 再版, 面付1, ハーフ, 手入力単価18.3）===")
    k = estimate_konica(dict(unit_price_manual=18.3), qty=1000)
    check("原価合計(D64)", k["cost_total"], 14286.34)
    check("材料粗利後(D65)", k["material_after"], 2746.857142857143)
    check("その他粗利後(D66)", k["other_after"], 15454.425)
    check("印刷代合計(D67)", k["print_total"], 18201.282142857144)
    check("参考単価(D68)", k["ref_unit"], 18.201282142857146, tol=0.001)
    check("提出用(D70)", k["print_submit"], 18300)
    check("合計(D76)", k["total"], 18300)

    print()
    print("★ ALL PASS" if ok else "★ 不一致あり（要修正）")
    return ok


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    verify()
