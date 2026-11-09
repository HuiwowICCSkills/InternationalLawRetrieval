# Channels and interfaces

Discovery: 2026-09-15, rechecked 2026-10-14, Python HTTP only. Operational endpoints inferred from public clients are **not promises of documented or stable public APIs**.

> **2026-11-09 拆分说明**：本文件中 `icty`、`ucr`、`irmct-cld`、`ictr`、`icd`、`icrc-ihl`、`icrc-customary`、`mpil`、`oril-icl`、`cilrap`、`fichl` 的条目是历史适配器说明，已在 `channels.json` 标为 `active:false`，不再出现在 `search --channels` 中。请分别使用独立技能 `ICTYSearcher`、`UCRSearcher`、`IRMCTCldSearcher`、`ICTRSearcher`、`ICDSearcher`、`ICRCSearcher`、`OPILSearcher`、`CILRAPSearcher`。当前可选渠道为 `jicj`、`cmn`、`toaep`、`klamberg`。

| Word resource | Selector | Implemented method | Limits |
|---|---|---|---|
| JICJ | `jicj` | Crossref journal works API | OUP HTTP 403; metadata not full text |
| ICTY homepage/cases | `icty` | [Official directory](https://www.icty.org/en/cases), HTTP crawl + LTD institution filter | Legacy site says selected documents are informational, not official registry records; native search returned empty JS-dependent result area |
| ICTY Legal Library / ICTR library | `ucr` | [UCR](https://ucr.irmct.org/) public recent-filings endpoint + LTD tribunal mirrors | UCR full search requires sign-in; authenticated search adapter not claimed; public recent filings are not the whole registry |
| ICTY/ICTR Case Law Database | `irmct-cld` | Public basic-search JSON + extracts | Selected Appeals Chamber holdings, not all trial/registry records |
| ICTR homepage/cases | `ictr` | [Migrated site](https://unictr.irmct.org/en/cases), HTTP native search + LTD filter | Distinguish web news from registry documents |
| CILRAP | `cilrap` | HTML/PDF crawl from purpose, thematic libraries, events, news | Bounded; no official search API confirmed |
| FICHL | `fichl` | fichl.org redirects to [CILRAP /fichl](https://www.cilrap.org/fichl) | Older FICHL Publication Series books now under TOAEP; also search `toaep` |
| CMN | `cmn` | [Knowledge Hub](https://www.casematrixnetwork.org/cmn-knowledge-hub) HTML crawl | Lexsitus/CLICC is served by the standalone `LexsitusSearcher` skill; this row covers CMN public pages only |
| TOAEP | `toaep` | Five series catalogues + LTD publisher filter | Catalogue may be newer than LTD holdings |
| International Crimes Database | `icd` | Public `GET /SearchResults/?q=&p=` keyword search over the whole case record | Five rows per page; a few English phrases are filtered at the front door, so those queries use a labelled term-by-term intersection. Detail pages are fetched separately |
| ICL Database & Commentary | `klamberg` | Klamberg TOAEP books + public Wayback snapshots | Lexsitus/CLICC is served by `LexsitusSearcher`; original domain returns Cloudflare 530, and Wayback is not a complete live database |
| ICRC IHL databases | `icrc-ihl` | Five JSON:API indexes; ICRC-authored LTD fallback | Native indexes return 200 for many queries; an exact phrase such as `command responsibility` may trigger a query-specific WAF 403, and individual indexes can return a transient 503. Retry keywords, variants or a later run before falling back |
| Customary IHL | `icrc-customary` | Rules/practice JSON:API; local full-text search of three Rules/Practice PDF volumes | Native indexes return 200 for many queries but can reject exact multi-word phrases or return a transient 503; the dated PDF corpus is not current online practice |
| MPIL | `mpil` | OPIL product search (`prd=MPEIPRO`) with a browser-like User-Agent and cached session cookies | Product-scoped to MPIL (MPEPIL + MPEiPro); rows carry title, author, module and subject metadata plus a leading excerpt, not the entry full text |
| ORIL ICL reports | `oril-icl` | OPIL UUID-facet search (`pc_32`) with a browser-like User-Agent and cached session cookies | ORIL International Criminal Law sub-series; rows carry the citation header, date, jurisdiction, subject terms and the editorial core issue(s). Report text is fetched separately and is often headnote-only anonymously |

**ICC Legal Tools Database is not a selector here.** It was split out into the standalone `LegalToolsSearcher` skill (its own repo, installable on another machine without this toolkit). The split is a distribution change only: for multi-source comparison it still counts as **one channel** of the same source list. The active `toaep` and `klamberg` channels still use Legal Tools **records as their labelled mirror fallback**, which is why the API notes in this file are kept.

## ICC official site search

The former `icc` selector was split into the standalone `ICCSearcher` skill on 2026-10-24. Use that skill for the official `/search` route, linked pages/PDFs, zero-based pagination, WAF handling, the bounded `/cases` crawl, and Legal Tools ICC fallback records. The implementation and verification details live in the `ICCSearcher` repository rather than this toolkit.

## MPIL and ORIL ICL

MPIL: `GET https://opil.ouplaw.com/search` with `sfam=&q=<query>&prd=MPEIPRO&access=all&level=all&pageSize=20|50&sort=relevance&page=N`.

ORIL ICL sub-series: the same endpoint with `sfam=&q=<query>&pc_32=68306099-6983-4cb7-a931-60f851434432&pageSize=20|50&sort=relevance&page=N` and **no** `access` parameter.
- Other ORIL sub-series facets, read from the facet tree. For `command responsibility`: `pc_20` ILDC 295, `pc_24` ICGJ 68, `pc_28` IHRL 212, `pc_32` ICL 365, `pc_36` IIC 53, `pc_40` ITL 18, against `pc_17` for the whole product at 1,011; the six sum exactly to the total. A keyword-free browse exposes all seven sub-series with browse counts (`pc_20` 2,878; `pc_28` 2,920; `pc_36` 1,870; `pc_32` 1,531; `pc_24` 554; `pc_40` 165; `pc_44` ILEC 116) summing to 10,034, the product total. `pc_44=1bf47a86-bafa-480c-af75-1099fb45836c` is ILEC. The tree lists only facets with hits, and the same family also carries `pc_83=5381f75c-dc3f-4d36-8119-445bc61ded` for OXIO, so match on UUID and label rather than assuming the `pc_*` prefix means an ORIL sub-series.

- The product filter is honoured only for a request that carries a browser-like User-Agent; the generic research agent receives HTTP 403, and a redirect-following client without cookie persistence loops through the publisher identity provider.
- `access` is a search-state parameter, not an access-level switch: sending `access=all` makes the server answer with the state `access=user`, i.e. "only items this session may read". MPIL is Subscribe-to-Open so all 165 rows stay readable and nothing changes, but the ORIL `command responsibility` set falls from 1,011 rows (top 20 all `locked`) to 4 readable rows (ICL 3 + ILDC 1, including the Ongwen judgment with 381,724 characters of full text). The state persists inside a session, so after one `access=all` request later plain requests also returned 16 for ORIL browse. The adapter therefore never sends `access` for the `pc_*` facets, and each channel keeps its own cookie file.. The state is session-scoped, not IP-scoped: one session that requested `access=all` kept returning 16 for later plain requests with its hidden field still reading `user`, while a brand-new session on the bare URL returned 10,034 with state `all`. Each channel therefore keeps its own cookie file.
- The `prd` facet behaves the other way and needs `access=all&level=all`, or the server drops the product filter and `genocide` returns 3,814 mixed MPIL/OSAIL rows instead of 411 MPIL-only rows. `level`, `pageSize` and `sort` alone had no measured effect on either family. Because both failures are silent, the adapter validates the returned rows against the declared Product and raises instead of returning a wrong set.
- A burst of requests makes the platform answer HTTP 405 with a `Human Verification` title for a few minutes (observed recovery after about 3.5 minutes); the adapter keeps a per-host minimum interval and treats that page as an access challenge, never as zero results.
- Entry URLs must be used exactly as returned: the same platform serves both `/law:icl/...` and `/law-icl/...` paths, and reconstructing one form for a document published under the other returns 404.
- Handshake cookies are kept in `<cache>/<channel>.cookies.txt`, which removes three redirects from later runs. A stale handshake is dropped and retried once.
- Result blocks are `div.contentItem`. MPIL rows: title `h2.itemTitle a`, author `div.itemAuthor`, metadata `dl.metadata` (Content type / Product / Module / Subject(s)), excerpt `div.component-content-summary`, and the `hasAccess` class means the entry page is readable in that session. ORIL rows instead carry `case-whole`/`locked` classes, add Date, Jurisdiction and editorially written `Core Issue(s)`, and have no excerpt block at all, so `Core Issue(s)` is the only summary available.
- Entry text is fetched separately. `#mainContent` yields the entry header plus body, including `Article last updated`, the Select Bibliography and Select Documents; it supersets `#readPanel`.
- `#mainContent` yields the citation header plus body for both products. MPIL is Subscribe-to-Open, so sampled entries were readable without a subscription. ORIL is a subscription product: in a 13-entry anonymous sample 12 report pages returned 1,333-2,266 characters (citation header plus core issue(s), i.e. headnote only, several with a sign-in prompt) while `law-icl-2038icc21` (Ongwen Trial Judgment) returned 381,724 characters with 426 numbered paragraphs. `text_characters` must be checked before a page is treated as a full report. Both products are secondary material under the source-layering rule in SKILL.md.

## JICJ / Crossref

`GET https://api.crossref.org/journals/1478-1387/works`

Parameters: `query`, `rows`, `offset`. Response: `message.items`, `message.total-results`. E-ISSN: 1478-1395. Positive query `command responsibility` returned **Command Responsibility in Irregular Groups**, DOI `10.1093/jicj/mqs085`. Relevance search is not strict Boolean full-text matching.

## Legal Tools

Not a selector in this toolkit — the ICC Legal Tools Database is served by the standalone `LegalToolsSearcher` skill (see the note after the selector table). The API below is kept because the listed mirror fallbacks still call it.

`GET https://legal-tools.org/api/ltddocs/search`

Parameters: `term`, `filter` as JSON string:

```json
{"from":0,"limit":5,"where":{"deleted":false,"organisation":"International Criminal Court (ICC)"}}
```

Response: `results[].hit`, `results[].highlight`, `total`, `facets`. `total` can vary in representation; preserve raw values/lower-bound flags. Useful hit fields: `documentUrl`, `pdfURL`, `documentOrigin.url`, `caseNumber`, `externalId`, `source`, `judicialDocumentType`, `dateCreated`. Opaque `languageIds` do not establish language names. `isAuthoritativeLanguage` concerns that version, not a translation generated by the assistant.

Verified organisation labels:

- `International Criminal Court (ICC)`
- `International Criminal Tribunal for the former Yugoslavia (ICTY)`
- `International Criminal Tribunal for Rwanda (ICTR)`
- `International Residual Mechanism for Criminal Tribunals (IRMCT)`
- `International Committee of the Red Cross (ICRC)`
- `Torkel Opsahl Academic EPublisher (TOAEP)`

Discovery: [public front-end JS](https://www.legal-tools.org/static/js/main.f48d644a.chunk.js), `API_URL` and `ltddocs/search`. The build hash changes; discover the current script from HTML if repairing. Only anonymous search/read routes are used. Admin routes in public scripts grant no additional permission.

## IRMCT CLD

- `GET https://cld.irmct.org/assets/homedata.json` → `data` array.
- Row fields: ID, notions, case, filing, date, ICTR statute, ICTY statute, IRMCT statute, ICTR rules, ICTY rules, IRMCT rules, other instruments, document path.
- `GET https://cld.irmct.org/home/jsonExtract/{ID}` → `extract` HTML.
- Resolve judgment paths relative to `https://cld.irmct.org/`.

The helper searches all basic-search **metadata**, then reads chosen extracts. It does not search unselected extract text. Also use Legal Tools for concepts absent from notions. Preserve multiple extracts from one judgment. The site's introduction advises verifying footnote numbering in full judgments.

## Lexsitus / CLICC / CMN

**Lexsitus is a separate channel.** Its search and node reading live in the
standalone `LexsitusSearcher` skill, which owns the API routes
(`/api/v1/search`, `/api/v1/nodes/path/{path}`), the observed tree kinds, and
the pagination caveat. This toolkit's `cmn` row only crawls
`casematrixnetwork.org`; it does not call the Lexsitus API any more. Route
Lexsitus questions to that skill rather than re-implementing the adapter here.

CMN's official Knowledge Hub links to CLICC. [TOAEP's catalogue](https://www.toaep.org/ps) provides related Klamberg books:

- [First edition](https://www.toaep.org/ps-pdf/29-klamberg)
- [Statute volume 1, second edition](https://www.toaep.org/ps-pdf/43-klamberg-nilsson-angotti-second)
- [Statute volume 2, second edition](https://www.toaep.org/ps-pdf/44-klamberg-nilsson-angotti-second)
- [Rules of Procedure and Evidence](https://www.toaep.org/ps-pdf/45-klamberg-nilsson-angotti)

These establish related alternatives, not a complete transfer of the old iclklamberg.com corpus.

## ICD (International Crimes Database)

Public keyword search, verified 2026-10-15 with direct HTTP, no browser and no login:

`GET https://www.internationalcrimesdatabase.org/SearchResults/?q=<terms>&p=<page>`

The site's own quick-search box posts to `/Home` and answers with a 302 to this same URL, so the GET form is the native result route. Each page renders five rows inside `div.search-results`: an `<h2>` carrying either `N results (ordered by relevance)` or `no results`, a `p.paging-controls` block with `page X of Y`, then repeated `<strong><a href="/Case/{id}">` entries each followed by a citation `<p>` and a `div.search-summary`. `no results` is a confirmed zero, not a failure. Matching covers the whole case record, including the summary (the deep term `Bourgmestre` finds Akayesu). `/Case/{id}` resolves without the slug, and pagination uses `p`; the server page size is fixed at five and ignores page-size parameters. Detail pages are plain server-rendered HTML carrying summary, procedural history, legally relevant facts, core legal questions, rules, holding, keywords, instruments and links.

Known traps:

- The Azure front door in front of the site answers any query whose text contains `command` followed by whitespace and another word with HTTP 403, a command-injection false positive. On 2026-10-15 `command responsibility`, `command and control` and `command structure` were all blocked, while `command` alone returned 116 results and `effective control` returned 153. Single tokens are unaffected, so the adapter intersects bounded term-by-term searches and labels the rows `icd-token-intersection` with a warning instead of reporting zero results or site unavailability.
- `POST` to `/AdvancedSearch` re-renders the form rather than returning results, and submitting it with a blocked phrase is filtered. Do not treat the form as the search route.
- `/Cases/ByName/All` returned HTTP 504 on repeated attempts while `/Cases/ByName` (which defaults to letter A), the per-letter pages and `/Cases/ByCategory` returned 200. A catalogue crawl is therefore still only a bounded fallback; the keyword search is the primary route.

CILRAP/FICHL/CMN/TOAEP main text is under `#content`. The helper removes navigation/scripts/forms and follows allowed-domain links up to its page/depth limit. PDF responses are extracted as text. `link-label-only` hits do not prove destination text was read.

## ICRC interfaces: live, with query-specific WAF

Public HTML links to `env-config.js` and `index.*.js`. The JS defines `getRulesResults`, `getPracticeResults`, `getTreatiesResults`, `getArticlesResults`, `getCommentariesResults`, `getRatificationsResults`, `getNPResults`.

`GET https://ihl-databases.icrc.org/{lang}/jsonapi/index/{index}`

Parameters: `page[limit]`, `page[offset]`, `filter[fulltext]`. Indexes:

- `cihl_rule_search`, `cihl_practice_search`
- `tspc_treaty_search`, `tspc_article_search`, `tspc_commentary_search`, `tspc_participant_search`
- `np_search`

Client requests can also include `fields[...]` and `include` for relationships. On 2026-10-14 the native indexes returned HTTP 200 and parsed rule, practice, treaty, commentary and national-practice records. The remaining limitations are query- and request-state-specific: `command responsibility` triggered HTTP 403 across several indexes, while `command`, `responsibility`, `superior responsibility`, `child soldiers` and `state responsibility` returned 200 in the first pass; a later `child soldiers` run received a transient 503 on one practice index. The adapter therefore records the exact query and falls back explicitly instead of treating the database as wholly unavailable. LTD-only fallback is not the complete ICRC database.


## Customary IHL book corpus

The original guide separately recommends the two-volume Rules/Practice collection. The helper downloads its three English PDF files from these verified LTD records, extracts every page once and caches text:

- Volume I, Rules: https://www.legal-tools.org/doc/78a250/pdf/ (catalogue: 689 pages).
- Volume II, Practice, Part I: https://www.legal-tools.org/doc/a5bc79/pdf/ (catalogue: 2017 pages).
- Volume II, Practice, Part II: https://www.legal-tools.org/doc/d8df48/pdf/ (catalogue: 2431 pages).

Actual page counts and hashes are emitted under `pagination.customary-books.volumes`. Pages are matched locally with AND over query tokens, then paginated across matched pages. The first search may take longer; subsequent queries reuse cached page text. Edition/year and printed pagination must be checked in the document, not inferred solely from the catalogue (which labels these 2009).

Do not filter this corpus by LTD `organisation=ICRC`: the older book records have missing organisation metadata. Also do not confuse `5d0edd` (misleadingly titled Vol. I, actually a one-page page-heads sheet) or `bee744` (title-page file) with the full book. These distinctions were established by catalogue metadata and actual PDF text checks.
