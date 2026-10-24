# 报名提交清单（照着做就行）

> 截止时间：**2026-10-25 23:59**（北京时间）。定榜用 **2026-10-26 00:00** 的 Star 数。

## 一、发布前自查（5 项，逐条打勾）

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
- [ ] **推送到 GitHub**（只剩这一步）

## 二、推到 GitHub

本地仓库**已经全部就绪**：2 条提交、39 个文件、作者是 `MrBean2067`、remote 已指向 `https://github.com/MrBean2067/mcd-lunch-ci.git`、`.env` 未被跟踪、README 占位符已替换。

远程仓库也已确认存在（public、空仓库、默认分支 `main`）。**只剩推送这一步**：

```bash
cd mcd-lunch-ci
git push -u origin main
```

推送时会要求凭据：

- **用 Git Credential Manager**：会弹浏览器让 GitHub 授权，授权完自动存凭据（推荐，最省事）；
- **手填**：用户名填 `MrBean2067`，密码填 **Personal Access Token**（不是账号密码，GitHub 早就禁了密码推送）。Token 在 <https://github.com/settings/tokens> 生成，勾 `repo` 即可。

如果 push 被拒（`rejected - fetch first`），说明建仓库时勾了 README/gitignore，用：

```bash
git pull --rebase origin main
git push -u origin main
```

推完确认三件事：仓库能**匿名打开**（退出登录或用无痕窗口）、README 顶部 hero 图正常显示、`docs/hero.svg` 路径没写错。

## 三、发报名 Issue

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
