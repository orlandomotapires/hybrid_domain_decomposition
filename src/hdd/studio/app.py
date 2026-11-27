"""Entry point of HDD Studio Desktop (``hdd-studio``)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import QApplication

from . import APP_ID, APP_NAME, ORGANIZATION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME}: desktop environment for hybrid domain decomposition.")
    parser.add_argument("--workspace", type=Path, help="project folder to open (default: the last one opened)")
    parser.add_argument("--theme", choices=("system", "light", "dark"), help="override the saved theme for this session")
    parser.add_argument("--gallery", action="store_true", help="open the widget gallery instead of the main window")
    parser.add_argument("--screenshot", metavar="DIR", type=Path, help="write PNG captures of the window in both themes to DIR, then exit")
    return parser


def create_application(argv: list[str] | None = None) -> QApplication:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv[:1])
    app.setOrganizationName(ORGANIZATION)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName(APP_ID)
    icons = Path(__file__).resolve().parent / "resources" / "app"
    if (icons / "hdd-studio.svg").is_file():
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QIcon

        icon = QIcon()
        for size in (16, 24, 32):  # the detail of the full icon blurs at these sizes
            icon.addFile(str(icons / "hdd-studio-small.svg"), QSize(size, size))
        for size in (48, 64, 128, 256):
            icon.addFile(str(icons / "hdd-studio.svg"), QSize(size, size))
        app.setWindowIcon(icon)
    _collect_garbage_on_the_gui_thread()
    return app


_gui_garbage_collector = None


def _collect_garbage_on_the_gui_thread() -> None:
    """Run Python's cyclic garbage collector only on the GUI thread, from a timer.

    Otherwise it runs in whichever thread happens to be allocating, such as a task-runner thread
    building a graph, and may destroy a Qt widget there. Qt objects must be destroyed in their
    own thread; doing it elsewhere deadlocked the window (the GUI thread waiting on a Qt lock
    while a worker thread destroyed a widget). pyqtgraph's collector does exactly this.
    """
    global _gui_garbage_collector
    if _gui_garbage_collector is None:
        from pyqtgraph.util.garbage_collector import GarbageCollector

        _gui_garbage_collector = GarbageCollector(interval=0.5)


def resolve_workspace(requested: Path | None, remembered: str | None) -> Path:
    """The folder to open: the requested one, else the last one opened, else the default workspace."""
    from hdd.services import workspace

    if requested is not None:
        return requested.expanduser().resolve()
    if remembered and Path(remembered).is_dir():
        return Path(remembered)
    return workspace.root()


def settle(app: QApplication, window=None, seconds: float = 0.6) -> None:
    """Process events until background tasks have delivered their results."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    if window is not None:
        window.ctx.tasks.wait(10000)
        window.ctx.tasks.drain()
    app.processEvents()
    app.processEvents()


def capture_screenshots(app: QApplication, directory: Path, root: Path) -> list[Path]:
    """Render the main window on ``root`` and the gallery, in both themes."""
    from .gallery import Gallery
    from .main_window import MainWindow
    from .settings import Settings
    from .theme import Theme

    directory.mkdir(parents=True, exist_ok=True)
    theme = Theme(app, "light")
    written: list[Path] = []

    def save(widget, name: str) -> None:
        path = directory / name
        if not widget.grab().save(str(path)):
            raise OSError(f"could not write {path}")
        written.append(path)

    for mode in ("light", "dark"):
        theme.apply(mode)
        window = MainWindow(theme, Settings.ephemeral(), root)
        window.resize(1440, 900)
        window.show()
        settle(app, window, 1.5)
        for kind in ("simulation", "coarsening", "matrix", "run"):
            if window.select_node(kind):
                settle(app, window, 1.5)
                save(window, f"main-{kind}-{mode}.png")
        window.close()
        gallery = Gallery(theme)
        gallery.resize(1180, 860)
        gallery.show()
        settle(app)
        gallery.content.adjustSize()
        settle(app)
        save(gallery.content, f"gallery-{mode}.png")
        gallery.close()
    return written


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    app = create_application()

    from . import diagnostics

    diagnostics.install()

    from .settings import Settings
    from .theme import Theme

    settings = Settings()
    root = resolve_workspace(args.workspace, settings.last_workspace())
    if args.screenshot is not None:
        for path in capture_screenshots(app, args.screenshot, root):
            print(path)
        return 0

    theme = Theme(app, args.theme or settings.theme_mode())
    if args.gallery:
        from .gallery import Gallery

        window = Gallery(theme)
    else:
        from .main_window import MainWindow

        window = MainWindow(theme, settings, root)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
