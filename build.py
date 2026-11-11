#!/usr/bin/env python3
"""Build the Asset Arena Wire static site.

Reads config.json and every releases/*.json file, validates them, and writes
the full site into _site/ (homepage, release pages, category pages, submit
page, RSS feed, sitemap). Standard library only.

Usage:
  python3 build.py            build published releases into _site/
  python3 build.py --drafts   also build releases with status "draft" (local preview)
  python3 build.py --check    validate releases only, write nothing
"""
import hashlib
import html
import json
import re
import shutil
import sys
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_site"
RELEASES_DIR = ROOT / "releases"
IMAGES_DIR = RELEASES_DIR / "images"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
ASSETS_DIR = ROOT / "assets"

REQUIRED = ["slug", "status", "date", "category", "organization", "headline", "body", "contact"]
STATUSES = {"published", "draft"}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
BANNED_DASHES = ("\u2013", "\u2014")  # en dash, em dash: house style forbids both


# ---------------------------------------------------------------- helpers

def esc(s):
    return html.escape(str(s or ""), quote=True)


def slugify(s):
    s = s.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def inline(text):
    """Escape text, then allow **bold** and [label](https://url) only."""
    t = esc(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        t,
    )
    return t


def nice_date(d):
    return d.strftime("%B %-d, %Y")


def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)


# ---------------------------------------------------------------- loading

def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def load_releases(cfg, include_drafts):
    errors, releases, seen = [], [], {}
    categories = set(cfg["categories"])
    for path in sorted(RELEASES_DIR.glob("*.json")):
        name = path.name
        try:
            r = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{name}: invalid JSON ({e})")
            continue
        missing = [k for k in REQUIRED if not r.get(k)]
        if missing:
            errors.append(f"{name}: missing {', '.join(missing)}")
            continue
        if not SLUG_RE.match(r["slug"]):
            errors.append(f"{name}: slug must be lowercase words joined by hyphens")
        if r["slug"] in seen:
            errors.append(f"{name}: slug '{r['slug']}' already used by {seen[r['slug']]}")
        seen[r["slug"]] = name
        if r["status"] not in STATUSES:
            errors.append(f"{name}: status must be one of {sorted(STATUSES)}")
        if r["category"] not in categories:
            errors.append(f"{name}: category '{r['category']}' is not in config.json")
        try:
            r["_date"] = date.fromisoformat(r["date"])
        except ValueError:
            errors.append(f"{name}: date must be YYYY-MM-DD")
            continue
        if not isinstance(r["body"], list) or not all(isinstance(p, str) for p in r["body"]):
            errors.append(f"{name}: body must be a list of paragraph strings")
        img = r.get("image")
        if img:
            src = img.get("src", "") if isinstance(img, dict) else ""
            if not src.startswith("images/") or Path(src).suffix.lower() not in IMAGE_EXTS:
                errors.append(f"{name}: image.src must be images/<file>.jpg|png|webp")
            elif not (RELEASES_DIR / src).is_file():
                errors.append(f"{name}: image file releases/{src} not found")
            elif not img.get("alt"):
                errors.append(f"{name}: image.alt is required (describe the image)")
        if not r["organization"].get("name"):
            errors.append(f"{name}: organization.name is required")
        for s in walk_strings(r):
            if any(ch in s for ch in BANNED_DASHES):
                errors.append(f"{name}: contains an em or en dash; use a comma, colon or hyphen")
                break
        if r["status"] == "published" or include_drafts:
            releases.append(r)
    releases.sort(key=lambda r: (r["_date"], r["headline"]), reverse=True)
    return releases, errors


# ---------------------------------------------------------------- layout

def asset_version(name):
    """Short content hash so browsers refetch an asset whenever it changes."""
    return hashlib.sha1((ASSETS_DIR / name).read_bytes()).hexdigest()[:8]


FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,500;6..72,600;6..72,700'
    '&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">'
)


def page(cfg, *, title, description, rel, body, path, og_type="website", extra_head="", og_image=None):
    canonical = cfg["base_url"].rstrip("/") + "/" + path
    og_image = og_image or cfg["base_url"].rstrip("/") + "/assets/asset-arena-wire-icon.png"
    card = "summary_large_image" if "/images/" in og_image else "summary"
    full_title = f"{title} | {cfg['site_name']}" if title != cfg["site_name"] else f"{cfg['site_name']} | {cfg['tagline']}"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:site_name" content="{esc(cfg['site_name'])}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="{esc(og_image)}">
<meta name="twitter:card" content="{card}">
<link rel="icon" type="image/png" href="{rel}assets/asset-arena-wire-icon.png?v={asset_version('asset-arena-wire-icon.png')}">
<link rel="apple-touch-icon" href="{rel}assets/asset-arena-wire-icon.png?v={asset_version('asset-arena-wire-icon.png')}">
<link rel="alternate" type="application/rss+xml" title="{esc(cfg['site_name'])}" href="{rel}feed.xml">
{FONTS}
<link rel="stylesheet" href="{rel}assets/style.css?v={asset_version('style.css')}">
{extra_head}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="masthead">
  <div class="wrap bar">
    <a class="brand" href="{rel}index.html"><span>Asset Arena <b>Wire</b></span></a>
    <nav aria-label="Main">
      <a href="{rel}index.html#latest">Latest</a>
      <a href="{rel}index.html#categories">Categories</a>
      <a href="{rel}index.html#pricing">Pricing</a>
      <a class="btn btn-accent" href="{rel}submit/index.html">Submit a release</a>
    </nav>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="foot">
  <div class="wrap foot-grid">
    <div>
      <p class="brand-foot">Asset Arena <b>Wire</b></p>
      <p class="muted">{esc(cfg['tagline'])}</p>
    </div>
    <div class="foot-links">
      <a href="{rel}feed.xml">RSS feed</a>
      <a href="{rel}submit/index.html">Submit a release</a>
      <a href="{esc(cfg['newsletter_url'])}" target="_blank" rel="noopener">Asset Arena newsletter</a>
    </div>
  </div>
  <div class="wrap fine">Releases are supplied by the organizations named in them and reviewed before publishing. &copy; {date.today().year} Asset Arena.</div>
</footer>
</body>
</html>
"""


def release_item(r, rel):
    badge = '<span class="fm">Founding Member</span>' if r.get("founding_member") else ""
    draft = '<span class="draft">Draft</span>' if r["status"] == "draft" else ""
    sub = f'<p class="item-sub">{inline(r["subheadline"])}</p>' if r.get("subheadline") else ""
    img = r.get("image")
    thumb = (f'<a class="thumb" href="{rel}news/{r["slug"]}/index.html" tabindex="-1" aria-hidden="true">'
             f'<img src="{rel}{esc(img["src"])}" alt="" loading="lazy"></a>') if img else ""
    return f"""<article class="item{' has-thumb' if img else ''}">
  {thumb}<div class="item-text">
  <div class="item-meta"><time datetime="{r['date']}">{nice_date(r['_date'])}</time><a class="chip" href="{rel}category/{slugify(r['category'])}/index.html">{esc(r['category'])}</a>{badge}{draft}</div>
  <h3><a href="{rel}news/{r['slug']}/index.html">{inline(r['headline'])}</a></h3>
  {sub}
  <p class="item-org">{esc(r['organization']['name'])}</p>
  </div>
</article>"""


def release_list(releases, rel, empty="No releases yet. Be the first to publish."):
    if not releases:
        return f'<p class="empty">{esc(empty)}</p>'
    return '<div class="list">' + "\n".join(release_item(r, rel) for r in releases) + "</div>"


def plans_html(cfg, rel):
    cards = []
    for p in cfg["plans"]:
        feats = "".join(f"<li>{esc(f)}</li>" for f in p["features"])
        badge = f'<p class="plan-badge">{esc(p["badge"])}</p>' if p.get("badge") else ""
        cls = "plan plan-featured" if p["id"] == "founding" else "plan"
        cards.append(f"""<div class="{cls}">
  {badge}<h3>{esc(p['name'])}</h3>
  <p class="plan-price"><span>{esc(p['price'])}</span> {esc(p['per'])}</p>
  <ul>{feats}</ul>
  <a class="btn {'btn-accent' if p['id'] == 'founding' else 'btn-ghost'}" href="{rel}submit/index.html?plan={p['id']}">{'Apply as a Founding Member' if p['id'] == 'founding' else 'Submit a release'}</a>
</div>""")
    return '<div class="plans">' + "\n".join(cards) + "</div>"


# ---------------------------------------------------------------- pages

def build_home(cfg, releases):
    rel = ""
    counts = {c: 0 for c in cfg["categories"]}
    for r in releases:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    cats = "".join(
        f'<a class="cat" href="category/{slugify(c)}/index.html"><span>{esc(c)}</span><small>{n} release{"s" if n != 1 else ""}</small></a>'
        for c, n in counts.items()
    )
    body = f"""
<section class="hero">
  <div class="wrap">
    <p class="eyebrow"><span class="pulse" aria-hidden="true"></span>Sports business newswire</p>
    <h1>The press release wire built for sports business.</h1>
    <p class="lede">Announce funding rounds, partnerships, launches and deals to the investors, operators, media and partners who follow the industry. Every release is reviewed. You pay only after approval.</p>
    <div class="ctas">
      <a class="btn btn-accent" href="submit/index.html">Submit a release</a>
      <a class="btn btn-ghost-dark" href="#pricing">See pricing</a>
    </div>
  </div>
</section>

<section class="section" id="latest">
  <div class="wrap">
    <div class="section-head"><h2>Latest releases</h2><a href="feed.xml" class="rss">RSS</a></div>
    {release_list(releases[:20], rel)}
  </div>
</section>

<section class="section alt" id="categories">
  <div class="wrap">
    <div class="section-head"><h2>Browse by category</h2></div>
    <div class="cats">{cats}</div>
  </div>
</section>

<section class="section" id="how">
  <div class="wrap">
    <div class="section-head"><h2>How it works</h2></div>
    <ol class="steps">
      <li><span class="n">01</span><h3>Submit</h3><p>Send your release through the form. No payment, no account.</p></li>
      <li><span class="n">02</span><h3>Review</h3><p>We check every release for accuracy, clarity and fit with the sports business audience.</p></li>
      <li><span class="n">03</span><h3>Approve and pay</h3><p>Once approved, you get an invoice. Your release is scheduled when it is paid.</p></li>
      <li><span class="n">04</span><h3>Publish</h3><p>Your release goes live with a permanent page, category placement and RSS distribution.</p></li>
    </ol>
  </div>
</section>

<section class="section alt" id="pricing">
  <div class="wrap">
    <div class="section-head"><h2>Pricing</h2></div>
    <p class="section-intro">Simple pricing. Nothing is charged until your release or membership is approved.</p>
    {plans_html(cfg, rel)}
  </div>
</section>

<section class="section" id="about">
  <div class="wrap about">
    <img class="headshot" src="assets/david-lasday-headshot.jpg" alt="David Lasday" width="160" height="160">
    <div>
      <p class="eyebrow dark">From the publisher of Asset Arena</p>
      <h2>David Lasday</h2>
      <p>David Lasday is a sports business connector, strategic advisor and the publisher of Asset Arena, the newsletter where sports, capital and infrastructure intersect. He works across sports tech, investment capital, facilities, teams and emerging leagues, sourcing deals and making double opt-in introductions across a global network of investors, operators and athletes.</p>
      <p>Asset Arena Wire grows out of that work: getting sports business news in front of the people who act on it.</p>
      <a class="btn btn-ghost" href="{esc(cfg['linkedin_url'])}" target="_blank" rel="noopener">Follow on LinkedIn</a>
    </div>
  </div>
</section>
"""
    return page(cfg, title=cfg["site_name"], description=cfg["description"], rel=rel, body=body, path="")


def build_release(cfg, r):
    rel = "../../"
    abouts = "".join(
        f'<h3>About {esc(a.get("name", ""))}</h3><p>{inline(a.get("text", ""))}</p>'
        for a in r.get("about", [])
    )
    c = r["contact"]
    contact_lines = [esc(c.get("name")), esc(c.get("organization"))]
    if c.get("email"):
        contact_lines.append(f'<a href="mailto:{esc(c["email"])}">{esc(c["email"])}</a>')
    if c.get("phone"):
        contact_lines.append(esc(c["phone"]))
    contact = "<br>".join(x for x in contact_lines if x)
    paras = list(r["body"])
    first = paras[0] if paras else ""
    dateline = f'<span class="dateline">{esc(r.get("dateline", "").upper())}, {nice_date(r["_date"])} /Asset Arena Wire/</span> ' if r.get("dateline") else ""
    body_html = f"<p>{dateline}{inline(first)}</p>" + "".join(f"<p>{inline(p)}</p>" for p in paras[1:])
    org = r["organization"]
    org_html = f'<a href="{esc(org["url"])}" target="_blank" rel="noopener">{esc(org["name"])}</a>' if org.get("url") else esc(org["name"])
    tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in r.get("tags", []))
    badge = '<span class="fm">Founding Member</span>' if r.get("founding_member") else ""
    draft = '<p class="draft-banner">Draft preview. Not published.</p>' if r["status"] == "draft" else ""
    sub = f'<p class="subhead">{inline(r["subheadline"])}</p>' if r.get("subheadline") else ""
    img = r.get("image")
    figure = ""
    og_image = None
    if img:
        cap = f'<figcaption>{inline(img["caption"])}</figcaption>' if img.get("caption") else ""
        figure = f'<figure class="release-figure"><img src="{rel}{esc(img["src"])}" alt="{esc(img["alt"])}">{cap}</figure>'
        og_image = cfg["base_url"].rstrip("/") + "/" + img["src"]
    ld = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": r["headline"],
        "datePublished": r["date"],
        "publisher": {"@type": "Organization", "name": cfg["site_name"]},
        "author": {"@type": "Organization", "name": org["name"]},
        "url": cfg["base_url"].rstrip("/") + f"/news/{r['slug']}/",
    }
    if og_image:
        ld["image"] = og_image
    extra = '<script type="application/ld+json">' + json.dumps(ld).replace("</", "<\\/") + "</script>"
    body = f"""
<article class="release wrap">
  {draft}
  <div class="item-meta"><time datetime="{r['date']}">{nice_date(r['_date'])}</time><a class="chip" href="{rel}category/{slugify(r['category'])}/index.html">{esc(r['category'])}</a>{badge}</div>
  <h1>{inline(r['headline'])}</h1>
  {sub}
  <p class="source">Source: {org_html}</p>
  {figure}
  <div class="release-body">{body_html}</div>
  <div class="release-about">{abouts}</div>
  <div class="release-contact"><h3>Media contact</h3><p>{contact}</p></div>
  <div class="tags">{tags}</div>
  <div class="share">
    <a class="btn btn-ghost" href="https://www.linkedin.com/sharing/share-offsite/?url={esc(cfg['base_url'].rstrip('/') + '/news/' + r['slug'] + '/')}" target="_blank" rel="noopener">Share on LinkedIn</a>
    <a class="btn btn-ghost" href="{rel}index.html#latest">More releases</a>
  </div>
</article>
<section class="section alt cta-band">
  <div class="wrap"><h2>Have sports business news to announce?</h2><a class="btn btn-accent" href="{rel}submit/index.html">Submit a release</a></div>
</section>
"""
    desc = r.get("subheadline") or r["body"][0][:200]
    return page(cfg, title=r["headline"], description=desc, rel=rel, body=body,
                path=f"news/{r['slug']}/", og_type="article", extra_head=extra, og_image=og_image)


def build_category(cfg, cat, releases):
    rel = "../../"
    items = [r for r in releases if r["category"] == cat]
    body = f"""
<section class="section">
  <div class="wrap">
    <p class="crumb"><a href="{rel}index.html#categories">Categories</a></p>
    <div class="section-head"><h1 class="page-title">{esc(cat)}</h1></div>
    {release_list(items, rel, empty="No releases in this category yet.")}
  </div>
</section>"""
    return page(cfg, title=cat, description=f"{cat} press releases on {cfg['site_name']}.",
                rel=rel, body=body, path=f"category/{slugify(cat)}/")


def build_submit(cfg):
    rel = "../"
    cat_opts = "".join(f"<option>{esc(c)}</option>" for c in cfg["categories"])
    plan_opts = "".join(
        f'<label class="radio"><input type="radio" name="plan" value="{esc(p["name"])}" data-id="{p["id"]}" required{" checked" if p["id"] == "single" else ""}>'
        f'<span><b>{esc(p["name"])}</b> {esc(p["price"])} {esc(p["per"])}</span></label>'
        for p in cfg["plans"]
    )
    endpoint = json.dumps(cfg["submit_endpoint"])
    body = f"""
<section class="section">
  <div class="wrap narrow">
    <p class="eyebrow dark">Submit a release</p>
    <h1 class="page-title">Send us your announcement</h1>
    <p class="section-intro">Nothing is charged now. We review every submission and reply within two business days. If approved, you receive an invoice and your release is scheduled once it is paid.</p>
    <form id="submit-form" novalidate>
      <fieldset class="plans-pick"><legend>Plan</legend>{plan_opts}</fieldset>

      <h2 class="form-h">Your details</h2>
      <div class="grid">
        <label>Your name<input name="contact_name" required autocomplete="name"></label>
        <label>Email<input name="email" type="email" required autocomplete="email"></label>
        <label>Organization<input name="organization" required autocomplete="organization"></label>
        <label>Organization website<input name="website" type="url" placeholder="https://"></label>
        <label>Phone (optional)<input name="phone" type="tel" autocomplete="tel"></label>
      </div>

      <h2 class="form-h">The release</h2>
      <div class="grid">
        <label class="full">Headline<input name="headline" required maxlength="160"></label>
        <label class="full">Subheadline (optional)<input name="subheadline" maxlength="240"></label>
        <label>Category<select name="category" required><option value="">Choose one</option>{cat_opts}</select></label>
        <label>Dateline city<input name="dateline" placeholder="e.g. New York"></label>
        <label>Requested release date<input name="release_date" type="date"></label>
        <label class="full">Release text<textarea name="body" rows="12" required placeholder="Paste the full release. Separate paragraphs with a blank line."></textarea></label>
        <div class="full upload">
          <label>Image (optional): logo, product shot or photo<input name="image_file" id="image_file" type="file" accept="image/jpeg,image/png,image/webp"></label>
          <p class="hint">JPG, PNG or WebP, up to 8 MB. Large photos are resized automatically. Landscape images look best.</p>
          <div class="preview" id="image_preview" hidden><img alt=""><button type="button" class="btn btn-ghost" id="image_clear">Remove image</button></div>
          <label>Image caption or credit (optional)<input name="image_caption" maxlength="300" placeholder="e.g. Photo courtesy of Acme Sports"></label>
          <label class="check"><input type="checkbox" name="image_rights" value="yes" id="image_rights"><span>I have the rights to publish this image.</span></label>
        </div>
        <label class="full">About your organization (boilerplate)<textarea name="about" rows="4"></textarea></label>
        <label class="full">Media contact (name, email, phone)<textarea name="media_contact" rows="2"></textarea></label>
        <label class="full">Anything else we should know?<textarea name="notes" rows="3"></textarea></label>
        <label class="hp" aria-hidden="true">Leave blank<input name="company_url" tabindex="-1" autocomplete="off"></label>
        <label class="check full"><input type="checkbox" name="confirm" value="yes" required><span>I am authorized to publish this release and its contents are accurate.</span></label>
      </div>
      <div class="submit-row">
        <button class="btn btn-accent" id="cta" type="submit">Submit for review</button>
        <p class="status" id="status" role="status"></p>
      </div>
    </form>
    <div class="thanks" id="thanks" hidden>
      <h2>Thanks, your release is in review.</h2>
      <p>We will reply by email within two business days. Nothing is charged until your release is approved.</p>
    </div>
  </div>
</section>
<script>
const ENDPOINT = {endpoint};
const form = document.getElementById('submit-form');
const statusEl = document.getElementById('status');
const cta = document.getElementById('cta');
const want = new URLSearchParams(location.search).get('plan');
if (want) {{ const r = form.querySelector('input[data-id="' + want + '"]'); if (r) r.checked = true; }}
const MAX_BYTES = 8 * 1024 * 1024, MAX_DIM = 2000;
const fileInput = document.getElementById('image_file');
const preview = document.getElementById('image_preview');
const rights = document.getElementById('image_rights');
let image = null; // {{ data, type }}

function readAsDataURL(f) {{
  return new Promise((ok, bad) => {{ const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = bad; r.readAsDataURL(f); }});
}}
async function prepareImage(f) {{
  const url = await readAsDataURL(f);
  const img = new Image();
  await new Promise((ok, bad) => {{ img.onload = ok; img.onerror = bad; img.src = url; }});
  const scale = Math.min(1, MAX_DIM / Math.max(img.width, img.height));
  if (scale === 1 && f.size <= 2 * 1024 * 1024) return {{ url, type: f.type }};
  const c = document.createElement('canvas');
  c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
  c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
  const type = f.type === 'image/png' ? 'image/png' : 'image/jpeg'; // keep PNG transparency for logos
  return {{ url: c.toDataURL(type, 0.86), type }};
}}
fileInput.addEventListener('change', async () => {{
  image = null; preview.hidden = true; rights.required = false; statusEl.textContent = '';
  const f = fileInput.files[0];
  if (!f) return;
  if (!/^image\\/(jpeg|png|webp)$/.test(f.type)) {{ statusEl.textContent = 'Please choose a JPG, PNG or WebP image.'; fileInput.value = ''; return; }}
  if (f.size > MAX_BYTES) {{ statusEl.textContent = 'That image is over 8 MB. Please choose a smaller one.'; fileInput.value = ''; return; }}
  try {{
    const p = await prepareImage(f);
    image = {{ data: p.url.split(',')[1], type: p.type }};
    preview.querySelector('img').src = p.url;
    preview.hidden = false;
    rights.required = true;
  }} catch (err) {{
    statusEl.textContent = 'That image could not be read. Please try another file.'; fileInput.value = '';
  }}
}});
document.getElementById('image_clear').addEventListener('click', () => {{
  fileInput.value = ''; image = null; preview.hidden = true; rights.required = false; rights.checked = false;
}});

form.addEventListener('submit', async (e) => {{
  e.preventDefault();
  if (!form.reportValidity()) return;
  if (!ENDPOINT || ENDPOINT.indexOf('script.google.com') === -1) {{
    statusEl.textContent = 'Online submissions are temporarily unavailable. Please try again later.';
    return;
  }}
  cta.disabled = true;
  statusEl.textContent = 'Sending...';
  try {{
    const fd = new FormData(form);
    fd.delete('image_file');
    const body = new URLSearchParams(fd);
    if (image) {{ body.set('image_data', image.data); body.set('image_type', image.type); }}
    await fetch(ENDPOINT, {{ method: 'POST', mode: 'no-cors', body }});
    form.hidden = true;
    document.getElementById('thanks').hidden = false;
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
  }} catch (err) {{
    statusEl.textContent = 'Something went wrong. Please try again.';
    cta.disabled = false;
  }}
}});
</script>"""
    return page(cfg, title="Submit a release", description="Submit a sports business press release to Asset Arena Wire. Pay only after approval.",
                rel=rel, body=body, path="submit/")


def build_404(cfg):
    base = cfg["base_url"].rstrip("/") + "/"
    body = f"""<section class="section"><div class="wrap narrow"><h1 class="page-title">Page not found</h1>
<p class="section-intro">That release or page does not exist.</p><a class="btn btn-accent" href="{esc(base)}">Go to the homepage</a></div></section>"""
    # 404 is served from any depth, so assets use absolute URLs
    return page(cfg, title="Not found", description="Page not found", rel=base, body=body, path="404.html")


def build_feed(cfg, releases):
    base = cfg["base_url"].rstrip("/")
    items = []
    for r in releases[:50]:
        if r["status"] != "published":
            continue
        link = f"{base}/news/{r['slug']}/"
        pub = format_datetime(datetime.combine(r["_date"], datetime.min.time(), timezone.utc))
        desc = r.get("subheadline") or r["body"][0]
        items.append(f"""<item><title>{esc(r['headline'])}</title><link>{esc(link)}</link><guid isPermaLink="true">{esc(link)}</guid>
<pubDate>{pub}</pubDate><category>{esc(r['category'])}</category><description>{esc(desc)}</description></item>""")
    now = format_datetime(datetime.now(timezone.utc))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>
<title>{esc(cfg['site_name'])}</title><link>{esc(base)}/</link>
<atom:link href="{esc(base)}/feed.xml" rel="self" type="application/rss+xml"/>
<description>{esc(cfg['description'])}</description><language>en</language><lastBuildDate>{now}</lastBuildDate>
{chr(10).join(items)}
</channel></rss>
"""


def build_sitemap(cfg, releases):
    base = cfg["base_url"].rstrip("/")
    urls = [f"{base}/", f"{base}/submit/"]
    urls += [f"{base}/category/{slugify(c)}/" for c in cfg["categories"]]
    urls += [f"{base}/news/{r['slug']}/" for r in releases if r["status"] == "published"]
    body = "".join(f"<url><loc>{esc(u)}</loc></url>" for u in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>\n'


# ---------------------------------------------------------------- main

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv):
    include_drafts = "--drafts" in argv
    cfg = load_config()
    releases, errors = load_releases(cfg, include_drafts)
    if errors:
        print("Release problems found:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        return 1
    if "--check" in argv:
        print(f"OK: {len(releases)} release(s) valid.")
        return 0

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ASSETS_DIR, OUT / "assets")
    if IMAGES_DIR.is_dir():
        shutil.copytree(IMAGES_DIR, OUT / "images")
    if (ROOT / "CNAME").exists():
        shutil.copy(ROOT / "CNAME", OUT / "CNAME")
    write(OUT / ".nojekyll", "")

    write(OUT / "index.html", build_home(cfg, releases))
    for r in releases:
        write(OUT / "news" / r["slug"] / "index.html", build_release(cfg, r))
    for c in cfg["categories"]:
        write(OUT / "category" / slugify(c) / "index.html", build_category(cfg, c, releases))
    write(OUT / "submit" / "index.html", build_submit(cfg))
    write(OUT / "404.html", build_404(cfg))
    write(OUT / "feed.xml", build_feed(cfg, releases))
    write(OUT / "sitemap.xml", build_sitemap(cfg, releases))
    write(OUT / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {cfg['base_url'].rstrip('/')}/sitemap.xml\n")

    print(f"Built {len(releases)} release(s) into {OUT.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
