import re
from urllib.parse import SplitResult

from ..types import Source

HOSTS = {"threads.com", "www.threads.com", "threads.net", "www.threads.net"}


def parse(url: SplitResult) -> Source:
    match = re.fullmatch(r"/(?:@[\w.]+/post|t|share)/([\w-]+)/?", url.path, re.ASCII)
    if not match:
        raise ValueError("Invalid Threads post URL")
    return Source("threads", match[1], f"https://{url.hostname}{url.path}")
