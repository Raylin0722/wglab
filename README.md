# 實驗室 WireGuard 外漏事件：調查練習

把一次真實的網路事件做成 Docker Compose 練習環境：玩家從學校的來信開始調查，
在網頁上操作實驗室的三台機器，最後交出報告並通過自動驗收。IP 與人名都已替換。

## 啟動

```bash
docker compose up -d --build
```

第一次約 2–3 分鐘（建置映像；之後網頁會顯示「初始化中」約 1 分鐘）。完成後打開 <http://localhost:8080>：

- 左邊是終端機，已經登入 227、router、routerlog。
- 右邊是學校的信、環境說明、報告範本、學校異常查詢與驗收。
- 上方可以「模擬一天」；每台機器可以單獨重開；「從頭來過」會重建三台玩家機器。

需求：Docker 與 Docker Compose；Linux kernel 內建 WireGuard（5.6 以上）或 Docker Desktop。
227、router、routerlog 與 control 需要 privileged；網頁與 wg-portal 只開在 127.0.0.1。

## 資料夾

| 路徑 | 內容 |
|---|---|
| `compose.yml` | 12 個容器：玩家機器 3 台、情境角色 8 個、control |
| `images/wg227` | 227：Ubuntu 24.04 + systemd-networkd + wg-portal v2.2.3 |
| `images/router`、`images/routerlog` | 實驗室閘道（Linux）與 log 主機 |
| `images/actor` | 情境角色：學校、網際網路、在家的 WireGuard 使用者、pc1、pc2、印表機 |
| `images/control` | 接線、初始化、模擬一天、驗收、網頁（出題程式都在這裡） |
| `player/` | 玩家文件：學校的信、環境說明、報告範本 |
| `topology.html` | 拓撲圖 |
| `instructor/` | 講師手冊與參考解答（**不要發給玩家**） |

## 架構重點

- 實驗室的機器都沒有 Docker 網路；control 在自己裡面用 bridge 當交換器、用 veth 當網路線把它們接起來，某台重開只重接它那段線。
- 「學校」與「網際網路」是模擬的，沒有任何封包會經由 Docker 離開。
- 驗收全自動：跑一輪、只重開 227 / router / routerlog、再跑一輪，並檢查出題程式有沒有被改過。

## 發給玩家

```bash
./pack.sh        # 產生 wglab-player.tar.gz（不含 instructor/）
```

玩家拿得到 `images/control/` 的原始碼；說明文件裡有請他們不要看，驗收時也會偵測程式是否被改過。
要當作業的話，建議改成由講師架設、玩家只能連到網頁。
