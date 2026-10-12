"""Load corpus/**/*.md into Document → Section trees. Sections follow the markdown heading structure."""
from __future__ import annotations
import hashlib, json, re
from dataclasses import dataclass, field
from pathlib import Path
from .config import settings

@dataclass
class Section:
    id: str                 # stable: sha1(doc_slug + heading_path + ordinal)[:16]
    doc_slug: str
    doc_title: str
    heading_path: list[str] # e.g. ["WhatsApp AI Sales Agent", "3. System Architecture", "Step 2: Two-Agent Design"]
    text: str               # body text (no heading line)
    order: int
    page_url: str | None
    kind: str
    site_slug: str | None

    @property
    def heading(self) -> str:
        return " › ".join(self.heading_path)

    def contextualised(self) -> str:
        """What gets embedded for pipeline A: a deterministic situating prefix + the body."""
        return f"Document: {self.doc_title}\nSection: {self.heading}\n\n{self.text}"

@dataclass
class Document:
    slug: str
    title: str
    kind: str
    source: str
    page_url: str | None
    site_slug: str | None
    summary: str | None
    path: Path
    sections: list[Section] = field(default_factory=list)

_FM = re.compile(r"^---\n(.*?)\n---\n", re.S)

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = _FM.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            try:
                meta[k.strip()] = json.loads(v.strip())
            except json.JSONDecodeError:
                meta[k.strip()] = v.strip().strip('"')
    return meta, text[m.end():]

def _split_sections(body: str, doc_title: str) -> list[tuple[list[str], str]]:
    """Walk headings; each heading starts a section whose path is the heading stack."""
    out: list[tuple[list[str], str]] = []
    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    cur_path: list[str] = [doc_title]

    def flush():
        txt = "\n".join(buf).strip()
        if txt:
            out.append((list(cur_path), txt))
        buf.clear()

    for line in body.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            level, title = len(m.group(1)), m.group(2).strip()
            if level == 1:
                stack = []          # the H1 is the document title; it is already the path root
                cur_path = [doc_title]
                continue
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            cur_path = [doc_title] + [t for _, t in stack]
        else:
            buf.append(line)
    flush()
    return out

MIN_WORDS = 25   # merge tiny sections (e.g. a one-line "Summary" heading) into the previous one

def corpus_hash(corpus_dir: Path | None = None) -> str:
    """Stable fingerprint of every markdown file in the corpus (path + bytes), so the server can tell at
    startup whether the index was built from the corpus it is now serving."""
    import hashlib
    corpus_dir = corpus_dir or settings.corpus_dir
    h = hashlib.sha256()
    for path in sorted(corpus_dir.rglob("*.md")):
        h.update(str(path.relative_to(corpus_dir)).encode()); h.update(b"\0"); h.update(path.read_bytes()); h.update(b"\0")
    return h.hexdigest()[:16]

def load_corpus(corpus_dir: Path | None = None) -> list[Document]:
    corpus_dir = corpus_dir or settings.corpus_dir
    docs: list[Document] = []
    for path in sorted(corpus_dir.rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        title = meta.get("title") or path.stem
        slug = meta.get("slug") or path.stem
        d = Document(slug=slug, title=title, kind=meta.get("kind", "doc"), source=meta.get("source", path.name),
                     page_url=meta.get("page_url"), site_slug=meta.get("site_slug"), summary=meta.get("summary"), path=path)
        raw_secs = _split_sections(body, title)
        # merge tiny sections forward
        merged: list[tuple[list[str], str]] = []
        for hp, txt in raw_secs:
            if merged and len(txt.split()) < MIN_WORDS and len(merged[-1][1].split()) < 400:
                ph, pt = merged[-1]
                merged[-1] = (ph, pt + "\n\n" + (hp[-1] + ": " if hp[-1] != ph[-1] else "") + txt)
            else:
                merged.append((hp, txt))
        for i, (hp, txt) in enumerate(merged):
            sid = hashlib.sha1(f"{slug}|{'›'.join(hp)}|{i}".encode()).hexdigest()[:16]
            d.sections.append(Section(id=sid, doc_slug=slug, doc_title=title, heading_path=hp, text=txt, order=i,
                                      page_url=d.page_url, kind=d.kind, site_slug=d.site_slug))
        docs.append(d)
    return docs

def all_sections(docs: list[Document]) -> list[Section]:
    return [s for d in docs for s in d.sections]

def split_long(section: Section, max_words: int = 380, overlap_words: int = 0) -> list[Section]:
    """Sections longer than max_words are split on paragraph boundaries. Keeps ids stable via suffix."""
    words = section.text.split()
    if len(words) <= max_words:
        return [section]
    paras = [p for p in section.text.split("\n\n") if p.strip()]
    parts: list[str] = []; cur: list[str] = []; n = 0
    for p in paras:
        w = len(p.split())
        if cur and n + w > max_words:
            parts.append("\n\n".join(cur)); cur, n = [], 0
        cur.append(p); n += w
    if cur: parts.append("\n\n".join(cur))
    out = []
    for j, txt in enumerate(parts):
        out.append(Section(id=f"{section.id}-{j}", doc_slug=section.doc_slug, doc_title=section.doc_title,
                           heading_path=section.heading_path + ([f"part {j+1}"] if len(parts) > 1 else []),
                           text=txt, order=section.order, page_url=section.page_url, kind=section.kind,
                           site_slug=section.site_slug))
    return out
