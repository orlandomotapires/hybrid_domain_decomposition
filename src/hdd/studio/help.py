"""Help panel: the reference documentation, browsable and searchable, opened in context with F1."""

from __future__ import annotations

import html
import re
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QSplitter, QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from hdd.services import wiki

from .theme import Theme

TOPIC_ROLE = Qt.ItemDataRole.UserRole + 1


_SUB = str.maketrans("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ")
_SUP = str.maketrans("0123456789+-=()in", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁱⁿ")
_SUB_CHARS, _SUP_CHARS = set("0123456789+-=()aehijklmnoprstuvx"), set("0123456789+-=()in")


def pretty_formula(text: str) -> str:
    """``P_{k-1}`` as ``Pₖ₋₁`` and ``x^{2}`` as ``x²`` where Unicode has the characters; anything else is kept."""
    def replace(match: re.Match) -> str:
        mark, body = match.group(1), match.group(2) or match.group(3)
        table, allowed = (_SUB, _SUB_CHARS) if mark == "_" else (_SUP, _SUP_CHARS)
        return body.translate(table) if set(body) <= allowed else match.group(0)

    return re.sub(r"([_^])(?:\{([^{}]+)\}|([0-9a-z]))", replace, text)


def render_topic(topic: dict[str, Any]) -> str:
    """Topic as HTML styled with the current theme."""
    c = Theme.instance().tokens.colors
    mono = Theme.instance().mono_font().family()
    e = html.escape

    def section(title: str, items: list[str] | None) -> str:
        if not items:
            return ""
        body = "".join(f"<li style='margin-bottom:4px'>{e(item)}</li>" for item in items)
        return f"<h3 style='margin:14px 0 4px 0'>{e(title)}</h3><ul style='margin-left:-18px'>{body}</ul>"

    parts = [
        f"<h2 style='margin:0 0 2px 0'>{e(topic['title'])}</h2>",
        f"<p style='color:{c.text_muted};margin:0 0 10px 0'>{e(topic.get('badge', ''))}</p>",
        f"<p>{e(topic.get('shortSummary', ''))}</p>",
    ]
    if topic.get("codeKey"):
        parts.append(f"<p style='color:{c.text_muted}'>Parameter: <span style='font-family:{mono}'>{e(topic['codeKey'])}</span></p>")
    if topic.get("formula"):
        parts.append(
            f"<table width='100%' cellpadding='8' style='background:{c.base_alt};border:1px solid {c.border};margin:6px 0'>"
            f"<tr><td style='font-family:{mono}'>{e(pretty_formula(topic['formula']))}</td></tr></table>"
        )
    parts.append(section("Background", topic.get("scientificBackground")))
    parts.append(section("In this implementation", topic.get("implementationDetails")))
    parts.append(section("Tuning guidelines", topic.get("tuningGuidelines")))
    if topic.get("sourceFile"):
        parts.append(f"<p style='color:{c.text_muted}'>Source: <span style='font-family:{mono}'>{e(topic['sourceFile'])}</span></p>")
    return f"<div style='color:{c.text}'>{''.join(parts)}</div>"


class HelpPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search the documentation")
        self.search.setClearButtonEnabled(True)
        self._search_action = QAction(self.search)
        Theme.instance().bind_icon(self._search_action, "search", "muted")
        self.search.addAction(self._search_action, QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self._fill)

        self.index = QTreeWidget()
        self.index.setHeaderHidden(True)
        self.index.setIndentation(14)
        self.index.setIconSize(QSize(16, 16))
        self.index.currentItemChanged.connect(self._on_item)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)
        self.view.document().setDocumentMargin(14)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        row = QWidget()
        row.setObjectName("ToolRow")
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(6, 4, 6, 4)
        row_layout.addWidget(self.search)
        left_layout.addWidget(row)
        left_layout.addWidget(self.index, 1)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(left)
        splitter.addWidget(self.view)
        splitter.setSizes([260, 520])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self._topic: dict[str, Any] | None = None
        Theme.instance().changed.connect(self._rerender)
        self._fill("")

    def _fill(self, text: str) -> None:
        matches = {t["id"] for t in wiki.search(text)}
        self.index.blockSignals(True)
        self.index.clear()
        for category in wiki.categories():
            items = [t for t in wiki.topics(category["key"]) if t["id"] in matches]
            if not items:
                continue
            parent = QTreeWidgetItem([category["shortLabel"]])
            parent.setToolTip(0, category["description"])
            parent.setIcon(0, Theme.instance().icon("docs", "muted"))
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for topic in items:
                child = QTreeWidgetItem([topic["title"]])
                child.setData(0, TOPIC_ROLE, topic["id"])
                parent.addChild(child)
            self.index.addTopLevelItem(parent)
            parent.setExpanded(bool(text) or self._topic is not None and self._topic["category"] == category["key"])
        self.index.blockSignals(False)

    def _on_item(self, item: QTreeWidgetItem | None, _previous) -> None:
        topic_id = item.data(0, TOPIC_ROLE) if item else None
        if topic_id:
            self.show_topic(topic_id)

    def show_topic(self, topic_id: str) -> bool:
        topic = wiki.topic(topic_id)
        if topic is None:
            return False
        self._topic = topic
        self._rerender()
        for i in range(self.index.topLevelItemCount()):
            parent = self.index.topLevelItem(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.data(0, TOPIC_ROLE) == topic_id:
                    parent.setExpanded(True)
                    self.index.blockSignals(True)
                    self.index.setCurrentItem(child)
                    self.index.blockSignals(False)
        return True

    def show_parameter(self, key: str) -> bool:
        topic = wiki.topic_for_parameter(key)
        return self.show_topic(topic["id"]) if topic else False

    def current_topic(self) -> dict[str, Any] | None:
        return self._topic

    def _rerender(self) -> None:
        if self._topic is not None:
            self.view.setHtml(render_topic(self._topic))
        else:
            self.view.setHtml(f"<p style='color:{Theme.instance().tokens.colors.text_muted}'>Choose a topic, or press F1 on a parameter.</p>")
