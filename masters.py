# -*- coding: utf-8 -*-
"""
マスタ管理（単価マスタ・商品マスタ）— JSON永続化

・単価マスタ（rates）：見積計算の定数・単価表。初期値は実際のExcelの値。
  data/rates.json に保存され、pricing_real がこれを読んで計算する（編集が計算に反映）。
・商品マスタ（products）：図番→品名・方式・標準仕様。注文書PDFの図番照合や入力プリセットに使う。
  data/products.json に保存。

保存ファイルが無い場合は下の DEFAULT を使う（＝Excel通りの計算）。
"""

import json
import os
import copy

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
RATES_PATH = os.path.join(DATA_DIR, "rates.json")
PRODUCTS_PATH = os.path.join(DATA_DIR, "products.json")

# =====================================================================
# 単価マスタ（初期値＝実Excelの定数・表）
# =====================================================================
DEFAULT_RATES = {
    "hiraatsu": {
        "yobi_shot": {"1": 1000, "2": 2000, "3": 3000, "4": 4000, "5": 5000},  # 予備ショット(色数)
        "hangata_G": {"1": 4000, "2": 5200, "3": 6400},                        # 版型セット代 平圧(No.2大型)
        "hangata_H": {"1": 5200, "2": 6400, "3": 7600, "4": 8800, "5": 10000}, # 版型セット代 間欠(No.3光)
        "tooshi_G": {"1": 1.2, "2": 1.44, "3": 1.68},                          # 通し工賃 平圧
        "tooshi_H": {"1": 1.44, "2": 1.68, "3": 1.92, "4": 2.16, "5": 2.4},    # 通し工賃 間欠
        "haku_toshi": 1.2, "num_tanka": 60, "add_hira_set": 4000, "add_hira_shot": 1.2,
        "add_kan_set": 5200, "add_kan_shot": 1.44, "set_pp": 1600, "set_haku": 4000,
        "set_num": 4800, "slitter": 4,
    },
    "konica": {
        "genshi_w": 25, "nuki_yobi": 1000, "onde_choshi": 20000, "iroawase": 20000,
        "loss_pct": 10, "ink_tanka": 38, "onde_set": 4800, "onde_koching": 10.9,
        "nuki_half": 1.2, "nuki_all": 1.44, "set_pp": 1600, "slitter": 4, "cooldown": 8,
    },
    "masking": {
        "genshi_tanka": 49, "nenchaku": 7, "nis": 26.4, "ink": 24, "pj_set": 6900,
        "pj_print": 5.8, "emul_set": 6900, "emul_print": 8, "komaki": 51.5, "cut": 51.5,
        "shikan": 31.8, "pp_naishoku": 8, "proof": 20000, "data_cost": 3000, "soryo": 1500,
        "tome_tiers": [[1000, 24000], [2000, 29600], [3000, 32400], [4000, 35200],
                       [5000, 38000], [6000, 43800], [7000, 46200], [8000, 48800],
                       [10000, 58000], [20000, 90000]],
    },
}

# 単価マスタ 各項目の日本語ラベル（編集画面用）
RATE_LABELS = {
    "hiraatsu": {
        "haku_toshi": "箔押し通し工賃", "num_tanka": "ナンバリング平米単価",
        "add_hira_set": "追加加工 平圧 セット", "add_hira_shot": "追加加工 平圧 ショット",
        "add_kan_set": "追加加工 間欠 セット", "add_kan_shot": "追加加工 間欠 ショット",
        "set_pp": "加工セット(PP)", "set_haku": "加工セット(箔)",
        "set_num": "加工セット(ナンバリング)", "slitter": "スリッター代(1m)",
    },
    "konica": {
        "genshi_w": "原紙幅(cm)固定", "nuki_yobi": "抜き予ショット固定", "onde_choshi": "オンデ調子出し(mm)",
        "iroawase": "色合せ(mm)", "loss_pct": "ロス分(%)", "ink_tanka": "インク単価",
        "onde_set": "オンデセット", "onde_koching": "オンデ工賃", "nuki_half": "抜き工賃(ハーフ)",
        "nuki_all": "抜き工賃(全)", "set_pp": "加工セット(PP)", "slitter": "スリッター代(1m)",
        "cooldown": "クールダウン(円/m)",
    },
    "masking": {
        "genshi_tanka": "原紙 平米単価", "nenchaku": "粘着剤", "nis": "シリコンニス", "ink": "インク",
        "pj_set": "PJセット代", "pj_print": "PJ印刷", "emul_set": "エマルジョンセット",
        "emul_print": "エマルジョン印刷", "komaki": "小巻", "cut": "カット(30φ)", "shikan": "紙管(30φ)",
        "pp_naishoku": "PPシート＋内職", "proof": "色校正(一律)", "data_cost": "印刷用データ作成", "soryo": "送料(1箱)",
    },
}

# =====================================================================
# 商品マスタ（初期値。図番→品名・方式・標準仕様）
# =====================================================================
_TEL_LABEL = "透明PET(下地PET#25)+ラミネート(PET#16)／黒1色／文字高3mm"
_TEL_SPEC = {"colors": 1, "machine": 2, "nuki": 2, "finish": 1, "material_note": _TEL_LABEL}

DEFAULT_PRODUCTS = [
    # 注文書（数量あり）
    {"zuban": "2L10-256692-11", "name": "富士精密 ラベル", "customer": "富士精密株式会社",
     "method": "平圧・間欠印刷",
     "spec": {"width": 40, "height": 20, "colors": 1, "machine": 2, "menzuke_w": 4, "menzuke_p": 4,
              "material_note": "上質紙", "nuki": 2, "finish": 1},
     "unit_price": 52.40, "note": "注文書 図番 2L10-256692-11"},
    # 東京エレクトロン(TEL) 図面：BASE, FRONT DUCT EPU ラベル（ラベル仕様は各図面の注記より）
    {"zuban": "TW10-518005-11", "name": "BASE, FRONT DUCT EPU ラベル", "customer": "東京エレクトロン",
     "method": "平圧・間欠印刷", "spec": dict(_TEL_SPEC), "unit_price": 0, "note": "TEL図面"},
    {"zuban": "TW10-518008-11", "name": "BASE, FRONT DUCT EPU ラベル", "customer": "東京エレクトロン",
     "method": "平圧・間欠印刷", "spec": dict(_TEL_SPEC), "unit_price": 0, "note": "TEL図面"},
    {"zuban": "TW10-518009-11", "name": "BASE, FRONT DUCT EPU ラベル", "customer": "東京エレクトロン",
     "method": "平圧・間欠印刷", "spec": dict(_TEL_SPEC), "unit_price": 0, "note": "TEL図面"},
    {"zuban": "TW10-518010-11", "name": "BASE, FRONT DUCT EPU ラベル", "customer": "東京エレクトロン",
     "method": "平圧・間欠印刷", "spec": dict(_TEL_SPEC), "unit_price": 0, "note": "TEL図面"},
    {"zuban": "SD-MTP-001", "name": "オリジナルマスキングテープ", "customer": "",
     "method": "マスキングテープ",
     "spec": {"width": 15, "maki_m": 5, "material_note": "和紙"},
     "unit_price": 0, "note": ""},
]


# =====================================================================
# 読み書き
# =====================================================================
def _deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def get_rates():
    """保存済みの単価マスタ（無ければ実Excelの初期値）。defaultに上書きマージして返す。"""
    try:
        with open(RATES_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        return _deep_merge(DEFAULT_RATES, saved)
    except Exception:
        return copy.deepcopy(DEFAULT_RATES)


def save_rates(rates):
    _ensure_dir()
    with open(RATES_PATH, "w", encoding="utf-8") as f:
        json.dump(rates, f, ensure_ascii=False, indent=2)


def reset_rates():
    try:
        os.remove(RATES_PATH)
    except FileNotFoundError:
        pass


def get_products():
    try:
        with open(PRODUCTS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return copy.deepcopy(DEFAULT_PRODUCTS)


def save_products(products):
    _ensure_dir()
    with open(PRODUCTS_PATH, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)


def find_product_by_zuban(zuban):
    z = (zuban or "").strip().lower()
    for p in get_products():
        if p.get("zuban", "").strip().lower() == z:
            return p
    return None
