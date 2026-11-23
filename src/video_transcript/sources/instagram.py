import re
from urllib.parse import SplitResult

from ..types import Source

HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}


def parse(url: SplitResult) -> Source:
    match = re.fullmatch(r"/(?:(?:[\w.]+/)?(p|reel|reels|tv))/([\w-]+)/?", url.path, re.ASCII)
    if not match:
        raise ValueError("Invalid Instagram post URL")
    kind = "reel" if match[1] == "reels" else match[1]
    return Source("instagram", match[2], f"https://www.instagram.com/{kind}/{match[2]}/")
