# Validation record

> **2026-11-09 拆分说明**：`icty`、`ucr`、`irmct-cld`、`ictr`、`icd`、`icrc-ihl`、`icrc-customary`、`mpil`、`oril-icl`、`cilrap`、`fichl` 已拆分为独立单站技能，并在 `channels.json` 标为 `active:false`。下文相关记录保留为历史适配器验证证据；当前 `search --channels` 只接受 `jicj`、`cmn`、`toaep`、`klamberg`。

## 2026-10-24 ICC official site search split out

The `icc` channel moved to the standalone `ICCSearcher` skill (console item `skill.ICCSearcher`). The toolkit removed the `references/channels.json` entry, ICC parser/search adapter, channel branch, fixtures and dedicated tests.

`ICCSearcher` owns the official `/search` route, zero-based pagination, WAF detection, linked HTML/PDF fetch, the bounded `/cases` crawl and Legal Tools ICC fallback. Its own validation record covers the successful `abcd`/`Ongwen`/`command responsibility` responses and the later WAF blocks. The old `icc` test block in this toolkit is historical and no longer part of `icl-research`.

## 2026-10-16 HeinOnline channel split out

The `heinonline` channel has been split into the standalone `HeinOnlineSearcher` skill (console item `skill.HeinOnlineSearcher`), which keeps the GDUFS `gdufs-auth-session` session, the Search Help syntax, the multi-field `advanced` form and the section-PDF `download` flow.
This toolkit removed the channel: the `references/channels.json` entry, the `scripts/heinonline_adapter.py` module, the channel branch, the `download`/`advanced` subcommands, the once-per-session browser preference gate, the `references/heinonline-search.md` copy and the related tests are gone. Records below that mention the channel are kept as history.

## 2026-10-15 ICD channel

Direct Python HTTP against the International Crimes Database, no browser, no login, no CAPTCHA or access-control bypass. The channel previously reported `unavailable-or-incomplete` with zero hits for every query; it now runs a working public keyword search.

Public route: `GET https://www.internationalcrimesdatabase.org/SearchResults/?q=<terms>&p=<page>`. Result rows live in `div.search-results`; the `<h2>` carries `N results (ordered by relevance)` or `no results`, `p.paging-controls` carries `page X of Y`, and each row is a `<strong><a href="/Case/{id}">` entry followed by a citation `<p>` and a `div.search-summary`. Server page size is five and page-size parameters (`ps`, `size`, `pagesize`, `n`) are ignored. `/Case/{id}` resolves without the slug.

Checks and observed values:

- `genocide`: 224 results, 45 pages; `--limit 10` fetched two server pages and returned ten rows.
- `Bourgmestre`: 10 results, with Akayesu at `/Case/51`, confirming that matching covers the case-record body and not only the title.
- `zzzxnonexistent785132904`: `no results` — a confirmed zero, reported as `no-results-in-queried-index`, not as site unavailability.
- Blocked phrase: `command responsibility` returned HTTP 403 from the Azure front door on every attempt (`command%20responsibility`, quoted and unquoted forms alike), as did `command and control` and `command structure`. Single tokens were unaffected: `command` 116 results, `responsibility` 253, `effective control` 153, `article 28` 525, `crime against humanity` 694 (the site search is term-based, not phrase-based). The adapter now intersects bounded term-by-term searches and labels those rows `icd-token-intersection`; for `command responsibility` this produced 22 cases containing both terms within the first 30 candidates per term, including Bemba, Yamashita and the East Timor command-responsibility cases.
- Non-route: `POST /AdvancedSearch` returned the form again with no results, and `POST /Home` quick-search with a blocked phrase was filtered. `/Cases/ByName/All` returned HTTP 504 on repeated attempts, while `/Cases/ByName`, the per-letter pages and `/Cases/ByCategory` returned 200.

Behavior tests cover the result-list parse, pagination, a confirmed zero, a missing results container treated as a failure, the labelled token intersection, and the channel-level fallback. All 30 tests in `scripts/test_icl_search.py` pass with no network access.

## 2026-10-14 recheck

Direct Python HTTP rechecked every channel that had previously been marked unavailable, plus the newly reachable ICRC endpoints. No browser, login, CAPTCHA or subscription bypass was used.

- `icrc-ihl` and `icrc-customary`: native JSON:API returned 200 for `child soldiers`, `command`, `responsibility`, `superior responsibility` and `state responsibility`. The exact phrase `command responsibility` returned HTTP 403 across the tested indexes, and a later `child soldiers` run returned a transient 503 on one practice index. The adapter now warns and falls back explicitly instead of treating the database as wholly unavailable.
- `icc` (historical; superseded by the 2026-10-24 split): `https://www.icc-cpi.int/cases` and case-filter pages returned 200. The previous `/situations` seed returned 404 and was removed. Legal Tools remained the fallback for procedural records.
- `icd`: the native form returned 200 and two results for `Akayesu`; a separate `command responsibility` run returned 403/504. Treat these as intermittent per-request failures, not permanent unavailability. Superseded 2026-10-15 by the section above: the public GET result list is the working route, and the phrase failure is a front-door filter on `command` plus a following word, not intermittent. Re-check of that run's retained HTTP cache found only three catalogue pages and the `/AdvancedSearch` GET and no `/SearchResults/` page: the `/Cases/ByCategory*` pages each carry exactly two Akayesu `/Case/` links (51, 50) while the form page carries none and the result page size is five, so the "two results" is far more consistent with the catalogue crawl fallback than with a form search result. Do not cite that line as evidence that the form searched the case records.
- `fichl`: `transitional justice` returned a 200 page match. The previous zero-hit `command responsibility` run was a bounded-crawl result, not absence from the site.
- `icty` and `ictr`: official case directories, case pages and sampled PDFs returned 200; ICTR native search returned 200.
- `toaep`: five catalogue pages and sampled PDFs returned 200.
- `ucr`: the public `https://ucr.irmct.org/api/Record/GetRecentlyFiled` endpoint returned 200 and real recent records without login. `GetInitData` and authenticated search routes returned 401. The adapter now adds public recent filings as a labelled partial result and keeps LTD mirrors; full search still requires an account.
- `klamberg`: the original domain returned Cloudflare 530. Wayback CDX and snapshots returned real historical pages and PDFs (`application/pdf`, 200), so the legacy record is partially recoverable but not a complete live database.
- `pypdf` absence caused misleading PDF-extraction warnings in one all-channel run. Installing `pypdf` in the temporary audit environment resolved those warnings; it is a dependency issue, not source unavailability.

The all-channel query itself is not a completeness claim: `partial`, `fallback` and `unavailable-or-incomplete` retain their original meanings.

Tested 2026-09-15 with direct Python HTTP, no browser. The installed helper, not only handwritten request examples, was executed. Raw development evidence is retained outside the distributed skill; it is not required to use the skill elsewhere.

## 2026-10-14 MPIL channel

`mpil` searches the OUP Max Planck Encyclopedia of Public International Law for ICL entries such as command responsibility, genocide, crimes against humanity and the ad hoc tribunals. No browser, login or subscription bypass was used.

- The generic research agent (`ICLResearch/1.0`) received HTTP 403 from `opil.ouplaw.com`; a browser-like User-Agent on the same URL returned 200. A redirect-following client without cookie persistence looped instead: `opil.ouplaw.com` to `oup2-idp.sams-sigma.com/authorize`, to `/oidc_callback?error=login_required`, back to the start.
- The product filter is `prd=MPEIPRO`. Passing `prd=MPEIPRO&EPIL` as one value encodes the `&` as `%26`, which silently drops the filter and mixes OSAIL and ORIL rows into the result set.
- Live checks: `command responsibility` 165 product-scoped matches (first hit Command Responsibility, Yoram Dinstein, MPEPIL), `genocide` 411, `state immunity` 430. Every sampled row reported Product = Max Planck Encyclopedias of International Law [MPIL], drawn from both the MPEPIL and MPEiPro modules.
- Pagination: `--offset 18 --limit 3` returned the last two rows of page 1 with `next_offset 20`; `--offset 25 --limit 2` reported page 2. `pageSize=50` is honoured.
- `fetch` on an entry URL returned 20,366 characters containing `Article last updated`, the numbered paragraphs, Select Bibliography and Select Documents, with no navigation chrome.
- Timing: the first request of a run takes 3.3-3.9 s including the redirect handshake and 1.0-1.8 s once the cookies are reused; `run.ps1` adds about 0.8 s of interpreter probing.
- `scripts/test_icl_search.py` now holds 19 tests, all passing offline, covering MPIL parsing, the pagination window, User-Agent use, stale-handshake retry, cookie-jar persistence and the fetch content selector.
- Not established: ORIL, OXIO, OHT and OSAIL on the same platform are not wired up or verified. Only the MPIL product is searched, and the channel count is now 18.

## 2026-10-14 ORIL International Criminal Law channel

`oril-icl` searches the International Criminal Law sub-series of Oxford Reports on International Law through the platform `pc_32` UUID facet. Anonymous HTTP only; no browser, login or subscription bypass was used.

- Search URL: `https://opil.ouplaw.com/search?sfam=&q=<query>&pc_32=68306099-6983-4cb7-a931-60f851434432&pageSize=20|50&sort=relevance&page=N`. Both `page=N` and `pageSize=50` work.
- Facet UUIDs measured on this platform: whole ORIL product `pc_17=bdcb8d33-0914-4cd9-bd2b-c84ac21665f7`; ICL sub-series `pc_32=68306099-6983-4cb7-a931-60f851434432`; ILDC sub-series `pc_20=129d4f34-d269-49ef-ac37-1557c85043fc`. Only these three were exercised.
- Measured counts (anonymous): ICL sub-series browse 1,531, `command responsibility` 365, `superior responsibility` 316, `genocide` 504. Contrast: MPIL `command responsibility` 165, whole ORIL product `command responsibility` 1,011 and `Akayesu` 250.
- Parameter trap, reproduced twice in fresh sessions: on the `pc_*` facets, adding `access=all` silently narrows the set (ICL 365 to 3; whole ORIL 1,011 to 4), while `level=all`, `pageSize` and `sort` alone changed nothing. The `prd` facet behaves the other way: MPIL needs `access=all&level=all` or the server drops the product filter and `genocide` returns 3,814 mixed MPIL/OSAIL rows instead of 411 MPIL-only rows. The adapter therefore sends the correct combination per facet family and validates the returned Product values, raising instead of returning a silently wrong set.
- Rows are `div.contentItem` with `case-whole`/`locked` classes: `h2.itemTitle a` for the title and URL, and `dl.metadata` carrying Date, Content type, Product, Module, Jurisdiction, Subject(s) and an editorially written `Core Issue(s)`. There is no `div.component-content-summary` (measured zero), so `Core Issue(s)` is the only summary available and no snippet should be promised.
- Anonymous readability sample of 13 report pages across ICL, ILDC, IHRL and ICGJ: 12 returned 1,333-2,266 characters (citation header plus core issue(s), i.e. headnote only, several carrying a sign-in prompt), and one, `law-icl-2038icc21` (Ongwen Trial Judgment), returned 381,724 characters with 426 numbered paragraphs. The sample does not support classifying completeness by sub-series or by case type, so `fetch` reports `text_characters` and callers must check it before treating a page as a full report.
- `#mainContent` is the working body container for ORIL pages (it also works for MPIL). These are the same container and User-Agent rules as the MPIL channel.
- Rate limiting: after roughly 20 requests in a burst the platform answered HTTP 405 with the title `Human Verification` for about 3.5 minutes, then returned the same counts for the same URLs. The adapter enforces a 2-second per-host gap for `opil.ouplaw.com` and classifies that page as an access challenge, never as zero results.
- Entry URLs must be used exactly as returned by search: this platform serves both `/law:icl/...` and `/law-icl/...` path forms, and rebuilding one form for a document published under the other returns 404.
- `scripts/test_icl_search.py` now holds 24 tests, all passing offline, including the ORIL facet parameters, the citation/core-issue row fields, the `locked` access wording and the product-mismatch rejection.
- Resolved on 2026-10-14: `access` is a search-state parameter, not an access-level switch. When the URL carries `access=all` the returned page fills its own hidden field with `access=user`, i.e. the server reads it as "only items this session may read"; `access=user` and `access=all` give identical results. That explains every observation: MPIL is Subscribe-to-Open so its 165 rows are all readable and the filter changes nothing, whereas the ORIL `command responsibility` set falls from 1,011 rows (top 20 all `locked`) to 4 readable rows (ICL 3 + ILDC 1, including the Ongwen judgment whose page carries 381,724 characters of full text). A keyword-free ORIL browse under `access=all` returns 16 rows: ILDC 10, ILEC 2, ICL 4, matching the previously reported 16 (ICL 4, ILDC 10). The state persists in the session, so after one `access=all` request later plain requests also returned 16 - which is what made the 1,011 figure look irreproducible earlier. The adapter therefore never sends `access` for ORIL and keeps a separate cookie file per channel.
- Fresh-session isolation test completed on 2026-10-14, one new session per case: a first request without `access` returned 10,034 ORIL browse rows with page state `all`, and a repeat in the same session stayed at 10,034; a separate new session with `access=all` returned 16 with state `user`, and `access=user` returned the same 16, confirming the two are equivalent. The state is session-scoped rather than IP-scoped: after one session requested `access=all`, two later plain requests in that same session stayed at 16 with the hidden field still reading `user`, while a further brand-new session requesting the bare URL returned 10,034 with state `all` again. That is what made 1,011 and 10,034 look irreproducible earlier in this round. The adapter keeps one cookie file per channel so this state cannot leak between them.
- ORIL sub-series facets. A keyword-free browse exposed the full list in the facet tree, with that browse's counts in brackets: `pc_20` ILDC 2,878; `pc_28` IHRL 2,920; `pc_36` IIC 1,870; `pc_32` ICL 1,531; `pc_24` ICGJ 554; `pc_40` ITL 165; `pc_44` ILEC 116; plus `pc_17` for the whole ORIL product at 10,034. The seven sum to 2,878+2,920+1,870+1,531+554+165+116 = 10,034, exactly the product total, so they partition ORIL. For `command responsibility`, the tree showed only six sub-series because ILEC had no hits - it lists only facets with matches. The ILEC UUID is `pc_44=1bf47a86-bafa-480c-af75-1099fb45836c`.
- The same tree also carried `pc_83=5381f75c-dc3f-4d36-8119-445bc61ded` for `Oxford International Organizations [OXIO]` (1 row in that browse), so the `pc_*` family is not exclusive to ORIL sub-series: match on UUID and label rather than assuming the parameter prefix identifies the product.
- Not established: the real extent of ORIL report-text coverage under an institutional session; and how stable the `access=user` readable subset is across other queries (only `command responsibility` and the keyword-free browse were re-tested here).

## Passing checks

- Skill Creator `quick_validate.py`: passed with Python `-X utf8` (the validator otherwise uses Windows GBK when reading Chinese frontmatter).
- `scripts/test_icl_search.py`: 5 passing behavior tests covering diacritic matching and distinct appellate extracts, explicit native-denial/mirror fallback, book page matching/pagination, offline network exclusion, and preservation of unexpected source errors.
- Full 15-channel CLI query `command responsibility`: all 15 channel reports returned. Some routes used cached successful HTTP responses; unavailable native requests retained their failures. A query without a match in a bounded crawl was not labelled exhaustive absence.
- JICJ query returned DOI `10.1093/jicj/mqs085` with bibliographic metadata.
- Legal Tools `Lubanga`, ICC organisation filter, offsets 0 and 3, limit 3: six distinct result IDs; all six institution labels were ICC.
- Artificial absent term `zzzxnonexistent785132904`: Legal Tools and CLD returned zero matches, correctly distinguished from access failure.
- CLD downloaded its public metadata table and retrieved real extracts with paragraph-numbered text.
- CLICC query returned Article 28 commentary body and footnotes. A returned `/api/v1/nodes/path/28-a-criminally-responsible?treeKind=Commentary&lang=en` returned HTTP 200 and document content. **This route moved to the standalone `LexsitusSearcher` skill on 2026-10-18**; the `icl-research` adapter no longer calls it. The standalone skill re-verified the route and recorded that the API's `pagination.total`/`totalPages` are unreliable.
- CILRAP `communitarian scholarship` and FICHL `transitional justice`: positive HTTP-page matches. ICD `Akayesu`: successful native form query; some other search terms received 403. ICD keyword search was later rebuilt on the public GET result list (2026-10-15).
- TOAEP PDF `https://www.toaep.org/pbs-pdf/203-dahl/`: fetched and extracted all 4 pages, no OCR needed. Tested both pypdf and the later installed PyMuPDF extraction path.
- Customary IHL fallback: all three mirrored English books downloaded and fully extracted, 5,137 pages total. `command responsibility` matched 201 pages with local all-token matching; output is paginated and not a legal relevance determination.
- Offline replay of Legal Tools, CLD and customary-book results: succeeded with the HTTP request method patched to throw if any network access was attempted. CLICC replay now belongs to the `LexsitusSearcher` skill's own tests.

## Customary book evidence

| Volume | Actual PDF pages | SHA-256 |
|---|---:|---|
| I, Rules (`78a250`) | 689 | `ba414d1714ec43dc8d64db971bab97442f69e1d62add3b78d97b6c8ba54aa6bc` |
| II, Practice, Part I (`a5bc79`) | 2017 | `62b1f43365058d9af2abd7b22db1cb39b2a5e3f425f72bf663b0da4689bfd9a8` |
| II, Practice, Part II (`d8df48`) | 2431 | `e2b0360423bb9886e6b65a617a3905dd50636c2e9cda897936db891c29248a16` |

PDF page position is not necessarily printed book pagination. Inspect the chosen page before citing. Book metadata dates vary by edition/reprint; this corpus is not the continually updated ICRC online database.

## Not established

- Authenticated UCR search, OUP subscriber full text, complete ODS keyword search, complete UN Digital Library web search, or ICJ judgment PDFs through direct links that return Cloudflare 403.
- Exhaustive current holdings, complete historical migration of iclklamberg.com, a complete text crawl of CILRAP/FICHL/CMN/ICD, or ongoing API stability. For ICD, the keyword search reaches the whole case record, but a phrase is only as complete as the bounded term-by-term intersection when the front door filters it.
- Visual page-layout QA was not performed or needed: these checks concern retrieved data and searchable text, not document rendering.

No accounts were registered, no messages sent, and no CAPTCHA or access-control bypass was used.
