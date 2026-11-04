import re
from urllib.parse import parse_qs, urljoin, urlsplit

from sentinel.errors import SourceError

ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}")
_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}")
_PATH = re.compile(r"/Archives/edgar/data/([1-9][0-9]{0,9})/([0-9]{18})/([^/]+)")


def schema_error(reason: str = "SEC_SCHEMA") -> SourceError:
    return SourceError("SOURCE_UNAVAILABLE", reason=reason)


def canonical_cik(cik: object) -> str:
    if not isinstance(cik, str) or re.fullmatch(r"[0-9]{1,10}", cik) is None or int(cik) == 0:
        raise schema_error()
    return cik.zfill(10)


def safe_filename(name: object) -> bool:
    return isinstance(name, str) and _FILE.fullmatch(name) is not None and ".." not in name


def directory(cik: str, accession: str) -> str:
    cik = canonical_cik(cik)
    if _ACCESSION.fullmatch(accession) is None:
        raise schema_error()
    return f"{ARCHIVE_BASE}/{int(cik)}/{accession.replace('-', '')}/"


def document_url(cik: str, accession: str, file_name: str) -> str:
    if not safe_filename(file_name):
        raise schema_error("SEC_UNSAFE_URL")
    return directory(cik, accession) + file_name


def validate_archive_url(url: str, *, expected_directory: str | None = None) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        raise schema_error("SEC_UNSAFE_URL") from None
    if (
        parts.scheme != "https"
        or parts.netloc != "www.sec.gov"
        or parts.query
        or parts.fragment
        or any(ord(char) < 33 or ord(char) > 126 for char in url)
    ):
        raise schema_error("SEC_UNSAFE_URL")
    match = _PATH.fullmatch(parts.path)
    if match is None or not safe_filename(match[3]):
        raise schema_error("SEC_UNSAFE_URL")
    if expected_directory is not None and not url.startswith(expected_directory):
        raise schema_error("SEC_UNSAFE_URL")
    return url


def resolve_link(base_url: str, href: str) -> str:
    # urljoin 会抹掉 ../，因此先拒绝可被归并的路径与编码，之后再核对目录。
    base = urlsplit(base_url)
    base_directory = base_url if base.path.endswith("/") else base_url.rsplit("/", 1)[0] + "/"
    validate_archive_url(base_directory + "validation.htm")
    if not href or any(ord(char) < 33 or ord(char) > 126 for char in href) or "\\" in href:
        raise schema_error("SEC_UNSAFE_URL")
    raw = urlsplit(href)
    if raw.scheme and raw.scheme != "https":
        raise schema_error("SEC_UNSAFE_URL")
    if raw.netloc and raw.netloc != "www.sec.gov":
        raise schema_error("SEC_UNSAFE_URL")
    if raw.path in {"/ix", "/ixviewer/ix.html", "/ixviewer/doc/action"}:
        query = parse_qs(raw.query, keep_blank_values=True)
        if set(query) != {"doc"} or len(query["doc"]) != 1 or raw.fragment:
            raise schema_error("SEC_UNSAFE_URL")
        href = query["doc"][0]
        if not href.startswith("/Archives/edgar/data/"):
            raise schema_error("SEC_UNSAFE_URL")
    if "%" in href or any(segment in {".", ".."} for segment in urlsplit(href).path.split("/")):
        raise schema_error("SEC_UNSAFE_URL")
    return validate_archive_url(urljoin(base_url, href), expected_directory=base_directory)
