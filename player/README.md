# 實驗室網路事件調查練習

你是實驗室的網路管理員。學校來信說實驗室的對外 IP 疑似中毒，請查出發生了什麼事、為什麼會發生，並讓它不再發生。

## 啟動

需要 Docker 與 Docker Compose（Linux，或 Windows / macOS 的 Docker Desktop）。在專案根目錄執行：

```bash
docker compose up -d --build
```

第一次約需 2–3 分鐘（建置映像、初始化，並自動跑一次「模擬一天」）。完成後打開：

**http://localhost:8080**

所有操作都在這個網頁：終端機（227、router、routerlog）、學校的信、環境說明、報告範本、學校異常查詢、模擬一天、重開、驗收、從頭來過。

整間實驗室由十幾個容器組成，**沒有任何封包會離開這些容器**，「學校」和「網際網路」都是模擬的。網頁只開給本機（127.0.0.1）。

## 你要交出來的東西

1. 一份報告：照 [REPORT-TEMPLATE.md](REPORT-TEMPLATE.md) 的格式。
2. 在網頁的「驗收」分頁全部通過。

詳細的規則與環境說明在網頁的「環境說明」分頁（[GUIDE.md](GUIDE.md)）。

## 關掉與重來

```bash
docker compose down        # 關掉（設定保留在容器裡）
docker compose down -v     # 連同所有紀錄一起清掉
```

網頁上的「從頭來過」只會重建 227、router、routerlog，不用關掉整個環境。
