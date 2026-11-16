"""
layout.py - what every page's frame shows: the nav's sections and their tabs, and how old the
account is. Jinja's `base.html` and the Vue layout both draw it, so the menu is defined once.

The pages are moving to Inertia one at a time: a link to one that has (`INERTIA_PAGES`, the
Vue side's `PageLink` reads them) is an Inertia visit, any other a full page load (an Inertia
visit answered with plain HTML would open it in Inertia's error dialog).

- `INERTIA_PAGES`: the paths Inertia serves, as patterns (JavaScript's regex syntax too)
- `NavTab`, `NavSection`, `Layout`: the views
- `layout_view`: the frame for a page at a path
- `nav_sections`: the menu
"""

from dataclasses import dataclass

INERTIA_PAGES = (
    r"^/$",
    r"^/info$",
    r"^/empower$",
    r"^/config$",
    r"^/champions/\d+$",
    r"^/teams$",
    r"^/chimera$",
    r"^/team-gear$",
)


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

    @property
    def current(self) -> bool:
        return any(tab.current for tab in self.tabs)


@dataclass(frozen=True)
class Layout:
    sections: tuple[NavSection, ...]
    synced_ago: str
    inertia_pages: tuple[str, ...] = INERTIA_PAGES


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
                ("/chimera", "Chimera", path.startswith("/chimera")),
                ("/team-gear", "Gear", path.startswith("/team-gear")),
            ),
        ),
        (
            "Info",
            "/info",
            (
                ("/info", "Faction Wars", path == "/info"),
                ("/empower", "Empower", path.startswith("/empower")),
            ),
        ),
    )
    return tuple(
        NavSection(label, link, tuple(NavTab(*tab) for tab in tabs)) for label, link, tabs in menu
    )
