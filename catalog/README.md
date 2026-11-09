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
<https://github.com/GDUFSICCSkills/InternationalLawRetrieval>

仓库结构：`skills/icl-research`、`skills/gil-research`、`skills/international-law-manual-research`、`catalog/`。来源控制台仍单独发行：<https://github.com/GDUFSICCSkills/InternationalLawSourceConsole>。
