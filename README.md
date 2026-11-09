# InternationalLawRetrieval

国际法检索工具本体：`icl-research`、`gil-research`、`international-law-manual-research` 三个核心 skill，以及来源目录和校验工具。

本仓库是**聚合器/工作流本体**，不是单站来源技能。单站检索技能（`LegalToolsSearcher`、`ICCSearcher`、`OPILSearcher`、`ICRCSearcher`、`ICJSearcher`、`HUDOCSearcher`、`ICDSearcher`、`IRMCTCldSearcher`、`UCRSearcher`、`ICTYSearcher`、`ICTRSearcher`、`UNTSSearcher`、`UNDocsSearcher`、`CILRAPSearcher`、`OpinioJurisSearcher`、`IntlLawObserverSearcher` 等）各自在 `HuiwowICCSkills` 下有独立私有仓库。

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
