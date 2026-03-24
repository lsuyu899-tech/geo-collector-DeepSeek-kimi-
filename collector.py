#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
import csv
import json
import os
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

COL_QUESTION = u"\u7528\u6237\u95ee\u9898"
COL_KIMI_ANSWER = u"Kimi\u56de\u7b54"
COL_KIMI_DOMAINS = u"Kimi\u6765\u6e90\u57df\u540d"
COL_KIMI_CHANNELS = u"Kimi\u6765\u6e90\u6e20\u9053"
COL_KIMI_URLS = u"Kimi\u6765\u6e90\u94fe\u63a5"
COL_KIMI_MARKED = u"Kimi\u6765\u6e90\u94fe\u63a5(\u6e20\u9053\u6807\u6ce8)"
COL_KIMI_STATUS = u"Kimi\u72b6\u6001"
COL_DOUBAO_ANSWER = u"\u8c46\u5305\u56de\u7b54"
COL_DOUBAO_DOMAINS = u"\u8c46\u5305\u6765\u6e90\u57df\u540d"
COL_DOUBAO_CHANNELS = u"\u8c46\u5305\u6765\u6e90\u6e20\u9053"
COL_DOUBAO_URLS = u"\u8c46\u5305\u6765\u6e90\u94fe\u63a5"
COL_DOUBAO_MARKED = u"\u8c46\u5305\u6765\u6e90\u94fe\u63a5(\u6e20\u9053\u6807\u6ce8)"
COL_DOUBAO_RAW_URLS = u"\u8c46\u5305\u539f\u59cb\u94fe\u63a5"
COL_DOUBAO_WS_CALLS = u"\u8c46\u5305\u8054\u7f51\u641c\u7d22\u6b21\u6570"
COL_DOUBAO_STATUS = u"\u8c46\u5305\u72b6\u6001"
COL_DEEPSEEK_ANSWER = u"DeepSeek\u56de\u7b54"
COL_DEEPSEEK_DOMAINS = u"DeepSeek\u6765\u6e90\u57df\u540d"
COL_DEEPSEEK_CHANNELS = u"DeepSeek\u6765\u6e90\u6e20\u9053"
COL_DEEPSEEK_URLS = u"DeepSeek\u6765\u6e90\u94fe\u63a5"
COL_DEEPSEEK_MARKED = u"DeepSeek\u6765\u6e90\u94fe\u63a5(\u6e20\u9053\u6807\u6ce8)"
COL_DEEPSEEK_STATUS = u"DeepSeek\u72b6\u6001"
COL_ELAPSED = u"\u8017\u65f6\u79d2"
COL_CREATED_AT = u"\u91c7\u96c6\u65f6\u95f4"

SUMMARY_COL_PLATFORM = u"\u5e73\u53f0"
SUMMARY_COL_RANK = u"\u6392\u540d"
SUMMARY_COL_CHANNEL = u"\u6765\u6e90\u6e20\u9053"
SUMMARY_COL_LINK_COUNT = u"\u94fe\u63a5\u6b21\u6570"
SUMMARY_COL_QUESTION_COUNT = u"\u8986\u76d6\u95ee\u9898\u6570"

PLATFORM_KIMI = u"Kimi"
PLATFORM_DOUBAO = u"\u8c46\u5305"
PLATFORM_DEEPSEEK = u"DeepSeek"

URL_RE = re.compile(r'https?://[^\s<>\]\)"\',;]+', re.IGNORECASE)
DEFAULT_SYSTEM_PROMPT = (
    "You are an information retrieval assistant. Use web results when needed. "
    "At the end, list the URLs you actually referenced."
)


def now_ts():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def dedupe_keep_order(items):
    seen = set(); out = []
    for x in items:
        if x in seen:
            continue
        seen.add(x); out.append(x)
    return out


def normalize_domain(url):
    try:
        netloc = urllib_parse.urlparse(url).netloc.strip().lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def extract_urls_from_text(text):
    if not text or not isinstance(text, str):
        return []
    return dedupe_keep_order(URL_RE.findall(text))


def extract_urls_from_obj(obj):
    urls = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                urls.extend(extract_urls_from_obj(v))
            elif isinstance(v, str):
                urls.extend(extract_urls_from_text(v))
                if k.lower() in ("url", "href", "link") and v.startswith("http"):
                    urls.append(v)
    elif isinstance(obj, list):
        for item in obj:
            urls.extend(extract_urls_from_obj(item))
    elif isinstance(obj, str):
        urls.extend(extract_urls_from_text(obj))
    return dedupe_keep_order(urls)


def extract_doubao_citation_urls(obj):
    urls = []
    if isinstance(obj, dict):
        if str(obj.get("type", "")).lower() == "url_citation":
            u = obj.get("url")
            if isinstance(u, str) and u.startswith("http"):
                urls.append(u)
        for v in obj.values():
            urls.extend(extract_doubao_citation_urls(v))
    elif isinstance(obj, list):
        for item in obj:
            urls.extend(extract_doubao_citation_urls(item))
    return dedupe_keep_order(urls)


def is_noise_url(url):
    d = normalize_domain(url)
    if not d:
        return True
    if "byteimg.com" in d:
        return True
    if d.startswith("p1-") or d.startswith("p2-") or d.startswith("p3-") or d.startswith("p26-"):
        return True
    if any(url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]):
        return True
    return False


def detect_channel(url):
    d = normalize_domain(url)
    if not d:
        return u"\u5176\u4ed6"
    if d in ("mp.weixin.qq.com", "weixin.qq.com"):
        return u"\u5fae\u4fe1\u516c\u4f17\u53f7"
    if "toutiao.com" in d:
        return u"\u4eca\u65e5\u5934\u6761"
    if "zhihu.com" in d:
        return u"\u77e5\u4e4e"
    if d == "zhidao.baidu.com":
        return u"\u767e\u5ea6\u77e5\u9053"
    if d == "jingyan.baidu.com":
        return u"\u767e\u5ea6\u7ecf\u9a8c"
    if d == "baike.baidu.com":
        return u"\u767e\u5ea6\u767e\u79d1"
    if d == "tieba.baidu.com":
        return u"\u767e\u5ea6\u8d34\u5427"
    if d == "baijiahao.baidu.com":
        return u"\u767e\u5bb6\u53f7"
    if "baidu.com" in d:
        return u"\u767e\u5ea6"
    if "sohu.com" in d:
        return u"\u641c\u72d0"
    if d.endswith("qq.com"):
        return u"\u817e\u8baf\u7cfb"
    if "163.com" in d:
        return u"\u7f51\u6613"
    if "weibo.com" in d:
        return u"\u5fae\u535a"
    if "xiaohongshu.com" in d:
        return u"\u5c0f\u7ea2\u4e66"
    if "bilibili.com" in d:
        return u"\u54d4\u54e9\u54d4\u54e9"
    if "csdn.net" in d:
        return "CSDN"
    return d


def summarize_channels(urls):
    return dedupe_keep_order([detect_channel(u) for u in (urls or []) if u])


def marked_urls(urls):
    out = []
    for u in (urls or []):
        if u:
            out.append("{}::{}".format(detect_channel(u), u))
    return dedupe_keep_order(out)


def extract_text_payload(content):
    out = []
    if isinstance(content, str):
        out.append(content)
    elif isinstance(content, dict):
        t = content.get("text")
        if isinstance(t, str):
            out.append(t)
        for v in content.values():
            out.extend(extract_text_payload(v))
    elif isinstance(content, list):
        for item in content:
            out.extend(extract_text_payload(item))
    return dedupe_keep_order(out)


def assistant_texts_from_obj(obj):
    texts = []
    if isinstance(obj, dict):
        if obj.get("role") == "assistant":
            texts.extend(extract_text_payload(obj.get("content")))
            if isinstance(obj.get("text"), str):
                texts.append(obj.get("text"))
        if obj.get("type") in ("text", "output_text") and isinstance(obj.get("text"), str):
            texts.append(obj.get("text"))
        for v in obj.values():
            texts.extend(assistant_texts_from_obj(v))
    elif isinstance(obj, list):
        for item in obj:
            texts.extend(assistant_texts_from_obj(item))
    return dedupe_keep_order([x for x in texts if isinstance(x, str) and x.strip()])


def count_web_search_calls(obj):
    c = 0
    if isinstance(obj, dict):
        if str(obj.get("type", "")).lower() == "web_search_call":
            c += 1
        for v in obj.values():
            c += count_web_search_calls(v)
    elif isinstance(obj, list):
        for item in obj:
            c += count_web_search_calls(item)
    return c


def http_post_json(url, headers, payload, timeout=120):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(url=url, data=body, headers=headers, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError("HTTP {} {}: {}".format(e.code, url, err))
    except URLError as e:
        raise RuntimeError("URL error for {}: {}".format(url, str(e)))


def run_with_retries(fn, max_retries, base_sleep):
    last = None
    for i in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(base_sleep * (2 ** i))
    raise last


def parse_allowed_temperature(err_text):
    if not err_text:
        return None
    m = re.search(r"only\s*([0-9]+(?:\.[0-9]+)?)\s*is allowed", str(err_text), re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None

class ProviderClients(object):
    def __init__(self, args):
        self.args = args
        self.kimi_key = os.getenv("MOONSHOT_API_KEY", "").strip()
        self.ark_key = os.getenv("ARK_API_KEY", "").strip()
        self.ark_model = (args.doubao_model or os.getenv("ARK_MODEL", "")).strip()
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.kimi_temperature_override = None

    def kimi(self, question):
        if not self.kimi_key:
            return {"answer": "", "urls": [], "domains": [], "status": "missing_api_key(MOONSHOT_API_KEY)"}
        headers = {"Authorization": "Bearer " + self.kimi_key, "Content-Type": "application/json"}
        url = self.args.kimi_base_url.rstrip("/") + "/chat/completions"
        messages = [{"role": "system", "content": self.args.system_prompt}, {"role": "user", "content": question}]
        all_urls = []
        answer = ""

        for _ in range(self.args.kimi_tool_loops):
            kimi_temperature = (
                self.kimi_temperature_override
                if self.kimi_temperature_override is not None
                else self.args.kimi_temperature
            )
            payload = {
                "model": self.args.kimi_model,
                "messages": messages,
                "temperature": kimi_temperature,
                "max_tokens": self.args.max_tokens,
                "tools": [{"type": "builtin_function", "function": {"name": "$web_search"}}],
                "thinking": {"type": "disabled"},
                "extra_body": {"thinking": {"type": "disabled"}},
            }
            try:
                data = run_with_retries(
                    lambda: http_post_json(url, headers, payload, timeout=self.args.timeout),
                    self.args.max_retries,
                    self.args.retry_base_sleep,
                )
            except Exception as e:
                allowed_temp = parse_allowed_temperature(str(e))
                if allowed_temp is None:
                    raise
                # Auto-adapt to provider-required fixed temperature for this model/account.
                self.kimi_temperature_override = allowed_temp
                payload["temperature"] = allowed_temp
                data = run_with_retries(
                    lambda: http_post_json(url, headers, payload, timeout=self.args.timeout),
                    self.args.max_retries,
                    self.args.retry_base_sleep,
                )
            all_urls.extend(extract_urls_from_obj(data))
            choice = ((data.get("choices") or [{}])[0]) if isinstance(data, dict) else {}
            msg = choice.get("message") or {}
            finish_reason = choice.get("finish_reason")

            if finish_reason == "tool_calls":
                tool_calls = msg.get("tool_calls") or []
                messages.append({
                    "role": "assistant",
                    "content": msg.get("content", ""),
                    "tool_calls": tool_calls,
                    "reasoning_content": msg.get("reasoning_content", ""),
                })
                for tc in tool_calls:
                    fn_info = tc.get("function") or {}
                    args_raw = fn_info.get("arguments", "{}")
                    try:
                        args_obj = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                    except Exception:
                        args_obj = {"raw_arguments": args_raw}
                    all_urls.extend(extract_urls_from_obj(args_obj))
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "name": fn_info.get("name", ""),
                        "content": json.dumps(args_obj, ensure_ascii=False),
                    })
                continue

            answer = msg.get("content", "") if isinstance(msg, dict) else ""
            all_urls.extend(extract_urls_from_text(answer))
            break

        urls = dedupe_keep_order([u for u in all_urls if u.startswith("http")])
        domains = dedupe_keep_order([normalize_domain(u) for u in urls if normalize_domain(u)])
        return {"answer": answer, "urls": urls, "domains": domains, "status": "ok" if answer else "empty_answer"}

    def doubao(self, question):
        if not self.ark_key:
            return {"answer": "", "urls": [], "domains": [], "status": "missing_api_key(ARK_API_KEY)"}
        if not self.ark_model:
            return {"answer": "", "urls": [], "domains": [], "status": "missing_model(--doubao-model or ARK_MODEL)"}

        headers = {"Authorization": "Bearer " + self.ark_key, "Content-Type": "application/json"}
        url = self.args.ark_base_url.rstrip("/") + "/responses"
        payload = {
            "model": self.ark_model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": self.args.system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": question}]},
            ],
            "tools": [{"type": "web_search", "max_keyword": self.args.doubao_max_keyword, "limit": self.args.doubao_limit}],
            "max_tool_calls": self.args.doubao_max_tool_calls,
            "temperature": self.args.temperature,
            "max_output_tokens": self.args.max_tokens,
        }
        try:
            data = run_with_retries(
                lambda: http_post_json(url, headers, payload, timeout=self.args.timeout),
                self.args.max_retries,
                self.args.retry_base_sleep,
            )
        except Exception as e:
            s = str(e)
            if "ToolNotOpen" in s:
                return {"answer": "", "urls": [], "domains": [], "status": "tool_not_open(activate_web_search_in_ark_console)"}
            return {"answer": "", "urls": [], "domains": [], "status": "error:" + s}

        raw_urls = dedupe_keep_order(extract_urls_from_obj(data))
        urls = dedupe_keep_order(extract_doubao_citation_urls(data)) or raw_urls
        urls = dedupe_keep_order([u for u in urls if not is_noise_url(u)])
        domains = dedupe_keep_order([normalize_domain(u) for u in urls if normalize_domain(u)])
        answer = "\n".join(assistant_texts_from_obj(data))
        ws_calls = count_web_search_calls(data)
        if answer and ws_calls > 0:
            status = "ok(web_search_called={})".format(ws_calls)
        elif answer:
            status = "ok_no_web_search_call"
        else:
            status = "empty_answer"
        return {
            "answer": answer,
            "urls": urls,
            "domains": domains,
            "status": status,
            "web_search_calls": ws_calls,
            "raw_urls": raw_urls,
        }

    def deepseek(self, question):
        if self.args.deepseek_mode == "skip":
            return {"answer": "", "urls": [], "domains": [], "status": "skipped_by_config"}
        if not self.deepseek_key:
            return {"answer": "", "urls": [], "domains": [], "status": "missing_api_key(DEEPSEEK_API_KEY)"}

        headers = {"Authorization": "Bearer " + self.deepseek_key, "Content-Type": "application/json"}
        url = self.args.deepseek_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.args.deepseek_model,
            "messages": [
                {"role": "system", "content": self.args.system_prompt},
                {"role": "user", "content": question + "\n\nIf possible, provide source URLs. If not web-enabled, say so clearly."},
            ],
            "temperature": self.args.temperature,
            "max_tokens": self.args.max_tokens,
        }
        try:
            data = run_with_retries(
                lambda: http_post_json(url, headers, payload, timeout=self.args.timeout),
                self.args.max_retries,
                self.args.retry_base_sleep,
            )
        except Exception as e:
            return {"answer": "", "urls": [], "domains": [], "status": "error:" + str(e)}

        choice = ((data.get("choices") or [{}])[0]) if isinstance(data, dict) else {}
        msg = choice.get("message") or {}
        answer = msg.get("content", "") if isinstance(msg, dict) else ""
        urls = dedupe_keep_order(extract_urls_from_obj(data) + extract_urls_from_text(answer))
        domains = dedupe_keep_order([normalize_domain(u) for u in urls if normalize_domain(u)])
        return {"answer": answer, "urls": urls, "domains": domains, "status": "ok_no_builtin_search" if answer else "empty_answer"}


def read_questions(path, question_column):
    out = []

    def resolve_question_column(fields, requested):
        fields = fields or []
        if not fields:
            return None

        req = (requested or "").strip()
        if req in fields:
            return req

        req_low = req.lower()
        for f in fields:
            if (f or "").strip().lower() == req_low and req_low:
                return f

        aliases = [
            "question",
            "questions",
            "query",
            "prompt",
            "input",
            "user_question",
            "问题",
            "用户问题",
            "提问",
            "问句",
            "关键词",
        ]
        for a in aliases:
            a_low = a.lower()
            for f in fields:
                if (f or "").strip().lower() == a_low:
                    return f

        if len(fields) == 1:
            return fields[0]
        return None

    if path.lower().endswith(".txt"):
        txt_encodings = ["utf-8", "utf-8-sig", "gb18030", "gbk"]
        txt_ok = False
        last_err = None
        for enc in txt_encodings:
            try:
                with open(path, "r", encoding=enc) as f:
                    for line in f:
                        q = line.strip()
                        if q:
                            out.append(q)
                txt_ok = True
                break
            except UnicodeDecodeError as e:
                last_err = e
                out = []
                continue
        if not txt_ok:
            raise ValueError("cannot decode txt file '{}', tried encodings={}, last_error={}".format(path, txt_encodings, last_err))
    elif path.lower().endswith(".csv"):
        csv_encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk"]
        decode_errors = []
        column_mismatch = []
        csv_ok = False
        for enc in csv_encodings:
            tmp = []
            try:
                with open(path, "r", encoding=enc, newline="") as f:
                    reader = csv.DictReader(f)
                    fields = reader.fieldnames or []
                    resolved_col = resolve_question_column(fields, question_column)
                    if not resolved_col:
                        column_mismatch.append((enc, question_column, fields))
                        continue
                    for row in reader:
                        q = (row.get(resolved_col) or "").strip()
                        if q:
                            tmp.append(q)
                out.extend(tmp)
                csv_ok = True
                break
            except UnicodeDecodeError as e:
                decode_errors.append((enc, str(e)))
                continue
        if not csv_ok:
            if column_mismatch:
                tried = ["{}:request='{}', fields={}".format(enc, req, fields) for enc, req, fields in column_mismatch]
                raise ValueError(
                    "question column '{}' not found and could not auto-detect. tried={}".format(question_column, tried)
                )
            raise ValueError("cannot decode csv file '{}', tried encodings={}, errors={}".format(path, csv_encodings, decode_errors))
    else:
        raise ValueError("unsupported input, use .txt or .csv")
    return dedupe_keep_order(out)


def is_done_status(s):
    s = (s or "").strip().lower()
    return bool(s) and (s.startswith("ok") or s == "skipped_by_config")


def row_get(row, keys):
    for k in keys:
        if k in row and row.get(k) is not None:
            return row.get(k)
    return ""


def load_done_questions(output_path, providers):
    if not os.path.exists(output_path):
        return set()
    done = set()
    with open(output_path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            q = (row_get(row, [COL_QUESTION, "question"]) or "").strip()
            if not q:
                continue
            ok = True
            for p in providers:
                if p == "kimi":
                    s = row_get(row, [COL_KIMI_STATUS, "kimi_status"])
                elif p == "doubao":
                    s = row_get(row, [COL_DOUBAO_STATUS, "doubao_status"])
                else:
                    s = row_get(row, [COL_DEEPSEEK_STATUS, "deepseek_status"])
                if not is_done_status(s):
                    ok = False
                    break
            if ok:
                done.add(q)
    return done


def ensure_output_header(path, fieldnames):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        csv.DictWriter(f, fieldnames=fieldnames).writeheader()


def append_row(path, fieldnames, row, lock):
    with lock:
        with open(path, "a", encoding="utf-8-sig", newline="") as f:
            csv.DictWriter(f, fieldnames=fieldnames).writerow(row)

def make_row(question, result_map, elapsed_s):
    def pick(name, key, default=""):
        return (result_map.get(name) or {}).get(key, default)
    kimi_urls = pick("kimi", "urls", []) or []
    doubao_urls = pick("doubao", "urls", []) or []
    deepseek_urls = pick("deepseek", "urls", []) or []
    return {
        COL_QUESTION: question,
        COL_KIMI_ANSWER: pick("kimi", "answer"),
        COL_KIMI_DOMAINS: "|".join(pick("kimi", "domains", []) or []),
        COL_KIMI_CHANNELS: "|".join(summarize_channels(kimi_urls)),
        COL_KIMI_URLS: "|".join(kimi_urls),
        COL_KIMI_MARKED: "|".join(marked_urls(kimi_urls)),
        COL_KIMI_STATUS: pick("kimi", "status"),
        COL_DOUBAO_ANSWER: pick("doubao", "answer"),
        COL_DOUBAO_DOMAINS: "|".join(pick("doubao", "domains", []) or []),
        COL_DOUBAO_CHANNELS: "|".join(summarize_channels(doubao_urls)),
        COL_DOUBAO_URLS: "|".join(doubao_urls),
        COL_DOUBAO_MARKED: "|".join(marked_urls(doubao_urls)),
        COL_DOUBAO_RAW_URLS: "|".join(pick("doubao", "raw_urls", []) or []),
        COL_DOUBAO_WS_CALLS: str(pick("doubao", "web_search_calls", "")),
        COL_DOUBAO_STATUS: pick("doubao", "status"),
        COL_DEEPSEEK_ANSWER: pick("deepseek", "answer"),
        COL_DEEPSEEK_DOMAINS: "|".join(pick("deepseek", "domains", []) or []),
        COL_DEEPSEEK_CHANNELS: "|".join(summarize_channels(deepseek_urls)),
        COL_DEEPSEEK_URLS: "|".join(deepseek_urls),
        COL_DEEPSEEK_MARKED: "|".join(marked_urls(deepseek_urls)),
        COL_DEEPSEEK_STATUS: pick("deepseek", "status"),
        COL_ELAPSED: "{:.2f}".format(elapsed_s),
        COL_CREATED_AT: now_ts(),
    }


def process_one(question, providers, clients):
    t0 = time.time(); res = {}
    for p in providers:
        try:
            if p == "kimi":
                res[p] = clients.kimi(question)
            elif p == "doubao":
                res[p] = clients.doubao(question)
            elif p == "deepseek":
                res[p] = clients.deepseek(question)
        except Exception as e:
            res[p] = {"answer": "", "urls": [], "domains": [], "status": "error:" + str(e)}
    return make_row(question, res, time.time() - t0)


def format_duration(seconds):
    s = int(max(0, seconds))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return "{:02d}:{:02d}:{:02d}".format(h, m, sec)
    return "{:02d}:{:02d}".format(m, sec)


def render_progress(completed, total, start_ts):
    if total <= 0:
        return
    elapsed = max(0.001, time.time() - start_ts)
    speed = float(completed) / elapsed
    eta = max(0, total - completed) / speed if speed > 0 else 0
    pct = 100.0 * float(completed) / float(total)
    bar_len = 28
    filled = min(bar_len, int(bar_len * completed / total))
    bar = "#" * filled + "-" * (bar_len - filled)
    line = u"\r\u8fdb\u5ea6 [{}] {}/{} ({:.1f}%)  \u5df2\u7528:{}  \u9884\u8ba1\u5269\u4f59:{}  \u901f\u5ea6:{:.2f}\u6761/\u79d2".format(
        bar, completed, total, pct, format_duration(elapsed), format_duration(eta), speed
    )
    sys.stdout.write(line); sys.stdout.flush()
    if completed >= total:
        sys.stdout.write("\n"); sys.stdout.flush()


def split_pipe(v):
    if not v:
        return []
    return [x for x in str(v).split("|") if x]


def parse_marked_item(item):
    if "::" in item:
        p = item.split("::", 1)
        return p[0].strip(), p[1].strip()
    u = item.strip()
    return detect_channel(u), u


def default_summary_path(output_path):
    base, ext = os.path.splitext(output_path)
    if not ext:
        ext = ".csv"
    return base + u"_\u6e20\u9053\u7edf\u8ba1\u6c47\u603b" + ext


def generate_channel_summary(output_path, summary_output):
    if not os.path.exists(output_path):
        return None
    stats = {
        PLATFORM_KIMI: defaultdict(lambda: {"link_count": 0, "question_count": 0}),
        PLATFORM_DOUBAO: defaultdict(lambda: {"link_count": 0, "question_count": 0}),
        PLATFORM_DEEPSEEK: defaultdict(lambda: {"link_count": 0, "question_count": 0}),
    }
    col_map = {PLATFORM_KIMI: COL_KIMI_MARKED, PLATFORM_DOUBAO: COL_DOUBAO_MARKED, PLATFORM_DEEPSEEK: COL_DEEPSEEK_MARKED}
    with open(output_path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            for platform_name, marked_col in col_map.items():
                items = split_pipe(row.get(marked_col, ""))
                if not items:
                    continue
                row_channels = set()
                for item in items:
                    ch, _ = parse_marked_item(item)
                    ch = ch or u"\u5176\u4ed6"
                    stats[platform_name][ch]["link_count"] += 1
                    row_channels.add(ch)
                for ch in row_channels:
                    stats[platform_name][ch]["question_count"] += 1

    rows = []
    for platform_name in [PLATFORM_KIMI, PLATFORM_DOUBAO, PLATFORM_DEEPSEEK]:
        pairs = list(stats[platform_name].items())
        pairs.sort(key=lambda x: (-x[1]["link_count"], -x[1]["question_count"], x[0]))
        for idx, (ch, agg) in enumerate(pairs, 1):
            rows.append({
                SUMMARY_COL_PLATFORM: platform_name,
                SUMMARY_COL_RANK: str(idx),
                SUMMARY_COL_CHANNEL: ch,
                SUMMARY_COL_LINK_COUNT: str(agg["link_count"]),
                SUMMARY_COL_QUESTION_COUNT: str(agg["question_count"]),
            })

    with open(summary_output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[SUMMARY_COL_PLATFORM, SUMMARY_COL_RANK, SUMMARY_COL_CHANNEL, SUMMARY_COL_LINK_COUNT, SUMMARY_COL_QUESTION_COUNT])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return summary_output


def parse_args():
    ap = argparse.ArgumentParser(description="Batch collect source URLs from AI providers.")
    ap.add_argument("--input", required=True, help="questions file: .txt or .csv")
    ap.add_argument("--output", default="results.csv", help="output csv path")
    ap.add_argument("--question-column", default="question", help="csv question column name")
    ap.add_argument("--providers", default="kimi,doubao,deepseek", help="kimi,doubao,deepseek")
    ap.add_argument("--workers", type=int, default=3, help="question-level concurrency")
    ap.add_argument("--max-retries", type=int, default=3, help="retry times")
    ap.add_argument("--retry-base-sleep", type=float, default=1.0, help="retry base sleep")
    ap.add_argument("--timeout", type=int, default=120, help="request timeout seconds")
    ap.add_argument("--temperature", type=float, default=0.2, help="sampling temperature")
    ap.add_argument("--max-tokens", type=int, default=1536, help="max output tokens")
    ap.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT, help="system prompt")
    ap.add_argument("--resume", action="store_true", help="skip already successful rows")
    ap.add_argument("--summary-output", default="", help="channel summary csv path")
    ap.add_argument("--kimi-base-url", default="https://api.moonshot.cn/v1", help="Kimi base url")
    ap.add_argument("--kimi-model", default="kimi-k2.5", help="Kimi model name")
    ap.add_argument("--kimi-temperature", type=float, default=1.0, help="Kimi temperature")
    ap.add_argument("--kimi-tool-loops", type=int, default=6, help="Kimi max tool loops")
    ap.add_argument("--ark-base-url", default="https://ark.cn-beijing.volces.com/api/v3", help="ARK base url")
    ap.add_argument("--doubao-model", default="", help="ARK model/endpoint id")
    ap.add_argument("--doubao-max-keyword", type=int, default=2, help="web_search max_keyword")
    ap.add_argument("--doubao-limit", type=int, default=10, help="web_search limit")
    ap.add_argument("--doubao-max-tool-calls", type=int, default=3, help="responses max_tool_calls")
    ap.add_argument("--deepseek-base-url", default="https://api.deepseek.com/v1", help="DeepSeek base url")
    ap.add_argument("--deepseek-model", default="deepseek-chat", help="DeepSeek model")
    ap.add_argument("--deepseek-mode", default="skip", choices=["skip", "api"], help="skip or api")
    return ap.parse_args()


def main():
    args = parse_args()
    providers = [x.strip() for x in args.providers.split(",") if x.strip()]
    bad = [x for x in providers if x not in ["kimi", "doubao", "deepseek"]]
    if bad:
        raise ValueError("unsupported providers: {}".format(bad))
    if args.workers < 1:
        raise ValueError("--workers must be >= 1")

    questions = read_questions(args.input, args.question_column)
    if not questions:
        print("No questions found in {}".format(args.input)); return 0

    done = load_done_questions(args.output, providers) if args.resume else set()
    pending = [q for q in questions if q not in done]

    fieldnames = [
        COL_QUESTION, COL_KIMI_ANSWER, COL_KIMI_DOMAINS, COL_KIMI_CHANNELS, COL_KIMI_URLS, COL_KIMI_MARKED, COL_KIMI_STATUS,
        COL_DOUBAO_ANSWER, COL_DOUBAO_DOMAINS, COL_DOUBAO_CHANNELS, COL_DOUBAO_URLS, COL_DOUBAO_MARKED, COL_DOUBAO_RAW_URLS, COL_DOUBAO_WS_CALLS, COL_DOUBAO_STATUS,
        COL_DEEPSEEK_ANSWER, COL_DEEPSEEK_DOMAINS, COL_DEEPSEEK_CHANNELS, COL_DEEPSEEK_URLS, COL_DEEPSEEK_MARKED, COL_DEEPSEEK_STATUS,
        COL_ELAPSED, COL_CREATED_AT,
    ]
    ensure_output_header(args.output, fieldnames)

    if not pending:
        print("[{}] all done. total={}, done={}".format(now_ts(), len(questions), len(done)))
        summary_path = args.summary_output.strip() or default_summary_path(args.output)
        s = generate_channel_summary(args.output, summary_path)
        if s: print("[{}] summary={}".format(now_ts(), os.path.abspath(s)))
        return 0

    print("[{}] start. total={}, pending={}, workers={}, providers={}".format(now_ts(), len(questions), len(pending), args.workers, ",".join(providers)))
    clients = ProviderClients(args)
    lock = threading.Lock()
    start_ts = time.time(); completed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        fut_map = {pool.submit(process_one, q, providers, clients): q for q in pending}
        for fut in as_completed(fut_map):
            q = fut_map[fut]
            try:
                row = fut.result()
            except Exception as e:
                row = {k: "" for k in fieldnames}
                row[COL_QUESTION] = q
                row[COL_DEEPSEEK_STATUS] = "worker_error:" + str(e)
                row[COL_CREATED_AT] = now_ts()
                row[COL_ELAPSED] = "0"
            append_row(args.output, fieldnames, row, lock)
            completed += 1
            render_progress(completed, len(pending), start_ts)

    summary_path = args.summary_output.strip() or default_summary_path(args.output)
    s = generate_channel_summary(args.output, summary_path)
    print("[{}] finished. output={}".format(now_ts(), os.path.abspath(args.output)))
    if s:
        print("[{}] summary={}".format(now_ts(), os.path.abspath(s)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
