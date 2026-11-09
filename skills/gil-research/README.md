# GIL Research

这是一般国际法检索工具的实际抓取版本。通过 HTTP/API 获取真实检索记录、可用正文和 PDF 页文本。本版本当前保留 8 个可选来源；未覆盖或受限部分均显式报告。`icj`、`echr`、`mpil`、`oril`、`unts`、`un_documents`、`opinio_juris`、`intl_law_observer` 已于 2026-11-09 拆分为独立技能，不再出现在 `--sources` 中。

## 机器可用性

机器可用：

- CJIL、EJIL、AJIL
- SSRN（Crossref 索引 + 摘要页无头回退）
- Google Scholar、Avalon

机器不可用：

- Oxford Reports（人工入口）
- 百链（人工入口）

`ICJ`、`HUDOC`、`MPIL`、`ORIL`、`UNTS`、`UN Documents`、`Opinio Juris`、`International Law Observer` 已分别由独立技能 `ICJSearcher`、`HUDOCSearcher`、`OPILSearcher`、`UNTSSearcher`、`UNDocsSearcher`、`OpinioJurisSearcher`、`IntlLawObserverSearcher` 承担；本工具不再把这些来源列入可选列表。`SSRN` 的检索索引仍是 Crossref，摘要页遇到 Cloudflare 时可无头读取。`Oxford Reports` 和 `百链` 需要机构登录。机器不可用不等于资料不存在。

```powershell
./run.ps1 search "state immunity" --sources all --limit 5 --out ./results.json
./run.ps1 search "jurisdictional immunities" --sources avalon --fetch --out ./avalon.json
./run.ps1 fetch "从结果 document_links 中选择的 PDF URL" --out ./text.json
./run.ps1 search "state immunity" --sources ssrn --limit 1 --fetch --out ./ssrn.json
./run.ps1 search "genocide" --sources cjil,ejil,ajil --limit 5 --out ./journals.json
./run.ps1 list
```

`heinonline` 渠道已于 2026-10-16 拆分为独立技能 [HeinOnlineSearcher](../HeinOnlineSearcher/SKILL.md)（来源控制台项 `skill.HeinOnlineSearcher`，与其它来源同等管理），机构会话仍由 `gdufs-auth-session` 提供。本工具包不再内置该渠道：检索、多字段高级检索与分节 PDF 下载都在该独立技能内完成。

`ejil_talk` 渠道已于 2026-10-16 拆分为独立技能 [EJILTalkSearcher](../EJILTalkSearcher/SKILL.md)（来源控制台项 `skill.EJILTalkSearcher`）。本工具包不再内置该渠道，检索 EJIL: Talk! 时直接调用该独立技能；它在来源清单中与其它来源同等管理。

`mpil` 与 `oril` 已拆分为独立技能 [OPILSearcher](../OPILSearcher/SKILL.md)；本工具不再内置这两个来源。`oxford_reports` 保留为人工入口，用于整库订阅路径。

`unts`、`un_documents`、`opinio_juris`、`intl_law_observer` 已拆分为独立技能 [UNTSSearcher](../UNTSSearcher/SKILL.md)、[UNDocsSearcher](../UNDocsSearcher/SKILL.md)、[OpinioJurisSearcher](../OpinioJurisSearcher/SKILL.md)、[IntlLawObserverSearcher](../IntlLawObserverSearcher/SKILL.md)。

运行入口：本目录内的 `run.ps1`。分发包不记录安装目录或开发机路径。`run.ps1` 优先使用技能内 Python 3.12 环境，不会在检索时联网安装依赖。其他机器用 Python 3.12+ 和 `requirements.txt`；Cloudflare 回退还要求本机 Chrome、Chromium 或 Edge。

结果类型及状态：

- `retrieved_metadata`：实际从 API 或官方检索页取得的记录。
- `retrieved_text`：已经取得正文或 HTML/PDF 文本，须核对 `content_scope`。
- `unavailable` / `fetch_error`：请求失败，保留错误，不能理解为无相关资料。
- `fallback`：替代语料库，具体范围写在 `scope`。
- `manual`：只有人工入口，结果数组为空，不伪装成检索命中。

2026-10-14 复核时 11 个渠道取得真实记录，其中两个博客返回正文；同日接入的 `mpil` 与 `oril` 渠道也已用真实检索与取全文验证。2026-10-15 补测确认 EJIL: Talk! 的 REST API 和 RSS/feed 路径在当前网络均被站点级 403 拦截，而无头 Chrome 打开 `/?s=war+crime` 可返回 142 页真实搜索结果，因此该渠道增加了浏览器 HTML 回退。HUDOC 先建立会话再查询，`mpil`/`oril` 使用浏览器式 UA 并复用会话 Cookie；这些站点仍可能按 IP 或频率返回 403/challenge。ODS 可按文号取得 PDF，关键词检索仍不完整；官方 UNTS Advanced Search 页面可用，但当前适配器仍只扫描 MTDSG。Crossref 元数据与部分摘要不等于文章全文。2026-10-16：EJIL: Talk! 渠道拆分到独立技能 `EJILTalkSearcher`，本工具包移除 `ejil_talk`；同日 HeinOnline 渠道拆分到独立技能 `HeinOnlineSearcher`，本工具包移除 `heinonline`。2026-11-02：ICJ 接入官方 Document Search；随后把同一无头核心扩展给 HUDOC JSON API 和 SSRN 摘要页。2026-11-09：`icj`、`echr`、`mpil`、`oril`、`unts`、`un_documents`、`opinio_juris`、`intl_law_observer` 拆分到对应独立技能；本工具移除这八个来源。历史验证记录保留在 `references/validation.md`。

原始响应与哈希自动保存到当前工作目录 `.gil-cache`。同一查询加 `--offline` 可离线重放；`--cache-ttl 0` 刷新。`--offset` 与结果 `pagination.next_offset` 配合翻页；`--format markdown` 输出可读正文。检索结果默认 UTF-8 JSON，结构为 `channels[].results`。

## 实测效果（2026-11-09）

以下命令与结果来自本机 `~/.codex/skills/gil-research` 的实网运行；检索日期 2026-11-09（Asia/Shanghai）。

```powershell
& .\run.ps1 search 'state immunity' --sources cjil,ejil,ajil,google_scholar,ssrn,avalon --limit 3
```

| 来源 | 状态 | total | 代表结果 |
| --- | --- | --- | --- |
| cjil | ok | 62 | Foreign State Immunity Law of China: A Preliminary Appraisal — Xinxiang Shi（2024-06-01），<https://doi.org/10.1093/chinesejil/jmae017> |
| ejil | ok | 124 | State Immunity and Judicial Countermeasures — Marco Longobardo（2021-04-23），<https://doi.org/10.1093/ejil/chab013> |
| ajil | ok | 735 | State responsibility in private civil action—sovereign immunity—immunity for jus cogens violations—belligerent occupation—peace treaties — Bernard H. Oxman, Ilias Bantekas（1998-10），<https://doi.org/10.2307/2998144> |
| google_scholar | unavailable | — | 未返回结果容器；保留为不可用，不写作零命中 |
| ssrn | fallback | 20,527 | State-Owned Corporations and State Immunity in Europe — Stefan Kirchner（2006），<https://doi.org/10.2139/ssrn.880718> |
| avalon | ok | — | Convention Between the United States and Belgium Concerning the Rights, Privileges, and Immunities of Consuls: December 5, 1868，<https://avalon.law.yale.edu/19th_century/bel008.asp> |

> 期刊来源是 Crossref 元数据和可用摘要，不是全文；SSRN 的 `fallback` 表示用 Crossref DOI prefix 10.2139 作为检索索引，摘要页可能再走无头回退。Avalon 是目录标题匹配后直接取文档，不是全库全文检索。Google Scholar 的 `unavailable` 是本次访问失败，不代表其索引中没有相关资料。
