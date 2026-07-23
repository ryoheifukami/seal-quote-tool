# -*- coding: utf-8 -*-
"""
問い合わせ本文（フォーム／メール）を読み取って、見積りフォームの各項目に整理する。

二段構え：
  ・APIキーがあれば AI（Claude）で読み取り … 崩れた自由文にも強い
  ・無ければ パターン照合（正規表現）で読み取り … ラベル付きの依頼文はしっかり拾える

返り値：parse_inquiry(text, api_key) -> (fields, method, notes)
  fields … 見積りフォームに入れる値の辞書（不明な項目は入れない）
  method … "AI" / "パターン照合"
  notes  … 補足メッセージのリスト（読み取れなかった等）
"""

import re

import pricing

AI_MODEL = "claude-haiku-4-5"   # 短い抽出作業なのでHaikuで十分・安価


# ---------------------------------------------------------------
# 値を pricing 側の正式な選択肢に寄せる（表記ゆれの吸収）
# ---------------------------------------------------------------
def _match_choice(value, choices):
    """value に最も近い選択肢を返す（部分一致・キーワード一致）。無ければ None。"""
    if not value:
        return None
    v = str(value)
    for c in choices:
        if c == v:
            return c
    for c in choices:
        if v in c or c in v:
            return c
    return None


_MATERIAL_KEYWORDS = [
    (("上質", "普通紙", "紙シール"), "上質紙（一般的な紙シール）"),
    (("コート", "アート紙"), "コート紙（つやのある紙）"),
    (("ユポ", "合成紙"), "合成紙ユポ（水に強い）"),
    (("透明", "pet", "フィルム", "クリア"), "透明PET（透明フィルム）"),
    (("塩ビ", "塩化ビニル", "屋外", "ステッカー素材"), "塩ビ（屋外ステッカー向け）"),
]

_PRODUCT_KEYWORDS = [
    (("マスキング", "マステ"), "マスキングテープ"),
    (("紙テープ", "オリジナルテープ"), "オリジナル紙テープ"),
    (("化粧品", "美容", "コスメ"), "化粧品・美容ラベル"),
    (("食品", "表示ラベル", "原材料"), "食品表示ラベル"),
    (("封かん", "封緘", "封"), "封かん・封緘シール"),
    (("ノベルティ", "販促"), "ノベルティシール"),
    (("バーコード", "管理", "jan"), "バーコード・管理ラベル"),
    (("ステッカー",), "ステッカー（一般）"),
    (("ラベル", "シール"), "商品ラベル"),
]

_FINISH_KEYWORDS = [
    (("グロスラミ", "つや有", "光沢ラミ", "グロス"), "ラミネート（グロス／つや有り）"),
    (("マットラミ", "つや消", "マット"), "ラミネート（マット／つや消し）"),
    (("uvニス", "ニス", "uv"), "UVニス（表面保護）"),
    (("箔", "ホットスタンプ", "金箔", "銀箔"), "箔押し（金・銀などの箔）"),
    (("強粘着", "強粘"), "強粘着（はがれにくい糊）"),
]


def _num(s):
    """カンマ入りの数字文字列を int に。失敗は None。"""
    try:
        return int(float(str(s).replace(",", "").strip()))
    except Exception:
        return None


# ---------------------------------------------------------------
# パターン照合（正規表現）での読み取り
# ---------------------------------------------------------------
def regex_parse(text):
    fields = {}
    t = text.replace("，", ",").replace("　", " ")
    low = t.lower()

    # 数量（○○枚/巻/本/個/ロール、○○〜○○枚 → 大きい方を採用）
    qtys = re.findall(r"([\d,]+)\s*[〜~\-ー]?\s*([\d,]*)\s*(?:枚|巻|本|個|ロール|ｹ|ケ)", t)
    if qtys:
        cand = []
        for a, b in qtys:
            for x in (a, b):
                n = _num(x)
                if n:
                    cand.append(n)
        if cand:
            fields["qty"] = max(cand)

    # シールサイズ（○○×○○ mm）
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm|㎜|ミリ)?\s*[×xX＊*]\s*(\d+(?:\.\d+)?)\s*(?:mm|㎜|ミリ)?", t)
    if m:
        fields["width_mm"] = _num(float(m.group(1)))
        fields["height_mm"] = _num(float(m.group(2)))

    # テープ幅・長さ
    mw = re.search(r"テープ幅[：:\s]*(\d+(?:\.\d+)?)\s*(?:mm|㎜)?", t)
    if not mw:
        mw = re.search(r"幅[：:\s]*(\d+(?:\.\d+)?)\s*(?:mm|㎜)", t)
    if mw:
        fields["tape_width_mm"] = _num(float(mw.group(1)))
    ml = re.search(r"(?:テープ)?長さ[：:\s]*(\d+(?:\.\d+)?)\s*m\b", t)
    if not ml:
        ml = re.search(r"(\d+(?:\.\d+)?)\s*m\s*巻", t)
    if ml:
        try:
            fields["tape_length_m"] = float(ml.group(1))
        except Exception:
            pass

    # 材質
    for keys, val in _MATERIAL_KEYWORDS:
        if any(k in low for k in keys):
            fields["material"] = val
            break

    # 品名
    for keys, val in _PRODUCT_KEYWORDS:
        if any(k.lower() in low for k in keys):
            fields["product"] = val
            break

    # 色味
    cm = re.search(r"単色\s*[×xX*]?\s*(\d+)\s*色", t) or re.search(r"(\d+)\s*色", t)
    if "フルカラー" in t or "カラー" in t and "単色" not in t:
        fields["color_type"] = "フルカラー"
    if "単色" in t or "スミ" in t or (cm and "フルカラー" not in t):
        fields["color_type"] = "単色"
        if cm:
            n = _num(cm.group(1))
            if n:
                fields["spot_colors"] = n
        else:
            fields["spot_colors"] = 1

    # セットアップ（内職）
    if "内職" in t or "セットアップ" in t:
        if re.search(r"内職[^。\n]{0,6}(しない|不要|なし)", t) or "セットアップしない" in t:
            fields["setup"] = pricing.SETUP_CHOICES[0]
        else:
            fields["setup"] = pricing.SETUP_CHOICES[1]

    # 加工オプション
    fin = []
    for keys, val in _FINISH_KEYWORDS:
        if any(k in low for k in keys):
            fin.append(val)
    if fin:
        fields["finishes"] = fin

    # 納期
    if any(k in t for k in ["急ぎ", "特急", "短納期", "至急"]):
        fields["lead_time"] = "お急ぎ（約3〜4営業日）"

    return fields


# ---------------------------------------------------------------
# AI（Claude）での読み取り
# ---------------------------------------------------------------
def ai_parse(text, api_key):
    """Claude で項目抽出。失敗時は例外を投げる（呼び出し側で regex にフォールバック）。"""
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    schema_hint = {
        "product": "品名の種類（例：商品ラベル / ステッカー / マスキングテープ 等）",
        "width_mm": "シールの幅(mm) 数値",
        "height_mm": "シールの高さ(mm) 数値",
        "material": "希望材質（例：上質紙 / コート紙 / ユポ / 透明PET / 塩ビ）",
        "color_type": "フルカラー または 単色",
        "spot_colors": "単色のときの色数（整数）",
        "tape_width_mm": "テープ幅(mm) 数値（テープ商品のみ）",
        "tape_length_m": "テープ長さ(m) 数値（テープ商品のみ）",
        "setup": "内職（セット作業）するなら true",
        "qty": "数量（枚）。範囲なら大きい方の整数",
        "finishes": "加工の配列（ラミネート/UVニス/箔押し/強粘着 など）",
        "lead_time": "急ぎ希望なら 'お急ぎ' そうでなければ '通常'",
        "name": "品名の呼び名（あれば）",
    }
    prompt = (
        "あなたはシール・ラベル印刷の受付担当です。次の問い合わせ本文から、見積りに必要な項目を"
        "JSONだけで抜き出してください。分からない項目はキー自体を省いてください。"
        "余計な説明やコードブロックは書かず、JSONオブジェクトのみを返すこと。\n\n"
        f"抜き出す項目の意味:\n{schema_hint}\n\n"
        f"問い合わせ本文:\n\"\"\"\n{text}\n\"\"\""
    )
    msg = client.messages.create(
        model=AI_MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError("AIの応答からJSONを取り出せませんでした")
    import json
    data = json.loads(m.group(0))

    fields = {}
    if data.get("product"):
        fields["product"] = data["product"]
    for k in ("width_mm", "height_mm", "tape_width_mm", "qty", "spot_colors"):
        if data.get(k) is not None:
            n = _num(data[k])
            if n is not None:
                fields[k] = n
    if data.get("tape_length_m") is not None:
        try:
            fields["tape_length_m"] = float(str(data["tape_length_m"]).replace(",", ""))
        except Exception:
            pass
    if data.get("material"):
        fields["material"] = data["material"]
    if data.get("color_type"):
        fields["color_type"] = "単色" if "単" in str(data["color_type"]) else "フルカラー"
    if data.get("setup") in (True, "true", "True", "する", 1):
        fields["setup"] = pricing.SETUP_CHOICES[1]
    if isinstance(data.get("finishes"), list) and data["finishes"]:
        fields["finishes"] = data["finishes"]
    if data.get("lead_time") and "急" in str(data["lead_time"]):
        fields["lead_time"] = "お急ぎ（約3〜4営業日）"
    if data.get("name"):
        fields["name"] = str(data["name"])
    return fields


# ---------------------------------------------------------------
# 正式な選択肢への正規化（AI・regex 共通）
# ---------------------------------------------------------------
def normalize_fields(raw):
    f = dict(raw)
    notes = []

    if "product" in f:
        c = _match_choice(f["product"], pricing.PRODUCT_CHOICES)
        if not c:
            for keys, val in _PRODUCT_KEYWORDS:
                if any(k.lower() in str(f["product"]).lower() for k in keys):
                    c = val
                    break
        if c:
            f["product"] = c
        else:
            f["name"] = f.get("name") or str(f["product"])
            f.pop("product", None)

    if "material" in f:
        c = _match_choice(f["material"], pricing.MATERIAL_CHOICES)
        if not c:
            for keys, val in _MATERIAL_KEYWORDS:
                if any(k in str(f["material"]).lower() for k in keys):
                    c = val
                    break
        if c:
            f["material"] = c
        else:
            notes.append(f"材質『{f['material']}』は候補に合わず、そのままにしました")
            f.pop("material", None)

    if "finishes" in f:
        fixed = []
        for x in f["finishes"]:
            c = _match_choice(x, pricing.FINISH_CHOICES)
            if not c:
                for keys, val in _FINISH_KEYWORDS:
                    if any(k in str(x).lower() for k in keys):
                        c = val
                        break
            if c and c not in fixed:
                fixed.append(c)
        if fixed:
            f["finishes"] = fixed
        else:
            f.pop("finishes", None)

    if f.get("color_type") == "単色" and not f.get("spot_colors"):
        f["spot_colors"] = 1

    return f, notes


def parse_inquiry(text, api_key=None):
    """本文を読み取って (fields, method, notes) を返す。"""
    text = (text or "").strip()
    if not text:
        return {}, "（未入力）", ["本文が空です。"]

    method = "パターン照合"
    notes = []
    raw = {}
    if api_key:
        try:
            raw = ai_parse(text, api_key)
            method = "AI"
        except Exception as e:
            notes.append(f"AI読み取りに失敗したためパターン照合に切り替えました（{type(e).__name__}）")
            raw = regex_parse(text)
    else:
        raw = regex_parse(text)

    fields, norm_notes = normalize_fields(raw)
    notes += norm_notes
    if not fields:
        notes.append("項目を読み取れませんでした。手入力をお願いします。")
    return fields, method, notes
