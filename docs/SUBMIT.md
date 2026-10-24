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

## 三、发报名 Issue

**一键预填（推荐）**：<https://github.com/M-China/mcd-developer-innovation-challenge/issues/new?title=%E3%80%90%E5%8F%82%E8%B5%9B%E7%94%B3%E8%AF%B7%E3%80%91%E5%8D%88%E9%A4%90%E6%B5%81%E6%B0%B4%E7%BA%BF%20mcd-lunch-ci&body=%E3%80%90%E5%8F%82%E8%B5%9B%E7%94%B3%E8%AF%B7%E3%80%91%E9%A1%B9%E7%9B%AE%E5%90%8D%E7%A7%B0%EF%BC%9A%E5%8D%88%E9%A4%90%E6%B5%81%E6%B0%B4%E7%BA%BF%20mcd-lunch-ci%E9%A1%B9%E7%9B%AE%E5%9C%B0%E5%9D%80%EF%BC%9Ahttps%3A//github.com/MrBean2067/mcd-lunch-ci%E9%A1%B9%E7%9B%AE%E7%AE%80%E4%BB%8B%EF%BC%9A%E6%8A%8A%E5%9B%A2%E9%98%9F%E7%82%B9%E5%8D%88%E9%A4%90%E4%BB%8E%E7%BE%A4%E8%81%8A%E6%8B%89%E9%94%AF%E5%8F%98%E6%88%90%E4%B8%80%E6%9D%A1%207%20%E9%98%B6%E6%AE%B5%20CI%20%E6%B5%81%E6%B0%B4%E7%BA%BF%EF%BC%9A%E6%AF%8F%E4%B8%AA%E4%BA%BA%E5%86%99%E6%B8%85%E9%A2%84%E7%AE%97%E3%80%81%E5%BF%8C%E5%8F%A3%E3%80%81%E7%83%AD%E9%87%8F%E4%B8%8A%E9%99%90%EF%BC%8C%E6%B1%82%E8%A7%A3%E5%99%A8%E7%94%A8%E5%B8%95%E7%B4%AF%E6%89%98%E5%89%8D%E6%B2%BF%20%2B%20%E6%95%B4%E6%95%B0%E8%83%8C%E5%8C%85%20DP%20%E7%BB%99%E5%87%BA%E5%9C%A8%E6%80%BB%E9%A2%84%E7%AE%97%E5%86%85%E7%A4%BE%E4%BC%9A%E7%A6%8F%E5%88%A9%E6%9C%80%E4%BC%98%E7%9A%84%E6%96%B9%E6%A1%88%EF%BC%8C%E8%B0%83%20MCP%20%E6%A0%B8%E4%BB%B7%E5%90%8E%E9%BB%98%E8%AE%A4%E5%8F%AA%E5%87%BA%E9%A2%84%E8%A7%88%E3%80%81%E5%8A%A0%20--confirm%20%E6%89%8D%E4%B8%8B%E5%8D%95%E3%80%82%E6%8A%A5%E5%91%8A%E4%BC%9A%E8%AF%B4%E6%B8%85%E3%80%8C%E8%B0%81%E5%A6%A5%E5%8D%8F%E4%BA%86%E3%80%81%E5%B7%AE%E5%A4%9A%E5%B0%91%E9%92%B1%E3%80%8D%EF%BC%8C%E5%B9%B6%E7%BB%99%E5%87%BA%E9%A2%84%E7%AE%97%E2%80%94%E6%BB%A1%E6%84%8F%E5%BA%A6%E5%89%8D%E6%B2%BF%E3%80%82%E5%BF%8C%E5%8F%A3/%E7%83%AD%E9%87%8F/%E9%A2%84%E7%AE%97%E6%98%AF%E4%BB%A3%E7%A0%81%E9%87%8C%E7%9A%84%E7%A1%AC%E8%BF%87%E6%BB%A4%EF%BC%8C%E6%A8%A1%E5%9E%8B%E6%97%A0%E6%9D%83%E6%94%BE%E8%A1%8C%E8%BF%87%E6%95%8F%E5%8E%9F%EF%BC%9B%E6%97%A0%20Token%20%E4%B9%9F%E8%83%BD%E8%B7%91%E9%80%9A%E5%85%A8%E6%B5%81%E7%A8%8B%E3%80%82%E5%90%8C%E6%97%B6%E6%89%93%E5%8C%85%E4%B8%BA%E5%8F%AF%E7%9B%B4%E6%8E%A5%E5%AE%89%E8%A3%85%E7%9A%84%20WorkBuddy%20Skill%EF%BC%88skill/mcd-lunch-ci/SKILL.md%EF%BC%89%E3%80%82%E5%9F%BA%E4%BA%8E%E9%BA%A6%E5%BD%93%E5%8A%B3%20MCP%EF%BC%9Aquery-nearby-stores%E3%80%81query-meals%E3%80%81query-meal-detail%E3%80%81list-nutrition-foods%E3%80%81query-store-coupons%E3%80%81calculate-price%E3%80%81create-order%E3%80%82>

点开标题和正文都已经填好，扫一眼确认仓库地址是你的，直接点 Submit 即可。

下面是不用链接时的手动版。

到官方仓库 <https://github.com/M-China/mcd-developer-innovation-challenge/issues> 新建 Issue。

**格式有两个坑，官方明确提醒过：**

1. 标题和正文的标签之间**不要换行**；
2. 项目地址**不要写成 Markdown 链接**，贴裸链接。

把下面这条**整段复制**，替换成你的仓库地址即可（直接一行，别按回车）：

```
【参赛申请】项目名称：午餐流水线 mcd-lunch-ci项目地址：https://github.com/MrBean2067/mcd-lunch-ci项目简介：把团队点午餐从群聊拉锯变成一条 7 阶段 CI 流水线：每个人写清预算、忌口、热量上限，求解器用帕累托前沿 + 整数背包 DP 给出在总预算内社会福利最优的方案，调 MCP 核价后默认只出预览、加 --confirm 才下单。报告会说清「谁妥协了、差多少钱」，并给出预算—满意度前沿。忌口/热量/预算是代码里的硬过滤，模型无权放行过敏原；无 Token 也能跑通全流程。同时打包为可直接安装的 WorkBuddy Skill（skill/mcd-lunch-ci/SKILL.md）。基于麦当劳 MCP：query-nearby-stores、query-meals、query-meal-detail、list-nutrition-foods、query-store-coupons、calculate-price、create-order。
```

Issue 标题可以写：`【参赛申请】午餐流水线 mcd-lunch-ci`

提交后系统会在 Issue 下回复报名成功/失败原因。失败就按原因改完重新发。

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
