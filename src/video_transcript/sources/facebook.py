import re
from urllib.parse import parse_qs, SplitResult

from ..types import Source

HOSTS = {"facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch", "www.fb.watch"}


def parse(url: SplitResult) -> Source:
    host = url.hostname
    if host in {"fb.watch", "www.fb.watch"}:
        match = re.fullmatch(r"/([\w-]+)/?", url.path, re.ASCII)
        if match:
            return Source("facebook", match[1], f"https://fb.watch/{match[1]}/")
    else:
        if url.path.rstrip("/") in {"/watch", "/video.php"}:
            values = parse_qs(url.query).get("v", [])
            if len(values) == 1 and re.fullmatch(r"[0-9]+", values[0]):
                return Source("facebook", values[0], f"https://www.facebook.com/watch/?v={values[0]}")
        patterns = (
            r"/(?:reel|reels|videos|share/(?:v|r|p))/([\w-]+)/?",
            r"/[\w.-]+/(?:videos|posts)/([\w-]+)/?",
            r"/[\w.-]+/videos/[\w.-]+/([\w-]+)/?",
        )
        for pattern in patterns:
            match = re.fullmatch(pattern, url.path, re.ASCII)
            if match:
                return Source("facebook", match[1], f"https://www.facebook.com{url.path}")
    raise ValueError("Invalid Facebook video URL")
