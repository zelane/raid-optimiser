"""
layout.py - what every page's frame shows (the Vue layout, `AppLayout.vue`): the nav's
sections and their tabs, and how old the account is.

- `NavTab`, `NavSection`, `Layout`: the views
- `layout_view`: the frame for a page at a path
- `nav_sections`: the menu
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NavTab:
    link: str
    label: str
    current: bool


@dataclass(frozen=True)
class NavSection:
    """A menu entry: its own link, and the pages under it (tabs in the band under the bar when
    there are several)."""

    label: str
    link: str
    tabs: tuple[NavTab, ...]


@dataclass(frozen=True)
class Layout:
    sections: tuple[NavSection, ...]
    synced_ago: str


def layout_view(path: str, optimiser_link: str, synced_ago: str) -> Layout:
    return Layout(nav_sections(path, optimiser_link), synced_ago)


def nav_sections(path: str, optimiser_link: str) -> tuple[NavSection, ...]:
    """Optimiser: the champion list, the champion last solved for (their optimiser), the
    settings solves use; Accessories; Teams: the team finder, the Chimera's trials, a team's
    gear; Info: the account's progress."""
    menu = (
        (
            "Optimiser",
            "/",
            (
                ("/", "Champions", path == "/"),
                (optimiser_link, "Optimiser", path.startswith("/champions/")),
                ("/config", "Config", path == "/config"),
            ),
        ),
        (
            "Accessories",
            "/accessories",
            (("/accessories", "Accessories", path.startswith("/accessories")),),
        ),
        (
            "Teams",
            "/teams",
            (
                ("/teams", "Finder", path.startswith("/teams")),
                ("/team-gear", "Gear", path.startswith("/team-gear")),
            ),
        ),
        (
            "Info",
            "/info",
            (
                ("/info", "Faction Wars", path == "/info"),
                ("/empower", "Empower", path.startswith("/empower")),
                ("/masteries", "Masteries", path.startswith("/masteries")),
            ),
        ),
    )
    return tuple(
        NavSection(label, link, tuple(NavTab(*tab) for tab in tabs)) for label, link, tabs in menu
    )
