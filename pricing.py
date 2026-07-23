# -*- coding: utf-8 -*-
"""
シール堂印刷 見積り計算エンジン（料金・原価データはすべて「仮」）

★このファイルが差し替えの核★
　シール堂さんの実際の単価表・原価が手に入ったら、下の「料金テーブル」ブロックの
　数値を書き換えるだけで本番の見積りになります。計算の流れ（estimate 関数）は
　基本そのまま使えます。数値には原則「※仮」と注記しています。

価格の考え方（業界一般の方式）：
  1. 1枚の面積(cm²) と 数量 で「基本単価（1枚あたり）」が決まる（面積帯×数量帯のマトリクス）
  2. 素材で単価を増減（素材係数）
  3. 加工オプション（ラミネート・箔押し等）を1枚あたり加算
  4. 型抜きは「抜き型代」を初期費用として1回だけ加算
  5. 特急は割増、最低料金を下回れば引き上げ
  6. 販売価格に対する原価率から 原価・粗利・粗利率 を算出
  7. 消費税(10%)を加算
"""

import math

# =====================================================================
# 料金テーブル（★ここを実データに差し替える★）  ※すべて仮の数値
# =====================================================================

# --- 面積帯（cm²）。1枚あたりの面積を、どの帯に入るかで分類する ---
# 例）縦3cm×横5cm = 15cm² → "〜25cm²" の帯
AREA_BANDS = [
    ("〜10cm²", 10),
    ("〜25cm²", 25),
    ("〜50cm²", 50),
    ("〜100cm²", 100),
    ("〜200cm²", 200),
    ("200cm²超", float("inf")),
]

# --- 数量帯。注文枚数がどの帯に入るか ---
QTY_BANDS = [
    ("〜100枚", 100),
    ("〜300枚", 300),
    ("〜500枚", 500),
    ("〜1,000枚", 1000),
    ("〜3,000枚", 3000),
    ("〜5,000枚", 5000),
    ("5,000枚超", float("inf")),
]

# --- 基本単価マトリクス（円 / 1枚）  ※仮 ---
# 行 = 面積帯（AREA_BANDS の順）、列 = 数量帯（QTY_BANDS の順）
# 数量が増えるほど1枚単価が下がる（量産で安くなる）構造にしてある。
BASE_UNIT_PRICE = {
    #                100    300    500    1000   3000   5000   5000超
    "〜10cm²":   [ 22.0,  12.0,   8.5,   6.0,   4.2,   3.4,   3.0],
    "〜25cm²":   [ 30.0,  16.0,  11.0,   7.8,   5.4,   4.4,   3.9],
    "〜50cm²":   [ 42.0,  22.0,  15.0,  10.5,   7.2,   5.9,   5.2],
    "〜100cm²":  [ 60.0,  32.0,  22.0,  15.5,  10.6,   8.7,   7.7],
    "〜200cm²":  [ 92.0,  50.0,  34.0,  24.0,  16.5,  13.6,  12.0],
    "200cm²超":  [140.0,  78.0,  54.0,  38.0,  26.5,  22.0,  19.5],
}

# --- 素材係数（基本単価に掛ける）  ※仮 ---
# 上質紙を1.0の基準にして、機能性素材ほど高くなる。
MATERIALS = {
    "上質紙（一般的な紙シール）":      1.00,
    "コート紙（つやのある紙）":        1.10,
    "合成紙ユポ（水に強い）":          1.35,
    "透明PET（透明フィルム）":         1.55,
    "塩ビ（屋外ステッカー向け）":      1.70,
}

# --- 加工オプション（1枚あたり加算 円）  ※仮 ---
# 複数選択された場合はすべて加算する。
FINISH_OPTIONS = {
    "ラミネート（グロス／つや有り）":  2.5,
    "ラミネート（マット／つや消し）":  2.8,
    "UVニス（表面保護）":              1.8,
    "箔押し（金・銀などの箔）":        6.0,
    "強粘着（はがれにくい糊）":        1.2,
}

# --- 仕上げ形態（1枚あたり加算 円）  ※仮 ---
# ロールや1枚カットは手間がかかる分わずかに加算。
CUT_FORMS = {
    "シート（台紙にまとめて）":    0.0,
    "ロール（機械貼り向け）":      1.5,
    "1枚カット（バラ）":           2.0,
}

# --- 形状。型抜きは抜き型代（初期費用）がかかる  ※仮 ---
SHAPES = {
    "四角":       {"die_cut": False},
    "角丸":       {"die_cut": False},
    "円・楕円":   {"die_cut": True},   # 円形は抜き型が必要
    "型抜き（フリーカット）": {"die_cut": True},
}
DIE_CUT_FEE = 8000  # 抜き型代（1デザインにつき1回）円  ※仮

# --- 納期 ---
LEAD_TIMES = {
    "通常（約7〜10営業日）": {"surcharge": 1.00, "note": "約7〜10営業日"},
    "お急ぎ（約3〜4営業日）": {"surcharge": 1.30, "note": "約3〜4営業日"},  # 特急割増 ※仮
}

MIN_ORDER_PRICE = 3000   # 最低料金（税抜）円  ※仮
TAX_RATE = 0.10          # 消費税率

# --- 原価率（販売価格・税抜に対する原価の割合）  ※仮 ---
# 素材が高機能なほど原価率も少し上がる想定。
BASE_COST_RATE = 0.55
MATERIAL_COST_RATE_ADJ = {
    "上質紙（一般的な紙シール）":      0.00,
    "コート紙（つやのある紙）":        0.01,
    "合成紙ユポ（水に強い）":          0.03,
    "透明PET（透明フィルム）":         0.05,
    "塩ビ（屋外ステッカー向け）":      0.06,
}
# 抜き型代の原価率（型代はほぼ外注実費に近い想定）  ※仮
DIE_CUT_COST_RATE = 0.80

# --- 品名（プルダウン用）。kind でシール系 / テープ系を分ける ---
# seal … サイズ(幅×高さ)と数量で計算 ／ tape … テープ幅×長さで計算
PRODUCTS = {
    "商品ラベル":            "seal",
    "化粧品・美容ラベル":    "seal",
    "食品表示ラベル":        "seal",
    "ステッカー（一般）":    "seal",
    "封かん・封緘シール":    "seal",
    "ノベルティシール":      "seal",
    "バーコード・管理ラベル": "seal",
    "マスキングテープ":      "tape",
    "オリジナル紙テープ":    "tape",
    "その他（自由入力）":    "seal",
}
PRODUCT_CHOICES = list(PRODUCTS.keys())

# --- 色味（単色は版がシンプルな分わずかに安い想定）  ※仮 ---
COLOR_TYPES = ["フルカラー", "単色"]
SPOT_BASE = 0.90            # 単色1色の係数（フルカラー=1.0基準） ※仮
SPOT_PER_EXTRA = 0.06       # 単色の色数が1増えるごとの加算 ※仮

# --- セットアップ（内職＝貼り合わせ・セット等の手作業）  ※仮 ---
SETUP_CHOICES = ["しない", "内職する（セット・貼り合わせ等）"]
SETUP_UNIT_PRICE = 3.0      # 内職ありのとき1枚あたり加算 円 ※仮

# --- テープ系の 仮 単価（幅cm × 長さm あたりの円。数量が増えるほど下がる） ---
# ※シールとは価格構造が別物。ここは特に粗い仮の値。
TAPE_RATE_BY_QTY = [24.0, 19.0, 16.0, 13.0, 11.0, 9.3, 8.0]  # QTY_BANDS と同じ並び ※仮

# 便利：画面の選択肢に使うリスト
SHAPE_CHOICES = list(SHAPES.keys())
MATERIAL_CHOICES = list(MATERIALS.keys())
FINISH_CHOICES = list(FINISH_OPTIONS.keys())
CUT_FORM_CHOICES = list(CUT_FORMS.keys())
LEAD_TIME_CHOICES = list(LEAD_TIMES.keys())
QTY_PRESETS = [100, 300, 500, 1000, 3000, 5000, 10000]


def product_kind(product):
    """品名から種類（seal / tape）を判定。未知の品名はシール扱い。"""
    return PRODUCTS.get(product, "seal")


def color_factor(color_type, spot_colors):
    """色味の係数。フルカラー=1.0、単色は色数に応じてやや安い→増える。"""
    if color_type == "単色":
        n = max(1, int(spot_colors or 1))
        return round(SPOT_BASE + SPOT_PER_EXTRA * (n - 1), 3)
    return 1.0


def tape_unit_price(width_mm, length_m, qty):
    """テープ1本（1ロール）あたりの 仮 単価。幅cm×長さm × 数量帯レート。"""
    w_cm = max(0.0, float(width_mm)) / 10.0
    length_m = max(0.0, float(length_m))
    qty_i = _band_index(qty, QTY_BANDS)
    return (w_cm * length_m) * TAPE_RATE_BY_QTY[qty_i]


# =====================================================================
# 計算ロジック（実データに差し替えても基本そのまま使える）
# =====================================================================

def calc_area_cm2(shape, width_mm, height_mm):
    """1枚の面積(cm²)を出す。円・楕円は幅=長径・高さ=短径として楕円面積で近似。"""
    w = max(0.0, float(width_mm)) / 10.0   # mm → cm
    h = max(0.0, float(height_mm)) / 10.0
    if shape == "円・楕円":
        # 楕円の面積 = π × (長径/2) × (短径/2)
        return math.pi * (w / 2.0) * (h / 2.0)
    return w * h


def _band_index(value, bands):
    """value が bands のどの帯に入るかの index を返す。"""
    for i, (_label, upper) in enumerate(bands):
        if value <= upper:
            return i
    return len(bands) - 1


def _band_label(value, bands):
    return bands[_band_index(value, bands)][0]


def base_unit_price(area_cm2, qty):
    """面積帯×数量帯から基本単価（1枚）を引く。"""
    area_i = _band_index(area_cm2, AREA_BANDS)
    qty_i = _band_index(qty, QTY_BANDS)
    area_label = AREA_BANDS[area_i][0]
    return BASE_UNIT_PRICE[area_label][qty_i]


def estimate(spec):
    """
    1品目の見積りを計算して、金額と内訳・原価/粗利を辞書で返す。

    spec: dict
      name        品名（任意）
      shape       形状（SHAPE_CHOICES のいずれか）
      width_mm    幅(mm)   ※円・楕円は長径
      height_mm   高さ(mm) ※円・楕円は短径
      material    素材（MATERIAL_CHOICES）
      cut_form    仕上げ形態（CUT_FORM_CHOICES）
      finishes    加工オプションのリスト（FINISH_CHOICES の部分集合）
      qty         数量（枚）
      lead_time   納期（LEAD_TIME_CHOICES）

    返り値の主なキー：
      unit_price      1枚単価（税抜・特急/最低料金反映後）
      subtotal        税抜金額
      tax             消費税
      total           税込金額
      cost            原価（税抜ベース）
      profit          粗利（税抜 - 原価）
      profit_rate     粗利率（粗利 / 税抜）
      breakdown       内訳（画面表示用のリスト）
      lead_time_note  納期の目安
      area_cm2 / area_band / qty_band など補助情報
    """
    product = spec.get("product", PRODUCT_CHOICES[0])
    kind = product_kind(product)
    shape = spec.get("shape", SHAPE_CHOICES[0])
    material = spec.get("material", MATERIAL_CHOICES[0])
    cut_form = spec.get("cut_form", CUT_FORM_CHOICES[0])
    finishes = spec.get("finishes", []) or []
    lead_time = spec.get("lead_time", LEAD_TIME_CHOICES[0])
    qty = int(spec.get("qty", 0) or 0)
    width_mm = spec.get("width_mm", 0) or 0
    height_mm = spec.get("height_mm", 0) or 0
    color_type = spec.get("color_type", COLOR_TYPES[0])
    spot_colors = int(spec.get("spot_colors", 1) or 1)
    setup = spec.get("setup", SETUP_CHOICES[0])
    setup_on = bool(setup) and setup != SETUP_CHOICES[0]
    tape_width_mm = spec.get("tape_width_mm", 0) or 0
    tape_length_m = spec.get("tape_length_m", 0) or 0

    breakdown = []
    area = calc_area_cm2(shape, width_mm, height_mm)

    # 入力が不十分なら 0 円で返す（画面側でエラーにしない）
    if kind == "tape":
        enough = qty > 0 and tape_width_mm > 0 and tape_length_m > 0
        need_msg = "テープ幅・テープ長さと数量を入力してください。"
    else:
        enough = qty > 0 and area > 0
        need_msg = "シールサイズ（幅・高さ）と数量を入力してください。"
    if not enough:
        return {
            "valid": False,
            "unit_price": 0.0, "subtotal": 0, "tax": 0, "total": 0,
            "cost": 0, "profit": 0, "profit_rate": 0.0,
            "breakdown": [], "area_cm2": area, "qty": qty,
            "lead_time_note": LEAD_TIMES[lead_time]["note"],
            "message": need_msg,
        }

    # 1. 基本単価（シール＝面積×数量／テープ＝幅×長さ×数量帯）
    if kind == "tape":
        unit = tape_unit_price(tape_width_mm, tape_length_m, qty)
        breakdown.append(("基本単価（テープ 幅×長さ）",
                          f"{int(tape_width_mm)}mm×{tape_length_m}m / {_band_label(qty, QTY_BANDS)}",
                          round(unit, 2)))
    else:
        unit = base_unit_price(area, qty)
        breakdown.append(("基本単価（面積×数量）",
                          f"{_band_label(area, AREA_BANDS)} / {_band_label(qty, QTY_BANDS)}",
                          round(unit, 2)))

    # 2. 素材係数
    m_coef = MATERIALS.get(material, 1.0)
    unit_after_material = unit * m_coef
    if m_coef != 1.0:
        breakdown.append(("素材係数", f"{material}（×{m_coef}）",
                          round(unit_after_material - unit, 2)))
    unit = unit_after_material

    # 2b. 色味（単色は係数でやや安く／色数で増える）
    c_coef = color_factor(color_type, spot_colors)
    if c_coef != 1.0:
        color_label = f"単色×{spot_colors}色" if color_type == "単色" else color_type
        before = unit
        unit = unit * c_coef
        breakdown.append(("色味", f"{color_label}（×{c_coef}）", round(unit - before, 2)))

    # 3. 加工オプション（1枚あたり加算）
    finish_add = sum(FINISH_OPTIONS.get(f, 0.0) for f in finishes)
    if finish_add:
        breakdown.append(("加工オプション", "／".join(finishes), round(finish_add, 2)))
    unit += finish_add

    # 3b. 仕上げ形態（1枚あたり加算）
    cut_add = CUT_FORMS.get(cut_form, 0.0)
    if cut_add:
        breakdown.append(("仕上げ形態", cut_form, round(cut_add, 2)))
    unit += cut_add

    # 3c. セットアップ（内職：セット・貼り合わせ等の手作業）1枚あたり加算
    if setup_on:
        breakdown.append(("セットアップ（内職）", "セット・貼り合わせ等", round(SETUP_UNIT_PRICE, 2)))
        unit += SETUP_UNIT_PRICE

    # 単価×数量
    pieces_subtotal = unit * qty

    # 4. 初期費用（型抜きの抜き型代。テープは対象外）
    die_fee = DIE_CUT_FEE if (kind == "seal" and SHAPES.get(shape, {}).get("die_cut")) else 0
    if die_fee:
        breakdown.append(("抜き型代（初期費用・1回）", shape, die_fee))

    subtotal_before = pieces_subtotal + die_fee

    # 5. 特急割増
    surcharge = LEAD_TIMES[lead_time]["surcharge"]
    subtotal_rush = subtotal_before * surcharge
    if surcharge != 1.0:
        breakdown.append(("特急割増", f"{lead_time}（×{surcharge}）",
                          round(subtotal_rush - subtotal_before)))

    # 6. 最低料金の下限調整
    min_adjusted = False
    subtotal = subtotal_rush
    if subtotal < MIN_ORDER_PRICE:
        breakdown.append(("最低料金の調整",
                          f"最低 {MIN_ORDER_PRICE:,}円に引き上げ",
                          round(MIN_ORDER_PRICE - subtotal)))
        subtotal = MIN_ORDER_PRICE
        min_adjusted = True

    subtotal = round(subtotal)

    # 7. 原価・粗利（税抜ベース）
    cost_rate = BASE_COST_RATE + MATERIAL_COST_RATE_ADJ.get(material, 0.0)
    # 枚数分の原価（原価率）＋ 型代の原価（型代は原価率高め）
    cost = (max(subtotal - die_fee, 0) * cost_rate) + (die_fee * DIE_CUT_COST_RATE)
    cost = round(cost)
    profit = subtotal - cost
    profit_rate = (profit / subtotal) if subtotal else 0.0

    # 8. 消費税・税込
    tax = round(subtotal * TAX_RATE)
    total = subtotal + tax

    return {
        "valid": True,
        "name": spec.get("name", ""),
        "product": product, "kind": kind,
        "shape": shape, "material": material, "cut_form": cut_form,
        "finishes": finishes, "lead_time": lead_time,
        "width_mm": width_mm, "height_mm": height_mm, "qty": qty,
        "color_type": color_type, "spot_colors": spot_colors, "color_factor": c_coef,
        "setup_on": setup_on,
        "tape_width_mm": tape_width_mm, "tape_length_m": tape_length_m,
        "area_cm2": round(area, 1),
        "area_band": _band_label(area, AREA_BANDS),
        "qty_band": _band_label(qty, QTY_BANDS),
        "unit_price": round(subtotal / qty, 2) if qty else 0.0,  # 実効1枚単価（型代・特急・最低料金反映後）
        "raw_unit_price": round(unit, 2),                        # 加工まで反映した素の1枚単価
        "die_fee": die_fee,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "cost": cost,
        "profit": profit,
        "profit_rate": profit_rate,
        "cost_rate": round(cost_rate, 3),
        "min_adjusted": min_adjusted,
        "breakdown": breakdown,
        "lead_time_note": LEAD_TIMES[lead_time]["note"],
        "spec_text": build_spec_text(spec, kind),
    }


def build_spec_text(spec, kind=None):
    """明細の「仕様」欄に入れる短い説明文を組み立てる。"""
    kind = kind or product_kind(spec.get("product", ""))
    material = spec.get("material", "")
    parts = []
    if kind == "tape":
        parts.append(f"テープ {int(spec.get('tape_width_mm', 0))}mm×{spec.get('tape_length_m', 0)}m")
        parts.append(material)
    else:
        shape = spec.get("shape", "")
        w, h = int(spec.get("width_mm", 0)), int(spec.get("height_mm", 0))
        size = f"{w}×{h}mm(楕円)" if shape == "円・楕円" else f"{w}×{h}mm"
        parts += [shape, size, material]

    color_type = spec.get("color_type", "フルカラー")
    parts.append(f"単色×{int(spec.get('spot_colors', 1) or 1)}色" if color_type == "単色" else "フルカラー")

    cut_form = spec.get("cut_form", "")
    if cut_form and kind != "tape":
        parts.append(cut_form)
    finishes = spec.get("finishes", []) or []
    if finishes:
        parts.append("／".join(finishes))
    if spec.get("setup") and spec.get("setup") != SETUP_CHOICES[0]:
        parts.append("内職あり")
    return " / ".join([p for p in parts if p])


def apply_discount(items, discount_type, discount_value):
    """
    複数品目（estimate の返り値のリスト）を合計し、値引きを適用して合計を返す。

    discount_type: "なし" / "金額（円）" / "割合（％）"
    discount_value: 値引き額 or 率
    """
    sub_sum = sum(it["subtotal"] for it in items if it.get("valid"))
    cost_sum = sum(it["cost"] for it in items if it.get("valid"))

    if discount_type == "金額（円）":
        discount = min(max(int(discount_value or 0), 0), sub_sum)
    elif discount_type == "割合（％）":
        rate = min(max(float(discount_value or 0), 0.0), 100.0)
        discount = round(sub_sum * rate / 100.0)
    else:
        discount = 0

    subtotal_after = sub_sum - discount
    tax = round(subtotal_after * TAX_RATE)
    total = subtotal_after + tax
    profit = subtotal_after - cost_sum          # 値引きは粗利から差し引かれる
    profit_rate = (profit / subtotal_after) if subtotal_after else 0.0

    return {
        "items_subtotal": sub_sum,        # 値引き前の税抜合計
        "discount": discount,             # 値引き額
        "subtotal_after": subtotal_after, # 値引き後の税抜
        "tax": tax,
        "total": total,                   # 税込合計
        "cost": cost_sum,
        "profit": profit,                 # 値引き後の粗利
        "profit_rate": profit_rate,       # 値引き後の粗利率
        "below_cost": profit < 0,         # 原価割れ（赤字）フラグ
    }
