"""Entry point of HDD Studio Desktop (``hdd-studio``)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import QApplication

from . import APP_ID, APP_NAME, ORGANIZATION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME}: desktop environment for hybrid domain decomposition.")
    parser.add_argument("--theme", choices=("system", "light", "dark"), help="override the saved theme for this session")
    parser.add_argument("--gallery", action="store_true", help="open the widget gallery instead of the main window")
    parser.add_argument(
        "--screenshot",
        metavar="DIR",
        type=Path,
        help="write PNG captures of the main window and the gallery in both themes to DIR, then exit",
    )
    return parser


def create_application(argv: list[str] | None = None) -> QApplication:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    app = QApplication(argv if argv is not None else sys.argv[:1])
    app.setOrganizationName(ORGANIZATION)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName(APP_ID)
    return app


def capture_screenshots(app: QApplication, directory: Path) -> list[Path]:
    """Render the main window and the gallery in both themes; return the files written."""
    from .gallery import Gallery
    from .main_window import MainWindow
    from .settings import Settings
    from .theme import Theme

    directory.mkdir(parents=True, exist_ok=True)
    theme = Theme(app, "light")
    written: list[Path] = []

    def settle() -> None:
        for _ in range(6):
            app.processEvents()

    def save(widget, name: str) -> None:
        path = directory / name
        if not widget.grab().save(str(path)):
            raise OSError(f"could not write {path}")
        written.append(path)

    for mode in ("light", "dark"):
        theme.apply(mode)
        window = MainWindow(theme, Settings.ephemeral())
        window.resize(1440, 900)
        window.show()
        settle()
        for kind, view in (("coarsening", "sparsity"), ("partitioning", "sparsity"), ("run", "locality")):
            window.select_node(kind)
            window.graphics.show_view(view)
            settle()
            save(window, f"main-{kind}-{mode}.png")
        window.close()

        gallery = Gallery(theme)
        gallery.resize(1180, 860)
        gallery.show()
        settle()
        gallery.content.adjustSize()
        settle()
        save(gallery.content, f"gallery-{mode}.png")
        gallery.close()
    return written


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    app = create_application()

    if args.screenshot is not None:
        for path in capture_screenshots(app, args.screenshot):
            print(path)
        return 0

    from .settings import Settings
    from .theme import Theme

    settings = Settings()
    theme = Theme(app, args.theme or settings.theme_mode())
    if args.gallery:
        from .gallery import Gallery

        window = Gallery(theme)
    else:
        from .main_window import MainWindow

        window = MainWindow(theme, settings)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
