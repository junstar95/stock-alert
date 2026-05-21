import os
# ★ test_krx.py에서 본인 KRX 계정 정보 그대로 복사하세요 ★
os.environ['KRX_ID'] = '95junstar'
os.environ['KRX_PW'] = 'wnstjd1717!'

from pykrx import stock
from datetime import datetime, timedelta
import pandas as pd
import holidays

# 한국 공휴일 캘린더
kr_holidays = holidays.KR()


def is_trading_day(d):
    """주말이나 한국 공휴일이면 거래일 아님"""
    return d.weekday() < 5 and d not in kr_holidays


def trading_day_n_back(target_date, n):
    """target_date 이전 n번째 거래일 (target_date 자체 제외)"""
    d = target_date - timedelta(days=1)
    count = 0
    while True:
        if is_trading_day(d):
            count += 1
            if count == n:
                return d
        d -= timedelta(days=1)


def calculate_release_threshold(stock_code, release_date_str, mult_t5, mult_t15):
    """투자경고 종목의 해제 기준가 계산"""
    
    # 종목명
    stock_name = stock.get_market_ticker_name(stock_code)
    
    # 해제일 파싱
    release_date = datetime.strptime(release_date_str, "%Y-%m-%d").date()
    today = datetime.now().date()
    
    # T-5, T-15 거래일 계산 (한국 공휴일 반영)
    t5_date = trading_day_n_back(release_date, 5)
    t15_date = trading_day_n_back(release_date, 15)
    
    print(f"📅 해제예정일: {release_date} (오늘: {today})")
    print(f"   T-5  계산: {t5_date}")
    print(f"   T-15 계산: {t15_date}")
    print()
    
    # OHLCV 가져오기 (T-15보다 더 전부터, 해제일 또는 오늘까지)
    fetch_start = t15_date - timedelta(days=10)
    fetch_end = min(release_date, today)
    
    df = stock.get_market_ohlcv(
        fetch_start.strftime("%Y%m%d"),
        fetch_end.strftime("%Y%m%d"),
        stock_code,
    )
    
    if df.empty:
        print(f"❌ {stock_name}({stock_code}) 데이터 없음")
        return
    
    # T-5, T-15 종가 추출
    t5_ts = pd.Timestamp(t5_date)
    t15_ts = pd.Timestamp(t15_date)
    
    if t5_ts not in df.index:
        print(f"⚠️ T-5({t5_date}) 데이터 없음 (미래 날짜일 수 있음)")
        return
    if t15_ts not in df.index:
        print(f"⚠️ T-15({t15_date}) 데이터 없음")
        return
    
    t5_close = df.loc[t5_ts, "종가"]
    t15_close = df.loc[t15_ts, "종가"]
    
    # 최근 15일 종가 최고가 (T-15부터 가장 최신 거래일까지)
    recent_df = df[df.index >= t15_ts]
    max_close = recent_df["종가"].max()
    max_date = recent_df["종가"].idxmax().date()
    
    # 3가지 기준가
    threshold_t5 = t5_close * mult_t5
    threshold_t15 = t15_close * mult_t15
    threshold_max = max_close
    
    # 최저값 = 해제 기준가
    release_threshold = min(threshold_t5, threshold_t15, threshold_max)
    
    # 현재가
    current_close = df.iloc[-1]["종가"]
    current_date = df.index[-1].date()
    
    # 결과 출력
    print("=" * 66)
    print(f"  📊 {stock_name} ({stock_code})  투자경고 해제 기준가")
    print("=" * 66)
    print(f"  해제예정일      : {release_date}")
    print()
    print(f"  [조건 1] T-5일 기준")
    print(f"    T-5일({t5_date}) 종가 : {int(t5_close):>10,}원")
    print(f"    × 배수 {mult_t5}            : {int(threshold_t5):>10,}원 이하")
    print()
    print(f"  [조건 2] T-15일 기준")
    print(f"    T-15일({t15_date}) 종가: {int(t15_close):>10,}원")
    print(f"    × 배수 {mult_t15}            : {int(threshold_t15):>10,}원 이하")
    print()
    print(f"  [조건 3] 최근 15일 종가 최고가")
    print(f"    최고일({max_date})    : {int(max_close):>10,}원 이하")
    print()
    print("-" * 66)
    print(f"  ✅ 해제 기준가 (3개 중 최저)  : {int(release_threshold):>10,}원 이하")
    print("-" * 66)
    print()
    print(f"  현재가 ({current_date})  : {int(current_close):,}원")
    
    gap = int(current_close - release_threshold)
    gap_pct = (gap / current_close) * 100
    
    if gap > 0:
        print(f"  → 해제까지 {gap:,}원 ({gap_pct:.2f}%) 하락 필요")
    else:
        print(f"  → 이미 해제 조건 충족! (여유 {-gap:,}원)")
    print("=" * 66)


# ===== 여기서 종목 정보 입력 =====
if __name__ == "__main__":
    calculate_release_threshold(
        stock_code="080220",          # 제주반도체
        release_date_str="2026-05-28", # 해제예정일
        mult_t5=1.45,                  # T-5 배수
        mult_t15=1.75,                 # T-15 배수
    )