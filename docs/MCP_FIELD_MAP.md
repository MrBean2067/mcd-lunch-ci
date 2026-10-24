# 麦当劳 MCP 实测字段表

这份文档是**实测记录**，不是照着文档抄的。所有字段名、单位、坑都来自对
`https://mcp.mcd.cn` 的真实调用（2026-10-24，服务端 `mcd-mcp 1.0.0`，协议 `2025-06-18`，35 个工具）。

写它的原因：公开资料里查不到这些细节，而每一个细节都能让接入代码直接算错钱。

## 0. 通用信封与回包形态

所有工具都是 POST JSON-RPC 2.0 到同一个地址，`Accept` 必须同时声明
`application/json, text/event-stream`。业务结果在 `result.content[].text` 里，格式是：

```
每个门店的基本信息按单行展示：\n
{"success":true,"code":200,"message":"请求成功","datetime":"...","traceId":"...","data":[...]}
```

**坑 1：`content[].text` 不是纯 JSON**，前面挂了一段给大模型看的说明文字。
直接 `json.loads` 必炸，必须先从文本里把 JSON 抠出来（`mcp_client.extract_json`）。

**坑 2：`initialize` 之后服务端会给 `Mcp-Session-Id` 响应头**，后续请求必须带上，
否则可能拿到空结果。

统一信封字段：`success` / `code` / `message` / `datetime` / `traceId` / `data`。

## 1. 到店/外送/团餐的 `beType` 与 `orderType` 配对

这是最容易传错的一组参数，传错不一定报错，但结果为空：

| 场景 | beType | orderType | beCode | 额外要求 |
| --- | --- | --- | --- | --- |
| 到店自取 | 1 | 1 | **不传**（传了会报错） | — |
| 得来速 | 5 | 1 | 必传（来自 `query-nearby-stores`） | — |
| 麦乐送 | 2 | 2 | 必传（来自 `delivery-query-stores`） | 需 `addressId` |
| 企业团餐 | 6 | 2 | 必传（来自 `delivery-query-stores`） | 需 `addressId` + `gmServiceCode` |

本项目默认走**到店自取（1/1）**：链路最短、不需要地址、个人 Token 就能跑通。

## 2. `query-nearby-stores` — 找门店

入参：`beType`(必填) + `searchType`(必填)
- `searchType=2` 按位置搜索 → 需 `city` + `keyword`
- `searchType=1` 搜收藏门店（新账号通常为空）

出参 `data[]`：

```json
{"storeCode":"1420762","storeName":"麦当劳深圳同方信息港餐厅",
 "address":"科技园北区朗山路11号同方信息港E栋G层5号商铺",
 "distance":403,"businessStatus":true,
 "businessStartTime":"07:00","businessEndTime":"23:00",
 "longitude":0.0,"latitude":0.0,"reservation":true,
 "reservationTimeOptions":[{"date":"2026-10-24","today":true,"reservationOptionText":"..."}]}
```

注意 `beType=1` 时**没有 `beCode`**（与文档一致）；`distance` 单位是米。
`longitude/latitude` 实测恒为 `0.0`，不要拿来算距离。

## 3. `query-meals` — 菜单（只有编码，没有名称和价格）

入参：`storeCode` + `orderType` + `beType`

出参 `data.categories[].meals[]`，每条**只有**：

```json
{"code":"9900004064","tags":["经典精选","全球爆款","全天供应"]}
```

**坑 3：菜单接口不返回餐品名和价格。** 名称要去 `query-meal-detail` 查，
价格只能靠 `calculate-price` 核出来。所以「拉一份能算钱的菜单」= 1 次 query-meals
+ N 次 query-meal-detail + N 次单项核价。

分类名带换行（`"鸡肉汉堡\n/卷"`），做映射前要先去掉。

## 4. `query-meal-detail` — 餐品详情（有名称，仍无价格）

入参：`storeCode` + `orderType` + `beType` + `code`

出参 `data`：

```json
{"code":"9900004064","name":"精选单人餐三件套",
 "rounds":[{"id":1,"name":"主食任意选","quantity":1,"minQuantity":1,"maxQuantity":1,
            "choices":[{"code":"1406","name":"板烧鸡腿堡","diffPrice":"+ ¥0",
                        "modification":{"items":[{"values":[{"name":"烤味酱","selectedKey":"0-1"}]}]}}]}],
 "image":"https://menu-img.mcd.cn/...","supportModify":false}
```

`rounds` 是套餐的可替换组成（主食任选/小食任选/饮料任选），`choices[].diffPrice`
是**加价文案字符串**（`"+ ¥2"`、`"- ¥1"`），不是数字，别直接拿去算钱。

周边商品（丝巾、痒痒挠）也会出现在菜单里，`rounds` 为空数组，靠名字过滤。

## 5. `calculate-price` — 唯一的价格来源

入参：`storeCode` + `orderType` + `beType` + `items[]`，`items` 每项
`{productCode, quantity, couponCode?, couponId?, modification?, roundList?}`。

出参 `data`：

```json
{"productOriginalPrice":6000,"productPrice":6000,"originalPrice":6000,
 "discount":0,"price":6000,
 "productList":[{"productCode":"9900004064","productName":"精选单人餐三件套",
                 "quantity":1,"originalSubtotal":3450,"subtotal":3450}],
 "takeWayList":[{"code":"eat-in","title":"堂食"},{"code":"locker-out","title":"外带"}]}
```

**坑 4：金额单位是「分」。** `6000` = ¥60。本项目全部经 `parse_amount(x, "fen")` 转换。

**坑 5（最贵的一个）：批量核价会把整单满减摊到每个商品上。**
把 102 个餐品塞进一次 `calculate-price` 去反推单价，返回的 `productList[].subtotal`
是**摊过折扣的金额**，拿它当单价会让本地合计比真实核价低 ¥40
（实测 ¥199.90 vs 官方 ¥222.40）。所以单价必须**逐项核价**（一次一个商品、quantity=1），
只有整单核价才用批量。

`takeWayList[].code` 是下单时 `orderType=1` 必传的 `takeWayCode`。

## 6. `list-nutrition-foods` — 类 CSV 文本，且按餐品名索引

无入参。出参 `data` 是**字符串**，不是 JSON：

```
[160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
  猪柳麦满分,null,1288,308,16,16,24,781,213
  中薯条,null,1210,289,4,12,38,165,18
```

**坑 6：索引键是 `productName`，不是 `productCode`。**
所以营养只能按名字 join 菜单；join 不上就标 `unavailable`，绝不填 0 充数。

**坑 7：缺失值写作 `null`**，`int("null")` 会抛异常；表头行尾的 `:` 会变成一行假数据；
餐品名里若含逗号会让所有列左移——列数对不上时必须丢弃整行，不能错位解析。

## 7. `query-store-coupons` / `available-coupons` — 券

- `query-store-coupons`（`storeCode`+`orderType`+`beType`）：实测本项目门店
  `beType=1` 返回 `data: []`，即当前无可用门店券。
- `available-coupons`（无入参）：返回的是 **Markdown 文本**，只有券标题和状态：

```
### 麦麦省优惠券列表：
- 优惠券标题：11.9元麦辣鸡腿堡 \
  状态：已领取 \
  优惠券图片：<img src="...">
```

**坑 8：麦麦省券没有金额字段、没有券码。** 无法自动算进方案，硬算就是编造折扣。
本项目如实显示「可用券 0 张」，不假装省了钱。

## 8. `create-order` — 唯一真实写操作

入参（`orderType=1`）：

```json
{"storeCode":"1420762","orderType":1,"beType":1,
 "items":[{"productCode":"515837","quantity":6}],
 "takeWayCode":"eat-in","needTableware":false,
 "remark":"mcd-lunch-ci 团队午餐 8 人"}
```

- `orderType=1` 必须带 `takeWayCode`（来自 `calculate-price` 的 `takeWayList`）
- `orderType=2` 必须带 `addressId`
- `beType=6` 团餐必须带 `gmServiceCode`（来自 `query-meal-assistance`）
- `remark` 最多 50 字

## 9. 团餐（`beType=6`）为什么本项目没默认用

团餐链路是：`delivery-query-addresses` → `delivery-query-stores`（拿 `beCode`）
→ `query-meals` → `query-meal-assistance` → `calculate-price` → `create-order`，
而且还能用 `query-promotions` 拿满减/满折规则（`promotionType` 31=满额减 / 33=订单折扣）。

但实测这个 Token 的 `delivery-query-addresses` 返回 `{"addresses": []}`——
没有外送地址就没有 `beCode`，整条链路走不下去（`delivery-create-address` 会往账号里
写真实地址，属写操作，不应由演示脚本擅自调用）。

所以默认走 `beType=1`，`--be-type 6` 保留给配好企业团餐地址的账号。

## 10. 复现方式

```bash
python -m mcd_lunch_ci doctor          # 连通性 + 门店 + 菜单 + 核价自检
python -m mcd_lunch_ci sync --refresh  # 全量拉一遍，落成本地快照
```

`doctor` 会打印实测到的门店、餐品数、营养覆盖率、最便宜餐品和一次真实核价结果；
`sync` 把整份菜单（101 个餐品 / 57 个有实测营养）写进 `data/live_menu_snapshot.json`，
之后不配 Token 也能用真数据跑完整流水线。
