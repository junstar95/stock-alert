import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import holidays

# KRX 계정 정보 (Streamlit secrets에서 자동으로 읽음)
os.environ['KRX_ID'] = st.secrets["KRX_ID"]
os.environ['KRX_PW'] = st.secrets["KRX_PW"]

from pykrx import stock

kr_holidays = holidays.KR()

st.set_page_config(page_title="투자경고 해제기준가", layout="wide")
st.title("📊 투자경고 종목 해제 기준가 대시보드")
st.caption(f"기준 일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

@st.cache_data
def load_csv():
    return pd.read_csv("warning_stocks.csv", encoding="utf-8-sig")

@st.cache_data(ttl=86400)
def build_ticker_map():
    today = datetime.now().date()
    while today.weekday() >= 5:
        today -= timedelta(days=1)
    ymd = today.strftime("%Y%m%d")
    name_to_ticker = {}
    for market in ["KOSPI", "KOSDAQ"]:
        try:
            tickers = stock.get_market_ticker_list(ymd, market=market)
            for t in tickers:
                try:
                    name = stock.get_market_ticker_name(t)
                    name_to_ticker[name] = t
                except Exception:
                    continue
        except Exception:
            continue
    return name_to_ticker

def is_trading_day(d):
    return d.weekday() < 5 and d not in kr_holidays

def n_trading_days_back(target_date, n):
    d = target_date - timedelta(days=1)
    count = 0
    while True:
        if is_trading_day(d):
            count += 1
            if count == n:
                return d
        d -= timedelta(days=1)

@st.cache_data(ttl=3600, show_spinner=False)
def calculate_release_info(company_name, release_date_str, t5_mult, t15_mult):
    try:
        ticker_map = build_ticker_map()
        ticker = ticker_map.get(company_name)
        if not ticker:
            return {"_error": f"종목코드 못 찾음: {company_name}"}
        
        release_date = datetime.strptime(release_date_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        t5_date = n_trading_days_back(release_date, 5)
        t15_date = n_trading_days_back(release_date, 15)
        fetch_start = t15_date - timedelta(days=15)
        fetch_end = min(release_date, today)
        
        df_ohlcv = stock.get_market_ohlcv(
            fetch_start.strftime("%Y%m%d"),
            fetch_end.strftime("%Y%m%d"),
            ticker,
        )
        if df_ohlcv.empty:
            return {"_error": f"OHLCV 비어있음: {company_name} ({ticker})"}
        
        t5_ts = pd.Timestamp(t5_date)
        t15_ts = pd.Timestamp(t15_date)
        
        # ★ T-15는 필수 / T-5는 없어도 진행
        if t15_ts not in df_ohlcv.index:
            return {"_error": f"T-15({t15_date}) 데이터 없음: {company_name}"}
        
        t5_close = df_ohlcv.loc[t5_ts, "종가"] if t5_ts in df_ohlcv.index else None
        t15_close = df_ohlcv.loc[t15_ts, "종가"]
        recent = df_ohlcv[df_ohlcv.index >= t15_ts]
        max_close = recent["종가"].max()
        
        # T-5 있으면 3개 조건 모두, 없으면 T-15와 최근15일최고가만으로 계산
        thresholds = [t15_close * t15_mult, max_close]
        if t5_close is not None:
            thresholds.append(t5_close * t5_mult)
        threshold = min(thresholds)
        
        current = df_ohlcv.iloc[-1]["종가"]
        gap = current - threshold
        gap_pct = (gap / current) * 100
        
        return {
            "종목코드": ticker,
            "현재가": int(current),
            "해제기준가": int(threshold),
            "필요하락원": int(gap),
            "필요하락pct": round(gap_pct, 2),
            "T5_없음": t5_close is None,
        }
    except Exception as e:
        return {"_error": f"{company_name}: {type(e).__name__}: {str(e)[:200]}"}

df = load_csv()
df["해제예정일"] = pd.to_datetime(df["해제예정일"]).dt.date

with st.sidebar:
    st.header("🔍 필터")
    today = datetime.now().date()
    only_future = st.checkbox("해제예정일이 오늘 이후만", value=True)
    only_pending = st.checkbox("미해제(필요하락>0)만 표시", value=True)
    multiplier_filter = st.multiselect(
        "T-5 배수 선택",
        options=sorted(df["T5_배수"].unique()),
        default=sorted(df["T5_배수"].unique()),
    )

if only_future:
    df = df[df["해제예정일"] >= today]
df = df[df["T5_배수"].isin(multiplier_filter)]

st.write(f"📋 분석 대상: **{len(df)}개 종목**")

if st.button("🔄 시세 분석 시작", type="primary"):
    with st.spinner("종목 매핑 준비 중..."):
        ticker_map = build_ticker_map()
    
    progress = st.progress(0)
    status = st.empty()
    results = []
    errors = []
    
    for i, row in enumerate(df.itertuples()):
        status.text(f"분석 중: {row.회사명} ({i+1}/{len(df)})")
        info = calculate_release_info(
            row.회사명,
            row.해제예정일.strftime("%Y-%m-%d"),
            row.T5_배수,
            row.T15_배수,
        )
        if info and "_error" not in info:
            results.append({
                "종목코드": info["종목코드"],
                "회사명": row.회사명,
                "해제예정일": row.해제예정일.strftime("%Y-%m-%d"),
                "T-5 배수": "" if info.get("T5_없음") else f"{row.T5_배수:.2f}",
                "T-15 배수": f"{row.T15_배수:.2f}",
                "현재가": info["현재가"],
                "해제기준가": info["해제기준가"],
                "필요하락(원)": info["필요하락원"],
                "필요하락(%)": info["필요하락pct"],
                "비고": "T-5 미반영" if info.get("T5_없음") else "",
            })
        elif info and "_error" in info:
            errors.append(info["_error"])
        progress.progress((i + 1) / len(df))
    
    status.empty()
    progress.empty()
    
    if results:
        all_results_df = pd.DataFrame(results)
        total_success = len(all_results_df)
        already_met = (all_results_df["필요하락(원)"] <= 0).sum()
        pending_count = (all_results_df["필요하락(원)"] > 0).sum()
        avg_drop = (
            all_results_df[all_results_df["필요하락(원)"] > 0]["필요하락(%)"].mean()
            if pending_count > 0 else 0
        )
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("계산 성공", f"{total_success}개")
        col2.metric("이미 기준 충족", f"{already_met}개")
        col3.metric("미해제(주시 필요)", f"{pending_count}개")
        col4.metric("미해제 평균 필요하락", f"{avg_drop:.1f}%")
    
    if errors:
        with st.expander(f"⚠️ 계산 실패한 종목 {len(errors)}개"):
            for e in errors[:20]:
                st.text(e)
    
    if not results:
        st.error("계산된 결과가 없습니다.")
    else:
        result_df = pd.DataFrame(results)
        if only_pending:
            result_df = result_df[result_df["필요하락(원)"] > 0]
        result_df = result_df.sort_values("필요하락(%)", ascending=True)
        
        st.divider()
        st.subheader("📋 종목별 분석 결과 (해제 임박순)")
        
        # ★ 표시용 포맷팅 (콤마, 단위)
        display_df = result_df.copy()
        display_df["현재가"] = display_df["현재가"].apply(lambda x: f"{x:,}원")
        display_df["해제기준가"] = display_df["해제기준가"].apply(lambda x: f"{x:,}원")
        display_df["필요하락(원)"] = display_df["필요하락(원)"].apply(lambda x: f"{x:,}원")
        display_df["필요하락(%)"] = display_df["필요하락(%)"].apply(lambda x: f"{x:.2f}%")
        
        # ★ HTML 테이블 + CSS로 강제 가운데 정렬
        st.markdown("""
        <style>
        .result-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
            margin-top: 8px;
        }
        .result-table th {
            background-color: #f0f2f6;
            text-align: center !important;
            padding: 12px 8px;
            border-bottom: 2px solid #d0d0d0;
            font-weight: 600;
            color: #262730;
        }
        .result-table td {
            text-align: center !important;
            padding: 10px 8px;
            border-bottom: 1px solid #eaeaea;
        }
        .result-table tr:hover {
            background-color: #fafafa;
        }
        </style>
        """, unsafe_allow_html=True)
        
        html_table = display_df.to_html(
            index=False,
            classes="result-table",
            escape=False,
        )
        st.markdown(html_table, unsafe_allow_html=True)
else:
    st.info("👆 위 버튼을 눌러 분석을 시작하세요.")
    st.subheader("📄 CSV 원본 데이터 미리보기")
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ===== 디버그 섹션 (임시) =====
with st.expander("🔧 디버그 정보", expanded=False):
    st.write("**환경 변수 확인**")
    st.write(f"- KRX_ID 설정됨: {bool(os.environ.get('KRX_ID'))}")
    st.write(f"- KRX_PW 설정됨: {bool(os.environ.get('KRX_PW'))}")
    st.write(f"- KRX_ID 길이: {len(os.environ.get('KRX_ID', ''))}")
    
    if st.button("🧪 KRX 연결 테스트"):
        try:
            today = datetime.now().date()
            while today.weekday() >= 5:
                today -= timedelta(days=1)
            ymd = today.strftime("%Y%m%d")
            st.write(f"테스트 날짜: {ymd}")
            
            with st.spinner("KOSPI 종목 가져오는 중..."):
                kospi = stock.get_market_ticker_list(ymd, market="KOSPI")
            st.write(f"✅ KOSPI 종목 수: **{len(kospi)}개**")
            
            with st.spinner("KOSDAQ 종목 가져오는 중..."):
                kosdaq = stock.get_market_ticker_list(ymd, market="KOSDAQ")
            st.write(f"✅ KOSDAQ 종목 수: **{len(kosdaq)}개**")
            
            if kospi:
                name = stock.get_market_ticker_name(kospi[0])
                st.write(f"테스트 - 첫 종목: {kospi[0]} = {name}")
            
            if len(kospi) == 0 and len(kosdaq) == 0:
                st.error("⚠️ KRX가 응답을 안 주거나 빈 데이터를 돌려주고 있음 → KRX 차단 의심")
        except Exception as e:
            st.error(f"❌ 에러: {type(e).__name__}: {e}")