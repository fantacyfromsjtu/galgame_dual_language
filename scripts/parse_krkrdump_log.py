import csv
import re
import sys
from pathlib import Path


HASH_RE = re.compile(r'"file://\./(?:[a-z]/)?(?:.*?/)?([^/\\]+\.xp3)>([0-9a-fA-F]{32}|\$)"')
ARCHIVE_RE = re.compile(r'"archive://([^/\\]+\.xp3)/(.+?)"')


def parse_log(path: Path):
    pending = {}
    rows = []

    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        hash_match = HASH_RE.search(line)
        if hash_match:
            archive = hash_match.group(1)
            digest = hash_match.group(2)
            pending[archive.lower()] = (archive, digest, line_no)
            continue

        archive_match = ARCHIVE_RE.search(line)
        if not archive_match:
            continue

        archive = archive_match.group(1)
        logical_path = archive_match.group(2)
        item = pending.get(archive.lower())
        if not item:
            continue

        pending_archive, digest, hash_line = item
        rows.append(
            {
                "archive": pending_archive,
                "hash": digest,
                "path": logical_path,
                "hash_line": hash_line,
                "path_line": line_no,
            }
        )

    unique = {}
    for row in rows:
        key = (row["archive"].lower(), row["hash"].lower(), row["path"])
        unique[key] = row

    return list(unique.values())


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: parse_krkrdump_log.py <KrkrDump.log> <out.csv>")

    log_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    rows = parse_log(log_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["archive", "hash", "path", "hash_line", "path_line"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} mappings to {out_path}")


if __name__ == "__main__":
    main()
