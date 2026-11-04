"""Extract a verified W-03 source archive with Unicode-safe Windows paths."""

import sys
import tarfile
from pathlib import Path, PurePosixPath

_UNUSED_DUCKDB_LINKS = frozenset(
    {
        "duckdb-1.4.3/data/csv/glob/crawl/.symbolic_link/link_to_file",
        "duckdb-1.4.3/data/csv/glob/crawl/.symbolic_link/mydir/link_to_upper_dir",
    }
)


def extract(archive: Path, destination: Path, root: str) -> None:
    if (destination / root).exists():
        raise ValueError("source destination already exists")
    with tarfile.open(archive, "r:gz") as source:
        members = []
        seen = set()
        for member in source.getmembers():
            name = member.name
            path = PurePosixPath(name)
            if (
                not path.parts
                or path.parts[0] != root
                or ".." in path.parts
                or "\\" in name
                or ":" in name
                or name in seen
            ):
                raise ValueError("unexpected source archive member")
            seen.add(name)
            if member.issym() and name in _UNUSED_DUCKDB_LINKS:
                continue
            if not (member.isdir() or member.isfile()):
                raise ValueError("unexpected source archive member type")
            members.append(member)
        source.extractall(destination, members=members, filter="data")


if __name__ == "__main__":
    extract(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
