#!/usr/bin/env python3
"""从 1024Store 目录与 npm registry 生成 DSH 插件市场索引（format 1）。

两阶段：先收集候选（快），再并发查询 npm 元数据（每个 8s 超时）。
"""
import json, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from collections import Counter

API = "https://api.deepseek1024.com/v1/plugins/search"
NPM = "https://registry.npmjs.org/"
UA = {"User-Agent": "dsh-market-index/1.0"}

QUERIES = [
    "ssh", "运维", "monitor", "监控", "backup", "备份", "docker", "kubernetes",
    "mysql", "redis", "nginx", "ansible", "terminal", "sftp", "服务器",
    "log", "prometheus", "zabbix", "sre", "tunnel", "database", "shell",
]

CATEGORY_RULES = [
    ("ssh", ["ssh", "sftp", "tunnel", "remote", "terminal", "shell", "pty"]),
    ("monitor", ["monitor", "监控", "alert", "prometheus", "grafana", "zabbix", "metric", "日志", "log"]),
    ("backup", ["backup", "备份", "restore", "snapshot", "restic", "borg"]),
    ("container", ["docker", "kubernetes", "k8s", "pod", "container", "helm"]),
    ("database", ["mysql", "redis", "postgres", "mongo", "database", "sql", "数据库"]),
    ("network", ["network", "网络", "dns", "ping", "port", "firewall", "proxy", "抓包"]),
    ("deploy", ["deploy", "ansible", "ci", "cd", "release", "部署", "发布"]),
]

CATEGORY_TITLES = {
    "ssh": {"en": "SSH & Remote", "zh": "远程与 SSH"},
    "monitor": {"en": "Monitoring", "zh": "监控与告警"},
    "backup": {"en": "Backup", "zh": "备份与恢复"},
    "container": {"en": "Containers", "zh": "容器与编排"},
    "database": {"en": "Databases", "zh": "数据库"},
    "network": {"en": "Network", "zh": "网络"},
    "deploy": {"en": "Deploy", "zh": "部署与自动化"},
    "tools": {"en": "Ops Tools", "zh": "运维工具"},
}

LABELS = {
    "ops": {"title": {"en": "Operations", "zh": "运维"}},
    "verified": {"title": {"en": "Install verified", "zh": "安装已验证"}},
}


def get(url, timeout=8):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def search(query, limit=20):
    try:
        return get(f"{API}?q={urllib.parse.quote(query)}&limit={limit}").get("results", [])
    except Exception as e:
        print(f"  ! search {query}: {e}", file=sys.stderr)
        return []


def package_from_install(install):
    if not isinstance(install, str):
        return None
    parts = install.split()
    if "add" not in parts:
        return None
    i = parts.index("add")
    if i + 1 >= len(parts):
        return None
    spec = parts[i + 1]
    if spec.startswith(("github:", "git+", "http", "file:")):
        return None
    if spec.startswith("@"):
        bits = spec.split("@")
        return "@" + bits[1]
    return spec.split("@")[0]


def npm_meta(name):
    try:
        d = get(NPM + urllib.parse.quote(name, safe="@"))
    except Exception:
        return None
    version = (d.get("dist-tags") or {}).get("latest")
    if not version or version not in d.get("versions", {}):
        return None
    m = d["versions"][version]
    dsh = m.get("dsh")
    if not isinstance(dsh, dict) or "bundle" not in dsh:
        return None
    ts = (d.get("time") or {}).get(version)
    published = 0
    if ts:
        try:
            published = int(time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))) - time.timezone
        except Exception:
            published = 0
    return {
        "version": version,
        "publishTimestamp": max(published, 0),
        "description": m.get("description") or "",
        "homepage": m.get("homepage"),
        "repository": m.get("repository"),
        "keywords": [k for k in (m.get("keywords") or []) if isinstance(k, str)][:6],
    }


def repo_url(meta, entry):
    r = meta.get("repository")
    u = r.get("url") if isinstance(r, dict) else r
    if not u:
        u = entry.get("url") or ""
    u = u.replace("git+", "").replace("git@github.com:", "https://github.com/")
    u = re.sub(r"\.git$", "", u)
    if u.startswith("github:"):
        u = "https://github.com/" + u[len("github:"):]
    if not u.startswith("http"):
        return None
    return u.split("#")[0]


def categorize(text):
    low = text.lower()
    for cid, words in CATEGORY_RULES:
        if any(w in low for w in words):
            return cid
    return "tools"


def main():
    seen, cands = set(), {}
    for q in QUERIES:
        for item in search(q):
            pid = item.get("id")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            name = package_from_install(item.get("install"))
            if name:
                cands[name] = item
        print(f"  query {q}: seen={len(seen)} cands={len(cands)}", file=sys.stderr)

    names = list(cands)
    metas = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        for name, meta in zip(names, pool.map(npm_meta, names)):
            if meta:
                metas[name] = meta
    print(f"npm hit {len(metas)}/{len(names)}", file=sys.stderr)

    entries = []
    for name, meta in metas.items():
        item = cands[name]
        url = repo_url(meta, item)
        if not url:
            continue
        desc = item.get("description") or {}
        zh = (desc.get("zh") if isinstance(desc, dict) else "") or ""
        en = (desc.get("en") if isinstance(desc, dict) else "") or ""
        text = " ".join([name, en, zh, " ".join(meta["keywords"])])
        entries.append({
            "name": name,
            "title": {"en": name, "zh": (zh or en or name)[:60]},
            "description": {"en": (en or zh or name)[:400], "zh": (zh or en or name)[:400]},
            "author": (item.get("owner") or "").strip() or None,
            "homepage": url,
            "repository": {"url": url},
            "metadata": {
                "category": categorize(text),
                "keywords": meta["keywords"],
                "labels": ["ops", "verified"],
                "sortKeys": {"stars": float(item.get("stars") or 0)},
            },
            "versions": [{
                "version": meta["version"],
                "publishTimestamp": meta["publishTimestamp"] or int(time.time()),
                "source": {"type": "npm"},
            }],
        })

    entries.sort(key=lambda e: -e["metadata"]["sortKeys"]["stars"])
    index = {
        "format": 1,
        "title": {"en": "Ops Toolbox (community mirror)", "zh": "运维工具集（社区镜像）"},
        "description": {
            "en": "Operations-oriented DSH plugins mirrored from the 1024Store catalog, each checked against npm metadata.",
            "zh": "面向系统集成与运维的 DSH 插件，选自 1024Store 社区目录，并逐条对照 npm 元数据校验。",
        },
        "metadata": {
            "categories": {k: {"title": v} for k, v in CATEGORY_TITLES.items()},
            "labels": LABELS,
            "sortKeys": {"stars": {"title": {"en": "Stars", "zh": "Star 数"}, "order": "desc"}},
        },
        "plugins": entries,
    }
    out = sys.argv[1] if len(sys.argv) > 1 else "index.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"plugins={len(entries)}")
    print(Counter(e["metadata"]["category"] for e in entries))
    for e in entries[:40]:
        print(f"  {e['name']:40s} {e['versions'][0]['version']:14s} {e['metadata']['category']}")


if __name__ == "__main__":
    main()
