# Kiểm tra bổ sung nguồn lịch sử

**Trạng thái: CHƯA ĐỦ BẢN LIVE.**

Khoảng dự báo: 2022-01-01 → 2022-01-30; 30 ngày.

| Nguồn bổ sung | Số ngày có dữ liệu |
| --- | ---: |
| Funding đã chốt | 30 |
| Global long/short từ kho 5 phút | 11 |
| Lịch sự kiện ForexFactory, theo giả định đã thông báo trước | 30 |
| ForexFactory có vintage được xác minh | 0 |
| Đủ tương đương live | 0 |

Không thay ô thiếu bằng 0, không dùng top-trader ratio thay global ratio.
Không đưa Actual/Forecast/Previous từ lịch tải hồi cứu vào prompt.
Nếu bật --calendar-schedule: chỉ lấy tên, giờ, đồng tiền, mức ảnh hưởng; chọn tối đa 10 sự kiện sắp tới trong tuần UTC. Ngày không có sự kiện khác với nguồn bị thiếu.
Trong 30 ngày có lịch, 25 ngày có ít nhất một sự kiện sắp tới được chọn. Các feature đếm sự kiện tính trong tối đa 10 sự kiện đưa vào prompt.
Lịch live lấy High/Medium của mọi đồng tiền, tối đa 10 sự kiện sắp tới; không chỉ USD.

ForexFactory hồi cứu: 95 sự kiện High/Medium mọi đồng tiền; 46 sự kiện USD trong khoảng dự báo.
Tìm vintage: 18 truy vấn; 7 truy vấn lỗi. Đây là tìm kiếm giới hạn, không chứng minh mọi kho lưu trữ đều không có dữ liệu.

## Kiểm tra nguồn

- File ZIP đối chiếu SHA-256 với .CHECKSUM của Binance trước khi đọc CSV.
- Funding đối chiếu API: {"archive_rows": 90, "api_rows": 90, "matched": true, "mismatch_timestamps": []}.
- Chỉ chọn available_at < prediction_time; không làm tròn timestamp funding về 00:00.
- Ratio trễ giả định 5 phút, tối đa 24 giờ tuổi; funding tối đa 12 giờ tuổi.
- Bộ gốc, nhãn và phân chia tập được giữ nguyên; bộ bổ sung có manifest riêng.

## Giới hạn còn lại

- ForexFactory event metadata only; assumes the historical schedule was announced before prediction. Schedule revisions unverified. Actual/forecast/previous/revision excluded.
- Global long/short uses the 5m archive column, not live period=1d; empty source cells remain missing.
- Funding is last settled rate, not a historical premiumIndex snapshot of lastFundingRate.
- On-chain and Fear & Greed publication times remain assumed; source vintages are unverified.
- Daily closed-candle evaluation differs from live intraday/current-candle fetching.
- This remains the base pilot's time split, not an independent held-out evaluation.
- Historical LLM knowledge contamination possible.

## Dựng lại offline

```sh
.venv/bin/python -m scripts.enrich_historical_dataset --base data/datasets/pilot_2022_01 --output data/datasets/pilot_2022_01_calendar --offline --calendar-schedule
```

`source_coverage.json`: thiếu gì theo ngày; `derivatives_source.json`: giá trị và nguồn từng điểm;
`forex_vintage_probe.json`: kết quả tìm bản lưu, không phải dữ liệu được duyệt vào prompt.
