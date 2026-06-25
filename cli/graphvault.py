#!/usr/bin/env python3
"""
GraphVault CLI — NexusLayer Graph Store
Version: 1.0.0

Store, query, and share code knowledge graphs.
Dashboard: https://graph.nexuslayer.eu
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# HTTP backend — prefer requests, fall back to urllib
# ---------------------------------------------------------------------------
try:
    import requests as _requests

    def _http_get(url, headers):
        resp = _requests.get(url, headers=headers, timeout=30)
        return resp.status_code, resp.text

    def _http_post(url, headers, body):
        resp = _requests.post(url, headers=headers, json=body, timeout=30)
        return resp.status_code, resp.text

    def _http_delete(url, headers):
        resp = _requests.delete(url, headers=headers, timeout=30)
        return resp.status_code, resp.text

except ImportError:
    import urllib.request
    import urllib.error

    def _http_get(url, headers):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    def _http_post(url, headers, body):
        data = json.dumps(body).encode()
        h = {**headers, "Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    def _http_delete(url, headers):
        req = urllib.request.Request(url, headers=headers, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()


# ---------------------------------------------------------------------------
# ANSI colours
# ---------------------------------------------------------------------------
GREEN  = "\033[92m"
RED    = "\033[91m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):    print(f"{GREEN}✓ {msg}{RESET}")
def err(msg):   print(f"{RED}✗ {msg}{RESET}", file=sys.stderr)
def header(msg):print(f"{CYAN}{BOLD}{msg}{RESET}")
def warn(msg):  print(f"{YELLOW}! {msg}{RESET}")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CONFIG_DIR  = Path.home() / ".graphvault"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_CONFIG = {"server": "https://graph.nexuslayer.eu", "token": ""}
VERSION = "1.0.0"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
        return dict(DEFAULT_CONFIG)
    try:
        return json.loads(CONFIG_FILE.read_text())
    except json.JSONDecodeError:
        warn("Config file is malformed — using defaults.")
        return dict(DEFAULT_CONFIG)


def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def auth_headers(cfg: dict) -> dict:
    return {"Authorization": f"Bearer {cfg['token']}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_json_response(text: str, context: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        err(f"Unexpected response from server ({context}): {text[:200]}")
        sys.exit(1)


def _require_token(cfg: dict):
    if not cfg.get("token"):
        err("No token set. Run: graphvault config set --token YOUR_JWT")
        sys.exit(1)


def _find_project(cfg: dict, project_name: str) -> dict:
    """Return the graph dict for project_name or exit."""
    status, body = _http_get(f"{cfg['server']}/v1/graphs", auth_headers(cfg))
    if status != 200:
        err(f"Failed to fetch graph list (HTTP {status}): {body[:200]}")
        sys.exit(1)
    data = _parse_json_response(body, "list graphs")
    graphs = data if isinstance(data, list) else data.get("graphs", data.get("data", []))
    for g in graphs:
        if g.get("project_name") == project_name or g.get("name") == project_name:
            return g
    err(f"Project '{project_name}' not found.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def cmd_config_set(args, cfg):
    if args.server:
        cfg["server"] = args.server.rstrip("/")
    if args.token:
        cfg["token"] = args.token
    save_config(cfg)
    ok(f"Config saved  server={cfg['server']}")


def cmd_push(args, cfg):
    _require_token(cfg)

    graph_path = Path(args.graph_json or "graphify-out/graph.json")
    if not graph_path.exists():
        err(f"Graph file not found: {graph_path}")
        sys.exit(1)

    try:
        graph_data = json.loads(graph_path.read_text())
    except json.JSONDecodeError as exc:
        err(f"Invalid JSON in {graph_path}: {exc}")
        sys.exit(1)

    # Normalise graphify's NetworkX format (uses "links") to our schema (uses "edges")
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges") or graph_data.get("links", [])
    normalised = {**graph_data, "nodes": nodes, "edges": edges}

    payload = {
        "project_name": args.project,
        "graph_data": normalised,
        "description": args.description or "",
    }

    if args.html:
        html_path = Path(args.html)
        if html_path.exists():
            payload["html_content"] = html_path.read_text()
        else:
            warn(f"HTML file not found, skipping: {args.html}")

    if args.report:
        report_path = Path(args.report)
        if report_path.exists():
            payload["report_content"] = report_path.read_text()
        else:
            warn(f"Report file not found, skipping: {args.report}")

    status, body = _http_post(f"{cfg['server']}/v1/graphs", auth_headers(cfg), payload)
    if status not in (200, 201):
        err(f"Push failed (HTTP {status}): {body[:300]}")
        sys.exit(1)

    ok(f"Pushed '{args.project}' — {len(nodes)} nodes, {len(edges)} edges")


def cmd_ls(args, cfg):
    _require_token(cfg)

    status, body = _http_get(f"{cfg['server']}/v1/graphs", auth_headers(cfg))
    if status != 200:
        err(f"Failed to fetch graphs (HTTP {status}): {body[:200]}")
        sys.exit(1)

    data = _parse_json_response(body, "ls")
    graphs = data if isinstance(data, list) else data.get("graphs", data.get("data", []))

    if not graphs:
        print("No graphs yet. Use 'graphvault push' to add one.")
        return

    col_w = [20, 8, 8, 13, 24]
    cols   = ["PROJECT", "NODES", "EDGES", "COMMUNITIES", "UPDATED"]
    sep    = "  "

    header(sep.join(c.ljust(w) for c, w in zip(cols, col_w)))
    print(CYAN + sep.join("-" * w for w in col_w) + RESET)

    for g in graphs:
        name   = str(g.get("project_name") or g.get("name", "—"))[:col_w[0]]
        nodes  = str(g.get("node_count",  g.get("nodes",  "—")))
        edges  = str(g.get("edge_count",  g.get("edges",  "—")))
        comms  = str(g.get("community_count", g.get("communities", "—")))
        upd    = str(g.get("updated_at",  g.get("updatedAt", "—")))[:col_w[4]]
        row    = [name, nodes, edges, comms, upd]
        print(sep.join(v.ljust(w) for v, w in zip(row, col_w)))


def cmd_pull(args, cfg):
    _require_token(cfg)

    graph = _find_project(cfg, args.project_name)
    graph_id = graph.get("id") or graph.get("_id")

    status, body = _http_get(
        f"{cfg['server']}/v1/graphs/{graph_id}/download",
        auth_headers(cfg),
    )
    if status != 200:
        err(f"Pull failed (HTTP {status}): {body[:200]}")
        sys.exit(1)

    out_path = Path(args.out or f"{args.project_name}-graph.json")
    out_path.write_text(body)
    ok(f"Saved to {out_path}")


def cmd_query(args, cfg):
    _require_token(cfg)

    graph = _find_project(cfg, args.project_name)
    graph_id = graph.get("id") or graph.get("_id")

    payload = {"question": args.question}
    status, body = _http_post(
        f"{cfg['server']}/v1/graphs/{graph_id}/query",
        auth_headers(cfg),
        payload,
    )
    if status != 200:
        err(f"Query failed (HTTP {status}): {body[:300]}")
        sys.exit(1)

    data = _parse_json_response(body, "query")

    # Print answer / summary if present
    answer = data.get("answer") or data.get("summary") or data.get("result")
    if answer:
        print(f"\n{BOLD}Answer:{RESET}")
        print(answer)

    # Print matched nodes
    nodes = data.get("nodes", [])
    if nodes:
        print(f"\n{CYAN}{BOLD}Matched nodes ({len(nodes)}):{RESET}")
        for n in nodes:
            nid   = n.get("id", "?")
            label = n.get("label") or n.get("name") or nid
            ntype = n.get("type") or n.get("group") or ""
            print(f"  • {label}" + (f"  [{ntype}]" if ntype else ""))

    # Print matched edges
    edges = data.get("edges", [])
    if edges:
        print(f"\n{CYAN}{BOLD}Matched edges ({len(edges)}):{RESET}")
        for e in edges:
            src = e.get("source") or e.get("from") or "?"
            tgt = e.get("target") or e.get("to") or "?"
            rel = e.get("label") or e.get("type") or e.get("relation") or "→"
            print(f"  {src}  {rel}  {tgt}")

    if not answer and not nodes and not edges:
        print(json.dumps(data, indent=2))


def cmd_rm(args, cfg):
    _require_token(cfg)

    project = args.project_name
    confirm = input(f"Delete '{project}'? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    graph = _find_project(cfg, project)
    graph_id = graph.get("id") or graph.get("_id")

    status, body = _http_delete(
        f"{cfg['server']}/v1/graphs/{graph_id}",
        auth_headers(cfg),
    )
    if status not in (200, 204):
        err(f"Delete failed (HTTP {status}): {body[:200]}")
        sys.exit(1)

    ok(f"Deleted '{project}'")


# ---------------------------------------------------------------------------
# Skill content
# ---------------------------------------------------------------------------
SKILL_CONTENT = """\
---
name: graphvault
description: >
  GraphVault is a NexusLayer product for storing, querying, and sharing code knowledge graphs.
  Use this skill when the user mentions graphvault, wants to push/store a graph, query a stored graph,
  or wants to view their project knowledge graphs on graph.nexuslayer.eu.
---

# GraphVault — NexusLayer Graph Store

Store your knowledge graphs (from graphify or any source) in the cloud and query them from anywhere.

**Dashboard:** https://graph.nexuslayer.eu

## Setup
```bash
graphvault config set --server https://graph.nexuslayer.eu --token YOUR_JWT
```

## Push a graph
```bash
graphvault push graphify-out/graph.json --project myrepo --html graphify-out/graph.html --report graphify-out/GRAPH_REPORT.md
```

## List graphs
```bash
graphvault ls
```

## Query a graph
```bash
graphvault query myrepo "what connects auth to the database?"
```

## MCP endpoint (point any IDE at your vault)
Add to your MCP config:
```json
{
  "mcpServers": {
    "graphvault": {
      "url": "https://graph.nexuslayer.eu/api/v1/mcp",
      "headers": { "Authorization": "Bearer YOUR_JWT" }
    }
  }
}
```
"""


def cmd_install(args, cfg):
    skill_dir  = Path.home() / ".claude" / "skills" / "graphvault"
    skill_file = skill_dir / "SKILL.md"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(SKILL_CONTENT)
    ok(f"Claude Code skill installed at {skill_file}")


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="graphvault",
        description="GraphVault CLI — NexusLayer Graph Store",
    )
    parser.add_argument(
        "--version", action="version", version=f"graphvault {VERSION}"
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # config set
    p_cfg = sub.add_parser("config", help="Manage configuration")
    cfg_sub = p_cfg.add_subparsers(dest="config_action", metavar="ACTION")
    p_cfg_set = cfg_sub.add_parser("set", help="Set server/token")
    p_cfg_set.add_argument("--server", metavar="URL",  help="GraphVault server URL")
    p_cfg_set.add_argument("--token",  metavar="JWT",  help="Bearer JWT token")

    # push
    p_push = sub.add_parser("push", help="Push a graph to GraphVault")
    p_push.add_argument(
        "graph_json", nargs="?", metavar="GRAPH_JSON_PATH",
        help="Path to graph.json (default: graphify-out/graph.json)",
    )
    p_push.add_argument("--project",     required=True, metavar="NAME",  help="Project name")
    p_push.add_argument("--html",        metavar="HTML_PATH",            help="Path to graph HTML file")
    p_push.add_argument("--report",      metavar="REPORT_PATH",          help="Path to report/markdown file")
    p_push.add_argument("--description", metavar="TEXT",                 help="Short description")

    # ls
    sub.add_parser("ls", help="List stored graphs")

    # pull
    p_pull = sub.add_parser("pull", help="Download a graph from GraphVault")
    p_pull.add_argument("project_name", metavar="PROJECT_NAME")
    p_pull.add_argument("--out", metavar="PATH", help="Output file path")

    # query
    p_query = sub.add_parser("query", help="Query a stored graph")
    p_query.add_argument("project_name", metavar="PROJECT_NAME")
    p_query.add_argument("question",     metavar="QUESTION")

    # rm
    p_rm = sub.add_parser("rm", help="Delete a graph from GraphVault")
    p_rm.add_argument("project_name", metavar="PROJECT_NAME")

    # install
    sub.add_parser("install", help="Install Claude Code skill for GraphVault")

    return parser


def main():
    parser = build_parser()
    args   = parser.parse_args()
    cfg    = load_config()

    if args.command == "config":
        if args.config_action == "set":
            cmd_config_set(args, cfg)
        else:
            parser.parse_args(["config", "--help"])

    elif args.command == "push":
        cmd_push(args, cfg)

    elif args.command == "ls":
        cmd_ls(args, cfg)

    elif args.command == "pull":
        cmd_pull(args, cfg)

    elif args.command == "query":
        cmd_query(args, cfg)

    elif args.command == "rm":
        cmd_rm(args, cfg)

    elif args.command == "install":
        cmd_install(args, cfg)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
