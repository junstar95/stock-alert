import requests
import re
import csv
import time
from datetime import date
from bs4 import BeautifulSoup

# === Session 준비 ===
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://kind.krx.co.kr/disclosure/details.do?method=searchDetailsMain",
})
session.get("https://kind.krx.co.kr/disclosure/details.do?method=searchDetailsMain", timeout=10)
print("[준비] 세션 시작 완료")

# === 공시 본문에서 4가지 정보 추출 (재사용 함수) ===
def extract_disclosure_info(acptno):
    try:
        r1 = session.get(
            "https://kind.krx.co.kr/common/disclsviewer.do",
            params={"method": "search", "acptno": acptno},
            timeout=10,
        )
        docno = next(
            (x for x in re.findall(r'\b(20\d{12})\b', r1.text) if x != acptno),
            None,
        )
        if not docno:
            return None

        body_url = (
            f"https://kind.krx.co.kr/external/"
            f"{acptno[:4]}/{acptno[4:6]}/{acptno[6:8]}/{acptno[8:]}/"
            f"{docno}/70804.htm"
        )
        r2 = session.get(body_url, timeout=10)
        r2.encoding = r2.apparent_encoding or "utf-8"
        text = BeautifulSoup(r2.text, "html.parser").get_text()

        m = re.search(r'T-5\s*\)의\s*종가보다\s*(\d+)\s*%\s*이상\s*상승', text)
        t5_rate = int(m.group(1)) if m else None
        m = re.search(r'T-15\s*\)의\s*종가보다\s*(\d+)\s*%\s*이상\s*상승', text)
        t15_rate = int(m.group(1)) if m else None
        m = re.search(r'최초\s*판단일은\s*(\d{1,2})월\s*(\d{1,2})일', text)
        judge_date = None
        if m:
            jm, jd = int(m.group(1)), int(m.group(2))
            dy = int(acptno[:4])
            dm = int(acptno[4:6])
            jy = dy + 1 if jm < dm else dy
            try:
                judge_date = date(jy, jm, jd)
            except ValueError:
                pass

        if t5_rate and t15_rate and judge_date:
            return {
                "해제예정일": judge_date.strftime("%Y-%m-%d"),
                "T5_배수": round(1 + t5_rate / 100, 2),
                "T15_배수": round(1 + t15_rate / 100, 2),
            }
    except Exception as e:
        print(f"      에러: {e}")
    return None

# === 검색 payload ===
def make_payload(page_index):
    p = {
        "method": "searchDetailsSub",
        "currentPageSize": "100",
        "pageIndex": str(page_index),
        "orderMode": "1",
        "orderStat": "D",
        "forward": "details_sub",
        "reportNm": "투자경고종목지정",
        "reportNmTemp": "투자경고종목 지정",
        "fromDate": "2026-04-21",
        "toDate": "2026-05-21",
        "bfrDsclsType": "on",
    }
    for i in [1,2,3,4,5,6,7,8,9,10,11,13,14,20]:
        p[f"disclosureType{i:02d}"] = ""
        p[f"pDisclosureType{i:02d}"] = ""
    for key in ["searchCodeType","repIsuSrtCd","allRepIsuSrtCd","oldSearchCorpName",
                "disclosureType","disTypevalue","reportCd","searchCorpName",
                "business","marketType","settlementMonth","securities",
                "submitOblgNm","enterprise","reportNmPop"]:
        p[key] = ""
    return p

# === [1] 검색 + 수집 ===
print("\n[1] KIND 검색")
all_disclosures = []
for page in range(1, 6):
    r = session.post(
        "https://kind.krx.co.kr/disclosure/details.do",
        data=make_payload(page),
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=15,
    )
    soup = BeautifulSoup(r.text, "html.parser")
    page_items = []
    for row in soup.find_all("tr"):
        m = re.search(r'\b(20\d{12})\b', str(row))
        if m:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            page_items.append({"acptno": m.group(1), "cells": cells})
    if not page_items:
        break
    all_disclosures.extend(page_items)
    print(f"    페이지 {page}: {len(page_items)}건 (누적 {len(all_disclosures)})")

# === [2] 개선된 필터 ===
print("\n[2] 필터링 (개선된 로직)")
filtered = []
for d in all_disclosures:
    full = " ".join(d["cells"])
    normalized = full.replace(" ", "")  # 띄어쓰기 무시
    
    has_designation = "투자경고종목지정" in normalized
    is_predesignation = "예고" in full
    is_release = "해제" in full
    is_trading_halt = "매매거래" in full
    
    if has_designation and not (is_predesignation or is_release or is_trading_halt):
        # 회사명/제목 추출
        company = next(
            (c for c in d["cells"] if c and "투자" not in c and "감시" not in c
             and "공시" not in c and "주가" not in c and "-" not in c
             and ":" not in c and not c.isdigit() and 1 < len(c) < 30),
            ""
        )
        title = next((c for c in d["cells"] if "투자" in c and "감시" not in c), "")
        d["회사명"] = company
        d["공시제목"] = title
        filtered.append(d)

print(f"    필터 후: {len(filtered)}건")

# 제주반도체 검증
jeju = next((d for d in filtered if d["acptno"] == "20260513001030"), None)
print(f"    제주반도체 검증: {'✅ 포함됨' if jeju else '❌ 못 찾음'}")

# === [3] 각 공시 본문 자동 파싱 ===
print(f"\n[3] 본문 파싱 시작 (총 {len(filtered)}건, 1~2분 소요)")
print("-" * 70)

results = []
for i, d in enumerate(filtered, 1):
    print(f"  [{i:2d}/{len(filtered)}] {d['acptno']} | {d['회사명'][:15]:15s} ...", end=" ", flush=True)
    info = extract_disclosure_info(d["acptno"])
    if info:
        results.append({
            "acptno": d["acptno"],
            "회사명": d["회사명"],
            "공시제목": d["공시제목"],
            **info,
        })
        print(f"✅ 해제일={info['해제예정일']}, T-5×{info['T5_배수']}, T-15×{info['T15_배수']}")
    else:
        print("⚠️ 추출 실패 (건너뜀)")
    time.sleep(0.3)  # KIND 부담 줄이기

# === [4] CSV 저장 ===
csv_path = "warning_stocks.csv"
with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=["acptno", "회사명", "공시제목", "해제예정일", "T5_배수", "T15_배수"])
    writer.writeheader()
    writer.writerows(results)

print(f"\n[4] CSV 저장 완료")
print(f"    경로: {csv_path}")
print(f"    성공: {len(results)}건 / 전체 {len(filtered)}건")
print(f"\n🎉 완료! 같은 폴더에 warning_stocks.csv 가 생겼습니다.")