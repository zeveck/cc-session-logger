"""Tests for serve.py and serve.js log servers.

Verifies index, raw markdown, rendered HTML, and 404 handling.

Usage:
    python3 tests/test_serve.py           # test both
    python3 tests/test_serve.py --py-only
    python3 tests/test_serve.py --js-only
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_SERVE = os.path.join(PKG_DIR, "py", "serve.py")
JS_SERVE = os.path.join(PKG_DIR, "js", "serve.js")

_PY_ONLY = "--py-only" in sys.argv
_JS_ONLY = "--js-only" in sys.argv
if _PY_ONLY:
    sys.argv.remove("--py-only")
if _JS_ONLY:
    sys.argv.remove("--js-only")

# Use different ports per runtime to avoid conflicts
_PORT_MAP = {"py": 13001, "js": 13002}


def _runtimes():
    if not _JS_ONLY:
        yield "py"
    if not _PY_ONLY:
        yield "js"


def _fetch(url):
    """Fetch a URL and return (status_code, body)."""
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


class ServeTestBase:
    """Mixin with serve tests. Subclasses set self.runtime."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_dir = os.path.join(self.tmpdir, ".claude", "logs")
        os.makedirs(self.log_dir)

        # Create test log files
        with open(os.path.join(self.log_dir, "2026-02-16-1856-abc12345.md"), "w") as f:
            f.write("# Session `abc12345` — 2026-02-16 18:56\n\n---\n\n**User:**\n> Hello\n\nHi there!\n")

        with open(os.path.join(self.log_dir, "2026-02-16-1900-abc12345-subagent-Explore-dddd1111.md"), "w") as f:
            f.write("# Subagent: Explore `dddd1111` — 2026-02-16 19:00\n\n---\n\nResearch results.\n")

        self.port = _PORT_MAP[self.runtime]
        self.base_url = f"http://127.0.0.1:{self.port}"

        # Start server
        if self.runtime == "py":
            cmd = [sys.executable, PY_SERVE]
        else:
            cmd = ["node", JS_SERVE]

        self.server = subprocess.Popen(
            cmd + ["--port", str(self.port), "--dir", self.log_dir],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        # Wait for server to be ready
        for _ in range(20):
            time.sleep(0.2)
            try:
                _fetch(self.base_url)
                break
            except Exception:
                continue

    def tearDown(self):
        self.server.terminate()
        self.server.wait(timeout=5)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # --- Index ---

    def test_index_returns_html(self):
        status, body = _fetch(self.base_url + "/")
        self.assertEqual(status, 200)
        self.assertIn("Session Logs", body)
        self.assertIn("<html", body)

    def test_index_lists_sessions(self):
        status, body = _fetch(self.base_url + "/")
        self.assertIn("abc12345", body)
        self.assertIn("view", body)
        self.assertIn("raw", body)

    def test_index_shows_subagent(self):
        status, body = _fetch(self.base_url + "/")
        self.assertIn("Explore", body)
        self.assertIn("dddd1111", body)

    # --- Raw markdown ---

    def test_raw_markdown(self):
        status, body = _fetch(self.base_url + "/2026-02-16-1856-abc12345.md")
        self.assertEqual(status, 200)
        self.assertIn("# Session `abc12345`", body)
        self.assertIn("> Hello", body)

    def test_raw_markdown_404(self):
        status, _ = _fetch(self.base_url + "/nonexistent.md")
        self.assertEqual(status, 404)

    # --- Rendered HTML ---

    def test_rendered_html(self):
        status, body = _fetch(self.base_url + "/2026-02-16-1856-abc12345")
        self.assertEqual(status, 200)
        self.assertIn("<html", body)
        self.assertIn("marked.parse", body)
        # The markdown content should be HTML-escaped inside the <pre>
        self.assertIn("Session", body)

    def test_rendered_404(self):
        status, _ = _fetch(self.base_url + "/nonexistent")
        self.assertEqual(status, 404)

    # --- CORS ---

    def test_cors_header(self):
        resp = urllib.request.urlopen(self.base_url + "/", timeout=5)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")

    # --- Empty directory ---

    def test_empty_index(self):
        """Server handles empty log directory gracefully."""
        # Remove all files
        for f in os.listdir(self.log_dir):
            os.remove(os.path.join(self.log_dir, f))

        status, body = _fetch(self.base_url + "/")
        self.assertEqual(status, 200)
        self.assertIn("No session logs found", body)


# Dynamically create test classes for each runtime
for runtime in _runtimes():
    cls_name = f"TestServe_{runtime}"
    cls = type(cls_name, (ServeTestBase, unittest.TestCase), {
        "runtime": runtime,
    })
    globals()[cls_name] = cls
del runtime, cls_name, cls


if __name__ == "__main__":
    unittest.main()
