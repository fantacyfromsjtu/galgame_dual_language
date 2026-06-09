import argparse
import shutil
import subprocess
from pathlib import Path


TOOL_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path.cwd()


def assert_safe_clean_path(path: Path):
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
        raise ValueError(f"Refusing to delete unsafe output directory: {resolved}")


def run_decompile(files, output_dir, freemote_dir):
    exe = freemote_dir / "PsbDecompile.exe"
    if not exe.exists():
        raise FileNotFoundError(exe)
    output_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    for index, path in enumerate(files, start=1):
        print(f"[{index}/{len(files)}] decompile {path.name}")
        result = subprocess.run(
            [str(exe), "-t", "Scn", "-o", str(output_dir), str(path)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            failures.append((path, result.stdout))
            print(result.stdout)
    if failures:
        print("Decompile failures:")
        for path, output in failures:
            print(f"  {path}")
            print(output)
        raise SystemExit(1)


def run_build(files, output_dir, freemote_dir):
    exe = freemote_dir / "PsBuild.exe"
    if not exe.exists():
        raise FileNotFoundError(exe)
    output_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    for index, path in enumerate(files, start=1):
        out_name = path.name
        if out_name.endswith(".scn.json"):
            out_name = out_name[:-5]
        elif out_name.endswith(".ks.json"):
            out_name = out_name[:-5] + ".scn"
        elif out_name.endswith(".json"):
            out_name = out_name[:-5] + ".scn"
        out_path = output_dir / out_name
        print(f"[{index}/{len(files)}] build {path.name} -> {out_path.name}")
        result = subprocess.run(
            [str(exe), "-p", "krkr", "-o", str(out_path), str(path)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0 or not out_path.exists():
            failures.append((path, result.stdout))
            print(result.stdout)
    if failures:
        print("Build failures:")
        for path, output in failures:
            print(f"  {path}")
            print(output)
        raise SystemExit(1)


def collect_files(input_dir, suffix):
    return sorted([path for path in input_dir.iterdir() if path.is_file() and path.name.endswith(suffix)], key=lambda p: p.name)


def main():
    parser = argparse.ArgumentParser(description="Batch decompile/build FreeMote scenario files.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_decompile = sub.add_parser("decompile")
    p_decompile.add_argument("--input-dir", required=True)
    p_decompile.add_argument("--output-dir", required=True)
    p_decompile.add_argument("--suffix", default=".ks.scn")
    p_decompile.add_argument("--freemote-dir", default=str(TOOL_ROOT / "tools" / "FreeMote"))
    p_decompile.add_argument("--clean", action="store_true")

    p_build = sub.add_parser("build")
    p_build.add_argument("--input-dir", required=True)
    p_build.add_argument("--output-dir", required=True)
    p_build.add_argument("--suffix", default=".ks.json")
    p_build.add_argument("--freemote-dir", default=str(TOOL_ROOT / "tools" / "FreeMote"))
    p_build.add_argument("--clean", action="store_true")

    args = parser.parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    freemote_dir = Path(args.freemote_dir)

    if args.clean and output_dir.exists():
        assert_safe_clean_path(output_dir)
        shutil.rmtree(output_dir)

    files = collect_files(input_dir, args.suffix)
    print(f"Found {len(files)} files in {input_dir}")
    if not files:
        raise SystemExit(1)

    if args.command == "decompile":
        run_decompile(files, output_dir, freemote_dir)
    else:
        run_build(files, output_dir, freemote_dir)


if __name__ == "__main__":
    main()
