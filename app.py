# -*- coding: utf-8 -*-
"""
シール堂印刷 見積り作成ツール（社員用 / Streamlit）

ダッシュボード型UI（B案）。左サイドバー・上部バー・入力カード・右のお見積りプレビュー。
機能は従来どおり：貼り付け読み取り／各項目入力／明細の積み上げ／値引き・原価・粗利／Excel見積書。

・料金と原価の数値はすべて「仮」。実データが来たら pricing.py を差し替えるだけ。
・貼り付け読み取りは ANTHROPIC_API_KEY があればAI、無ければパターン照合。
・合言葉ロック：.streamlit/secrets.toml に STAFF_PASSWORD を書くと入口で認証。空なら誰でも入れる。
"""

import os
import sys
from datetime import date, datetime

# 公開サーバー(Linux)の文字コードがasciiでも日本語ログで落ちないようUTF-8に固定
for _stream_name in ("stdout", "stderr"):
    try:
        getattr(sys, _stream_name).reconfigure(encoding="utf-8")
    except Exception:
        pass

import streamlit as st

import pricing
import intake_parse
import real_quote
import masters_ui
import store
from quote_excel import build_quote_excel, ISSUER

st.set_page_config(page_title="シール堂印刷 見積り作成ツール", page_icon="🏷️", layout="wide")

# ロゴ（assets/logo.png があれば使う）
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
HAS_LOGO = os.path.exists(LOGO_PATH)
if HAS_LOGO:
    try:
        st.logo(LOGO_PATH)
    except Exception:
        pass


def get_api_key():
    """ANTHROPIC_API_KEY を Secrets → 環境変数 の順で探す。無ければ空文字。"""
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        key = ""
    return key or os.environ.get("ANTHROPIC_API_KEY", "")


# ===== 合言葉ゲート（任意） =====
def check_password():
    expected = ""
    try:
        expected = st.secrets.get("STAFF_PASSWORD", "")
    except Exception:
        expected = os.environ.get("STAFF_PASSWORD", "")
    if not expected:
        return True
    if st.session_state.get("_authed"):
        return True
    st.title("🏷️ シール堂印刷 見積り作成ツール")
    pw = st.text_input("合言葉を入力してください（社員用）", type="password")
    if st.button("入る"):
        if pw == expected:
            st.session_state["_authed"] = True
            st.rerun()
        else:
            st.error("合言葉が違います。")
    return False


if not check_password():
    st.stop()


# ===== 見た目（CSS） =====
st.markdown("""
<style>
:root{--bg:#EDF0F4;--card:#fff;--line:#E5E8EC;--navy:#22303F;--btn:#1F2C3A;
--green:#B7C77E;--greenSoft:#EDF1DC;--text:#1E2A36;--muted:#6B7A88;}
.stApp{background:var(--bg);}
header[data-testid="stHeader"]{display:none;}
#MainMenu,footer{visibility:hidden;}
.block-container{padding-top:1.1rem;padding-bottom:2rem;max-width:1440px;}
h1,h2,h3,h4{color:var(--text);}
/* サイドバー */
[data-testid="stSidebar"]{background:var(--navy);}
[data-testid="stSidebar"] *{color:#C7D0D9;}
[data-testid="stSidebar"] .stButton>button{width:100%;text-align:left;justify-content:flex-start;
background:transparent;border:none;color:#C7D0D9;font-weight:500;padding:.5rem .6rem;border-radius:8px;}
[data-testid="stSidebar"] .stButton>button:hover{background:rgba(255,255,255,.06);color:#fff;}
[data-testid="stSidebar"] .stButton>button[kind="primary"]{background:rgba(183,199,126,.16);
color:#EDF1DC;border-left:3px solid var(--green);}
/* カード */
[data-testid="stVerticalBlockBorderWrapper"]{background:var(--card);border:1px solid var(--line);
border-radius:12px;}
.st-key-topbar{background:#fff;border:1px solid var(--line);border-radius:12px;padding:.35rem .8rem;margin-bottom:1rem;}
.st-key-topbar [data-testid="stVerticalBlockBorderWrapper"]{border:none;background:transparent;}
/* ボタン（濃紺プライマリ／ダウンロード） */
.stButton>button[kind="primary"],[data-testid="stDownloadButton"] button{background:var(--btn);
border:1px solid var(--btn);color:#fff;border-radius:8px;font-weight:600;}
.stButton>button[kind="primary"]:hover,[data-testid="stDownloadButton"] button:hover{background:#2b3b4d;color:#fff;}
[data-testid="stDownloadButton"] button{width:100%;}
/* セグメント（色味・セットアップ）選択中を緑に */
[data-testid="stSegmentedControl"] button[aria-checked="true"]{background:var(--greenSoft)!important;
border-color:var(--green)!important;color:#54632c!important;}
/* プレビュー内の見出し等 */
.previewNum{font-size:2rem;font-weight:800;color:var(--text);line-height:1.1;}
.badge{display:inline-block;background:#EEF1F4;color:#6B7A88;border:1px solid var(--line);
border-radius:999px;padding:1px 10px;font-size:.72rem;font-weight:600;}
.kv{display:flex;justify-content:space-between;align-items:baseline;padding:2px 0;color:var(--text);}
.kv .k{color:var(--muted);font-size:.86rem;}
.kv .v{font-weight:600;}
.brandttl{font-weight:700;color:#EAEFF4;font-size:1.02rem;line-height:1.15;}
.brandsub{color:#8FA0AE;font-size:.66rem;letter-spacing:.08em;}
/* 端末がダークモードでも入力欄が黒くならないよう固定（保険） */
.stApp [data-testid="stTextInput"] input,.stApp [data-testid="stNumberInput"] input,
.stApp [data-testid="stTextArea"] textarea,.stApp [data-baseweb="select"]>div,
.stApp [data-baseweb="input"]{background:#fff!important;color:#1E2A36!important;}
.stApp [data-baseweb="select"] *{color:#1E2A36!important;}
.stApp [data-testid="stWidgetLabel"] p,.stApp [data-testid="stWidgetLabel"] label{color:#3A4756!important;}
.stApp [data-testid="stMetricValue"],.stApp [data-testid="stMetricLabel"]{color:#1E2A36!important;}
/* サイドバーは濃紺のまま（上の白指定を打ち消す） */
[data-testid="stSidebar"] *{color:#C7D0D9!important;}
[data-testid="stSidebar"] .stButton>button[kind="primary"]{color:#EDF1DC!important;}
/* --- 文字コントラストを常に確保（端末がダークモードでも本文は濃色に固定） --- */
.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp h5,.stApp h6{color:#1E2A36!important;}
.stApp label{color:#33404D!important;}
.stApp [data-testid="stMarkdownContainer"] p,.stApp [data-testid="stMarkdownContainer"] li,
.stApp [data-testid="stMarkdownContainer"] strong{color:#33404D!important;}
.stApp [data-baseweb="tab"]{color:#5B6B7B!important;}
.stApp [data-baseweb="tab"][aria-selected="true"]{color:#1E2A36!important;}
.stApp [data-testid="stCaptionContainer"],.stApp [data-testid="stCaptionContainer"] *{color:#6B7A88!important;}
.stApp [data-testid="stExpander"] summary,.stApp [data-testid="stExpander"] summary *{color:#33404D!important;}
.stApp [data-testid="stCheckbox"] label,.stApp [data-testid="stCheckbox"] label *{color:#33404D!important;}
.stApp [data-testid="stRadio"] label,.stApp [data-testid="stRadio"] label *{color:#33404D!important;}
/* サイドバーの色指定を再優先（本文用の濃色指定を打ち消す） */
[data-testid="stSidebar"] .brandttl{color:#EAEFF4!important;}
[data-testid="stSidebar"] .brandsub{color:#8FA0AE!important;}
/* 色味・セットアップ等のトグル：選択中は必ず緑（標準のピンクを打ち消す） */
.stApp [data-testid="stBaseButton-segmented_controlActive"]{
background:#EDF1DC!important;border-color:#B7C77E!important;color:#54632c!important;}
/* データフレーム（表）も白背景・濃字に固定 */
.stApp [data-testid="stDataFrame"]{background:#fff!important;}
/* ===== ボタン・サイドバーの文字色を明示（本文の濃色指定がボタン文字に効くのを打ち消す） ===== */
/* サイドバー ナビ：白文字（アクティブは緑の左線＋白文字） */
[data-testid="stSidebar"] .stButton>button,[data-testid="stSidebar"] .stButton>button *{
color:#FFFFFF!important;font-weight:600!important;}
[data-testid="stSidebar"] .stButton>button[kind="primary"]{background:rgba(183,199,126,.20)!important;
border-left:3px solid #B7C77E!important;}
/* プライマリ／ダウンロード：濃紺背景に白文字 */
.stApp .stButton>button[kind="primary"],.stApp .stButton>button[kind="primary"] *,
.stApp [data-testid="stDownloadButton"] button,.stApp [data-testid="stDownloadButton"] button *{
color:#FFFFFF!important;}
/* セカンダリ（ページ内の枠線ボタン）：白背景に濃字（グレー文字を廃止） */
.stApp [data-testid="stMain"] .stButton>button[kind="secondary"]{
background:#FFFFFF!important;border:1px solid #C4CBD4!important;}
.stApp [data-testid="stMain"] .stButton>button[kind="secondary"],
.stApp [data-testid="stMain"] .stButton>button[kind="secondary"] *{color:#1E2A36!important;font-weight:600!important;}
.stApp [data-testid="stMain"] .stButton>button[kind="secondary"]:hover{
background:#EEF1F4!important;border-color:#9AA6B2!important;}
</style>
""", unsafe_allow_html=True)


# ===== セッション初期化 =====
st.session_state.setdefault("items", [])
st.session_state.setdefault("quote_seq", 1)
st.session_state.setdefault("page", "見積作成")

_DEFAULTS = {
    "f_product": pricing.PRODUCT_CHOICES[0], "f_name": "",
    "f_shape": pricing.SHAPE_CHOICES[0], "f_width": 50, "f_height": 30,
    "f_material": pricing.MATERIAL_CHOICES[0], "f_cutform": pricing.CUT_FORM_CHOICES[0],
    "f_finishes": [], "f_color_type": pricing.COLOR_TYPES[0], "f_spot_colors": 1,
    "f_tape_w": 15, "f_tape_l": 5.0, "f_setup": pricing.SETUP_CHOICES[0],
    "f_qty": 1000, "f_lead": pricing.LEAD_TIME_CHOICES[0],
}
for _k, _v in _DEFAULTS.items():
    st.session_state.setdefault(_k, _v)


def yen(v):
    return f"¥{v:,.0f}"


def apply_parsed(fields):
    """読み取り結果を入力欄（session_state）へ反映。値は正式な選択肢に正規化済み前提。"""
    mp = {"product": "f_product", "name": "f_name", "width_mm": "f_width",
          "height_mm": "f_height", "material": "f_material", "cut_form": "f_cutform",
          "finishes": "f_finishes", "color_type": "f_color_type", "spot_colors": "f_spot_colors",
          "tape_width_mm": "f_tape_w", "tape_length_m": "f_tape_l", "setup": "f_setup",
          "qty": "f_qty", "lead_time": "f_lead"}
    for src, key in mp.items():
        if src not in fields:
            continue
        val = fields[src]
        if key in ("f_width", "f_height", "f_tape_w"):
            val = max(0, min(2000, int(val)))
        elif key == "f_qty":
            val = max(0, int(val))
        elif key == "f_spot_colors":
            val = max(1, min(6, int(val)))
        st.session_state[key] = val


def new_quote():
    st.session_state["items"] = []
    st.session_state["quote_seq"] += 1


# =====================================================================
# サイドバー（ブランド＋ナビ）
# =====================================================================
NAV = [("ダッシュボード", "📊"), ("見積作成", "📝"), ("見積履歴", "🕘"),
       ("テンプレート", "📄"), ("商品マスタ", "📦"), ("単価マスタ", "🏷️"), ("設定", "⚙️")]

with st.sidebar:
    b1, b2 = st.columns([1, 3], vertical_alignment="center")
    with b1:
        if HAS_LOGO:
            st.image(LOGO_PATH, width=44)
        else:
            st.markdown("### 🏷️")
    with b2:
        st.markdown('<div class="brandttl">シール堂印刷</div>'
                    '<div class="brandsub">SEAL-DO SINCE 1933</div>', unsafe_allow_html=True)
    st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)
    for label, icon in NAV:
        is_active = st.session_state["page"] == label
        if st.button(f"{icon}　{label}", key=f"nav_{label}",
                     type="primary" if is_active else "secondary"):
            st.session_state["page"] = label
            st.rerun()


# =====================================================================
# 上部バー
# =====================================================================
with st.container(key="topbar"):
    t1, t2, t3, t4 = st.columns([6, 1.4, 0.5, 1.2], vertical_alignment="center")
    with t1:
        st.markdown(f"**{st.session_state['page']}**"
                    "　<span style='color:#6B7A88;font-size:.8rem'>シール・ラベル・ステッカー見積り</span>",
                    unsafe_allow_html=True)
    with t2:
        if st.button("＋ 新規作成", key="btn_new", type="primary"):
            new_quote()
            st.rerun()
    with t3:
        st.markdown("<div style='text-align:center;font-size:1.1rem'>🔔</div>", unsafe_allow_html=True)
    with t4:
        st.markdown("<div style='text-align:right;color:#3B4552;font-weight:600'>👤 深見 ▾</div>",
                    unsafe_allow_html=True)


# =====================================================================
# ページ本体
# =====================================================================
def preparing_banner(title, desc):
    """各ページ共通の見出し（準備中バッジ＋説明）。中身はダミーの画面イメージ。"""
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin:.2rem 0 .1rem">'
        f'<h3 style="margin:0">{title}</h3>'
        f'<span class="badge" style="background:#FFF3D6;color:#8A6D1B;border-color:#F0DFB0">準備中（画面イメージ）</span>'
        f'</div><div style="color:#6B7A88;font-size:.85rem;margin-bottom:.8rem">{desc}</div>',
        unsafe_allow_html=True)


def render_builder():
    tab_make, tab_hist = st.tabs(["見積作成", "見積履歴"])

    with tab_hist:
        st.info("見積履歴は準備中です（保存機能は今後追加予定）。")

    with tab_make:
        left, right = st.columns([2, 1.05], gap="large")

        # ---------------- 左：入力 ----------------
        with left:
            # 貼り付け読み取り
            with st.expander("📋 フォーム・メールの問い合わせ内容を貼り付けて自動反映", expanded=False):
                st.text_area("問い合わせ本文をそのまま貼り付け", key="f_paste", height=140,
                             placeholder="例）\n数量：1000〜2000枚\nシールサイズ：50㎜×30㎜\n"
                                         "希望する材質：透明PET\n色味：フルカラー\n納期：お急ぎ")
                api_key = get_api_key()
                cap = "AI読み取り（APIキー検出）" if api_key else "パターン照合（APIキー未設定）"
                st.caption(f"現在の読み取り方式：**{cap}**　※キーを設定すると自動でAIに切り替わります")
                if st.button("読み取って各項目に反映", type="primary"):
                    fields, method, notes = intake_parse.parse_inquiry(
                        st.session_state.get("f_paste", ""), api_key)
                    apply_parsed(fields)
                    st.session_state["_parse_method"] = method
                    st.session_state["_parse_notes"] = notes
                    st.session_state["_parse_count"] = len(fields)
                    st.rerun()
            if st.session_state.get("_parse_method"):
                st.info(f"読み取り：{st.session_state['_parse_method']}／"
                        f"{st.session_state.get('_parse_count', 0)}項目を反映しました。")
                for n in st.session_state.get("_parse_notes", []):
                    st.caption("・" + n)

            # 品目を入力（モックと同じ行構成：品名/形状/幅/高さ → 材質/仕上げ/色味 → 加工/セットアップ/数量）
            with st.container(border=True):
                st.markdown("#### 品目を入力")

                row1 = st.columns(4)
                product = row1[0].selectbox("品名（種類）", pricing.PRODUCT_CHOICES, key="f_product")
                kind = pricing.product_kind(product)
                if kind == "tape":
                    shape = pricing.SHAPE_CHOICES[0]
                    row1[1].number_input("テープ幅 (mm)", min_value=0, max_value=2000, step=1, key="f_tape_w")
                    row1[2].number_input("テープ長さ (m)", min_value=0.0, max_value=1000.0, step=1.0, key="f_tape_l")
                else:
                    shape = row1[1].selectbox("形状", pricing.SHAPE_CHOICES, key="f_shape")
                    row1[2].number_input("幅 (mm)" + ("／長径" if shape == "円・楕円" else ""),
                                         min_value=0, max_value=2000, step=1, key="f_width")
                    row1[3].number_input("高さ (mm)" + ("／短径" if shape == "円・楕円" else ""),
                                         min_value=0, max_value=2000, step=1, key="f_height")
                if product == "その他（自由入力）":
                    st.text_input("品名（自由入力）", key="f_name",
                                  placeholder="例）商品ラベル A（化粧品用）")

                row2 = st.columns(3)
                material = row2[0].selectbox("希望する材質", pricing.MATERIAL_CHOICES, key="f_material")
                if kind == "tape":
                    cut_form = pricing.CUT_FORM_CHOICES[0]
                    row2[1].empty()
                else:
                    cut_form = row2[1].selectbox("仕上げ形態", pricing.CUT_FORM_CHOICES, key="f_cutform")
                with row2[2]:
                    st.caption("色味")
                    color_type = st.segmented_control("色味", pricing.COLOR_TYPES, key="f_color_type",
                                                      label_visibility="collapsed") or "フルカラー"
                    if color_type == "単色":
                        st.number_input("色数（単色）", min_value=1, max_value=6, step=1, key="f_spot_colors")

                row3 = st.columns(3)
                row3[0].multiselect("加工オプション", pricing.FINISH_CHOICES, key="f_finishes")
                with row3[1]:
                    st.caption("セットアップ（内職）")
                    setup = st.segmented_control(
                        "セットアップ", pricing.SETUP_CHOICES, key="f_setup",
                        format_func=lambda x: "しない" if x == pricing.SETUP_CHOICES[0] else "内職する",
                        label_visibility="collapsed") or pricing.SETUP_CHOICES[0]
                row3[2].number_input("数量（枚）", min_value=0, max_value=10_000_000, step=100, key="f_qty")

                finishes = st.session_state["f_finishes"]
                add = st.button("＋ この品目を明細に追加", type="primary", width="stretch")

            # 見積書の情報
            with st.container(border=True):
                st.markdown("#### 見積書の情報")
                i1, i2, i3, i4 = st.columns(4)
                customer = i1.text_input("宛先", placeholder="株式会社サンプル", key="q_customer")
                subject = i2.text_input("件名", placeholder="商品ラベル印刷 御見積", key="q_subject")
                staff = i3.text_input("担当者", placeholder="深見", key="q_staff")
                valid_days = i4.number_input("有効期限(日数)", min_value=7, max_value=180, value=30, step=1)

                d1, d2, d3 = st.columns([1, 1, 2])
                discount_type = d1.selectbox("値引き（社内調整）", ["なし", "金額（円）", "割合（％）"])
                if discount_type == "割合（％）":
                    discount_value = d2.number_input("値引き率(%)", min_value=0.0, max_value=100.0,
                                                     value=0.0, step=1.0)
                elif discount_type == "金額（円）":
                    discount_value = d2.number_input("値引き額(円)", min_value=0, value=0, step=500)
                else:
                    d2.empty()
                    discount_value = 0
                remarks = d3.text_input("備考（見積書に載る）", placeholder="色校正1回込み／送料別途 など",
                                        key="q_remarks")

            # 納期・その他（オプション）
            with st.expander("納期・その他（オプション）", expanded=False):
                st.radio("納期", pricing.LEAD_TIME_CHOICES, horizontal=True, key="f_lead")

            # 現在の入力から見積り計算
            spec = {
                "product": product, "name": st.session_state.get("f_name", ""),
                "shape": shape, "width_mm": st.session_state["f_width"],
                "height_mm": st.session_state["f_height"], "material": material,
                "cut_form": cut_form, "finishes": finishes,
                "color_type": color_type, "spot_colors": st.session_state["f_spot_colors"],
                "setup": setup, "tape_width_mm": st.session_state["f_tape_w"],
                "tape_length_m": st.session_state["f_tape_l"],
                "qty": st.session_state["f_qty"], "lead_time": st.session_state["f_lead"],
            }
            result = pricing.estimate(spec)

            if add:
                if result["valid"]:
                    st.session_state["items"].append(result)
                    st.toast(f"明細に追加：{result['spec_text']}（{yen(result['total'])} 税込）")
                    st.rerun()
                else:
                    st.warning(result.get("message", "入力を確認してください。"))

            # 明細（積み上げ）
            items = st.session_state["items"]
            with st.container(border=True):
                st.markdown("#### 明細")
                if not items:
                    st.caption("まだ明細がありません。上の「＋ この品目を明細に追加」で品目を追加できます。"
                               "（1品目だけなら、追加せず右の「見積書を作成」でもそのまま出力できます）")
                else:
                    rows = [{
                        "No": i + 1, "品名": it.get("name") or f"シール・ラベル {i+1}",
                        "仕様": it["spec_text"], "数量": f"{it['qty']:,}枚",
                        "単価": f"¥{it['unit_price']:,.2f}", "金額(税抜)": it["subtotal"],
                        "原価": it["cost"], "粗利": it["profit"],
                    } for i, it in enumerate(items)]
                    st.dataframe(rows, width="stretch", hide_index=True, column_config={
                        "金額(税抜)": st.column_config.NumberColumn(format="¥%d"),
                        "原価": st.column_config.NumberColumn(format="¥%d"),
                        "粗利": st.column_config.NumberColumn(format="¥%d"),
                    })
                    dc = st.columns(min(len(items), 6))
                    for i in range(len(items)):
                        if dc[i % 6].button(f"No.{i+1} 削除", key=f"del_{i}"):
                            st.session_state["items"].pop(i)
                            st.rerun()

        # ---------------- 右：お見積りプレビュー ----------------
        with right:
            items = st.session_state["items"]
            items_for_total = items if items else ([result] if result["valid"] else [])
            totals = (pricing.apply_discount(items_for_total, discount_type, discount_value)
                      if items_for_total else None)

            with st.container(border=True, key="previewcard"):
                st.markdown('<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">'
                            '<h4 style="margin:0;white-space:nowrap">お見積りプレビュー</h4>'
                            '<span class="badge">下書き</span></div>', unsafe_allow_html=True)
                st.markdown("<div style='height:.4rem'></div>", unsafe_allow_html=True)

                cur_qty = f"{result['qty']:,}" if result["valid"] else "—"
                cur_unit = f"¥{result['unit_price']:,.2f}" if result["valid"] else "—"
                st.markdown(f'<div class="kv"><span class="k">数量（枚）</span><span class="v">{cur_qty}</span></div>'
                            f'<div class="kv"><span class="k">単価（税抜）</span><span class="v">{cur_unit}</span></div>',
                            unsafe_allow_html=True)
                st.divider()

                if totals:
                    disc = ("－" + yen(totals["discount"])) if totals["discount"] else "¥0"
                    st.markdown(
                        f'<div class="kv"><span class="k">小計</span><span class="v">{yen(totals["items_subtotal"])}</span></div>'
                        f'<div class="kv"><span class="k">値引き</span><span class="v">{disc}</span></div>'
                        f'<div class="kv"><span class="k">消費税(10%)</span><span class="v">{yen(totals["tax"])}</span></div>',
                        unsafe_allow_html=True)
                    st.markdown("<div style='height:.3rem'></div>", unsafe_allow_html=True)
                    st.markdown('<div class="kv"><span class="k">合計金額（税込）</span></div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="previewNum">{yen(totals["total"])}</div>', unsafe_allow_html=True)
                    if totals["below_cost"]:
                        st.error("⚠ 原価割れ（赤字）です。値引きを見直してください。")
                    elif totals["profit_rate"] < 0.15:
                        st.warning("粗利率が15%未満です。")
                else:
                    st.caption("サイズと数量を入力すると金額が表示されます。")

                st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)
                inc_profit = st.checkbox("原価・粗利も載せる（社内用）", value=False)

                # 「見積書を作成」＝Excel見積書のダウンロード
                if items_for_total:
                    quote_no = f"SD-{date.today().strftime('%Y%m%d')}-{st.session_state['quote_seq']:03d}"
                    meta = {"quote_no": quote_no, "issue_date": date.today(), "valid_days": valid_days,
                            "customer": customer, "subject": subject, "staff": staff,
                            "remarks": remarks, "show_profit": inc_profit}
                    xlsx = build_quote_excel(items_for_total, totals, meta)
                    fname = f"見積書_{customer or 'お客様'}_{quote_no}.xlsx"
                    st.download_button("📄 見積書を作成（Excel）", data=xlsx, file_name=fname,
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       type="primary", width="stretch")
                else:
                    st.button("📄 見積書を作成（Excel）", disabled=True, width="stretch")

                if st.button("PDF出力", width="stretch", key="btn_pdf"):
                    st.info("PDF出力は準備中です。現在はExcel見積書をご利用ください。")

                # 社内用：原価・粗利
                if totals:
                    with st.expander("社内用：原価・粗利"):
                        st.markdown(
                            f'<div class="kv"><span class="k">原価合計</span><span class="v">{yen(totals["cost"])}</span></div>'
                            f'<div class="kv"><span class="k">粗利（値引後）</span><span class="v">{yen(totals["profit"])}</span></div>'
                            f'<div class="kv"><span class="k">粗利率</span><span class="v">{totals["profit_rate"]*100:.1f}%</span></div>',
                            unsafe_allow_html=True)
                        if result["valid"]:
                            with st.popover("入力中の品目の内訳"):
                                for lb, dt, am in result["breakdown"]:
                                    st.write(f"- **{lb}**：{dt}"
                                             + (f" … {am:+,}" if isinstance(am, (int, float)) else ""))

                st.markdown(
                    f'<div style="color:#8FA0AE;font-size:.72rem;margin-top:.6rem">'
                    f'最終更新：{datetime.now().strftime("%Y/%m/%d %H:%M")}</div>', unsafe_allow_html=True)


def _dot(status):
    return {"受注": "🟢 受注", "送付済": "🔵 送付済", "下書き": "⚪ 下書き", "失注": "🔴 失注"}.get(status, status)


def render_dashboard():
    st.markdown("### ダッシュボード")
    hist = store.get_history()
    if not hist:
        st.info("まだ見積データがありません。見積作成で「💾 この見積を履歴に保存」を押すと、ここに集計されます。")
        return
    total_sum = sum(h.get("total", 0) for h in hist)
    cnt = len(hist)
    this_month = datetime.now().strftime("%Y/%m")
    month_cnt = sum(1 for h in hist if h.get("date", "")[:7] == this_month)
    month_sum = sum(h.get("total", 0) for h in hist if h.get("date", "")[:7] == this_month)
    avg = total_sum / cnt if cnt else 0
    for col, (lab, val) in zip(st.columns(4), [
            ("見積件数（累計）", f"{cnt} 件"), ("今月の件数", f"{month_cnt} 件"),
            ("今月の金額（税込）", yen(month_sum)), ("平均金額（税込）", yen(avg))]):
        with col:
            with st.container(border=True):
                st.metric(lab, val)

    from collections import Counter
    bym = Counter(h.get("method", "?") for h in hist)
    bymonth = {}
    for h in hist:
        m = h.get("date", "")[:7]
        if m:
            bymonth[m] = bymonth.get(m, 0) + h.get("total", 0)
    c1, c2 = st.columns([2, 1], gap="large")
    with c1:
        with st.container(border=True):
            st.markdown("#### 月別 見積金額")
            months = sorted(bymonth)[-6:]
            if months:
                st.bar_chart({"月": months, "金額": [bymonth[m] for m in months]},
                             x="月", y="金額", color="#B7C77E", height=240)
    with c2:
        with st.container(border=True):
            st.markdown("#### 方式別 件数")
            st.bar_chart({"方式": list(bym.keys()), "件数": list(bym.values())},
                         x="方式", y="件数", color="#22303F", height=240, horizontal=True)

    with st.container(border=True):
        st.markdown("#### 直近の見積")
        rows = [{"見積番号": h.get("quote_no", ""), "日付": h.get("date", ""), "宛先": h.get("customer", ""),
                 "品名": h.get("name", ""), "方式": h.get("method", ""), "金額(税込)": h.get("total", 0),
                 "状態": _dot(h.get("status", ""))} for h in hist[:10]]
        st.dataframe(rows, hide_index=True, width="stretch",
                     column_config={"金額(税込)": st.column_config.NumberColumn(format="¥%d")})


def render_history():
    st.markdown("### 見積履歴")
    hist = store.get_history()
    if not hist:
        st.info("まだ履歴がありません。見積作成で「💾 この見積を履歴に保存」を押すと記録されます。")
        return
    q = st.text_input("検索（宛先・品名・見積番号・方式）", key="hist_q")
    rows = []
    for h in hist:
        blob = f"{h.get('quote_no','')} {h.get('customer','')} {h.get('name','')} {h.get('method','')}"
        if q and q not in blob:
            continue
        rows.append({"見積番号": h.get("quote_no", ""), "日付": h.get("date", ""), "宛先": h.get("customer", ""),
                     "品名": h.get("name", ""), "方式": h.get("method", ""), "数量": h.get("qty", 0),
                     "単価": h.get("unit", 0), "金額(税込)": h.get("total", 0), "状態": _dot(h.get("status", ""))})
    with st.container(border=True):
        st.dataframe(rows, hide_index=True, width="stretch", column_config={
            "金額(税込)": st.column_config.NumberColumn(format="¥%d"),
            "単価": st.column_config.NumberColumn(format="¥%.2f"),
            "数量": st.column_config.NumberColumn(format="%d")})
        st.caption(f"表示 {len(rows)} 件 ／ 全 {len(hist)} 件")
        if st.button("履歴をすべて削除"):
            store.clear_history()
            st.rerun()


def render_templates():
    st.markdown("### テンプレート")
    st.markdown("見積作成で保存した**入力プリセット**の一覧です。「この内容で作成」を押すと、"
                "その内容で見積作成に読み込みます。")
    ts = store.get_templates()
    if not ts:
        st.info("まだテンプレートがありません。見積作成の「⭐ テンプレート」から現在の入力を保存できます。")
        return
    cols = st.columns(3)
    for i, t in enumerate(ts):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"**{t['name']}**")
                st.caption(f"方式：{t.get('method','')}")
                if st.button("この内容で作成", key=f"tpl_use_{i}", type="primary", width="stretch"):
                    real_quote._apply_template(t)
                    st.session_state["page"] = "見積作成"
                    st.rerun()
                if st.button("削除", key=f"tpl_del_{i}"):
                    store.delete_template(t["name"])
                    st.rerun()


def render_products():
    preparing_banner("商品マスタ", "品名・標準仕様を登録して入力を省力化（品名は現在の設定を表示）")
    with st.container(border=True):
        c1, c2, _ = st.columns([1, 1, 3])
        c1.button("＋ 新規登録", disabled=True)
        c2.button("CSVで取り込み", disabled=True)
        std = {
            "商品ラベル": ("四角 50×30mm", "上質紙", "—"),
            "化粧品・美容ラベル": ("角丸 40×60mm", "透明PET", "ラミネート(グロス)"),
            "食品表示ラベル": ("四角 50×30mm", "上質紙", "—"),
            "ステッカー（一般）": ("型抜き 70×70mm", "塩ビ", "UVニス"),
            "封かん・封緘シール": ("円 φ30mm", "コート紙", "—"),
            "ノベルティシール": ("円 φ50mm", "合成紙ユポ", "—"),
            "バーコード・管理ラベル": ("四角 40×20mm", "上質紙", "強粘着"),
            "マスキングテープ": ("テープ 15mm×5m", "和紙", "—"),
            "オリジナル紙テープ": ("テープ 20mm×10m", "上質紙", "—"),
        }
        rows = []
        for name, kind in pricing.PRODUCTS.items():
            if name == "その他（自由入力）":
                continue
            size, mat, fin = std.get(name, ("—", "—", "—"))
            rows.append({"品名": name, "種類": "テープ" if kind == "tape" else "シール・ラベル",
                         "標準サイズ": size, "標準材質": mat, "標準加工": fin})
        st.dataframe(rows, hide_index=True, width="stretch")
        st.caption("※ ここで登録した品名が、見積作成の「品名（種類）」プルダウンに反映される想定です。")


def render_pricing_master():
    preparing_banner("単価マスタ",
                     "見積計算の単価・係数を管理する画面。実データが決まったらここを更新（＝pricing.py 差し替え）。現在は仮の値を表示")
    with st.container(border=True):
        st.markdown("#### 基本単価マトリクス（円 / 1枚）")
        qlabels = [b[0] for b in pricing.QTY_BANDS]
        mrows = []
        for area_label, prices in pricing.BASE_UNIT_PRICE.items():
            row = {"面積帯": area_label}
            row.update({ql: p for ql, p in zip(qlabels, prices)})
            mrows.append(row)
        st.dataframe(mrows, hide_index=True, width="stretch")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        with st.container(border=True):
            st.markdown("#### 素材係数")
            st.dataframe([{"素材": k, "係数": v} for k, v in pricing.MATERIALS.items()],
                         hide_index=True, width="stretch")
    with c2:
        with st.container(border=True):
            st.markdown("#### 加工オプション加算（円/枚）")
            st.dataframe([{"加工": k, "加算": v} for k, v in pricing.FINISH_OPTIONS.items()],
                         hide_index=True, width="stretch")

    with st.container(border=True):
        st.markdown("#### そのほかの基準値")
        m = st.columns(4)
        m[0].metric("最低料金（税抜）", f"¥{pricing.MIN_ORDER_PRICE:,}")
        m[1].metric("抜き型代", f"¥{pricing.DIE_CUT_FEE:,}")
        m[2].metric("特急割増", f"×{pricing.LEAD_TIMES['お急ぎ（約3〜4営業日）']['surcharge']}")
        m[3].metric("基準原価率", f"{int(pricing.BASE_COST_RATE*100)}%")
        st.button("この単価表を保存", disabled=True)


def render_settings():
    preparing_banner("設定", "発行元情報・税率・見積番号などの管理（現在の値を表示・編集は準備中）")
    with st.container(border=True):
        st.markdown("#### 発行元情報（見積書に印字）")
        s1, s2 = st.columns(2)
        s1.text_input("会社名", value=ISSUER["company"], disabled=True)
        s2.text_input("電話", value=ISSUER["tel"], disabled=True)
        st.text_input("住所", value=f"{ISSUER['postal']} {ISSUER['address']}", disabled=True)

    with st.container(border=True):
        st.markdown("#### 見積の既定値")
        g1, g2, g3 = st.columns(3)
        g1.text_input("消費税率", value="10 %", disabled=True)
        g2.text_input("有効期限の既定", value="30 日", disabled=True)
        g3.text_input("見積番号の形式", value="SD-YYYYMMDD-連番", disabled=True)

    with st.container(border=True):
        st.markdown("#### セキュリティ・連携")
        c1, c2 = st.columns(2)
        c1.text_input("社員モードの合言葉", value="", type="password",
                      placeholder="未設定（誰でも利用可）", disabled=True)
        has_key = bool(get_api_key())
        c2.text_input("AI読み取り用APIキー", value="設定済み" if has_key else "",
                      placeholder="未設定（パターン照合で動作）", disabled=True)
        st.caption("※ 合言葉とAPIキーは .streamlit/secrets.toml で設定します（この画面からの編集は準備中）。")


# ルーティング
PAGES = {
    "ダッシュボード": render_dashboard,
    "見積作成": real_quote.render,
    "見積履歴": render_history,
    "テンプレート": render_templates,
    "商品マスタ": masters_ui.render_products,
    "単価マスタ": masters_ui.render_rates,
    "設定": render_settings,
}
PAGES.get(st.session_state["page"], real_quote.render)()

st.caption("※ 金額・原価はすべて仮の設定です。実際の単価表・原価が決まったら pricing.py の数値を差し替えてください。")
