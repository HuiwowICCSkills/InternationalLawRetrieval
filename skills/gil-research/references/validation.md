# 实际验证

> **2026-11-09 拆分说明**：`icj`、`echr`、`mpil`、`oril`、`unts`、`un_documents`、`opinio_juris`、`intl_law_observer` 已拆分为独立技能，并在 `resources.json` 标为 `active:false`；下文相关记录保留为历史适配器验证证据。当前 `--sources` 只接受 8 个 active 来源。

## 2026-11-02 ICJ 正式渠道接入

ICJ 已从“仅案件标题目录”升级为正式 Document Search 渠道，并为具体 PDF 接入默认无头的 Cloudflare 回退。

| 测试 | 结果 | 处理 |
|---|---|---|
| `https://www.icj-cij.org/list-of-all-cases` | HTTP 200；`Nicaragua` 返回 5 条案件标题 | 保留为兼容的官方目录路径 |
| `https://www.icj-cij.org/advanced-search?search_api_fulltext=war%20crime` | HTTP 200；Document Search 表单存在，页面报告约 4,380 条结果并返回具体 PDF 链接 | 新适配器解析题名、案件、文书类型、日期和 PDF URL |
| `070-19860627-JUD-01-00-EN.pdf` 直接请求 | HTTP 403，响应为 `text/html` challenge | 触发 ICJ 专用浏览器回退 |
| 同一 PDF，无头 Chrome 回退 | HTTP 200，`application/pdf`，8,473,285 字节；两次 Cloudflare 挑战均自动通过；约 16.45 秒 | 默认使用 `CF_HEADLESS=true` |
| 有头/无头文件对照 | 两者 SHA-256 均为 `D6EC713FD229187ECF607DEA5239EF0A4FE2B645B68072A24FC10C0F67FB18FD` | 确认无头模式取得的是同一份真实判决 |
| PDF 结构 | `%PDF-1.4`，140 页，未加密，首页为 1986 年 Nicaragua 案实体判决 | 不是 HTML 错误页或伪装响应 |
| `search 'war crime' --fetch --limit 1` | 搜索状态 `ok`；首条 PDF 直连 403 后自动无头回退为 200，取得 2 页正文，频道无 warning | 验证搜索结果到 PDF 的正式组合链路 |

实现与边界：

- 搜索和案件页继续使用直接 HTTP；只有官方 `www.icj-cij.org` 的 PDF 在直连出现 403/challenge 时才启动无头浏览器，其他来源不会进入回退。
- 浏览器核心来自 `sarperavci/CloudflareBypassForScraping` 3.0.0，vendored 于 `vendor/CloudflareBypassForScraping`；运行时使用 DrissionPage 驱动本机 Chrome/Edge，单浏览器池、临时用户目录，结束后关闭。
- 默认无头；helper 提供 `--headful` 仅作故障排查，不进入正式检索默认路径。
- 本地 DNS 将 `www.icj-cij.org` 解析为保留地址 `198.18.0.95`，因此没有使用上游 HTTP 服务的 SSRF 校验路由；GIL 侧先严格限定 HTTPS、官方 ICJ 主机和 `.pdf` 路径，再直接调用 vendored core。
- 回退成功后，PDF 原始字节与元数据仍写入 `.gil-cache`，并保留直连失败、浏览器传输方式、UA、Cloudflare Cookie 名称、SHA-256 与页文本提取结果；不保存 Cookie 值。
- 无头回退仍可能受站点策略、IP 风控和浏览器版本影响；失败时报告 `fetch_error` 并交人工，不把挑战页解释为无资料。

## 2026-11-02 Cloudflare 渠道审计

本轮对控制台中所有明确提到 Cloudflare、WAF、challenge 或访问受限的渠道做了单次最小请求审计，并区分 Cloudflare、机构登录、站点自有安全策略和源站失效。

| 渠道 | 当前现象 | 判定与处理 |
|---|---|---|
| ECHR / HUDOC | `/eng` 返回 HTTP 403，标题 `Just a moment...` | 标准 Cloudflare；已接入无头 JSON 回退 |
| SSRN 原站 | DOI 跳转后的论文页返回 HTTP 403，标题 `Just a moment...` | 标准 Cloudflare；已接入 DOI 规范化和摘要页无头回退 |
| ICRC IHL / Customary IHL | `command responsibility` 返回 HTTP 403，页面为 `Request Not Compliant`；`responsibility` 单词查询返回 HTTP 200 JSON | 不是 Cloudflare，是 ICRC 自有查询级安全策略；未把通用 CF 绕过强加给该站 |
| ICC 官网 | `doctor` 的原生 `/search` 返回 200，总数 447 | 当前无阻断；无需启动回退 |
| EJIL: Talk! | `doctor` 的站点根页和 REST API 均返回 200 | 先前拆分技能的无头 WAF 回退仍正常 |
| Klamberg 旧站 | `https://iclklamberg.com/` 返回 HTTP 530，17 字节纯文本 | Cloudflare 后面的源站失效，浏览器无法修复；继续使用 Wayback 与 TOAEP 标注回退 |
| Oxford Reports / OPIL | 只有高频请求后的 `Human Verification` 405，正常请求 200 | 不是 Cloudflare；继续保持每主机 2 秒限速和人工订阅边界 |

HUDOC 与 SSRN 的实际修复：

- HUDOC 直连 `/eng` 为 403；无头会话通过挑战后，同一 JSON API 返回 HTTP 200、`resultcount=42`。该响应没有 `cf_clearance`，仅含 HUDOC、`__cf_bm` 和统计 Cookie，因此回退以合法 JSON 与结果结构作为成功判据。
- 正式 `gil-research search 'command responsibility' --sources echr --limit 1` 返回 `status=ok`、42 条总数和真实裁判题名，证据状态为 `403,200`。
- 对首条结果的 `/eng?i=003-7235632-9843605` 运行 `fetch`，无头浏览器跳到 HUDOC 渲染页并返回 HTTP 200，取得 2,347 字符公开页面文本、2 个 PDF 链接、真实标题和 `403,200` 证据链。
- SSRN `abstract_id=4819620` 的无头页面返回 HTTP 200 和真实论文标题；一个已失效的旧测试页面返回 410，说明“通过 Cloudflare”与“页面仍存在”必须分开判断。
- 正式 `gil-research search 'state immunity' --sources ssrn --limit 1 --fetch` 将 Crossref 的 `10.2139` DOI 规范化为 SSRN 论文页，取得 2,241 字符公开摘要正文，证据状态为 Crossref `200`、原站 `403`、无头回退 `200`。
- SSRN 回退只承诺公开摘要页，不把摘要页或下载按钮自动等同于已取得论文 PDF。

## 2026-10-16 HeinOnline 渠道拆分

HeinOnline 已拆分为独立技能 `HeinOnlineSearcher`（来源控制台项 `skill.HeinOnlineSearcher`），与其它来源同等管理；机构会话仍由 `gdufs-auth-session` 提供。
本工具包随之移除 `heinonline` 渠道：`resources.json` 条目、`heinonline_adapter.py`、`advanced` 子命令、`--auth-session/--auth-config/--chrome-path` 参数、首次检索的浏览器来源偏好流程（改动后本工具已无 `requires_browser` 来源）、`references/heinonline-search.md` 副本与四个专用测试删除。
HeinOnline 的 Search Help 语法、多字段高级检索与分节 PDF `download` 流程现由 EJILTalkSearcher 同级的 `HeinOnlineSearcher` 技能维护；下方历史记录中相关条目保留为证据。

## 2026-10-16 EJIL: Talk! 渠道拆分

EJIL: Talk! 已拆分为独立技能 `EJILTalkSearcher`（来源控制台项 `skill.EJILTalkSearcher`），与其它来源同等管理。
本工具包随之移除 `ejil_talk` 渠道：`resources.json` 条目、WordPress 无头回退解析（`wordpress_browser` / `parse_ejil_talk_html`）及四个专用测试删除；首次检索的浏览器来源判定只保留 `requires_browser`。
同日复核结论：本工具包旧 UA（Chrome/120）的 REST 请求持续被 403，而独立技能（Chrome/155 UA）REST 直连成功，故拆分不损失检索能力；该渠道后续行为与核验以 EJILTalkSearcher 自身记录为准。下方 2026-10-15 的 REST 403 与 HTML 回退核验保留为历史证据。

## 2026-10-15 ICJ 搜索入口复核

本轮复核 ICJ 官网站内搜索与文档搜索，确认两点：`quick-search` 不是判例全文检索，`advanced-search` 才是；但两者目前都无法由直接 HTTP 或无头浏览器稳定使用。

| 路径 | 直接 HTTP | 无头 Chrome | 真实浏览器会话 |
|---|---|---|---|
| `https://www.icj-cij.org/quick-search` | 通用研究和浏览器式 UA 均返回 HTTP 403 | 返回 Cloudflare `请稍候…` 托管验证页 | 正常打开，标题为 `Site search` |
| `https://www.icj-cij.org/advanced-search` | 通用研究和浏览器式 UA 均返回 HTTP 403 | 返回 Cloudflare `请稍候…` 托管验证页 | 正常打开，标题为 `Document search` |

真实浏览器会话中的实际检索：

- `quick-search` 提交 `war crime` 后跳转到 `https://www.icj-cij.org/quick-search?search_api_fulltext=war+crime`，页面显示 4 条网页结果，其中包括 `Arrest Warrant of 11 April 2000` 和 `Trial of Pakistani Prisoners of War` 两个案件页。页面明确说明该搜索引擎只检索网页，按相关性排序；判例 PDF 全文需使用 document search。
- `advanced-search` 的表单 ID 为 `views-exposed-form-document-search-page-1`，关键词字段为 `search_api_fulltext`，另有精确短语、通配词、案件、文书类型、附带程序、日期、每页条数和排序字段。提交 `war crime` 后得到 `About 4380 results`，结果行同时返回案件页链接和具体 PDF 直链，例如 `https://www.icj-cij.org/sites/default/files/case-related/192/192-20260922-pre-01-00-en.pdf`。页面明确说明该搜索引擎检索网站发布的案件相关 PDF 全文。
- 完整查询 URL 形如 `https://www.icj-cij.org/advanced-search?search_api_fulltext=war+crime&search_api_fulltext_1=&search_api_fulltext_2=&case_selection=1&field_document_group_type=All&field_doc_incidental_proceedings=All&field_date_of_the_document%5Bmin%5D=&field_date_of_the_document%5Bmax%5D=&items_per_page=10&sort_order=DESC`。

适配器决策：

- `icj` 自动渠道继续使用 `https://www.icj-cij.org/list-of-all-cases` 案件标题目录，因为它可以在直接 HTTP 路径使用；关键词只匹配案件标题，不是判决全文检索。
- `advanced-search` 是更合适的全文检索入口，但当前只能在真实浏览器会话中使用。直接 HTTP 和无头路径都会遇到 Cloudflare 托管验证，不能通过自动化点击验证框绕过；因此不在自动渠道里伪装可用。
- `international-law-manual-research` 的 ICJ 路由已补入 `advanced-search` 作为人工/真实浏览器全文检索入口，并保留 `quick-search` 但注明它只搜网页。

## 2026-10-15 EJIL: Talk! 浏览器回退复核

本轮针对 2026-10-14 仍被 403 拦截的 EJIL: Talk! 做了定向复核。结论是普通 HTTP 路径全部不可用，但站点自身给浏览器使用的 HTML 搜索页可以恢复检索。

| 测试路径 | 结果 | 处理 |
|---|---|---|
| `https://www.ejiltalk.org/wp-json/wp/v2/posts?search=war+crime` | HTTP 403，响应为简短 `403 - Forbidden` | 保留为 REST 首选路径；不把 403 当零结果 |
| `/wp-json/wp/v2/posts` 无参数 | HTTP 403 | 确认拦截是站点级，不是关键词触发 |
| `/?rest_route=/wp/v2/posts&search=war+crime` | HTTP 403 | 排除 REST 路由变体 |
| `/feed/?s=war+crime` 与 `/search/war+crime/feed/rss2/` | HTTP 403 | 排除 RSS/feed 替代路径 |
| `https://www.ejiltalk.org/?s=war+crime`，普通 HTTP、完整浏览器请求头 | HTTP 403，标题 `403 - Forbidden` | 请求头伪装不足以恢复 |
| 同一 URL，无头 Chrome，空 Cookie | HTTP 200，标题 `Search Results for "war crime" – EJIL: Talk!`，页面显示 `Page 1 of 142`，10 条结果 | 接入 `browser_fallback`；无需机构 Cookie 或 VPN |

实现与边界：

- 适配器先请求 WordPress REST API；仅在收到 `RetrievalError`（包括 HTTP 403）且本会话启用了浏览器来源时，才运行无头 Chrome HTML 回退。浏览器来源被关闭时仍保留并报告原始 403。
- HTML 回退解析 `section.search-page-articles` 下的 `div.post-tease-ejil`：题名取 `h3`，链接取 `a.article-link[href]`，日期取 `div.featured-date-and-author > p`，作者取 `a.blog-info-author`，摘要取 `div.post-tease-content-ejil > p`。
- 该页每页 10 条。结果元数据状态为 `ok`，证据记录 `browser: headless-chrome`、最终 URL、抓取时间和 SHA-256；`total` 置空，因为页面只报告页数，不报告精确命中数。
- 回退只返回搜索结果条目的题名、日期、作者和 teaser，不取得文章正文；正文仍需对条目 URL 运行 `fetch`，并按站点当时的访问状态报告结果。
- 测试覆盖 HTML 卡片解析、REST 403 时触发回退、未启用浏览器来源时保留 403。

## 2026-10-14 复核

本轮用直接 HTTP 和技能适配器复核全部 15 个渠道，重点检查此前标记为受限或失败的来源。结论是多数旧限制属于适配器问题，不是资源永久不可用。

| 渠道 | 复核结果 | 处理 |
|---|---|---|
| EJIL: Talk! | 官网和 WordPress API 在首次直接请求中返回 200；通用 `GILResearch/2.0` UA 会被 403。随后高频复核触发站点端 WAF/频控，同一浏览器式 UA 也开始返回 403 | 在 `resources.json` 为该渠道增加浏览器式 User-Agent；不能把后续 403 当永久不可用 |
| HUDOC/ECHR | 官网 200；建立会话后带 `Accept`、`Referer`、`X-Requested-With` 请求查询接口，曾返回 200 和真实结果。高频复核后站点开始对同一 IP 返回 Cloudflare challenge | `hudoc()` 增加会话预热和请求头；403/challenge 按单次请求报告 |
| SSRN | 原站、论文页、DOI 跳转和 `api.ssrn.com` 仍为 Cloudflare 403；Crossref `10.2139` 元数据和摘要可用 | 保留 Crossref fallback，明确原站全文未取得 |
| UN ODS | `documents.un.org` 首页 200；`/api/symbol/access?s=A/RES/59/38&l=E` 返回 200 PDF；`/api/search` 提示缺少 auth token；Unite Search 的 ODS 集合返回计数但没有 docs | 明确“按文号可取全文，关键词检索不完整” |
| UN Digital Library | 网页搜索仍返回 202 challenge；OAI-PMH `ListSets` 和 `ListRecords` 返回 200 XML 和真实记录 | 记录元数据收割可用，网页全文搜索仍受限 |
| UNTS | 官网 200；`AdvanceSearch.aspx?tab=UNTS` 200；UNTS 卷册 PDF 200 | 记录官方完整检索入口可用；当前适配器仍只扫描 MTDSG |
| ICJ | 案件页 200 并含 190 个 PDF 链接；测试的新旧判决 PDF 直链均返回 Cloudflare 403 | 区分“案件页/文档目录可用”和“PDF 全文未取得” |
| Google Scholar | 本次全渠道查询返回真实结果 | 保留原有抓取逻辑；限流和 challenge 仍按失败处理 |
| MPIL | 通用研究 UA 访问 `opil.ouplaw.com` 返回 403；浏览器式 UA 配合持久化 Cookie 返回 200 和产品过滤后的真实结果，词条页正文可直接读取 | 新增 `opil` 适配器与 `mpil` 渠道，不再需要浏览器自动化；详见下节 |
| ORIL | 同一平台、同一条匿名 HTTP 路径即可检索：全库浏览 10,034 条，`command responsibility` 1,011 条；报告页可读性因案件而异 | 新增 `oril` 来源（`pc_17` 分面）；`oxford_reports` 保留为人工入口，用于整库订阅路径 |

离线验证仍覆盖原有 11 个成功渠道。本轮新增的 header/cache 逻辑会在缓存键和证据中记录请求头，避免把不同请求头的结果混在一起。

### OPIL 渠道：MPIL 与 ORIL（2026-10-14）

`mpil` 渠道检索 OUP《Max Planck Encyclopedia of Public International Law》。此前 `oxford_reports` 记的 "HTTP 403" 是请求头问题，不是资源不可用。

- 通用研究 UA（`GILResearch/2.0`，以及 `python-requests` 默认 UA）访问 `opil.ouplaw.com` 返回 403；换成浏览器式 UA 后同一 URL 返回 200。
- 用 curl 且不带 Cookie jar 跟随重定向会陷入 OIDC 循环：`opil.ouplaw.com` 到 `oup2-idp.sams-sigma.com/authorize`，再到 `/oidc_callback?error=login_required`，又回到起点。带 Cookie 持久化的会话不会循环。这是此前把该平台记为不可达的直接原因。
- 两组分面的参数需求相反，且都是静默的：`prd`（MPIL）必须带 `access=all&level=all`，否则服务端丢掉产品过滤，`genocide` 由 411 条（全部 MPIL）变成 3,814 条并混入 OSAIL；`pc_*`（ORIL 子分册）则不能带 `access=all`，否则塌缩，ORIL 1,011 条变 4 条、ICL 分册 365 条变 3 条。`level=all`、`pageSize`、`sort` 单独加都无影响，已分别测定。把 `prd=MPEIPRO&EPIL` 当作单个参数值传入还会被编码为 `%26`，同样静默失效。适配器因此同时采用正确参数组合并校验返回行的 Product 字段，不匹配即报错。
- 该地址返回的结果全部属于 MPIL（MPEPIL 与 MPEiPro 两个模块）；`pageSize=50` 生效，`page=N` 翻页生效，`page=21` 返回第 401–411 条。
- 结果块选择器 `div.contentItem`：题名 `h2.itemTitle a`，作者 `div.itemAuthor`，元数据 `dl.metadata`（Content type / Product / Module / Subject(s)），摘录 `div.component-content-summary`；`hasAccess` class 表示本次会话该词条页可读。
- 词条页正文取自 `#mainContent`：它是 `#readPanel` 的超集，多出的约 230 字符正是题名、作者、Content type、Product、Module 和 "Article last updated" 等引用元数据。
- 耗时（本机实测）：全新会话含握手 3.3–3.9 秒，复用会话 Cookie 后 1.0–1.8 秒；经 `run.ps1` 调用另加约 0.84 秒启动与解释器探测开销。连续 4 次查询实测：首个 5.69 秒（握手并写入 Cookie），随后 2.99 / 3.13 / 3.24 秒。
- 样本：`command responsibility` 命中 165 条，首条为 Command Responsibility（Yoram Dinstein†，MPEPIL，last updated September 2015），`--fetch` 取得该词条 20,366 字符，含编号段落、Select Bibliography 与 Select Documents；`genocide` 命中 411 条，Genocide 词条 `--fetch` 取得 53,079 字符。
- 未做：OXIO、OHT、OSAIL 在同一平台也响应浏览器式 UA，但产品分面与覆盖范围未逐一验证，未接入。

### ORIL 来源实测（2026-10-14）

`oril` 用 `pc_17` 分面检索整个 Oxford Reports on International Law。匿名会话即可检索，不需要浏览器、登录或绕过订阅。

- 检索地址：`https://opil.ouplaw.com/search?sfam=&q=<关键词>&pc_17=bdcb8d33-0914-4cd9-bd2b-c84ac21665f7[&pageSize=20|50][&page=N]`。`page=N` 与 `pageSize=50` 均生效。
- 分面 UUID：ORIL 全库 `pc_17=bdcb8d33-0914-4cd9-bd2b-c84ac21665f7`；ICL 分册 `pc_32=68306099-6983-4cb7-a931-60f851434432`；ILDC 分册 `pc_20=129d4f34-d269-49ef-ac37-1557c85043fc`。
- 本次实测命中数（匿名）：ORIL 全库浏览 10,034；`command responsibility` 1,011；`Akayesu` 250。ICL 分册：浏览 1,531；`command responsibility` 365；`superior responsibility` 316；`genocide` 504。MPIL 同一查询对照 165。另有报告值 `genocide` 1,191、`superior responsibility` 1,281、`torture` 2,541、`immunity` 1,507（ORIL 全库），未逐一复测。
- 结果行结构：`div.contentItem`，class 含 `case-whole`、`locked`、`standardResult`；标题与链接在 `h2.itemTitle a`；`dl.metadata` 含 Date、Content type、Product、Module、Jurisdiction、Subject(s) 与编者 `Core Issue(s)`。ORIL 行实测没有任何 `div.component-content-summary`（0 个），所以摘要只能取 `Core Issue(s)`；文档不应承诺 ORIL 结果自带 snippet。
- 正文可读性批量抽样（匿名 13 条，跨 ICL、ILDC、IHRL、ICGJ）：12 条为 1,333–2,266 字符，内容是引证头加 `Core Issue(s)`，属于 headnote 级，其中若干条带 sign-in 提示；1 条 `law-icl-2038icc21`（Ongwen Trial Judgment）为 381,724 字符、426 个编号段落且无 sign-in，是完整判决文本。抽样不足以按分册或案件类型归类完整性，`fetch` 返回的 `text_characters` 必须逐条核对，不能把 headnote 当完整报告。
- 正文容器 `#mainContent` 对 MPIL 与 ORIL 都适用，取到的是引证头加正文。
- 人工验证页：短时间约 20 次请求后平台开始返回 HTTP 405，标题为 `Human Verification`，约 3.5 分钟后恢复；恢复后同一 URL 返回相同计数。适配器对 `opil.ouplaw.com` 设 2 秒最小请求间隔，并把该页按访问挑战处理，绝不当作零结果。
- 条目 URL 必须原样使用检索返回的 href：同一平台的路径存在 `/law:icl/...` 和 `/law-icl/...` 两种形态，手工按其中一种规则拼接会对另一种返回 404（本轮曾据此误判 Ongwen 条目不存在）。
- `access` 是搜索状态参数，不是访问级别开关。请求 URL 里带 `access=all` 时，返回页面自身回填的隐藏字段变成 `access=user`，即服务端把它解释为“只保留当前会话有权读取的条目”；`access=user` 与 `access=all` 得到相同结果。这解释了全部现象：MPIL 是 Subscribe-to-Open，165 条本来全部可读，所以过滤前后一致；ORIL 是订阅产品，`command responsibility` 在有该分面时只剩 4 条（ICL 3 + ILDC 1，全部为 OPEN，含全文 381,724 字符的 Ongwen 判决），无该参数时是 1,011 条且首页 20 条全部 `locked`。
- 全新会话隔离复测（2026-10-14 补测，每个用例单独开新会话）：首个请求不带 `access` 的 ORIL 浏览为 10,034、页面状态 `all`；同一会话重复请求仍是 10,034，没有漂移；另开新会话带 `access=all` 为 16、状态 `user`；带 `access=user` 同样 16，确认两者等价。状态是**会话级**而非 IP 级：某会话先请求 `access=all` 后，该会话内后续不带 `access` 的两次请求都停在 16 且状态字段仍为 `user`；而再开一个全新会话请求同样的裸 URL，又回到 10,034、状态 `all`。这正是本轮早前把 1,011/10,034 误判为“无法复现”的原因。适配器为每个来源使用独立 Cookie 文件，也是为了不让这种状态跨来源串扰。
- 无关键词浏览时 ORIL 全库在 `access=all` 下为 16 条：ILDC 10、ILEC 2、ICL 4，与先前报告的 16（ICL 4、ILDC 10）吻合。同一会话里一旦用过 `access=all`，后续不带该参数的请求也会保持 16，说明该状态会留在会话中；这也是本会话早前把 1,011 误判为“无法复现”的原因。适配器因此对 ORIL 完全不发送 `access`，并且每个来源使用各自独立的 Cookie 文件（`<source>.cookies.txt`），避免状态互相污染。
- ORIL 子分册分面。无关键词浏览时从分面树读到完整清单，括号为该次浏览计数：`pc_20` ILDC 2,878、`pc_28` IHRL 2,920、`pc_36` IIC 1,870、`pc_32` ICL 1,531、`pc_24` ICGJ 554、`pc_40` ITL 165、`pc_44` ILEC 116，加 `pc_17` ORIL 全库 10,034。七个子分册之和 2,878+2,920+1,870+1,531+554+165+116 = 10,034，与全库相等，说明它们是对 ORIL 的完整划分。`command responsibility` 查询下 ILEC 无命中，所以那次分面树只有六个子分册——分面树只列出当前查询有命中的项。ILEC 的 UUID 为 `pc_44=1bf47a86-bafa-480c-af75-1099fb45836c`。
- 同一棵分面树里还出现了 `pc_83=5381f75c-dc3f-4d36-8119-445bc61ded` 即 `Oxford International Organizations [OXIO]`（该次 1 条），说明 `pc_*` 这一族并不专属于 ORIL；取分面时要认 UUID 与标签，不要假设 `pc_*` 一定是 ORIL 子分册。
- 仍未确立：ORIL 全库正文覆盖在机构会话下的实际范围；以及 `access=user` 可读子集在其他查询下的稳定性（本轮只对 `command responsibility` 与无关键词浏览两种情形复测过）。
- 订阅边界：ORIL 是订阅产品，与 MPIL 的 Subscribe-to-Open 不同。整库正文覆盖预期需要机构会话，`oxford_reports` 人工入口因此保留。

## 2026-09-22 基线

从 `state immunity` 查询开始对原 15 个渠道逐一测试。成功指确实收到记录，不代表完整覆盖或任何查询均成功。

| 渠道 | 本次结果 | 实现及边界 |
|---|---|---|
| CJIL | 2 条 | Crossref，ISSN 1746-9937；题名、作者、DOI、期刊及可用摘要 |
| EJIL | 2 条 | Crossref，ISSN 1464-3596；同上 |
| AJIL | 2 条 | Crossref，ISSN 2161-7953；同上 |
| Opinio Juris | 2 篇正文 | WordPress posts API；正文各 15,571 / 13,864 字符 |
| International Law Observer | 2 篇正文 | WordPress posts API；正文各 1,399 / 1,827 字符 |
| EJIL: Talk! | 受限 | 早期探测 HTTP 403，本次关键词请求超时；未验证成功 |
| UNTS | 1 条替代目录记录 | 扫描 29 个 UNTC/MTDSG 章节目录；秘书长保存多边条约子集，不是 UNTS 完整登记库 |
| ICJ | 1 案 | 案件标题目录命中国家豁免案；案件页面取得 16,792 字符及 127 个 PDF 链接；测试判决 PDF 返回 403 |
| ECHR/HUDOC | 受限 | HTTP 403；保留适配器，但响应解析未获在线成功验证 |
| UN Documents | 2 条替代索引记录 | 官方 Unite Search 的 un 集合，可能为新闻；Digital Library 返回空 HTTP 202，ODS 返回数量但无 docs，不能声称完成 ODS 检索 |
| Google Scholar | 2 条 | 直接解析公开 HTML 结果；无浏览器，无 API 稳定性保证，挑战页面报失败 |
| SSRN | 2 条及摘要 | Crossref DOI 前缀 10.2139 子集；SSRN 原站 HTTP 403 |
| Avalon | 1 条及网页全文 | 扫描 9 个世纪目录；通过 `--fetch` 取得美国—比利时领事公约网页 14,231 字符 |
| Oxford Reports | 人工入口 | HTTP 403，未接入订阅身份 |
| 百链 | 人工入口 | 跳转 login.jsp，需要机构身份 |

PDF 与条约页面另行验证：

- 从条约目录返回的详情页抓取《国家及其财产管辖豁免公约》状态及文献链接。
- 从详情页实际返回的 `Certified true copy` 链接下载 124 页认证 PDF，提取 171,037 字符。PDF 页 1、2、5、7、23、41、59、61、81、119、122、123 无可提取文字，标入 `ocr_needed`；不宣称扫描页已识别。
- 从详情页实际返回的联大第 59/38 号决议链接下载 14 页 PDF，提取 35,206 字符，各页有文字。
- 联合国条约英文题名目录 PDF：32 页，70,587 字符。
- 所有成功响应保存原始字节、最终 URL、抓取时间及 SHA-256；PDF 输出保留物理页位置。

离线验证覆盖 11 个成功渠道的同一查询，复用原始响应，保留原抓取时间。逻辑测试覆盖：不联网离线模式、缺失记录不冒充零结果、期刊边界、WordPress 正文、EJIL: Talk! HTML 回退解析、小条数分页不跳过结果、ASP.NET 表单不吞掉文档正文、联合国摘要数组处理。测试命令：`python -m unittest discover -p 'test_*.py' -v`。

旧实现多数只生成链接；新版 schema_version=2 显式包含渠道状态、真实结果、失败原因与证据。`ok` 不表示来源完整，标题目录查询不等于全文检索，Crossref 的相关性结果仍需核验论题匹配。
