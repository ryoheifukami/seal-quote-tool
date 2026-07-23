# -*- coding: utf-8 -*-
"""
単価マスタ・商品マスタ 編集画面（Streamlit）

masters.py の JSON に読み書きし、編集内容が見積計算（pricing_real）に反映される。
"""

import streamlit as st
import masters

METHODS = ["平圧・間欠印刷", "マスキングテープ", "コニカミノルタ オンデマンド"]


def _edit_scalars(method_key, values, labels):
    """スカラー定数を項目=値の表で編集。編集後の {key: value} を返す。"""
    rows = [{"項目": labels.get(k, k), "_key": k, "値": values[k]} for k in labels]
    ed = st.data_editor(rows, hide_index=True, width="stretch", key=f"sc_{method_key}",
                        disabled=["項目", "_key"], column_order=["項目", "値"])
    return {r["_key"]: r["値"] for r in ed}


def _edit_map(title, mapping, k_label, v_label, key):
    """{'1':num,...} を表で編集し、編集後の {str: num} を返す。"""
    st.caption(title)
    rows = [{k_label: k, v_label: v} for k, v in mapping.items()]
    ed = st.data_editor(rows, hide_index=True, width="stretch", key=key, disabled=[k_label])
    return {str(r[k_label]): r[v_label] for r in ed}


def render_rates():
    st.markdown("### 単価マスタ")
    st.markdown("見積計算に使う**単価・係数・料金表**です。初期値は実際のExcelと同じ。"
                "編集して保存すると、見積計算に反映されます。")
    rates = masters.get_rates()
    new = {"hiraatsu": {}, "konica": {}, "masking": {}}

    with st.container(border=True):
        st.markdown("#### 平圧・間欠印刷")
        h = rates["hiraatsu"]
        new["hiraatsu"].update(_edit_scalars("h", h, masters.RATE_LABELS["hiraatsu"]))
        c1, c2 = st.columns(2)
        with c1:
            new["hiraatsu"]["yobi_shot"] = _edit_map("予備ショット（色数）", h["yobi_shot"], "色数", "予備ショット", "h_yobi")
            new["hiraatsu"]["hangata_G"] = _edit_map("版型セット代 平圧", h["hangata_G"], "色数", "金額", "h_hgG")
            new["hiraatsu"]["hangata_H"] = _edit_map("版型セット代 間欠", h["hangata_H"], "色数", "金額", "h_hgH")
        with c2:
            new["hiraatsu"]["tooshi_G"] = _edit_map("通し工賃 平圧", h["tooshi_G"], "色数", "工賃", "h_tsG")
            new["hiraatsu"]["tooshi_H"] = _edit_map("通し工賃 間欠", h["tooshi_H"], "色数", "工賃", "h_tsH")

    with st.container(border=True):
        st.markdown("#### コニカミノルタ オンデマンド")
        new["konica"].update(_edit_scalars("k", rates["konica"], masters.RATE_LABELS["konica"]))

    with st.container(border=True):
        st.markdown("#### マスキングテープ")
        m = rates["masking"]
        new["masking"].update(_edit_scalars("m", m, masters.RATE_LABELS["masking"]))
        st.caption("止めシール（数量帯ごとの金額）")
        trows = [{"数量上限": lim, "金額": val} for lim, val in m["tome_tiers"]]
        ted = st.data_editor(trows, hide_index=True, width="stretch", key="m_tome", num_rows="dynamic")
        new["masking"]["tome_tiers"] = [[int(r["数量上限"]), int(r["金額"])] for r in ted
                                        if r.get("数量上限") not in (None, "")]

    b1, b2, _ = st.columns([1, 1, 3])
    if b1.button("💾 単価マスタを保存", type="primary"):
        merged = masters.get_rates()
        for mk in new:
            merged[mk].update(new[mk])
        masters.save_rates(merged)
        st.success("保存しました。以後の見積計算に反映されます。")
    if b2.button("初期値（Excel）に戻す"):
        masters.reset_rates()
        st.success("初期値に戻しました。")
        st.rerun()


def render_products():
    st.markdown("### 商品マスタ")
    st.markdown("**図番→品名・方式・標準仕様**の一覧です。注文書PDFの図番照合や、見積入力の下敷きに使います。"
                "行の追加・編集ができます（一番下の空行に入力すると追加）。")
    products = masters.get_products()
    rows = [{"図番": p.get("zuban", ""), "品名": p.get("name", ""), "方式": p.get("method", ""),
             "顧客": p.get("customer", ""), "参考単価": p.get("unit_price", 0),
             "標準仕様(メモ)": p.get("spec", {}).get("material_note", ""), "備考": p.get("note", "")}
            for p in products]
    ed = st.data_editor(
        rows, hide_index=True, width="stretch", num_rows="dynamic", key="ed_products",
        column_config={"方式": st.column_config.SelectboxColumn("方式", options=METHODS),
                       "参考単価": st.column_config.NumberColumn("参考単価", format="¥%.2f")})

    if st.button("💾 商品マスタを保存", type="primary"):
        newp = []
        for r in ed:
            zuban = (r.get("図番") or "").strip()
            name = (r.get("品名") or "").strip()
            if not zuban and not name:
                continue
            old = masters.find_product_by_zuban(zuban) or {}
            spec = old.get("spec", {})
            spec["material_note"] = r.get("標準仕様(メモ)", "")
            newp.append({"zuban": zuban, "name": name, "method": r.get("方式", ""),
                         "customer": r.get("顧客", ""), "unit_price": r.get("参考単価", 0) or 0,
                         "note": r.get("備考", ""), "spec": spec})
        masters.save_products(newp)
        st.success(f"保存しました（{len(newp)}件）。")
    st.caption("※ 図番の詳細な寸法・面付などの標準仕様は、見積作成で図番を選ぶと下敷きになります（今後さらに拡充予定）。")
