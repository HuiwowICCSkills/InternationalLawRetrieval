#!/usr/bin/env python3
"""Headless Cloudflare fallback for approved international-law research hosts."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / 'vendor' / 'CloudflareBypassForScraping'
SSRN_DOI_RE = re.compile(r'^/10\.2139/ssrn\.(\d+)$', re.I)


def find_browser() -> str:
    configured = os.environ.get('GIL_ICJ_BROWSER_PATH') or os.environ.get('CF_BROWSER_PATH')
    if configured:
        path = Path(configured)
        if path.is_file():
            return str(path)
        raise FileNotFoundError(f'Configured browser does not exist: {path}')

    candidates = [
        Path(os.environ.get('PROGRAMFILES', '')) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('PROGRAMFILES(X86)', '')) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Google/Chrome/Application/chrome.exe',
        Path(os.environ.get('PROGRAMFILES', '')) / 'Microsoft/Edge/Application/msedge.exe',
        Path(os.environ.get('PROGRAMFILES(X86)', '')) / 'Microsoft/Edge/Application/msedge.exe',
        Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
        Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'),
        Path('/usr/bin/google-chrome'),
        Path('/usr/bin/google-chrome-stable'),
        Path('/usr/bin/chromium'),
        Path('/usr/bin/chromium-browser'),
        Path('/usr/bin/microsoft-edge'),
    ]
    for command in ('chrome', 'google-chrome', 'google-chrome-stable', 'chromium', 'msedge', 'microsoft-edge'):
        resolved = shutil.which(command)
        if resolved:
            candidates.append(Path(resolved))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError('Chrome, Chromium or Edge was not found; set GIL_ICJ_BROWSER_PATH')


def normalize_target(url: str, expected: str = 'auto') -> tuple[str, str]:
    """Return (normalized URL, expected body kind) for an approved target."""
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise ValueError('Only absolute HTTPS research URLs are supported')
    host = parsed.hostname.lower()

    if host in {'icj-cij.org', 'www.icj-cij.org'} and parsed.path.lower().endswith('.pdf'):
        kind = 'pdf'
    elif host == 'hudoc.echr.coe.int' and parsed.path == '/app/query/results':
        kind = 'json'
    elif host == 'hudoc.echr.coe.int' and parsed.path == '/eng' and re.search(r'(?:^|&)i=', parsed.query):
        kind = 'rendered_html'
    elif host == 'papers.ssrn.com' and parsed.path == '/sol3/papers.cfm' and re.search(r'(?:^|&)abstract_id=\d+', parsed.query):
        kind = 'html'
    elif host == 'doi.org' and SSRN_DOI_RE.match(parsed.path):
        abstract_id = SSRN_DOI_RE.match(parsed.path).group(1)
        return f'https://papers.ssrn.com/sol3/papers.cfm?abstract_id={abstract_id}', 'html'
    else:
        raise ValueError('URL is not in the approved Cloudflare fallback list')

    if expected != 'auto' and expected != kind:
        raise ValueError(f'Expected {expected}, but the target resolves to {kind}')
    return url, kind


def configure_environment(headless: bool) -> None:
    os.environ['CF_BROWSER_PATH'] = find_browser()
    os.environ['CF_BROWSERS'] = '1'
    os.environ['CF_HEADLESS'] = 'true' if headless else 'false'
    os.environ.setdefault('CF_CHALLENGE_TIMEOUT', '60')
    os.environ.setdefault('CF_JOB_TIMEOUT', '180')


def validate_body(kind: str, body: bytes, content_type: str, status_code: int) -> dict:
    if status_code != 200:
        raise RuntimeError(f'Target returned HTTP {status_code}')
    if kind == 'pdf':
        if not body.startswith(b'%PDF'):
            raise RuntimeError(f'Expected a PDF, received {content_type or "unknown content"}')
        return {'validated': 'pdf-signature'}
    if kind == 'json':
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError) as exc:
            raise RuntimeError('Expected JSON, received an invalid body') from exc
        if not isinstance(payload, dict):
            raise RuntimeError('Expected a JSON object')
        return {
            'validated': 'json-object',
            'resultcount': payload.get('resultcount'),
            'has_results': 'results' in payload,
        }
    if kind == 'rendered_html':
        text = body.decode('utf-8', 'replace')[:30000]
        if '<html' not in text.lower():
            raise RuntimeError('Expected rendered HTML')
        if re.search(r'just a moment|cf-chl|challenge-platform|access denied|human verification', text, re.I):
            raise RuntimeError('Rendered HTML still contains an access challenge')
        title = re.search(r'<title[^>]*>(.*?)</title>', text, re.I | re.S)
        return {
            'validated': 'rendered-html',
            'title': re.sub(r'\s+', ' ', title.group(1)).strip() if title else '',
        }
    text = body.decode('utf-8', 'replace')[:20000]
    if '<html' not in text.lower():
        raise RuntimeError(f'Expected HTML, received {content_type or "unknown content"}')
    if re.search(r'just a moment|cf-chl|challenge-platform|access denied|human verification', text, re.I):
        raise RuntimeError('HTML still contains an access challenge')
    title = re.search(r'<title[^>]*>(.*?)</title>', text, re.I | re.S)
    return {
        'validated': 'html-page',
        'title': re.sub(r'\s+', ' ', title.group(1)).strip() if title else '',
    }


async def fetch_target(url: str, output: Path, expected: str, headless: bool) -> dict:
    url, kind = normalize_target(url, expected)
    configure_environment(headless)
    sys.path.insert(0, str(VENDOR))
    from cf_bypasser import CFBypasser

    bypasser = CFBypasser(log=True)
    started = time.monotonic()
    started_ok = False
    try:
        await bypasser.start()
        started_ok = True
        async with bypasser.pool.lease() as slot:
            try:
                # The vendored HTTP endpoints discard responses when Cloudflare is
                # detected without setting cf_clearance. HUDOC currently clears the
                # challenge but returns valid JSON without that cookie, so invoke
                # the reviewed core job directly and validate the body by schema.
                mode = 'html' if kind == 'rendered_html' else 'fetch'
                data, cf_detected = await bypasser.pool.run(
                    bypasser._job, slot.browser, url, None, None, mode
                )
            except BaseException:
                slot.poisoned = True
                raise
        if not data:
            raise RuntimeError('Cloudflare fallback returned no response')
        if kind == 'rendered_html':
            body = (data.get('html') or '').encode('utf-8')
            content_type = 'text/html; charset=utf-8'
        else:
            body = data.get('body') or b''
            content_type = data.get('content_type') or ''
        validation = validate_body(kind, body, content_type, data.get('status_code'))

        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_name(output.name + '.tmp')
        temp.write_bytes(body)
        temp.replace(output)
        return {
            'ok': True,
            'kind': kind,
            'status_code': data['status_code'],
            'content_type': content_type,
            'bytes': len(body),
            'url': data.get('url') or url,
            'cf_detected': cf_detected,
            'browser_headless': headless,
            'user_agent': data.get('user_agent') or '',
            'cookie_names': sorted((data.get('cookies') or {}).keys()),
            'elapsed_seconds': round(time.monotonic() - started, 2),
            'output': str(output),
            **validation,
        }
    finally:
        if started_ok or bypasser.pool.started:
            await bypasser.cleanup()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--out', required=True)
    parser.add_argument(
        '--expect',
        choices=['auto', 'pdf', 'json', 'html', 'rendered_html'],
        default='auto',
    )
    parser.add_argument(
        '--headful',
        action='store_true',
        help='Show the browser window for troubleshooting. Headless is the default.',
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    try:
        result = asyncio.run(
            fetch_target(args.url, Path(args.out).resolve(), args.expect, not args.headful)
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': f'{type(exc).__name__}: {exc}'}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
