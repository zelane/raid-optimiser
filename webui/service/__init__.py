"""
service - what the web pages show, as plain data: no HTML and no web framework, so a JSON API
(for a Vue front end, say) can return the same objects with `dataclasses.asdict`. A module per
page, over `current` (the state they read) and `views` (what they share).
"""
