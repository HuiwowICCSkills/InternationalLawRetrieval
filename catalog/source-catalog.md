# 国际法检索来源目录

`source-catalog.json` 是来源 ID、名称、说明、分组、标签和默认启用的唯一来源。
`source_catalog.py` 负责加载与结构校验，并可直接用于检查：

```powershell
python .\source_catalog.py validate
python .\source_catalog.py list
python .\source_catalog.py defaults
```

`search-sources-control/` 是独立控制台，单独发行，通过外部 `--catalog` 参数读取本目录：

- 从 `/api/catalog` 读取上述目录；
- 在 `sources-state.json` 中保存每个来源的开关与本次检索备注；
- 不保存、不复制任何来源 ID、名称或说明。

新增或修改来源时，只改 `source-catalog.json`。控制台刷新后会读取最新目录；
目录中新增的来源若尚无状态，会采用其 `default_enabled` 值。

可外接网页搜索和 `web_fetch` API；本工具默认不内置。

## 外部通用联网技能

`local-skills` 分组中的 `multi-search-engine`、`web-access`、`agent-browser`、`spider-mind` 是通用联网/浏览器能力，不随本工具打包，也不由本工具维护。它们可从上游单独获取：

- `multi-search-engine`：Codex 技能市场 / SkillHub 同名技能；公开实现参考 <https://github.com/NachaFromMars/multi-search-engine>。
- `web-access`：<https://github.com/eze-is/web-access>。
- `agent-browser`：<https://github.com/vercel-labs/agent-browser>，安装 `npm i -g agent-browser && agent-browser install`。
- `spider-mind`：<https://github.com/qunliu031208-debug/spider-mind> 或通过 `skill-installer` 安装。

这些技能不属于国际法检索工具的必装依赖；检索工具的核心路径和各单站 skill 不依赖它们。
