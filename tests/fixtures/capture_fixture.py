# tests/fixtures/capture_fixture.py —— 一次性腳本，抓真實資料存成 fixture，不是 production 程式碼
from twchips import taifex

d = taifex.options_daily("2026-08-19", product="TXO", session="regular")
d.to_csv("tests/fixtures/2026-08-19_regular.csv", index=False)
print(f"抓到 {len(d)} 筆，存到 tests/fixtures/2026-08-19_regular.csv")

# 順便印出關鍵驗證資訊，寫進 README 記錄
months = sorted(d[d["到期月份(週別)"].astype(str).str.match(r"^\d{6}$")]["到期月份(週別)"].unique())
weeks = sorted(set(d["到期月份(週別)"].unique()) - set(months))
print("月選:", months)
print("週選:", weeks)
near = d[d["到期月份(週別)"] == months[0]]
print(f"近月({months[0]}) 到期日:", near["契約到期日"].unique())
print(f"近月筆數: {len(near)}，非零OI筆數: {(near['未沖銷契約數'].fillna(0) > 0).sum()}")
print("未沖銷契約數 dtype:", near["未沖銷契約數"].dtype)
print("買賣權值:", d["買賣權"].unique())
