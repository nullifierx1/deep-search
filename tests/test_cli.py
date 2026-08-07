from pathlib import Path

from python_deep_search.cli import build_parser


def test_default_sites_path_exists() -> None:
    args = build_parser().parse_args(["needle"])

    assert Path(args.sites).exists()
