# -*- coding: utf-8 -*-
"""
注文書PDF（画像）の読み取り → 図番照合 → 見積作成へ自動入力

流れ：
  1. PDFをアップロード → 1ページ目を画像化して表示
  2. APIキーがあれば Claude（画像認識）で図番・数量を自動抽出。無ければ図番を手入力。
  3. 図番を商品マスタで照合 → 一致した品名・方式・標準仕様＋数量を見積作成にセット。

注文書PDFは多くがスキャン画像（文字が埋め込まれていない）なので、
テキスト抽出ではなく画像認識（AI）で読み取る。APIキーが無い場合は図番の手入力で対応。
"""

import base64
import json
import os
import re

import streamlit as st

import masters

# ファイル名から図番らしき文字列を取り出す（例 "TW10-518005-11 (3).pdf" → "TW10-518005-11"）
_ZUBAN_RE = re.compile(r"[A-Za-z0-9]{2,}-\d{3,}-\d{1,3}")


def zuban_from_filename(fname):
    base = os.path.splitext(fname or "")[0]
    m = _ZUBAN_RE.search(base)
    return m.group(0) if m else ""

VISION_MODEL = "claude-haiku-4-5"

# 各方式のスペック→入力ウィジェットのキー対応（型キャスト付き）
_SPEC_MAP = {
    "平圧・間欠印刷": [("width", "h_w", float), ("height", "h_h", float), ("colors", "h_col", int),
                  ("machine", "h_mac_v", int), ("menzuke_w", "h_mw", int), ("menzuke_p", "h_mp", int)],
    "コニカミノルタ オンデマンド": [("width", "k_w", float), ("height", "k_h", float),
                          ("print_w", "k_pw", int), ("nuki_w", "k_nw", int), ("nuki_p", "k_np", int)],
    "マスキングテープ": [("width", "m_w", float), ("maki_m", "m_mk", float)],
}
_QTY_KEY = {"平圧・間欠印刷": "h_qty", "コニカミノルタ オンデマンド": "k_qty", "マスキングテープ": "m_qty"}


def pdf_pages_png(pdf_bytes, max_pages=12, zoom=2.0):
    """PDFの各ページをPNG(bytes)のリストに。pymupdfが無ければ空リスト。"""
    try:
        import fitz
    except Exception:
        return []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = []
    for i in range(min(len(doc), max_pages)):
        pix = doc[i].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        out.append(pix.tobytes("png"))
    return out


def pdf_first_page_png(pdf_bytes):
    """互換用：1ページ目だけ。"""
    pages = pdf_pages_png(pdf_bytes, max_pages=1)
    return pages[0] if pages else None


def extract_order_by_ai(pngs, api_key, products=None):
    """Claude画像認識で、図面/注文書の全ページから『文字情報』を読み取り、
    商品マスタのどの商品に該当するかを推測して返す。失敗時は例外。"""
    from anthropic import Anthropic
    if isinstance(pngs, (bytes, bytearray)):
        pngs = [pngs]
    client = Anthropic(api_key=api_key)

    prod_lines = ""
    for p in (products or []):
        prod_lines += (f'- 図番:{p.get("zuban","")} ／ 品名:{p.get("name","")} '
                       f'／ 方式:{p.get("method","")} ／ ラベル仕様:{p.get("spec",{}).get("material_note","")}\n')

    prompt = (
        f"これは印刷会社（シール堂印刷）向けの『図面』または『注文書』PDFの全ページ画像です（全{len(pngs)}ページ）。\n"
        "■ やること1：図形は無視してよいので、全ページの**文字情報を正確に読み取る**。特に注記(NOTE/注記)の"
        "『ラベル仕様』（材質＝下地/ラミネート、文字色、下地色、字体、文字高さ・太さ 等）と、"
        "図番(DRAWING NO.)・品名(TITLE)を読むこと。\n"
        "■ やること2：下の【登録済み商品マスタ】の中から、この図面が該当すると思われる商品を推測して1つ選ぶ。"
        "図番が一致すればそれを最優先。無ければ品名やラベル仕様（材質・色）の一致度から最も近いものを推測する。\n"
        "【登録済み商品マスタ】\n" + (prod_lines or "（登録なし）\n") +
        "次のJSONだけを返す：\n"
        '{"zuban":"読み取った図番","name":"品名/図面名","material":"ラベル材質(読み取った文字)","colors":色数(黒1色なら1),'
        '"width":ラベル幅mm(あれば),"height":ラベル高さmm(あれば),"qty":数量(あれば整数),'
        '"matched_zuban":"該当すると推測した商品マスタの図番(無ければ空)","matched_name":"その品名",'
        '"confidence":"高/中/低","match_reason":"推測の根拠(短く)"}\n'
        "分からない項目は省略。JSONのみ、説明やコードブロックは不要。")

    content = [{"type": "image",
                "source": {"type": "base64", "media_type": "image/png",
                           "data": base64.b64encode(p).decode()}} for p in pngs]
    content.append({"type": "text", "text": prompt})
    msg = client.messages.create(model=VISION_MODEL, max_tokens=800,
                                 messages=[{"role": "user", "content": content}])
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    import re
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError("画像から情報を取り出せませんでした")
    return json.loads(m.group(0))


def _apply_product(prod, qty):
    """商品マスタの1件＋数量を、見積作成の入力（session_state）へセット。"""
    method = prod.get("method")
    if method:
        st.session_state["rq_method"] = method
    if qty and method in _QTY_KEY:
        try:
            st.session_state[_QTY_KEY[method]] = int(qty)
        except Exception:
            pass
    spec = prod.get("spec", {}) or {}
    for skey, wkey, cast in _SPEC_MAP.get(method, []):
        if skey in spec:
            try:
                st.session_state[wkey] = cast(spec[skey])
            except Exception:
                pass


def render_intake():
    """見積作成の先頭に置く「図面・注文書PDF読み取り」ブロック。"""
    st.session_state.setdefault("pdf_zuban_in", "")
    st.session_state.setdefault("pdf_qty_in", 0)
    with st.expander("📄 図面・注文書PDFを読み取って自動入力（図番照合）", expanded=False):
        st.caption("🔖 PDF読み取り：**全ページ＋該当商品推測版 v3**（この表示が出ていれば最新コードです）")
        up = st.file_uploader("図面・注文書のPDFをアップロード", type=["pdf"], key="pdf_up")
        try:
            api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        except Exception:
            api_key = ""
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

        pages = []
        if up is not None:
            # 新しいファイルがアップされたら、ファイル名から図番を自動セット
            if st.session_state.get("_pdf_last") != up.name:
                st.session_state["_pdf_last"] = up.name
                st.session_state["pdf_zuban_in"] = zuban_from_filename(up.name)
                st.session_state["pdf_qty_in"] = 0
                st.session_state["pdf_pgview"] = 1
            pages = pdf_pages_png(up.getvalue(), zoom=1.4)
            if pages:
                st.caption(f"全 {len(pages)} ページを読み込みました（**全ページが読み取り対象**です）")
                # 全ページをサムネイルで一覧表示
                ncol = 4
                for r in range(0, len(pages), ncol):
                    cols = st.columns(ncol)
                    for j, png in enumerate(pages[r:r + ncol]):
                        with cols[j]:
                            st.image(png, width="stretch")
                            st.caption(f"{r + j + 1} / {len(pages)} ページ")
            if api_key and pages:
                if st.button(f"🤖 AIで全{len(pages)}ページの文字を読み取り、該当商品を推測する",
                             type="primary", key="pdf_ai"):
                    try:
                        ai_pngs = pdf_pages_png(up.getvalue(), zoom=1.6, max_pages=10)
                        data = extract_order_by_ai(ai_pngs, api_key, products=masters.get_products())
                        # 推測した該当商品（matched_zuban）を優先、無ければ読み取った図番
                        z = data.get("matched_zuban") or data.get("zuban")
                        if z:
                            st.session_state["pdf_zuban_in"] = z
                        if data.get("qty"):
                            st.session_state["pdf_qty_in"] = int(data["qty"])
                        st.session_state["pdf_ai_data"] = data
                        st.rerun()
                    except Exception as e:
                        st.warning(f"AI読み取りに失敗（{type(e).__name__}）。図番はファイル名から自動入力されています。")
            elif pages:
                st.caption("💡 図番はファイル名から自動入力しました。**全ページの文字を読み取り該当商品を推測**するには "
                           "ANTHROPIC_API_KEY の設定が必要です（未設定でも図番照合で仕様を呼び出せます）。")

        c1, c2 = st.columns([2, 1])
        c1.text_input("図番", key="pdf_zuban_in")
        c2.number_input("数量", min_value=0, step=1, key="pdf_qty_in")
        zuban = st.session_state["pdf_zuban_in"]
        qty = st.session_state["pdf_qty_in"]

        d = st.session_state.get("pdf_ai_data")
        if d:
            st.success("🤖 AIが読み取った文字情報："
                       + "／".join(f"{lab}={d[k]}" for k, lab in
                                  [("zuban", "図番"), ("name", "品名"), ("material", "材質"),
                                   ("colors", "色数"), ("width", "幅mm"), ("height", "高mm"), ("qty", "数量")]
                                  if d.get(k)))
            if d.get("matched_zuban") or d.get("matched_name"):
                st.info(f"🔎 該当商品の推測：**{d.get('matched_name','')}**"
                        f"（図番 {d.get('matched_zuban','')}／確度 {d.get('confidence','')}）\n\n"
                        f"根拠：{d.get('match_reason','')}")

        if zuban:
            prod = masters.find_product_by_zuban(zuban)
            if prod:
                st.info(f"✅ 図番照合一致：**{prod['name']}**（{prod.get('customer','')}／方式：{prod.get('method','?')}）\n\n"
                        f"標準仕様：{prod.get('spec', {}).get('material_note', '')}")
                if st.button("この内容で見積入力に反映", type="primary", key="pdf_apply"):
                    _apply_product(prod, qty)
                    st.success("見積作成に反映しました。下の入力（寸法など）をご確認ください。")
                    st.rerun()
            else:
                st.warning(f"図番『{zuban}』は商品マスタに未登録です。"
                           "商品マスタに登録すると、次回から仕様を自動で呼び出せます。")
