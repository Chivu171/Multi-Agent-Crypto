# Bổ sung nguồn lịch sử cho dataset pilot

**Cập nhật sau khi làm rõ yêu cầu:** bản mới nhất `pilot_2022_01_forecast_previous` có lịch sự kiện sắp tới cùng Forecast/Previous từ nguồn, loại Actual/Revision và ghi giả định về thông tin biết trước dự báo. Bản lịch thuần `pilot_2022_01_calendar` vẫn giữ lại. Xem [Bổ sung lịch ForexFactory](BO_SUNG_LICH_FOREX.md). Phần dưới mô tả bộ `pilot_2022_01_enriched` trước khi bật các chế độ lịch này.

**Kết quả: đã bổ sung dữ liệu thật có kiểm tra nguồn, nhưng CHƯA hoàn thành bộ tương đương đầy đủ với live.**

Bộ mới: `data/datasets/pilot_2022_01_enriched/`.
Bộ gốc `data/datasets/pilot_2022_01/` không bị sửa. Nhãn và phân chia tập giữ nguyên.
Phạm vi vẫn là 30 dự đoán ngày 01–30/01/2022, lúc 00:00 UTC, chân trời 24 giờ.

## Đã lấy được gì?

| Trường | Độ phủ tại thời điểm dự đoán | Kiểm tra / giới hạn |
| --- | ---: | --- |
| Funding đã chốt của BTCUSDT | 30/30 ngày | 90 bản ghi trong khoảng đối chiếu khớp API Binance; không phải snapshot lịch sử `premiumIndex.lastFundingRate`. |
| Global long/short account ratio | 11/30 ngày, 20–30/01 | Đọc đúng `count_long_short_ratio` trong kho metrics 5 phút; không dùng top-trader ratio thay thế. Live truy vấn `period=1d`, nên chưa khẳng định tương đương. |
| ForexFactory đúng thời điểm lịch sử | 0/30 ngày đã xác minh | Lịch hồi cứu có dữ liệu nhưng chưa xác minh nội dung đã được biết tại thời điểm dự báo. |
| Đủ tất cả đầu vào tương đương live | 0/30 ngày | Không gán nhãn hoàn thành hoặc loại bỏ các ngày thiếu để làm đẹp coverage. |

Live Sentiment lấy tối đa 10 sự kiện High/Medium sắp tới của **mọi đồng tiền**, không chỉ USD.
Trong lịch hồi cứu đã lưu, khoảng 01–30/01 có **95 sự kiện High/Medium mọi đồng tiền**, trong đó **46 sự kiện USD**.
Các số này là bản ghi lịch kinh tế, không phải bài báo, và vẫn chưa được đưa vào prompt.

## Nguồn và cách dựng

1. Tải ZIP funding tháng 12/2021 và 01/2022, cùng metrics từng ngày từ 31/12/2021 đến 29/01/2022, từ kho chính thức `data.binance.vision`.
2. Tải `.CHECKSUM` đi kèm, so SHA-256 của ZIP trước khi giải mã CSV. Lưu nguyên response, URL, tham số, thời gian tải và checksum để kiểm tra lại.
3. Đối chiếu funding với `GET /fapi/v1/fundingRate`: timestamp và giá trị của 90 bản ghi khớp nhau, không có sai biệt. Đây là hai kênh của cùng Binance, không phải hai nhà cung cấp độc lập.
4. Chọn bản ghi có `available_at < prediction_time`. Funding giữ nguyên timestamp đến mili giây; không kéo bản ghi 00:00:00.006 về 00:00:00 để dùng sớm.
5. Funding dùng quan sát đã chốt gần nhất, tuổi tối đa 12 giờ. Ratio dùng cột global account ratio, giả định trễ 5 phút, tuổi tối đa 24 giờ. Các giả định thời điểm này được lưu trong từng điểm, chưa phải bằng chứng về độ trễ công bố thực tế.
6. Ô ratio trống được giữ thiếu. Không điền 0, không lấy ngày tương lai, không nội suy và không dùng chỉ số top-trader thay thế.
7. Adapter đánh giá đọc các điểm mới và đưa cả thời gian, nguồn, ý nghĩa chỉ số vào prompt Market Agent. Nó kiểm tra lại điểm tương lai, điểm quá cũ và số không hữu hạn trước khi dùng.

Nguồn chính thức: [Binance Public Data](https://github.com/binance/binance-public-data/), [Binance Futures Market Data](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data), [ForexFactory Calendar](https://www.forexfactory.com/calendar).

## Vì sao ForexFactory chưa được đưa vào?

Đã tra 18 yêu cầu tìm bản lưu lịch/JSON/XML qua Wayback Availability API; 7 yêu cầu gặp lỗi giới hạn truy cập. Những kết quả tìm được chưa đủ xác minh lịch sắp tới cho các mốc dự báo.

- Trang tuần 02/01/2022 trả về bản chụp 29/01/2022, sau tuần cần dự đoán.
- Bản XML ngày 29/01/2022 có thể là ứng viên kiểm tra cho ngày cuối pilot, nhưng yêu cầu tải nội dung trả HTTP 429. Response lỗi và URL được lưu tại `forex_followup/`.
- Không coi ngày diễn ra sự kiện là ngày Forecast/Previous chắc chắn đã được công bố. Không coi việc loại cột Actual là đủ chứng minh các cột còn lại đúng thời điểm.

Đây là tìm kiếm có giới hạn, không chứng minh mọi kho khác đều không có dữ liệu. Muốn đưa ForexFactory vào cần bản chụp có thời gian trước dự báo và xác minh đúng tuần/nội dung, hoặc nguồn có lịch sử phiên bản tương đương.

## Code và kiểm tra

- `data_sources/historical_derivatives.py`: tải, kiểm checksum, parse và chọn điểm trước mốc dự báo; đối chiếu API funding.
- `scripts/enrich_historical_dataset.py`: xác minh bộ gốc, tạo bộ bổ sung, thống kê độ phủ và lưu kết quả tìm vintage ForexFactory.
- `scripts/evaluate_direction.py`: nhận dữ liệu bổ sung và thêm `--require-full-live`; bộ chưa đủ sẽ bị từ chối trước mọi lần gọi LLM.
- `tests/test_historical_enrichment.py`: 15 test mới về checksum, mili giây, giá trị âm funding, ratio thiếu/không hợp lệ, rò rỉ tương lai, điểm quá cũ, adapter và chốt chặn full-live. Fixture nhỏ trong test là dữ liệu tổng hợp được ghi rõ, không phải dữ liệu đưa vào dataset.

**236 test pass** trên toàn bộ suite; nhóm kiểm tra dataset/adapter có 35 test pass.
Đã kiểm tra độc lập 30 snapshot với CSV ZIP gốc, giữ nguyên nhãn, kiểm checksum 11 artifact và dựng lại offline cho file giống hệt từng byte.
Kết quả kiểm tra dữ liệu thực: `verification_result.json` trong bộ mới.
Chưa gọi LLM để chạy một đợt đánh giá hệ thống mới trong lần bổ sung này.

## Cách sử dụng

Dựng lại không cần mạng, dùng raw response đã lưu và bộ gốc:

```sh
.venv/bin/python -m scripts.enrich_historical_dataset --offline
```

Kiểm tra điều kiện đánh giá đầy đủ:

```sh
.venv/bin/python -m scripts.evaluate_direction \
  --dataset data/datasets/pilot_2022_01_enriched \
  --output outputs/direction_enriched_full_check \
  --require-full-live
```

Với bộ hiện tại lệnh này **phải từ chối chạy**, vì chưa đủ dữ liệu. Nếu chủ động đánh giá bản nguồn hạn chế, bỏ cờ đó và ghi rõ giới hạn trong báo cáo; kết quả dùng input khác không được so trực tiếp với baseline cũ như một thí nghiệm chỉ thay Debate. Các nhánh so sánh phải chạy cùng bộ mới và cùng đầu ra Specialist.

## Những việc còn cần để đạt yêu cầu đầy đủ

1. Tìm được và kiểm tra vintage ForexFactory trước các mốc dự đoán; hiện vướng cả thiếu bằng chứng lẫn HTTP 429.
2. Tìm dữ liệu global ratio đúng lịch/định nghĩa cho các ngày còn thiếu. Nếu đổi giai đoạn đánh giá hoặc đổi cấu hình live sang quan sát 5 phút thì phải ghi đó là một thay đổi thiết kế, không tự coi hai trường tương đương.
3. Chốt dùng funding đã chốt hay `premiumIndex.lastFundingRate`, rồi thống nhất định nghĩa live/historical. Không thay định nghĩa âm thầm.
4. Kiểm tra thêm thời gian công bố thực tế của on-chain/Fear & Greed; bộ cũ vẫn dùng độ trễ giả định 2 ngày/1 ngày.
5. Khi đầu vào đã thống nhất, mở rộng thời gian và giữ tập đánh giá chưa dùng để chỉnh phương pháp; bộ 30 ngày này vẫn chỉ là pilot.

Vì chưa có bằng chứng nguồn để hoàn thành các mục trên, kết quả hiện tại được ghi là **bổ sung một phần**, không phải dataset đầy đủ như live.
