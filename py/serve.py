#!/usr/bin/env python3
"""Serve session logs over HTTP.

Serves .claude/logs/ as browsable, shareable session threads.
Raw markdown for machines (another Claude via WebFetch), rendered HTML for humans.

Usage:
    python3 serve.py                    # localhost:3000
    python3 serve.py --port 8080        # custom port
    python3 serve.py --host 0.0.0.0     # expose to network
    python3 serve.py --dir .claude/logs  # custom log directory
"""

import argparse
import html
import os
import re
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote

DEFAULT_PORT = 3000
DEFAULT_HOST = "127.0.0.1"
DEFAULT_DIR = os.path.join(".claude", "logs")

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/github-markdown-css@5/github-markdown-dark.min.css">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  body {{
    background: #0d1117;
    color: #e6edf3;
    max-width: 960px;
    margin: 0 auto;
    padding: 2rem 1rem;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }}
  .markdown-body {{
    background: transparent;
  }}
  .markdown-body pre {{
    background: #161b22;
  }}
  .markdown-body code {{
    background: #161b22;
  }}
  nav {{ margin-bottom: 1.5rem; }}
  nav a {{ color: #58a6ff; text-decoration: none; }}
  nav a:hover {{ text-decoration: underline; }}
  #content {{ display: none; }}
  #rendered {{ }}
</style>
</head>
<body>
<nav><a href="/">&larr; All sessions</a></nav>
<div id="raw" class="markdown-body"></div>
<pre id="content">{content}</pre>
<script>
  const md = document.getElementById('content').textContent;
  document.getElementById('raw').innerHTML = marked.parse(md);
</script>
</body>
</html>
"""

INDEX_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Session Logs</title>
<style>
  body {{
    background: #0d1117;
    color: #e6edf3;
    max-width: 960px;
    margin: 0 auto;
    padding: 2rem 1rem;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }}
  h1 {{ border-bottom: 1px solid #30363d; padding-bottom: 0.5rem; }}
  .session {{
    padding: 0.75rem 0;
    border-bottom: 1px solid #21262d;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .session-name {{
    font-family: monospace;
    font-size: 0.95rem;
  }}
  a {{ color: #58a6ff; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .links {{ font-size: 0.85rem; }}
  .links a {{ margin-left: 1rem; }}
  .subagent {{ opacity: 0.7; font-size: 0.85rem; margin-left: 0.5rem; }}
  .empty {{ color: #8b949e; font-style: italic; }}
</style>
</head>
<body>
<h1>Session Logs</h1>
{entries}
</body>
</html>
"""


def parse_log_name(filename):
    """Extract metadata from a log filename."""
    name = filename.replace(".md", "")
    # Format: {date}-{HHMM}-{session}[-subagent-{type}-{agent}]
    # HHMM is optional (older logs don't have it)
    m = re.match(
        r"(\d{4}-\d{2}-\d{2})-(?:(\d{4})-)?(\w+?)(?:-subagent-(.+)-(\w+))?$",
        name,
    )
    if not m:
        return {"raw": name, "date": "", "time": "", "session": "",
                "agent_type": None, "agent_id": None}
    time_part = m.group(2)
    return {
        "raw": name,
        "date": m.group(1),
        "time": f"{time_part[:2]}:{time_part[2:]}" if time_part else "",
        "session": m.group(3),
        "agent_type": m.group(4),
        "agent_id": m.group(5),
    }


def build_index(log_dir):
    """Build the index HTML page."""
    try:
        files = [f for f in os.listdir(log_dir)
                 if f.endswith(".md") and not f.startswith(".")]
    except FileNotFoundError:
        files = []

    files.sort(reverse=True)

    if not files:
        entries = '<p class="empty">No session logs found.</p>'
    else:
        parts = []
        for f in files:
            meta = parse_log_name(f)
            name_display = f.replace(".md", "")

            if meta["date"]:
                date_time = f'{meta["date"]} {meta["time"]}'.strip()
                label = f'{date_time} &mdash; {meta["session"]}'
            else:
                label = meta["raw"]
            if meta["agent_type"]:
                label += (f'<span class="subagent">'
                          f'{meta["agent_type"]} {meta["agent_id"] or ""}'
                          f'</span>')

            slug = f.replace(".md", "")
            parts.append(
                f'<div class="session">'
                f'  <span class="session-name">{label}</span>'
                f'  <span class="links">'
                f'    <a href="/{slug}">view</a>'
                f'    <a href="/{f}">raw</a>'
                f'  </span>'
                f'</div>'
            )
        entries = "\n".join(parts)

    return INDEX_TEMPLATE.format(entries=entries)


class LogHandler(BaseHTTPRequestHandler):
    """HTTP request handler for session logs."""

    log_dir = DEFAULT_DIR

    def do_GET(self):
        path = unquote(self.path).lstrip("/")

        # Index
        if not path:
            body = build_index(self.log_dir)
            self._respond(200, body, "text/html")
            return

        # Raw markdown: /filename.md
        if path.endswith(".md"):
            file_path = os.path.join(self.log_dir, os.path.basename(path))
            if os.path.isfile(file_path):
                with open(file_path, "r") as f:
                    content = f.read()
                self._respond(200, content, "text/plain; charset=utf-8")
            else:
                self._respond(404, "Not found", "text/plain")
            return

        # Rendered HTML: /filename (no .md)
        md_file = os.path.join(self.log_dir, os.path.basename(path) + ".md")
        if os.path.isfile(md_file):
            with open(md_file, "r") as f:
                content = f.read()
            title = os.path.basename(path)
            body = HTML_TEMPLATE.format(
                title=html.escape(title),
                content=html.escape(content),
            )
            self._respond(200, body, "text/html")
            return

        self._respond(404, "Not found", "text/plain")

    def _respond(self, code, body, content_type):
        encoded = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt, *args):
        # Quieter logging
        sys.stderr.write(f"  {args[0]} {args[1]}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Serve session logs over HTTP.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--dir", default=DEFAULT_DIR,
                        help="Log directory (default: .claude/logs)")
    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        print(f"  Log directory not found: {args.dir}")
        print("  Run this from your project root, or specify --dir.")
        sys.exit(1)

    LogHandler.log_dir = args.dir

    server = HTTPServer((args.host, args.port), LogHandler)
    url = f"http://{args.host}:{args.port}"
    if args.host == "127.0.0.1":
        url = f"http://localhost:{args.port}"

    print()
    print(f"  Serving session logs at {url}")
    print(f"  Log directory: {args.dir}")
    print(f"  Press Ctrl+C to stop.")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
