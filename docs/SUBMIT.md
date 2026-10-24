# 报名提交清单（照着做就行）

> 截止时间：**2026-10-25 23:59**（北京时间）。定榜用 **2026-10-26 00:00** 的 Star 数。

## 一、发布前自查（逐条对照）

- [x] `README.md` 存在，且文件名大小写完全一致
- [x] `CONTEST_DECLARATION.md` 存在，**内容与官方仓库原文件一字不差**（本仓库已原样放入，不要改）
- [x] `MCP_INTEGRATION.md` 存在
- [x] 源代码可运行：`python -m mcd_lunch_ci demo` 能跑出结果（40 个测试全绿）
- [x] `workbuddy.md` 存在（换 3000 WorkBuddy 积分用）
- [x] `skill/mcd-lunch-ci/SKILL.md` 存在（对应活动「开发 Skill」的要求）
- [x] 仓库里**没有任何真实 Token**（已扫描，Token 只在未跟踪的 `.env`）
- [x] 仓库是 **Public**
- [x] 仓库创建时间 2026-10-24（在 2025-12-25 之后）
- [x] README 里的 `<you>` 占位符已替换成 `MrBean2067`
- [x] 本地已有 2 条提交，作者为 `MrBean2067`，remote 已指向 `MrBean2067/mcd-lunch-ci`
- [x] **已推送到 GitHub**（2026-10-24 21:10，3 条提交 / 39 个文件）

## 二、推到 GitHub（已完成）

已推送成功：`main` 分支 3 条提交、39 个文件，作者 `MrBean2067`。

**这台机器推 GitHub 会失败，原因和绕法记在这里，以后改代码还要推：**

`github.com` 直连被重置（`Connection was reset` / `CONNECT tunnel failed 502`），
但系统里装了代理，`127.0.0.1:10808` 是 **SOCKS5** 端口，走它就能通。仓库级配置已经设好：

```bash
git config http.proxy "socks5h://127.0.0.1:10808"
git config https.proxy "socks5h://127.0.0.1:10808"
```

之后 `git push` 直接可用（凭据由 Git Credential Manager 提供，已缓存）。
如果哪天代理关了导致 push 失败，清掉配置即可：

```bash
git config --unset http.proxy
git config --unset https.proxy
```

提示：`socks5h` 的 `h` 表示域名也交给代理解析，写成 `socks5://` 有时会解析失败。

## 三、发报名 Issue（已提交，但正文需修正）

已提交：**Issue #1286**
<https://github.com/M-China/mcd-developer-innovation-challenge/issues/1286>
状态：open，等待系统校验回复。

**出过的问题（务必知道）**：一开始用了 `?title=&body=` 预填链接，URL 共 2285 字符，
粘贴过程中被截到约 687 字符，结果 Issue 正文只提交了前 **108 个字**，
断在「7 阶段 CI 流水线」，项目简介是半句话。长 URL 传中文正文不可靠，**以后别用**。

**修正步骤**：

1. 打开上面的 Issue，右上角 **Edit**
2. 正文整体替换为 `docs/ISSUE_BODY.txt` 的**全部内容**（就一行，453 字）
3. 保存

**格式红线**（官方明确提醒过，违反会导致校验失败）：

1. 标签和内容之间**不要换行**——`【参赛申请】`、`项目名称：`、`项目地址：`、`项目简介：`
   以及各自的内容，全部挤在同一行
2. 项目地址**不要写成 Markdown 链接**，贴裸链接 `https://github.com/MrBean2067/mcd-lunch-ci`

`docs/ISSUE_BODY.txt` 是正文的唯一来源，要改内容只改这个文件。

系统会在 Issue 下回复报名成功或失败原因。失败就按原因改完重新发。

## 四、拉 Star（这一步不做，前面都白做）

排名只看 Star 数，**Star 为 0 连榜都进不去**，且第 100 名门槛已经是 44 星。发布后 24 小时是关键窗口：

1. **标题里带具体数字**比任何形容词都有效。参考：`8 个人点午饭吵了 20 分钟，我把它做成了一条 CI 流水线`
2. 首屏必须有能一眼看懂的产物：README 里的 hero 图和终端输出已经是这个作用，别删。
3. 发出去的渠道（按性价比排序）：
   - 掘金 / 少数派 / V2EX（分享创造节点）
   - 即刻、小红书（带终端截图和 hero 图）
   - 公司/学校的技术群、同事群（顺手说一句"以后点午饭用它"）
4. 凡是有人问"怎么用"，先让他跑 `python -m mcd_lunch_ci demo`——**不需要 Token**，30 秒能看到结果，这是他点 Star 的最短路径。
5. 实时链路已联调通过，可以直接把 `doctor` 的输出贴出来当证据（见第五节）。

## 五、实时链路已经联调通过（2026-10-24）

Token 已实测接入，`doctor` 四步全绿、`run --live` 的官方核价与本地求和分毫不差。复现：

```bash
# 1) 把 Token 写进项目根目录 .env（已在 .gitignore 里）
echo 'MCD_MCP_TOKEN=你的Token' > .env

# 2) 自检：连通性 → 门店 → 菜单 → 核价
python -m mcd_lunch_ci doctor

# 3) 想换城市/门店：
python -m mcd_lunch_ci doctor --city 上海市 --keyword 静安寺
python -m mcd_lunch_ci run --live --city 北京市 --keyword 国贸

# 4) 从真实 MCP 同步一份菜单快照（之后零 Token 也能用真数据）
python -m mcd_lunch_ci sync --refresh
```

实测结果：`mcd-mcp 1.0.0`、35 个工具、门店「麦当劳深圳同方信息港餐厅」102 个餐品、57 条实测营养、
8 人 ¥200 方案应付 ¥199.40，与 `calculate-price` 官方金额完全一致。

如果换门店后某些餐品解析失败，把 `out/live-trace.json` 留下来对照
[`docs/MCP_FIELD_MAP.md`](MCP_FIELD_MAP.md)——所有字段名、单位、坑都记录在那份实测表里，
不靠猜。

## 六、别忘了

- 奖品兑换与信息提交截止 **2026-11-14**，获奖邮件会发到 GitHub 注册邮箱；注册邮箱没公开的，注意 GitHub OAuth 授权弹窗。
- 榜单在官方仓库的 `RANKING.md`，定时更新，可以自己盯着看排名。
