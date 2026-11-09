# InternationalLawRetrieval

国际法检索工具本体：`icl-research`、`gil-research`、`international-law-manual-research` 三个核心 skill，以及来源目录和校验工具。

本仓库是**聚合器/工作流本体**，不是单站来源技能。单站检索技能（`LegalToolsSearcher`、`ICCSearcher`、`OPILSearcher`、`ICRCSearcher`、`ICJSearcher`、`HUDOCSearcher`、`ICDSearcher`、`IRMCTCldSearcher`、`UCRSearcher`、`ICTYSearcher`、`ICTRSearcher`、`UNTSSearcher`、`UNDocsSearcher`、`CILRAPSearcher`、`OpinioJurisSearcher`、`IntlLawObserverSearcher` 等）各自在 `HuiwowICCSkills` 下有独立公开仓库。

> `skills/*/SKILL.md` 中的 `../<Skill>/SKILL.md` 相对链接按“所有 skill 都安装在同一个 `~/.codex/skills` 目录”编写；单独克隆本仓库时不会包含这些独立 skill，相关链接可能指向不存在的路径。按 README 的安装步骤把独立 skill 一并放入 `~/.codex/skills` 后即可正常解析。

## 目录

| 路径 | 用途 |
|---|---|
| `skills/icl-research/` | 国际刑法聚合检索；当前 4 个可选渠道：`jicj`、`cmn`、`toaep`、`klamberg`；已拆来源保留为 `legacy_channels` |
| `skills/gil-research/` | 一般国际法聚合检索；当前 8 个可选来源，含 2 个手动入口 |
| `skills/international-law-manual-research/` | 登录、订阅全文、UCR/UNTS/ODS 等人工补检交接 |
| `catalog/source-catalog.json` | 来源 ID、名称、说明、分组、标签和默认启用状态 |
| `catalog/source_catalog.py` | 来源目录校验与查询工具 |
| `catalog/source-catalog.md` | 来源目录维护说明 |

`catalog/source-catalog.json` 当前为 **37 项、34 项默认启用**；来源控制台是单独发行物，见 `HuiwowICCSkills/InternationalLawSourceConsole`。

## 外部通用联网技能（不随本仓库打包）

`catalog` 的 `local-skills` 分组列出的是四个通用联网/浏览器技能。它们不随本工具、单站 skill 或控制台仓库发布，需从上游单独获取：

| 技能 | 获取方式 |
|---|---|
| `multi-search-engine` | Codex 技能市场 / SkillHub 搜索同名技能（本机记录版本 2.1.3）；公开实现参考 <https://github.com/NachaFromMars/multi-search-engine>，上游版本可能不同 |
| `web-access` | <https://github.com/eze-is/web-access>（MIT） |
| `agent-browser` | <https://github.com/vercel-labs/agent-browser>；安装 `npm i -g agent-browser && agent-browser install` |
| `spider-mind` | <https://github.com/qunliu031208-debug/spider-mind>；或通过 `skill-installer` 安装 |

这些技能只影响通用网页搜索和浏览器自动化；`icl-research`、`gil-research` 及各单站检索技能的核心 HTTP/API 路径不依赖它们。`catalog` 中的 `local-skills` 只是本机能力记录，不代表本仓库包含这些技能。

## 安装

Windows PowerShell：

```powershell
git clone https://github.com/HuiwowICCSkills/InternationalLawRetrieval.git "$env:USERPROFILE\Documents\InternationalLawRetrieval"
Copy-Item -Recurse -Force `
  "$env:USERPROFILE\Documents\InternationalLawRetrieval\skills\*" `
  "$env:USERPROFILE\.codex\skills\"

python -X utf8 -m pip install -r "$env:USERPROFILE\Documents\InternationalLawRetrieval\skills\icl-research\scripts\requirements.txt"
python -X utf8 -m pip install -r "$env:USERPROFILE\Documents\InternationalLawRetrieval\skills\gil-research\requirements.txt"
```

`gil-research` 的 Cloudflare 回退需要其 `vendor/` 目录和 `requirements.txt`；`ICJSearcher`/`HUDOCSearcher` 的无头回退依赖在各自仓库的 requirements 中。

## 校验

```powershell
python -X utf8 .\catalog\source_catalog.py validate --path .\catalog\source-catalog.json

Push-Location .\skills\icl-research
python -X utf8 -m unittest discover -s .\scripts -p 'test_*.py' -q
Pop-Location

Push-Location .\skills\gil-research
python -X utf8 -m unittest test_gil_research -q
Pop-Location

Push-Location .\skills\international-law-manual-research
python -X utf8 -m unittest discover -s .\scripts -p 'test_*.py' -q
Pop-Location
```

## 边界

- `icl-research` / `gil-research` 是聚合器；已拆来源在各自单站 skill 中维护，聚合器只保留历史适配器配置用于回归测试和兼容 `fetch`。
- `icl-research` 的 `list` 会区分 `channels`（当前可选）与 `legacy_channels`；`search --channels` 不接受 legacy ID。
- `gil-research` 的 `--sources all` 只运行当前 8 个 active 来源。
- 来源目录不包含正文内容；检索结果、全文和访问限制由对应 skill/来源负责。
- `gdufs-auth-session` / `HeinOnlineSearcher` 的登录态不随仓库发布，需要在新机器上重新登录；`HUDOCSearcher` / `ICJSearcher` 和 `gil-research` 的无头回退需要 Chrome 及对应 requirements 中的浏览器依赖。

## 实测效果（2026-11-09）

以下命令与结果来自本机 `~/.codex/skills` 下同名 skill 的实网运行；检索日期 2026-11-09（Asia/Shanghai），输出为该次运行实际返回的 JSON 报告。

### `icl-research`：国际刑法聚合检索

```powershell
& .\run.ps1 search 'genocide' --channels jicj,cmn,toaep --limit 5
```

本次 `jicj` 返回 `status=ok`、5 条 Crossref 元数据；`toaep` 返回 `status=partial`（bounded crawl，`exhaustive=false`）并命中 10 条 TOAEP 目录/PDF 记录；`cmn` 返回 `status=partial`，只取到站点首页和两份介绍性 PDF，没有文章级命中。代表性结果：

| 渠道 | 题名 | 作者 / 日期 | 链接 |
| --- | --- | --- | --- |
| jicj | Genocide, Complicity in Genocide and International v. Domestic Jurisdiction | Harmen G. van der Wilt；2006-05-01 | <https://doi.org/10.1093/jicj/mql014> |
| jicj | 'Complicity in Genocide' versus 'Aiding and Abetting Genocide': Construing the Difference in the ICTR and ICTY Statutes | C. Eboe-Osuji；2005-03-01 | <https://doi.org/10.1093/jicj/3.1.56> |
| jicj | Divergent Approaches to Determining Responsibility for Genocide: The Darfur Commission of Inquiry and the ICJ's Judgment in the Genocide Case | A. B. Loewenstein, S. A. Kostas；2007-09-01 | <https://doi.org/10.1093/jicj/mqm049> |
| toaep | Darfur’s Second Genocide: Breaking the Cycle of Violence and Impunity in Sudan | TOAEP 政策简报 PDF | <https://www.toaep.org/pbs-pdf/162-iliopoulos/> |
| toaep | A Critical Assessment of the Exhibition ‘Burma’s Path to Genocide’ at the US Holocaust Memorial Museum | TOAEP 政策简报 PDF | <https://www.toaep.org/pbs-pdf/130-tonkin/> |

> `jicj` 是 Crossref 书目元数据，不含出版社全文；`toaep` 和 `cmn` 是有界爬取，命中数不是全站统计。`cmn` 本次未取得文章级结果，保留 `partial` 状态，不能据此认为 CMN 没有相关资料。

### `gil-research`：一般国际法聚合检索

```powershell
& .\run.ps1 search 'state immunity' --sources cjil,ejil,ajil,google_scholar,ssrn,avalon --limit 3
```

六个来源的实际状态与代表结果如下（`total` 为各来源报告值；Google Scholar 本次不可用，SSRN 走 Crossref 回退）：

| 来源 | 状态 | total | 代表结果 |
| --- | --- | --- | --- |
| cjil | ok | 62 | Foreign State Immunity Law of China: A Preliminary Appraisal — Xinxiang Shi（2024-06-01），<https://doi.org/10.1093/chinesejil/jmae017> |
| ejil | ok | 124 | State Immunity and Judicial Countermeasures — Marco Longobardo（2021-04-23），<https://doi.org/10.1093/ejil/chab013> |
| ajil | ok | 735 | State responsibility in private civil action—sovereign immunity—immunity for jus cogens violations—belligerent occupation—peace treaties — Bernard H. Oxman, Ilias Bantekas（1998-10），<https://doi.org/10.2307/2998144> |
| google_scholar | unavailable | — | 未返回结果容器；保留为不可用，不写作零命中 |
| ssrn | fallback | 20,527 | State-Owned Corporations and State Immunity in Europe — Stefan Kirchner（2006），<https://doi.org/10.2139/ssrn.880718> |
| avalon | ok | — | Convention Between the United States and Belgium Concerning the Rights, Privileges, and Immunities of Consuls: December 5, 1868，<https://avalon.law.yale.edu/19th_century/bel008.asp> |

> 期刊来源是 Crossref 元数据和可用摘要，不是全文；SSRN 的 `fallback` 表示用 Crossref DOI prefix 10.2139 作为检索索引，摘要页可能再走无头回退。Avalon 是目录标题匹配后直接取文档，不是全库全文检索。

### `international-law-manual-research`：人工补检交接

```powershell
python -X utf8 '<skill-dir>/scripts/handoff.py' --input './icl-research.json' --format markdown --out './manual-tasks.md'
```

以本次 `icl-research` 的 `genocide` 报告为输入，实际生成 1 项人工待办（`icl:jicj` 期刊全文补取）和 4 项“可先自动处理”的后续动作（`icl:cmn`、`icl:toaep` 各 2 项）。清单明确标注所有任务均未执行，`pending` 不等于已取得全文。
