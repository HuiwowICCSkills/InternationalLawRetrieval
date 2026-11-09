# 国际法检索工具

本目录提供国际法检索工具及其来源目录：

- `source-catalog.json`：来源 ID、名称、说明、分组和默认启用状态；
- `source_catalog.py`：来源目录校验与查询工具；
- `source-catalog.md`：来源目录维护说明。

控制台是单独发行物，位于 `search-sources-control/`，不随本工具一起打包。
控制台通过外部 `--catalog` 参数读取本工具提供的来源目录。

可外接网页搜索和 `web_fetch` API；本工具默认不内置。

## 发布

本工具及三个核心 skill 已发布为私有仓库：
<https://github.com/HuiwowICCSkills/InternationalLawRetrieval>

仓库结构：`skills/icl-research`、`skills/gil-research`、`skills/international-law-manual-research`、`catalog/`。来源控制台仍单独发行：<https://github.com/HuiwowICCSkills/InternationalLawSourceConsole>。

## 外部通用联网技能

`local-skills` 分组中的 `multi-search-engine`、`web-access`、`agent-browser`、`spider-mind` 不随本工具打包，需从上游单独获取：`web-access` 见 <https://github.com/eze-is/web-access>，`agent-browser` 见 <https://github.com/vercel-labs/agent-browser>，`spider-mind` 见 <https://github.com/qunliu031208-debug/spider-mind>；`multi-search-engine` 从 Codex 技能市场 / SkillHub 搜索同名技能，公开实现参考 <https://github.com/NachaFromMars/multi-search-engine>。它们不是国际法检索的必装依赖。
