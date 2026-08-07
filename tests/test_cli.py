from pathlib import Path

from python_deep_search.cli import build_parser


def test_default_sites_path_exists() -> None:
    args = build_parser().parse_args(["needle"])

    assert Path(args.sites).exists()


def test_browser_argument_is_available_for_open() -> None:
    args = build_parser().parse_args(["needle", "--open", "--browser", "firefox"])

    assert args.open is True
    assert args.browser == "firefox"
