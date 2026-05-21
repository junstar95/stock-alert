import os

# ★ 여기 두 줄을 본인 KRX 계정 정보로 바꾸세요 ★
os.environ['KRX_ID'] = '95junstar'
os.environ['KRX_PW'] = 'wnstjd1717!'

from pykrx import stock
from datetime import datetime, timedelta

# 직전 영업일
today = datetime.now()
while today.weekday() >= 5:
    today -= timedelta(days=1)
ymd = today.strftime("%Y%m%d")

print(f"조회 날짜: {ymd}")
print("-" * 60)

# 1) 코스피 종목 리스트
print("\n[1] 코스피 종목 가져오는 중... (30초~1분 소요)")
tickers = stock.get_market_ticker_list(ymd, market="KOSPI")
print(f"   → 코스피 종목 수: {len(tickers)}개")
print(f"   → 첫 3개 종목코드: {tickers[:3]}")

# 2) 종목명 확인
print("\n[2] 종목명 확인 중...")
for code in tickers[:3]:
    name = stock.get_market_ticker_name(code)
    print(f"   → {code}: {name}")

# 3) 시세·시총·PER (삼성전자 테스트)
print("\n[3] 삼성전자(005930) 정보 가져오는 중...")
cap = stock.get_market_cap(ymd, ymd, "005930")
fund = stock.get_market_fundamental(ymd, ymd, "005930")
print(f"   → 시가총액: {cap.iloc[0]['시가총액']:,}원")
print(f"   → PER: {fund.iloc[0]['PER']}")
print(f"   → PBR: {fund.iloc[0]['PBR']}")

print("\n✅ pykrx 정상 작동!")