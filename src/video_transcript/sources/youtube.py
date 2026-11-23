import re
from urllib.parse import parse_qs, SplitResult

from ..types import Source

HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def parse(url: SplitResult) -> Source:
    if url.hostname == "youtu.be":
        identifier = url.path.strip("/")
    elif url.path == "/watch":
        values = parse_qs(url.query).get("v", [])
        identifier = values[0] if len(values) == 1 else ""
    else:
        match = re.fullmatch(r"/(?:shorts|live|embed)/([^/]+)/?", url.path)
        identifier = match[1] if match else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", identifier):
        raise ValueError("Invalid YouTube video ID")
    return Source("youtube", identifier, f"https://www.youtube.com/watch?v={identifier}")
