"""Export docs/wiki to a clone of the repository's GitHub Wiki.

docs/wiki is the source; the GitHub Wiki is a published copy. To update it:

    git clone https://github.com/orlandomotapires/hybrid_domain_decomposition.wiki.git /tmp/hdd-wiki
    python docs/wiki/export_github_wiki.py /tmp/hdd-wiki
    cd /tmp/hdd-wiki && git add -A && git commit -m "Update from docs/wiki" && git push

What changes on the way:

- ``README.md`` becomes ``Home.md``; other pages get a capitalised name
  (``how-it-works.md`` → ``How-it-works.md``, shown as "How it works").
- Links between pages lose ``.md``, as wiki links do.
- Images, including ones elsewhere in the repository such as the app icon, are
  copied to ``images/`` and linked by their raw URL (also in ``<img src>`` tags);
  links to other repository files point to the file on GitHub.
- A page's own ``# Title`` is dropped (the wiki shows the page name), except on Home.
- ``_Sidebar.md`` lists every page; ``_Footer.md`` says where to edit the source.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

WIKI = Path(__file__).resolve().parent
REPO = "orlandomotapires/hybrid_domain_decomposition"
BRANCH = "main"
RAW_IMAGES = f"https://raw.githubusercontent.com/wiki/{REPO}/images/"
REPO_FILES = f"https://github.com/{REPO}/blob/{BRANCH}/"
LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)")
HTML_SRC = re.compile(r'(<img\b[^>]*\bsrc=")([^"]+)(")')

SIDEBAR = [
    ("Start here", ["installation", "how-it-works"]),
    ("Use it", ["desktop-app", "command-line", "simulations", "matrix-library", "batch-studies", "parameter-tuning",
                "workspaces", "quantum-backends"]),
    ("Reference", ["parameter-reference", "development"]),
]


def page_name(stem: str) -> str:
    return "Home" if stem == "README" else stem[:1].upper() + stem[1:]


def _title(stem: str) -> str:
    return page_name(stem).replace("-", " ")


def _image_url(path: str, target: Path | None) -> str:
    """Raw URL of an image; images outside docs/wiki/images are copied next to the others."""
    if path.startswith("images/"):
        return RAW_IMAGES + path[len("images/"):]
    source = (WIKI / path).resolve()
    if target is not None:
        shutil.copyfile(source, target / "images" / source.name)
    return RAW_IMAGES + source.name


def convert(text: str, stem: str, target: Path | None = None) -> str:
    def html_src(match: re.Match) -> str:
        before, src, after = match.groups()
        return match.group(0) if re.match(r"^[a-z]+:", src) else f"{before}{_image_url(src, target)}{after}"

    def link(match: re.Match) -> str:
        bang, label, target_ = match.groups()
        if re.match(r"^[a-z]+:", target_) or target_.startswith("#"):
            return match.group(0)
        path, _, anchor = target_.partition("#")
        suffix = f"#{anchor}" if anchor else ""
        if bang:
            return f"{bang}[{label}]({_image_url(path, target)})"
        if path.endswith(".md") and "/" not in path:
            return f"{bang}[{label}]({page_name(path[:-3])}{suffix})"
        repo_path = (WIKI / path).resolve().relative_to(WIKI.parents[1])
        return f"{bang}[{label}]({REPO_FILES}{repo_path.as_posix()}{suffix})"

    if stem != "README":
        text = re.sub(r"\A# [^\n]*\n+", "", text)
    return LINK.sub(link, HTML_SRC.sub(html_src, text))


def export(target: Path) -> list[str]:
    if not (target / ".git").exists():
        raise SystemExit(f"{target} is not a clone of the wiki repository")
    for old in target.glob("*.md"):
        old.unlink()
    shutil.rmtree(target / "images", ignore_errors=True)
    shutil.copytree(WIKI / "images", target / "images")
    written = []
    for page in sorted(WIKI.glob("*.md")):
        name = f"{page_name(page.stem)}.md"
        (target / name).write_text(convert(page.read_text(encoding="utf-8"), page.stem, target), encoding="utf-8")
        written.append(name)
    sidebar = ["**[Home](Home)**", ""]
    for heading, stems in SIDEBAR:
        sidebar += [f"**{heading}**", ""] + [f"- [{_title(s)}]({page_name(s)})" for s in stems] + [""]
    (target / "_Sidebar.md").write_text("\n".join(sidebar), encoding="utf-8")
    (target / "_Footer.md").write_text(
        f"These pages are generated from [docs/wiki]({REPO_FILES}docs/wiki) in the repository; edit them there.\n",
        encoding="utf-8",
    )
    return written


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    for name in export(Path(argv[0]).resolve()):
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
