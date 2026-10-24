# MCP 集成说明

本文说明 `mcd-lunch-ci` 实际调用了哪些麦当劳 MCP 工具、按什么顺序调用、每步的业务价值，以及遇到异常时怎么降级。

所有字段、单位、坑都是**实测**出来的，完整字段表见 [docs/MCP_FIELD_MAP.md](docs/MCP_FIELD_MAP.md)。

## 1. 接入信息

| 项 | 值 |
| --- | --- |
| 服务地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP（服务端可能以 `text/event-stream` 回包，客户端两种都要能解析） |
| 鉴权 | 请求头 `Authorization: Bearer <MCD_MCP_TOKEN>` |
| Token 获取 | [open.mcd.cn/mcp](https://open.mcd.cn/mcp) → 手机号登录 → 控制台 → 激活 → 复制 |
| Token 存放 | 项目根目录 `.env`（已在 `.gitignore` 里，不进仓库）；`cli.load_dotenv()` 自动读取 |
| 客户端 | 自研零依赖客户端 `mcd_lunch_ci/mcp_client.py`（仅用 `urllib` + `json`） |
| 实测服务端 | `mcd-mcp 1.0.0`，协议 `2025-06-18`，35 个工具 |
| 限流 | 600 次/分钟，超限返回 429，客户端翻译成可读提示 |
| 实测门店 | 麦当劳深圳同方信息港餐厅（`storeCode=1420762`，403m） |

## 2. 实际调用的工具

| 工具 | 入参（实测必填） | 实际返回 | 在哪个阶段用 |
| --- | --- | --- | --- |
| `query-nearby-stores` | `beType`,`searchType`,`city`,`keyword` | `data[]`：`storeCode`/`storeName`/`address`/`distance` | 解析门店 |
| `query-meals` | `storeCode`,`orderType`,`beType` | `data.categories[].meals[].{code,tags}` — **无名称无价格** | 拉可售清单 |
| `query-meal-detail` | `storeCode`,`orderType`,`beType`,`code` | `data.{code,name,rounds,image}` — **仍无价格** | 补名称与套餐组成 |
| `list-nutrition-foods` | 无 | **类 CSV 文本**，按餐品名索引 | 热量硬约束的依据 |
| `calculate-price` | `storeCode`,`orderType`,`beType`,`items[]` | `data.{price,originalPrice,discount,productList[],takeWayList[]}`，单位**分** | 取单价 + 核价 |
| `query-store-coupons` | `storeCode`,`orderType`,`beType` | `data[]`（本门店实测为空） | 券后应付 |
| `available-coupons` | 无 | Markdown 文本（只有标题和状态） | 券信息兜底 |
| `create-order` | `storeCode`,`orderType`,`beType`,`items[]`,`takeWayCode` | 订单号 + 支付链接 | 唯一真实写操作，默认不调用 |
| `query-order` | `orderId` | 订单详情 | 可选收尾核对 |

未使用：`query-promotions` / `query-meal-assistance`（仅 `beType=6` 企业团餐可用，见字段表第 9 节）、
`party-*`（主题活动）、积分商城与抽奖系列。这些能力与"团队午餐决议"场景不直接相关。

## 3. 调用流程

```
        ┌────────────────────────────────────────────────┐
        │ MCD_MCP_TOKEN（.env / 环境变量，不落盘不进库）   │
        └───────────────────┬────────────────────────────┘
                            ▼
        initialize ──► tools/list ──► query-nearby-stores ──► storeCode
                            │
                            ▼
                      query-meals ──► codes[] + tags[]        ← 只有编码
                            │
              ┌─────────────┴──────────────┐
              ▼                            ▼
      query-meal-detail ×N            list-nutrition-foods
      （并发 6，落盘缓存）             （CSV 文本，按名字 join）
              │                            │
              └──────────┬─────────────────┘
                         ▼
            calculate-price ×N（逐项，拿真实单价）   ← 关键：不能批量
                         │
                         ▼
            求解器（本地，无网络）：帕累托前沿 + 预算 DP
                         │
                         ▼
            calculate-price（整单核价，官方金额为准）
                         │
                   --confirm ?
                    │        │
                  否│        │是
                    ▼        ▼
               预览载荷   create-order ──► orderId + payUrl
```

关键设计：**求解全程在本地完成**。MCP 只负责"取事实"（菜单、营养、券）和"执行动作"（核价、下单），不做决策。这样即使 MCP 某次返回抖动，方案也不会莫名其妙变化，且所有推理过程可复现、可单元测试。

## 4. 实测踩到的 5 个坑（都写成了代码 + 测试）

| 坑 | 后果 | 处理 |
| --- | --- | --- |
| `content[].text` 是「说明文字 + JSON」 | `json.loads` 直接失败 | `extract_json()` 扫描文本抠出 JSON |
| 菜单接口不返回名称和价格 | 拿不到能算钱的菜单 | `query-meal-detail` 补名称，`calculate-price` 取单价 |
| **批量核价把满减摊到每个商品** | 本地合计比官方核价低 ¥40（¥199.90 vs ¥222.40） | 单价**逐项核价**，整单核价才批量；最终金额以官方为准 |
| 营养表按**餐品名**索引且是 CSV 文本 | 按 code join 会全军覆没 | 按名称匹配（精确→包含），匹配不上标 `unavailable` |
| 金额单位是**分** | 差 100 倍 | 全部经 `parse_amount(x, "fen")`，禁止裸数字参与金额运算 |

前 4 条各有对应单元测试（`tests/test_live_protocol.py`），第 5 条在 `tests/test_money.py`。

## 5. 降级策略

| 情况 | 处理 |
| --- | --- |
| 找门店失败 | 直接报错并提示换 `--city/--keyword`，不编一个假门店 |
| 某餐品查不到详情/核不出价 | 跳过该餐品，不猜价格、不填 0 |
| 营养数据缺失 | 标 `nutrition_source=unavailable`；有热量上限的成员**无法选用**该餐品（缺数据 ≠ 0 卡），报告里热量显示「未知」 |
| `calculate-price` 整单核价失败 | 回退本地求和，报告明确写「未核价」，不假装核过 |
| 门店券接口返回空 | 如实显示「可用券 0 张」，不用麦麦省券的标题去臆造折扣 |
| 401 | 提示 Token 无效/过期，指向 open.mcd.cn 控制台 |
| 429 | 提示限流（600 次/分钟），要求退避后重试，不在循环里刷 |

## 6. 金额单位的处理（本项目最在意的一件事）

麦当劳 MCP 的金额单位并不统一：`calculate-price` 的 `price` 是**分**（`6000` = ¥60），
而主题活动场次价也是分、部分展示字段是元。混算一次就是 100 倍错误，且很难在测试里被发现。

因此本项目：

1. 内部一律用整数**分**（`Money`）；
2. 外部金额必须经 `parse_amount(value, unit)`，单位未知直接抛 `MoneyError`，**禁止猜测**；
3. 在线模式下单位固定为 `fen`（`--price-unit` 只为兼容保留）；
4. 有专门的单元测试锁住这个行为：

```python
session_price = parse_amount(5800, "fen")      # ¥58.00
misread_as_yuan = parse_amount(5800, "yuan")   # ¥5800.00 ← 100 倍错误
assert misread_as_yuan.fen == session_price.fen * 100
```

5. 报告里的「应付」以官方核价为准；本地合计与官方不一致时会单独打印一行差额说明。

## 7. 写操作的护栏

`create-order` 是唯一会改变真实世界状态的调用，因此：

- 默认**只生成预览载荷**，不调用；
- 必须同时满足：`--live` + `--confirm`，且该单号在报告里明确打印；
- 下单失败不静默：打印原始回包并写出 `out/live-trace.json`；
- **付款永远由人完成**——Agent 不持有支付凭证，也不调用任何支付接口；
- 演示脚本不调用 `delivery-create-address`、`auto-bind-coupons` 这类会往账号里写数据的接口。

## 8. 业务价值

| 对谁 | 价值 |
| --- | --- |
| 团队里的"点餐倒霉蛋" | 从 20 分钟群聊拉锯变成一条命令；不用背每个人的忌口 |
| 有过敏/忌口/信仰约束的人 | 约束是硬过滤，方案里不可能出现他不能吃的东西，且报告会求证"零违反" |
| 管预算的人 | 拿到"预算—满意度前沿"这条曲线，知道省钱的代价落在谁头上，而不是拍脑袋砍预算 |
| 开发者 | 一个可以直接抄的 MCP 实战样板：零依赖客户端、CSV 文本解析、金额单位陷阱、批量核价摊分陷阱、写操作护栏、离线可复现演示 |

## 9. 离线模式与在线模式的关系

| | `demo` / `--offline` | `sync` | `--live` |
| --- | --- | --- | --- |
| 需要 Token | 否 | 是（一次性） | 是 |
| 数据来源 | `data/live_menu_snapshot.json`（真实同步）或 `menu_snapshot.json`（样例） | 真实 MCP | 真实 MCP |
| 求解器 | 完全相同 | — | 完全相同 |
| 菜单耗时 | 0ms | ~10s（之后走缓存） | 首跑 ~10s，缓存后 <1s |
| 核价 | 本地求和，标注「未核价」 | — | `calculate-price`，标注「已核价」 |
| 下单 | 永远预览 | — | `--confirm` 后真实创建 |

离线模式不是"假 demo"：默认读的 `data/live_menu_snapshot.json` 是从真实 MCP 同步下来的
**101 个餐品、57 条实测营养**，跑的是同一套求解器、同一套报告。这样评审不申请 Token
也能看到真实数据的结果，回归测试也不需要网络。
