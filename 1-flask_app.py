"""Link shortener with click analytics (Flask + SQLite + Jinja2). Single file: just run it."""
import os, re, random, sqlite3, string
from datetime import datetime, timezone
from jinja2 import DictLoader
from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

TEMPLATES = {
    "base.html": """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Shortly{% endblock %}</title>
  <style>
    :root{--bg:#f6f7fb;--ink:#161a2e;--mute:#667;--card:#fff;--acc:#4f46e5;--line:#dfe2ee;--err:#c0392b;--ok:#1b7f5c}
    @media(prefers-color-scheme:dark){:root{--bg:#0f1120;--ink:#eef0fb;--mute:#9aa0c3;--card:#181b30;--line:#2a2e4d;--acc:#8b86ff}}
    body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,sans-serif}
    main{max-width:760px;margin:0 auto;padding:24px 16px 60px}
    a{color:var(--acc)} h1{margin:0 0 4px} .mute{color:var(--mute)}
    .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:16px}
    input{width:100%;padding:11px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit;margin:4px 0 10px}
    button{background:var(--acc);color:#fff;border:0;border-radius:8px;padding:10px 16px;font:inherit;cursor:pointer}
    button.ghost{background:none;color:var(--err);padding:4px 8px}
    .flash{padding:10px 14px;border-radius:8px;margin-top:12px;border:1px solid var(--line)}
    .flash.error{color:var(--err)} .flash.ok{color:var(--ok)}
    table{width:100%;border-collapse:collapse} td,th{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}
    td.url{word-break:break-all;max-width:260px;color:var(--mute);font-size:.9rem}
    .bar{background:var(--acc);height:14px;border-radius:4px}
  </style>
</head>
<body>
<main>
  <h1><a href="{{ url_for('index') }}" style="text-decoration:none;color:inherit">Shortly</a></h1>
  <p class="mute">Shorten links and see who clicks them.</p>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}<div class="flash {{ cat }}">{{ msg }}</div>{% endfor %}
  {% endwith %}
  {% block body %}{{ content }}{% endblock %}
</main>
</body>
</html>
""",
    "index.html": """{% extends "base.html" %}
{% block body %}
<form class="card" method="post">
  <label for="url">Long URL</label>
  <input id="url" name="url" type="url" placeholder="https://example.com/a/very/long/link" required>
  <label for="alias">Custom alias (optional)</label>
  <input id="alias" name="alias" placeholder="my-link">
  <button>Shorten</button>
</form>
<div class="card">
  <strong>Your links</strong>
  {% if links %}
  <table>
    <tr><th>Short</th><th>Destination</th><th>Clicks</th><th></th></tr>
    {% for l in links %}
    <tr>
      <td><a href="{{ url_for('follow', code=l.code) }}">/{{ l.code }}</a><br><a class="mute" href="{{ url_for('stats', code=l.code) }}">stats</a></td>
      <td class="url">{{ l.url }}</td>
      <td>{{ l.clicks }}</td>
      <td><form method="post" action="{{ url_for('delete', code=l.code) }}"><button class="ghost" aria-label="Delete {{ l.code }}">Delete</button></form></td>
    </tr>
    {% endfor %}
  </table>
  {% else %}<p class="mute">No links yet. Create your first one above.</p>{% endif %}
</div>
{% endblock %}
""",
    "stats.html": """{% extends "base.html" %}
{% block title %}Stats for /{{ link.code }}{% endblock %}
{% block body %}
<div class="card">
  <h2 style="margin-top:0">/{{ link.code }}</h2>
  <p class="mute" style="word-break:break-all">{{ link.url }}</p>
  <p><strong>{{ total }}</strong> total clicks &middot; created {{ link.created[:10] }}</p>
</div>
<div class="card">
  <strong>Clicks per day</strong>
  {% for d in daily %}
  <div style="display:grid;grid-template-columns:90px 1fr 30px;gap:8px;align-items:center;margin-top:8px">
    <span class="mute">{{ d.day }}</span>
    <div class="bar" style="width:{{ (d.n / biggest * 100)|round }}%"></div>
    <span>{{ d.n }}</span>
  </div>
  {% else %}<p class="mute">No clicks yet.</p>{% endfor %}
</div>
<p><a href="{{ url_for('index') }}">&larr; Back</a></p>
{% endblock %}
""",
}

app = Flask(__name__)
app.jinja_loader = DictLoader(TEMPLATES)   # templates live in this file
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-me")
app.config["DATABASE"] = os.environ.get("DATABASE", "links.db")

ALPHABET = string.ascii_letters + string.digits
URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.I)
ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]{3,20}$")
RESERVED = {"stats", "delete", "static"}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS links(
            id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL,
            url TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS clicks(
            id INTEGER PRIMARY KEY, link_id INTEGER NOT NULL REFERENCES links(id),
            at TEXT NOT NULL, agent TEXT);
        """
    )


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_code(db):
    while True:
        code = "".join(random.choices(ALPHABET, k=6))
        if not db.execute("SELECT 1 FROM links WHERE code=?", (code,)).fetchone():
            return code


@app.route("/", methods=["GET", "POST"])
def index():
    db = get_db()
    if request.method == "POST":
        url = request.form.get("url", "").strip()
        alias = request.form.get("alias", "").strip()
        if not URL_RE.match(url):
            flash("Enter a valid URL starting with http:// or https://", "error")
        elif alias and (not ALIAS_RE.match(alias) or alias.lower() in RESERVED):
            flash("Alias must be 3-20 letters, numbers, - or _", "error")
        elif alias and db.execute("SELECT 1 FROM links WHERE code=?", (alias,)).fetchone():
            flash("That alias is taken", "error")
        else:
            code = alias or new_code(db)
            db.execute("INSERT INTO links(code, url, created) VALUES (?,?,?)", (code, url, now()))
            db.commit()
            flash(f"Created {request.host_url}{code}", "ok")
            return redirect(url_for("index"))
    links = db.execute(
        """SELECT l.code, l.url, l.created, COUNT(c.id) AS clicks
           FROM links l LEFT JOIN clicks c ON c.link_id = l.id
           GROUP BY l.id ORDER BY l.id DESC"""
    ).fetchall()
    return render_template("index.html", links=links)


@app.route("/<code>")
def follow(code):
    db = get_db()
    link = db.execute("SELECT * FROM links WHERE code=?", (code,)).fetchone()
    if not link:
        abort(404)
    db.execute(
        "INSERT INTO clicks(link_id, at, agent) VALUES (?,?,?)",
        (link["id"], now(), request.headers.get("User-Agent", "")[:200]),
    )
    db.commit()
    return redirect(link["url"])


@app.route("/stats/<code>")
def stats(code):
    db = get_db()
    link = db.execute("SELECT * FROM links WHERE code=?", (code,)).fetchone()
    if not link:
        abort(404)
    total = db.execute("SELECT COUNT(*) FROM clicks WHERE link_id=?", (link["id"],)).fetchone()[0]
    daily = db.execute(
        """SELECT substr(at,1,10) AS day, COUNT(*) AS n FROM clicks
           WHERE link_id=? GROUP BY day ORDER BY day DESC LIMIT 14""",
        (link["id"],),
    ).fetchall()
    biggest = max([d["n"] for d in daily], default=1)
    return render_template("stats.html", link=link, total=total, daily=daily[::-1], biggest=biggest)


@app.route("/delete/<code>", methods=["POST"])
def delete(code):
    db = get_db()
    link = db.execute("SELECT id FROM links WHERE code=?", (code,)).fetchone()
    if link:
        db.execute("DELETE FROM clicks WHERE link_id=?", (link["id"],))
        db.execute("DELETE FROM links WHERE id=?", (link["id"],))
        db.commit()
        flash("Link deleted", "ok")
    return redirect(url_for("index"))


@app.errorhandler(404)
def not_found(_e):
    return render_template("base.html", content="Page not found."), 404


with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True)
