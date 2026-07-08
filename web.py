"""Game Update Bot - Web Dashboard"""

import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger(__name__)


def create_web_server(port: int) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(DASHBOARD_HTML.encode())
            elif self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass

    return HTTPServer(("0.0.0.0", port), Handler)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Game Update Bot</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:24px;max-width:900px;margin:0 auto}
h1{font-size:20px;margin-bottom:8px;color:#f0f6fc}
.sub{color:#8b949e;font-size:13px;margin-bottom:20px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin-bottom:12px}
.card h3{font-size:15px;color:#58a6ff;margin-bottom:8px}
.card p{font-size:13px;color:#8b949e;line-height:1.5}
code{background:#21262d;padding:2px 6px;border-radius:4px;font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px}
.stat{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:12px;text-align:center}
.stat .num{font-size:28px;font-weight:700;color:#58a6ff}
.stat .label{font-size:12px;color:#8b949e;margin-top:4px}
</style>
</head>
<body>
<h1>Game Update Bot</h1>
<p class="sub">Discord bot tracking game patches from Steam, Reddit, Google News & gaming RSS feeds.</p>
<div class="card">
<h3>Commands</h3>
<p>
<code>/ping</code> — Check bot status<br>
<code>/updates [game]</code> — Show all game update times<br>
<code>/latest &lt;game&gt;</code> — Full details for a game<br>
<code>/pinboard</code> — Create auto-updating pinned board<br>
<code>/stopboard</code> — Stop the board<br>
<code>/search &lt;name&gt;</code> — Search tracked games<br>
<code>/refresh</code> — Clear cache & re-fetch
</p>
</div>
<div class="card">
<h3>Sources</h3>
<p>Steam RSS Feed, Google News, Reddit, PCGamer/IGN/Eurogamer RSS, Steam Build Tracker</p>
</div>
</body>
</html>"""
