"""Build an offline, conditional manual-research checklist from GIL/ICL reports."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = json.loads((ROOT / 'references/routes.json').read_text(encoding='utf-8'))['routes']


def build(report, domain=None):
    channels = report.get('channels')
    if not isinstance(channels, list):
        raise ValueError('Expected a GIL/ICL search report with channels array')
    tasks, automatic = [], []
    for channel in channels:
        if not isinstance(channel, dict):
            raise ValueError('Each channel must be an object')
        detected = 'gil' if channel.get('source') else 'icl' if channel.get('channel') else None
        if not detected or (domain and domain != detected):
            raise ValueError('Channel identifiers do not match the selected report domain')
        source = channel.get('source') or channel['channel']
        selector = detected + ':' + source
        status = channel.get('status', 'unknown')
        warnings = channel.get('warnings') or []
        if not isinstance(warnings, list):
            warnings = [str(warnings)]
        rows = channel.get('results') or []
        failures = [r.get('fetch_error') for r in rows if r.get('fetch_error')]
        reason = '; '.join(str(v) for v in warnings + failures)
        lower = reason.casefold()
        failed = status in ('unavailable', 'unavailable-or-incomplete', 'error', 'partial', 'manual') or bool(failures)
        has_text = lambda r: bool(r.get('full_text') or (r.get('document', {}).get('pages') and r['document'].get('result_type') == 'retrieved_text' and not r['document'].get('ocr_needed')))
        all_have_text = bool(rows) and all(has_text(r) for r in rows)
        chosen = [route for route in ROUTES if selector in route['selectors'] and (route.get('trigger') != 'failure' or failed)]
        timeout_only = ('timeout' in lower or 'timed out' in lower or 'connectionerror' in lower or 'cache miss' in lower) and not any(w in lower for w in ['403','401','captcha','login','sign-in'])
        if timeout_only:
            automatic.append({'source':selector,'reason':reason,'action':'先检查网络/缓存或进行一次有界在线重试；失败后才评估人工补检。'})
        if 'bounded' in lower or 'crawl' in lower:
            automatic.append({'source':selector,'reason':reason,'action':'先用原工具扩大合理的页数/深度或调整关键词；有限抓取不是必须人工操作。'})
        for route in chosen:
            if route['id'] == 'journal-fulltext' and all_have_text:
                continue
            task = {k:v for k,v in route.items() if k not in ('selectors','trigger')}
            task.update(source=selector, query=report.get('query') or channel.get('query', ''),
                        observation_time=channel.get('retrieved_at') or report.get('generated_at') or report.get('timestamp'),
                        status='pending', required=False, current_channel_status=status,
                        reason=reason or channel.get('scope') or '按本次研究的全文、原站或覆盖要求决定是否执行',
                        retrieved_results=len(rows),
                        observed_urls=list(dict.fromkeys(r['url'] for r in rows if r.get('url'))),
                        priority='after_automatic_retry' if timeout_only else 'conditional_on_research_need')
            tasks.append(task)
        if failed and not chosen and not timeout_only:
            automatic.append({'source':selector,'reason':reason,'action':'先诊断原工具或具体下载失败；仅在确认登录/订阅/访问挑战后交人工补检。'})
        for row in rows:
            if row.get('document', {}).get('ocr_needed'):
                automatic.append({'source':selector,'url':row.get('url'),'action':'对缺少文本的 PDF 页使用可用 OCR 并复核，不默认要求人工全文录入。','pages':row['document']['ocr_needed']})
    return {'schema_version':1,'query':report.get('query',''),'network_used':False,
            'note':'这是条件性待办清单，所有任务均未执行；需结合研究目标判断，不能视作已取得结果。',
            'manual_tasks':tasks,'automatic_followups':automatic}


def markdown(data):
    lines = ['# 国际法人工补检清单', '', '查询：' + data['query'], '', data['note'], '']
    for task in data['manual_tasks']:
        lines.extend(['## ' + task['source'] + ' · ' + task['title'], '',
                      '适用条件：' + task['condition'], '当前状态：' + task['current_channel_status'],
                      '待办状态：pending（未执行）', '原因：' + task['reason'], ''])
        lines.extend(['输入报告日期：' + str(task['observation_time'] or '未提供；需核对'), ''])
        lines.extend(str(i) + '. ' + action for i,action in enumerate(task['actions'],1))
        lines.extend(['', '入口：' + '；'.join(task['entries']), '回收材料：' + '；'.join(task['deliverables']), ''])
        if task['observed_urls']:
            lines.extend(['本次已返回的具体链接：', ''] + ['- ' + u for u in task['observed_urls']] + [''])
    if data['automatic_followups']:
        lines.extend(['## 可先自动处理', ''])
        lines.extend('- ' + f['source'] + '：' + f['action'] for f in data['automatic_followups'])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--domain', choices=['gil','icl'])
    parser.add_argument('--out')
    parser.add_argument('--format', choices=['json','markdown'], default='json')
    args = parser.parse_args()
    try:
        data = build(json.loads(Path(args.input).read_text(encoding='utf-8-sig')),args.domain)
    except (ValueError,OSError) as exc:
        parser.error(str(exc))
    content = markdown(data) if args.format == 'markdown' else json.dumps(data,ensure_ascii=False,indent=2)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(content,encoding='utf-8')
        print(json.dumps({'out':str(path.resolve()),'manual_tasks':len(data['manual_tasks']),'automatic_followups':len(data['automatic_followups'])},ensure_ascii=False))
    else:
        print(content)


if __name__ == '__main__':
    main()
