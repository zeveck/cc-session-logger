#!/usr/bin/env node
/**
 * Serve session logs over HTTP.
 *
 * Serves .claude/logs/ as browsable, shareable session threads.
 * Raw markdown for machines (another Claude via WebFetch), rendered HTML for humans.
 *
 * Usage:
 *   node serve.js                       # localhost:3000
 *   node serve.js --port 8080           # custom port
 *   node serve.js --host 0.0.0.0        # expose to network
 *   node serve.js --dir .claude/logs    # custom log directory
 */

const http = require("http");
const fs = require("fs");
const path = require("path");

const DEFAULT_PORT = 3000;
const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_DIR = path.join(".claude", "logs");

const HTML_TEMPLATE = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TITLE</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/github-markdown-css@5/github-markdown-dark.min.css">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"><\/script>
<style>
  body {
    background: #0d1117;
    color: #e6edf3;
    max-width: 960px;
    margin: 0 auto;
    padding: 2rem 1rem;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }
  .markdown-body {
    background: transparent;
  }
  .markdown-body pre {
    background: #161b22;
  }
  .markdown-body code {
    background: #161b22;
  }
  nav { margin-bottom: 1.5rem; }
  nav a { color: #58a6ff; text-decoration: none; }
  nav a:hover { text-decoration: underline; }
  #content { display: none; }
</style>
</head>
<body>
<nav><a href="/">&larr; All sessions</a></nav>
<div id="raw" class="markdown-body"></div>
<pre id="content">CONTENT</pre>
<script>
  const md = document.getElementById('content').textContent;
  document.getElementById('raw').innerHTML = marked.parse(md);
<\/script>
</body>
</html>`;

const INDEX_TEMPLATE = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Session Logs</title>
<style>
  body {
    background: #0d1117;
    color: #e6edf3;
    max-width: 960px;
    margin: 0 auto;
    padding: 2rem 1rem;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }
  h1 { border-bottom: 1px solid #30363d; padding-bottom: 0.5rem; }
  .session {
    padding: 0.75rem 0;
    border-bottom: 1px solid #21262d;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .session-name {
    font-family: monospace;
    font-size: 0.95rem;
  }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .links { font-size: 0.85rem; }
  .links a { margin-left: 1rem; }
  .subagent { opacity: 0.7; font-size: 0.85rem; margin-left: 0.5rem; }
  .empty { color: #8b949e; font-style: italic; }
</style>
</head>
<body>
<h1>Session Logs</h1>
ENTRIES
</body>
</html>`;

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function parseLogName(filename) {
  const name = filename.replace(".md", "");
  // HHMM is optional (older logs don't have it)
  const m = name.match(
    /^(\d{4}-\d{2}-\d{2})-(?:(\d{4})-)?(\w+?)(?:-subagent-(.+)-(\w+))?$/
  );
  if (!m) {
    return { raw: name, date: "", time: "", session: "", agentType: null, agentId: null };
  }
  const timePart = m[2];
  return {
    raw: name,
    date: m[1],
    time: timePart ? `${timePart.slice(0, 2)}:${timePart.slice(2)}` : "",
    session: m[3],
    agentType: m[4] || null,
    agentId: m[5] || null,
  };
}

function buildIndex(logDir) {
  let files;
  try {
    files = fs.readdirSync(logDir).filter(
      (f) => f.endsWith(".md") && !f.startsWith(".")
    );
  } catch {
    files = [];
  }

  files.sort().reverse();

  if (!files.length) {
    return INDEX_TEMPLATE.replace(
      "ENTRIES",
      '<p class="empty">No session logs found.</p>'
    );
  }

  const parts = files.map((f) => {
    const meta = parseLogName(f);
    let label;
    if (meta.date) {
      const dateTime = `${meta.date} ${meta.time}`.trim();
      label = `${dateTime} &mdash; ${meta.session}`;
    } else {
      label = meta.raw;
    }
    if (meta.agentType) {
      label += `<span class="subagent">${meta.agentType} ${meta.agentId || ""}</span>`;
    }
    const slug = f.replace(".md", "");
    return (
      `<div class="session">` +
      `  <span class="session-name">${label}</span>` +
      `  <span class="links">` +
      `    <a href="/${slug}">view</a>` +
      `    <a href="/${f}">raw</a>` +
      `  </span>` +
      `</div>`
    );
  });

  return INDEX_TEMPLATE.replace("ENTRIES", parts.join("\n"));
}

function parseArgs(argv) {
  const args = { port: DEFAULT_PORT, host: DEFAULT_HOST, dir: DEFAULT_DIR };
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === "--port" && argv[i + 1]) {
      args.port = parseInt(argv[++i], 10);
    } else if (argv[i] === "--host" && argv[i + 1]) {
      args.host = argv[++i];
    } else if (argv[i] === "--dir" && argv[i + 1]) {
      args.dir = argv[++i];
    }
  }
  return args;
}

function main() {
  const args = parseArgs(process.argv);

  if (!fs.existsSync(args.dir)) {
    console.log(`  Log directory not found: ${args.dir}`);
    console.log("  Run this from your project root, or specify --dir.");
    process.exit(1);
  }

  const server = http.createServer((req, res) => {
    const urlPath = decodeURIComponent(req.url || "/").replace(/^\/+/, "");

    function respond(code, body, contentType) {
      const buf = Buffer.from(body, "utf-8");
      res.writeHead(code, {
        "Content-Type": contentType,
        "Content-Length": buf.length,
        "Access-Control-Allow-Origin": "*",
      });
      res.end(buf);
    }

    // Index
    if (!urlPath) {
      respond(200, buildIndex(args.dir), "text/html");
      return;
    }

    // Raw markdown: /filename.md
    if (urlPath.endsWith(".md")) {
      const filePath = path.join(args.dir, path.basename(urlPath));
      try {
        const content = fs.readFileSync(filePath, "utf-8");
        respond(200, content, "text/plain; charset=utf-8");
      } catch {
        respond(404, "Not found", "text/plain");
      }
      return;
    }

    // Rendered HTML: /filename (no .md)
    const mdFile = path.join(args.dir, path.basename(urlPath) + ".md");
    try {
      const content = fs.readFileSync(mdFile, "utf-8");
      const title = escapeHtml(path.basename(urlPath));
      const body = HTML_TEMPLATE
        .replace("TITLE", title)
        .replace("CONTENT", escapeHtml(content));
      respond(200, body, "text/html");
    } catch {
      respond(404, "Not found", "text/plain");
    }
  });

  server.listen(args.port, args.host, () => {
    const url =
      args.host === "127.0.0.1"
        ? `http://localhost:${args.port}`
        : `http://${args.host}:${args.port}`;
    console.log();
    console.log(`  Serving session logs at ${url}`);
    console.log(`  Log directory: ${args.dir}`);
    console.log("  Press Ctrl+C to stop.");
    console.log();
  });
}

main();
