# -*- coding: utf-8 -*-
"""動作確認テスト。実行: py test_smoke.py"""
import sys

from streamlit.testing.v1 import AppTest

import machine_select as ms
import pricing_real

sys.stdout.reconfigure(encoding="utf-8")
FAILED = []


def check(name, cond, detail=""):
    print(("OK  " if cond else "NG! ") + name + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


# --- 計算エンジン（Excelと一致） ---
check("計算エンジンがExcelと一致", pricing_real.verify())

# --- 印刷機選定・面付目安 ---
cands, excl, haku = ms.suggest_machines(colors=1, width=50, height=30, need_half_cut=True)
check("1色ハーフカットの候補は5機種", sorted(m["name"] for m in cands) == sorted(
    ["間欠JNAS250", "間欠ES150", "平圧270", "平圧150", "ロータリーP25"]))
cands, _, _ = ms.suggest_machines(colors=5, width=50, height=30, need_half_cut=True)
check("5色はJNAS250のみ", [m["name"] for m in cands] == ["間欠JNAS250"])
jnas = next(m for m in ms.DEFAULT_MACHINES if m["name"] == "間欠JNAS250")
check("面付目安 4,999枚=1 / 5,000枚=2 / 8,000枚=4 / 10,000枚=5",
      [ms.menzuke_hint(jnas, q) for q in (4999, 5000, 8000, 10000)] == [1, 2, 4, 5])
check("コニカは面付目安の表記が無いのでNone", ms.menzuke_hint(ms.DEFAULT_MACHINES[0], 5000) is None)


# --- 画面（3方式がエラー無く表示される／材料行・面付目安が出る） ---
def open_app(method):
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    at.session_state["page"] = "見積作成"
    at.session_state["rq_mode"] = "✏️ 仕様を直接入力"
    at.session_state["rq_method"] = method
    at.run()
    return at


for method in ("平圧・間欠印刷", "マスキングテープ", "コニカミノルタ オンデマンド"):
    at = open_app(method)
    check(f"{method}: 画面エラー無し", not at.exception, str(at.exception))

at = open_app("平圧・間欠印刷")
infos = [i.value for i in at.info]
check("材料行（紙幅×購入m）が出る", any("使用材料：紙幅" in i for i in infos))
check("原紙単価0のとき警告が出る", any("未入力" in w.value for w in at.warning))
at.number_input(key="h_gt").set_value(86.0).run()
check("原紙単価を入れると警告が消える", not any("未入力" in w.value for w in at.warning))
at.number_input(key="h_qty").set_value(8000).run()
caps = " ".join(c.value for c in at.caption)
check("数量8,000枚で『4面付が目安』", "4面付" in caps)

# --- 平圧で5色にしても落ちない ---
at = open_app("平圧・間欠印刷")
at.selectbox(key="h_mac").set_value("間欠").run()
at.number_input(key="h_col").set_value(5).run()
at.selectbox(key="h_mac").set_value("平圧").run()
check("間欠5色→平圧に戻しても落ちない", not at.exception, str(at.exception))

print("\n" + ("★ ALL PASS" if not FAILED else f"★ 失敗 {len(FAILED)}件: {FAILED}"))
sys.exit(1 if FAILED else 0)
