#!/usr/bin/env python3
"""
Convert every source about Aditya into the canonical corpus: corpus/<kind>/<slug>.md with YAML-ish
frontmatter. Structure is preserved (headings → #, lists → -, tables → markdown tables, embedded
images → media/ files referenced in order) so the chunkers can split on it.

Sources
  1. ~/Downloads/AI-N-Automation Docs/*.docx        → corpus/docs/<nn>-<slug>.md   (kind: project)
  2. applications/resume_copy.py                    → corpus/profile/resume.md      (kind: profile)
  3. applications/INTERVIEW_PREP.md  (Part 1 only)  → corpus/profile/engineering-stories.md
  4. site/src/content/profile.ts + projects.ts      → corpus/profile/about.md, corpus/site/<slug>.md
  5. corpus/profile/facts.md is hand-written and kept as is.

Every string passes through redact() — see scripts/redact.py.

    .venv/bin/python scripts/convert_corpus.py
"""
from __future__ import annotations
import io, json, os, re, sys, shutil, importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CORPUS = ROOT / "corpus"
DOCS_SRC = Path.home() / "Downloads" / "AI-N-Automation Docs"
APPS = ROOT.parent / "applications"
SITE = ROOT.parent / "site"

sys.path.insert(0, str(HERE))
from redact import redact  # noqa: E402

# docx number → (doc slug, portfolio /work/<slug> page or None)
SITE_MAP = {
    "01": ("product-matcher", "product-matcher"),
    "02": ("catalog-enrichment", "catalog-metadata"),
    "03": ("product-facets", "catalog-metadata"),
    "04": ("sister-products-clustering", "sister-products"),
    "05": ("call-quality-analysis", "call-qa"),
    "06": ("badho-bytes", None),
    "07": ("catalog-localization", "catalog-metadata"),
    "08": ("weight-estimation", None),
    "09": ("badho-search", "semantic-search"),
    "10": ("resume-ocr", None),
    "11": ("pincode-enrichment", None),
    "12": ("ad-video-generation", None),
    "13": ("delivery-manager", "delivery-fleet"),
    "14": ("buyer-mcp", "buyer-mcp"),
    "15": ("whatsapp-sales-agent", "whatsapp-sales-agent"),
    "16": ("order-lifecycle-automation", "order-lifecycle-automation"),
    "17": ("delhivery-ops-autopilot", "delhivery-ops-autopilot"),
    "18": ("aditya-mcp", "aditya-mcp"),
    "19": ("referral-credit-engine", "live-money-paths"),
    "20": ("scratch-qr-cashback", "live-money-paths"),
}
# Only tier-1 projects have a /work/<slug> page on the site.
TIER1 = {"delivery-fleet", "buyer-mcp", "whatsapp-sales-agent", "order-lifecycle-automation",
         "delhivery-ops-autopilot", "live-money-paths", "aditya-mcp"}

def fm(**kv) -> str:
    lines = ["---"]
    for k, v in kv.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            lines.append(f"{k}: {json.dumps(list(v), ensure_ascii=False)}")
        else:
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---\n")
    return "\n".join(lines)

def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}  ({len(text.split())} words)")

# ---------------------------------------------------------------- 1. docx
def index_summaries() -> dict[str, str]:
    """One-line summaries from INDEX.md, keyed by the two-digit prefix."""
    out = {}
    idx = DOCS_SRC / "INDEX.md"
    if not idx.exists():
        return out
    for line in idx.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(\d\d) - .*?\.docx\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|", line)
        if m:
            out[m.group(1)] = m.group(3).strip()
    return out

def convert_docx(path: Path, summaries: dict[str, str]):
    import docx
    from docx.oxml.ns import qn
    d = docx.Document(str(path))
    num = path.name[:2]
    doc_slug, site_slug = SITE_MAP.get(num, (re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-"), None))
    media_dir = CORPUS / "media" / doc_slug
    if media_dir.exists():
        shutil.rmtree(media_dir)

    # image rId → saved filename, assigned in document order
    rels = {r.rId: r for r in d.part.rels.values() if "image" in r.reltype}
    img_n = 0
    out: list[str] = []
    title = None

    def para_md(p) -> str | None:
        nonlocal img_n, title
        style = (p.style.name or "").lower()
        text = p.text.strip()
        # images inside this paragraph
        blips = p._p.findall(".//" + qn("a:blip"))
        img_lines = []
        for b in blips:
            rid = b.get(qn("r:embed"))
            if rid in rels:
                img_n += 1
                part = rels[rid].target_part
                ext = os.path.splitext(part.partname)[1] or ".png"
                fn = f"fig-{img_n:02d}{ext}"
                media_dir.mkdir(parents=True, exist_ok=True)
                (media_dir / fn).write_bytes(part.blob)
                img_lines.append(f"![Figure {img_n}](media/{doc_slug}/{fn})")
        if not text and not img_lines:
            return None
        if style.startswith("heading") or style == "title":
            level = 1 if style == "title" else int(re.sub(r"\D", "", style) or 1)
            if title is None:
                title = text
                return f"# {text}"
            return "#" * min(level + 0, 6) + " " + text if level > 1 else "## " + text
        if "list" in style or p._p.pPr is not None and p._p.pPr.find(qn("w:numPr")) is not None:
            body = f"- {text}"
        else:
            body = text
        return "\n".join([body] + img_lines) if text else "\n".join(img_lines)

    def table_md(t) -> str:
        rows = [[c.text.strip().replace("\n", " ") for c in r.cells] for r in t.rows]
        if not rows:
            return ""
        w = max(len(r) for r in rows)
        rows = [r + [""] * (w - len(r)) for r in rows]
        head = "| " + " | ".join(rows[0]) + " |"
        sep = "| " + " | ".join("---" for _ in range(w)) + " |"
        body = ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return "\n".join([head, sep] + body)

    body_el = d.element.body
    for child in body_el.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            from docx.text.paragraph import Paragraph
            md = para_md(Paragraph(child, d))
            if md:
                out.append(md)
        elif tag == "tbl":
            from docx.table import Table
            out.append(table_md(Table(child, d)))

    title = title or path.stem[5:]
    text = "\n\n".join(out)
    # The house-format docs end with a "Media" section that only lists filenames — drop it.
    text = re.split(r"\n## \d+\.\s*Media\s*\n", text)[0].rstrip() + "\n"
    text = redact(text)
    page_url = f"https://adityamukhopadhyay.vercel.app/work/{site_slug}" if site_slug in TIER1 else None
    header = fm(title=title, slug=doc_slug, kind="project", site_slug=site_slug, page_url=page_url,
                source=path.name, summary=summaries.get(num))
    write(CORPUS / "docs" / f"{num}-{doc_slug}.md", header + text)

# ---------------------------------------------------------------- 2. resume
def convert_resume():
    spec = importlib.util.spec_from_file_location("resume_copy", APPS / "resume_copy.py")
    RC = importlib.util.module_from_spec(spec); spec.loader.exec_module(RC)
    L = [f"# {RC.NAME} — Resume", "", f"**{RC.HEADLINE}**", "", f"Location: {RC.LOCATION}", "",
         "## Summary", "", RC.SUMMARY, "", "## Skills", ""]
    for h, b in RC.SKILLS:
        L.append(f"- **{h}:** {b}")
    L += ["", "## Experience", ""]
    def role(r):
        t, co, dates, _ = r
        return f"### {t} — {co} ({dates})"
    L.append(role(RC.BADHO_ROLE)); L.append("")
    for t, pts in RC.BADHO_PROJECTS:
        L.append(f"#### {t}")
        L += [f"- {p}" for p in pts]; L.append("")
    L.append(role(RC.STRIX_ROLE)); L += [f"- {p}" for p in RC.STRIX_POINTS]; L.append("")
    L.append(role(RC.ACME_ROLE));  L += [f"- {p}" for p in RC.ACME_POINTS];  L.append("")
    L += ["## Education", ""]
    for deg, inst, m in RC.EDUCATION:
        L.append(f"- **{deg}** — {inst} · {m}")
    L += ["", "## Side projects", ""]
    for t, y, b in RC.SIDE_PROJECTS:
        L.append(f"- **{t}** ({y}) — {b}")
    L += ["", "## Contact", "", f"- Email: {RC.EMAIL}", f"- Phone: {RC.PHONE}"]
    for label, href, _ in RC.LINKS:
        L.append(f"- {label}: {href}")
    text = redact("\n".join(L) + "\n")
    write(CORPUS / "profile" / "resume.md",
          fm(title="Aditya Mukhopadhyay — Resume", slug="resume", kind="profile",
             page_url="https://adityamukhopadhyay.vercel.app/resume", source="resume_copy.py") + text)

# ---------------------------------------------------------------- 3. story bank
def convert_stories():
    src = (APPS / "INTERVIEW_PREP.md").read_text(encoding="utf-8")
    start = src.index("# PART 1")
    end = src.index("# PART 2")
    part = src[start:end]
    part = part.replace("# PART 1 — THE STORY BANK", "# Engineering stories — how the projects were built, what failed, what changed", 1)
    # de-interview it: these were written as prep notes; keep the substance, drop the coaching voice
    part = re.sub(r"(?im)^\s*(say this|you say|answer:|if they ask|they will ask)[^\n]*\n", "", part)
    text = redact(part.strip() + "\n")
    write(CORPUS / "profile" / "engineering-stories.md",
          fm(title="Engineering stories — problems, decisions, failures and fixes", slug="engineering-stories",
             kind="profile", source="INTERVIEW_PREP.md (story bank)") + text)

# ---------------------------------------------------------------- 4. site content
def _ts_to_json(ts_path: Path, export_name: str):
    """Evaluate the TS module with Node's native type stripping and print the export as JSON."""
    import subprocess, tempfile
    src = ts_path.read_text(encoding="utf-8")
    src = re.sub(r"^import\s[^\n]*\n", "", src, flags=re.M)          # drop imports (content files are self-contained)
    src = re.sub(r"^export\s+(const|type|function)", r"\1", src, flags=re.M)
    src = re.sub(r"^export\s+default\s+", "", src, flags=re.M)
    src += f"\nconsole.log(JSON.stringify({export_name}));\n"
    with tempfile.NamedTemporaryFile("w", suffix=".ts", delete=False, encoding="utf-8") as f:
        f.write(src); tmp = f.name
    r = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", tmp], capture_output=True, text=True)
    os.unlink(tmp)
    if r.returncode != 0:
        raise RuntimeError(f"node failed on {ts_path.name}: {r.stderr[:400]}")
    return json.loads(r.stdout)

def convert_site():
    prof = _ts_to_json(SITE / "src/content/profile.ts", "profile")
    L = [f"# About {prof['name']['first']} {prof['name']['last']}", "",
         f"**{prof['role']} at {prof['company']}** ({prof['companyUrl']})", "", prof["tagline"], ""]
    for p in prof.get("intro", []): L += [p, ""]
    L += ["## What differentiates the work", ""]
    for s in prof.get("signals", []):
        L += [f"### {s['title']}", "", s["body"], f"(See: https://adityamukhopadhyay.vercel.app{s['href']})", ""]
    L += ["## Skills", "", "- **Core:** " + ", ".join(prof["skills"]["core"]),
          "- **AI:** " + ", ".join(prof["skills"]["ai"]), "", "## Experience", ""]
    for e in prof.get("experience", []):
        L += [f"### {e['role']} — {e['org']} ({e['period']})", ""]
        L += [f"- {b}" for b in e.get("bullets", [])]; L.append("")
    for k in ("education", "links"):
        if k in prof and isinstance(prof[k], dict):
            L += [f"## {k.title()}", ""] + [f"- {a}: {b}" for a, b in prof[k].items()] + [""]
    write(CORPUS / "profile" / "about.md",
          fm(title="About Aditya Mukhopadhyay", slug="about", kind="profile",
             page_url="https://adityamukhopadhyay.vercel.app/", source="site/profile.ts") + redact("\n".join(L) + "\n"))

    projs = _ts_to_json(SITE / "src/content/projects.ts", "projects")
    for p in projs:
        L = [f"# {p['title']}", "", p.get("short", ""), "",
             f"Period: {p.get('period','')}. Stack: {', '.join(p.get('stack', []))}.", ""]
        if p.get("headline"):
            L += ["## Headline numbers", ""] + [f"- **{m['value']}** — {m['label']}" + (f" ({m['note']})" if m.get("note") else "") for m in p["headline"]] + [""]
        if p.get("context"):
            L += ["## Context", ""] + [c + "\n" for c in p["context"]]
        if p.get("mechanisms"):
            L += ["## How it works", ""]
            for m in p["mechanisms"]:
                L += [f"### {m['title']}", "", m["body"], ""]
        if p.get("metrics"):
            L += ["## Measured results", ""] + [f"- **{m['value']}** — {m['label']}" + (f" ({m['note']})" if m.get("note") else "") for m in p["metrics"]] + [""]
        if p.get("honesty"):
            L += ["## What the numbers do and do not claim", "", p["honesty"], ""]
        if p.get("lessons"):
            L += ["## Lessons", ""] + [f"- {x}" for x in p["lessons"]] + [""]
        if p.get("detail"):
            L += ["## Detail", ""] + [x + "\n" for x in p["detail"]]
        page = f"https://adityamukhopadhyay.vercel.app/work/{p['slug']}" if p.get("tier") == 1 else "https://adityamukhopadhyay.vercel.app/#work"
        write(CORPUS / "site" / f"{p['slug']}.md",
              fm(title=p["title"], slug=f"site-{p['slug']}", kind="portfolio", site_slug=p["slug"],
                 page_url=page, source="site/projects.ts", themes=p.get("themes")) + redact("\n".join(L) + "\n"))

def main():
    (CORPUS / "docs").mkdir(parents=True, exist_ok=True)
    print("1. project docs")
    summaries = index_summaries()
    for f in sorted(DOCS_SRC.glob("*.docx")):
        convert_docx(f, summaries)
    print("2. resume");  convert_resume()
    print("3. stories"); convert_stories()
    print("4. site");    convert_site()
    n = len(list(CORPUS.rglob("*.md")))
    print(f"\ncorpus: {n} markdown files under {CORPUS.relative_to(ROOT)}/")

if __name__ == "__main__":
    main()
