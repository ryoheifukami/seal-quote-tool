# -*- coding: utf-8 -*-
"""
見積履歴・テンプレートの保存（JSON永続化）

・history.json … 作成した見積の記録（ダッシュボード集計・履歴一覧に使う）
・templates.json … 見積作成の入力プリセット
"""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
TEMPLATES_PATH = os.path.join(DATA_DIR, "templates.json")


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---- 見積履歴 ----
def get_history():
    return _load(HISTORY_PATH)


def add_history(rec):
    h = get_history()
    h.insert(0, rec)              # 新しい順
    _save(HISTORY_PATH, h[:1000])


def clear_history():
    _save(HISTORY_PATH, [])


# ---- テンプレート ----
def get_templates():
    return _load(TEMPLATES_PATH)


def save_template(name, method, inputs):
    ts = [t for t in get_templates() if t.get("name") != name]
    ts.insert(0, {"name": name, "method": method, "inputs": inputs})
    _save(TEMPLATES_PATH, ts)


def delete_template(name):
    _save(TEMPLATES_PATH, [t for t in get_templates() if t.get("name") != name])
