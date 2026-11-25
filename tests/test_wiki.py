"""The wiki (docs/wiki) stays in step with the code: generated pages are current and links resolve."""

import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "docs" / "wiki"
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"```.*?```", re.DOTALL)


def _generator():
    spec = importlib.util.spec_from_file_location("generate_parameter_reference", WIKI / "generate_parameter_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _anchors(path: Path) -> set[str]:
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    anchors = set()
    for heading in re.findall(r"^#{1,6}\s+(.+)$", text, re.MULTILINE):
        slug = re.sub(r"[^\w\- ]", "", heading.strip().lower())
        anchors.add(re.sub(r"\s", "-", slug))
    return anchors


def _documents() -> list[Path]:
    readmes = [p for p in ROOT.rglob("README.md") if not any(part.startswith(".") for part in p.relative_to(ROOT).parts)]
    return sorted(set(readmes) | set(WIKI.glob("*.md")))


class WikiTest(unittest.TestCase):
    def test_parameter_reference_is_generated_from_the_help_content(self) -> None:
        generator = _generator()
        import json

        expected = generator.render(json.loads(generator.SOURCE.read_text(encoding="utf-8")))
        actual = (WIKI / "parameter-reference.md").read_text(encoding="utf-8")
        self.assertEqual(expected, actual, "Run: python docs/wiki/generate_parameter_reference.py")

    def test_links_point_to_existing_files_and_headings(self) -> None:
        broken = []
        for doc in _documents():
            for target in LINK.findall(FENCE.sub("", doc.read_text(encoding="utf-8"))):
                if re.match(r"^[a-z]+:", target):
                    continue  # external
                path_part, _, anchor = target.partition("#")
                resolved = (doc.parent / path_part).resolve() if path_part else doc
                if not resolved.exists():
                    broken.append(f"{doc.relative_to(ROOT)}: {target} (missing file)")
                elif anchor and resolved.suffix == ".md" and anchor not in _anchors(resolved):
                    broken.append(f"{doc.relative_to(ROOT)}: {target} (missing heading)")
        self.assertEqual([], broken)

    def test_every_wiki_page_is_linked_from_the_index(self) -> None:
        index = (WIKI / "README.md").read_text(encoding="utf-8")
        pages = {p.name for p in WIKI.glob("*.md")} - {"README.md"}
        self.assertEqual(set(), {p for p in pages if f"({p})" not in index})


if __name__ == "__main__":
    unittest.main()
