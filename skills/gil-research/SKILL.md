---
name: gil-research
description: 检索一般国际法的期刊、百科、博客、条约和判例，使用公开 API、直接 HTTP 和本地缓存返回真实记录。
---

# General International Law Research

使用当前 skill 目录内的 `gil_research.py`。`<skill-dir>` 代表本 SKILL.md 所在目录。Windows 下用 `run.ps1` 调用，它会依次探测：本 skill 内`venv` → Codex bundled runtime → WorkBuddy 托管 Python → PATH 上的 `python`；普通 Python 需先安装 `requirements.txt`。缓存保存在工作目录的 `.gil-cache`，不写入用户本地资料库。

> **2026-11-09 拆分**：`icj`、`echr`、`mpil`、`oril`、`unts`、`un_documents`、`opinio_juris`、`intl_law_observer` 已拆分为独立技能 `ICJSearcher`、`HUDOCSearcher`、`OPILSearcher`、`UNTSSearcher`、`UNDocsSearcher`、`OpinioJurisSearcher`、`IntlLawObserverSearcher`。本工具的 `--sources` 只保留 8 个可选来源；`resources.json` 中这些条目标记为 `active:false`，仅作历史适配器配置保留。

首次在同一会话使用本技能时，先给用户一句简要提示：当前有 8 个可选来源，其中 `Oxford Reports`、百链仍只是人工入口、需要机构登录；其余 6 个可直接检索。SSRN 已接入默认无头的 Cloudflare 回退，不需要人工打开浏览器。同一会话只提示一次，不要每次检索重复。

```powershell
& '<skill-dir>/run.ps1' search 'state immunity' --sources all --limit 5 --out './gil-results.json'
& '<skill-dir>/run.ps1' search 'jurisdictional immunities' --sources avalon --fetch --out './avalon.json'
& '<skill-dir>/run.ps1' search 'state immunity' --sources ssrn --limit 1 --fetch --out './ssrn.json'
& '<skill-dir>/run.ps1' search 'genocide' --sources cjil,ejil,ajil --limit 5 --out './journals.json'
& '<skill-dir>/run.ps1' list
```

`heinonline` 渠道已拆分为独立技能 [HeinOnlineSearcher](../HeinOnlineSearcher/SKILL.md)（来源控制台项 `skill.HeinOnlineSearcher`，与其它来源同等管理），机构会话仍由 [gdufs-auth-session](../gdufs-auth-session/SKILL.md) 提供。本工具包不再内置该渠道：检索、多字段高级检索与分节 PDF 下载都在该独立技能内完成。

`ejil_talk` 渠道已拆分为独立技能 [EJILTalkSearcher](../EJILTalkSearcher/SKILL.md)（来源控制台项 `skill.EJILTalkSearcher`，与其它来源同等管理）。本工具包不再内置该渠道：检索 EJIL: Talk! 时直接调用该独立技能。

`mpil` 与 `oril` 的检索、条目页读取、OPIL 会话 Cookie 和分面参数校验现已全部由 [OPILSearcher](../OPILSearcher/SKILL.md) 承担；本工具不再把这两个来源列入 `--sources`。

`unts`、`un_documents`、`opinio_juris`、`intl_law_observer` 分别由 [UNTSSearcher](../UNTSSearcher/SKILL.md)、[UNDocsSearcher](../UNDocsSearcher/SKILL.md)、[OpinioJurisSearcher](../OpinioJurisSearcher/SKILL.md)、[IntlLawObserverSearcher](../IntlLawObserverSearcher/SKILL.md) 承担；本工具不再把这四个来源列入 `--sources`。

1. 把中文法律问题转成英文关键词、案件名、文号等变体再检索。工具支持 UTF-8 输入输出，但不自动翻译。API 使用各站自己的相关性规则；目录检索要求所有关键词命中标题，带简单英文单复数归一化。
2. 用户要求全部渠道时用 `--sources all`，保留每个渠道的 `status`、`scope`、`warnings`。不能省略失败渠道，也不能把连接失败当作无相关资料。
3. 博客 API 默认返回正文；期刊返回 DOI 元数据及可用摘要。`--fetch` 继续获取返回的页面；页面可能只是出版商或案件介绍，不能据此宣称取得文章或判决全文。
4. 从 `document_links` 选择具体原始 PDF，再运行 `fetch '<实际返回的URL>' --out './document.json'`。保留 `pages[].page`（PDF位置，不是印刷页码）、`ocr_needed`、来源 URL、抓取时间和 SHA-256。扫描页缺文字时需明确说明。
5. 如果缺少高位阶直接裁判，把“争点在相关案件中是否被提出但未获裁判”作为独立检索目标。通常先用书状或程序记录确认争点已提交，再以裁判全文和最终处置确认未获处理；若裁判自身清楚显示争点已进入其视野，也可直接判断。之后才可把“明示无须裁判”“以其他理由回避”或“仅提及未处理”列为检索结果，并说明段落与未裁判原因；不能证明争点曾被提出时，不能推定法院默许或留有空间。
6. 用实际正文核对引文与段落，不用搜索摘要代替原文。法律文件、博客、新闻、摘要与认证文本需分别表述。每项实质性检索结果都要交代关键上下文和 reasoning，不能只写结论。

**结果呈现最低标准**

- 判例或法院/法庭决定：说明法院或机构、日期和文书号、程序阶段、争议问题、裁判结论、关键理由及实际处理范围；如有单独/反对意见、后续处理或不同的拘束力层级，应一并区分。
- 学术观点或评论：说明作者或机构、核心论点、主要论证链、依赖的材料或方法，以及作者自设的限制或反论；博客和评注要明确标为学术或评论材料，不能写成一手权威。
- 只能核验题目、元数据或摘要时，明确说明这一边界，不能据标题或摘要补写法院或作者的完整推理。批量结果应逐项保留一句关键上下文/reasoning，或设置相应栏目。

当前能力及证据边界见 [resources.json](resources.json) 和 [验证说明](references/validation.md)：

- `ok` 表示该适配器成功，不表示穷尽；`partial` 有抓取或覆盖缺口；`fallback` 是明确标注的替代语料；`unavailable` 失败；`skipped` 表示本次会话未启用该来源；`manual` 未抓取。
- `retrieved_metadata` 不是全文；`retrieved_text` 只表示已取得所声明范围的文本。`document` 是单独抓取结果，`fetch_error` 不能忽略。
- `mpil`、`oril`、`icj`、`echr`、`unts`、`un_documents`、`opinio_juris`、`intl_law_observer` 已拆分为独立技能，不再属于本工具的可选来源；`oxford_reports` 仍保留为整库订阅的人工入口。
- SSRN 搜索仍以 Crossref 的 `10.2139` DOI 索引为来源。对返回的 `doi.org/10.2139/ssrn.<id>` 或 SSRN `abstract_id` 页面执行 `--fetch` 时，先规范化为 SSRN 摘要页；Cloudflare challenge 后由无头 Chrome 取得公开摘要正文。该路径不承诺自动取得 SSRN 下载按钮后的论文 PDF。
- `unts`、`un_documents` 的 UNTS/UN 文件检索边界见各自的独立技能文档。
- SSRN 的 Crossref 索引不覆盖未登记 DOI 的论文；期刊严格按 ISSN 隔离。SSRN 摘要页的无头回退只恢复公开页面，订阅或站点自身下载门槛仍需按实际响应报告。
- SSRN 的公开摘要页回退仍可能按 IP、频率或会话状态返回 403/challenge；回退失败才报告不可用，不能据此断言资料不存在。Oxford Reports 与百链仍仅保留人工入口。登录、订阅、原站补检与完整库补检的操作归独立技能 `international-law-manual-research`，见 [人工补检入口](../international-law-manual-research/SKILL.md)。报告的 `manual_handoff` 是条件性转交提示，不表示必须人工执行。HTTP 403 不重试；超时/连接失败最多重试一次。

`--offset` 按结果位置翻页；优先使用返回的 `pagination.next_offset`。Google Scholar 每次最多读取所在页，可能不足指定条数。`--max-pages` 限制目录页数量，结果说明实际范围。

`--offline` 只读缓存，缺失即失败；`--cache-ttl 0` 强制刷新。原始成功响应和哈希元数据一并缓存，可复核；最大响应 40 MiB。检索 JSON 使用 schema_version 2，顶层 `channels` 包含每个渠道的结果和状态，已不沿用旧版“策略列表”。
