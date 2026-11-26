import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .store import Store


def resolve_index_dir(repo, db):
    return Path(db).resolve() if db else Path(repo).resolve() / ".codectx"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="codectx", description="Local symbol search and graph context"
    )
    parser.add_argument("-V", "--version", action="version", version=f"codectx {__version__}")
    subs = parser.add_subparsers(dest="command")
    p = subs.add_parser("doctor")
    p.add_argument("--repo")
    p.add_argument("--db")
    p.add_argument("--json", action="store_true")
    for command in ("index", "symbols", "search", "embed", "graph", "context", "coverage"):
        p = subs.add_parser(command)
        if command == "symbols":
            p.add_argument("file")
            p.add_argument("--json", action="store_true")
        if command in {"search", "context"}:
            p.add_argument("query")
            p.add_argument("-k", type=int, default=10)
        if command == "graph":
            p.add_argument("symbol")
            group = p.add_mutually_exclusive_group()
            for kind in (
                "callers",
                "callees",
                "subtypes",
                "supertypes",
                "overrides",
                "overridden-by",
            ):
                group.add_argument("--" + kind, action="store_true")
        p.add_argument(
            "repo", **({} if command in {"index", "embed"} else {"nargs": "?", "default": "."})
        )
        p.add_argument("--db")
        if command in {"index", "embed"}:
            p.add_argument("--force", action="store_true")
        if command == "index":
            p.add_argument("--stats", action="store_true")
            p.add_argument(
                "--bodies", action="store_true", help="index source passages for body search"
            )
        if command == "search":
            p.add_argument(
                "--mode", choices=("lexical", "semantic", "hybrid", "body"), default="lexical"
            )
        if command in {"graph", "context"}:
            p.add_argument("--depth", type=int, default=1)
        if command == "context":
            p.add_argument("--tokens", type=int, default=8000)
            p.add_argument("--mode", choices=("hybrid", "body"), default="hybrid")
        if command == "coverage":
            p.add_argument("--sample", type=int, default=100)
    return parser


def dispatch(args):
    if args.command == "doctor":
        from .doctor import diagnose

        report = diagnose(args.repo, args.db)
        print(json.dumps(report.to_dict(), indent=2) if args.json else report.to_text())
        return report.exit_code
    root = Path(args.repo).resolve()
    path = resolve_index_dir(root, args.db)
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")
    if args.command != "index" and not (path / "manifest.json").exists():
        raise RuntimeError(f"No index at {path}. Run `codectx index {root}` first.")
    if getattr(args, "k", 1) < 1 or getattr(args, "depth", 0) < 0:
        raise ValueError("k must be positive and depth nonnegative")
    writable = args.command in {"index", "embed"}
    if getattr(args, "mode", None) == "body":
        return _print_passages(args, path)
    if writable:
        from filelock import FileLock

        path.mkdir(parents=True, exist_ok=True)
        with FileLock(path / ".writer.lock"):
            return _dispatch_store(args, root, path, writable)
    return _dispatch_store(args, root, path, writable)


def _print_passages(args, path):
    from .body import search_bodies

    budget = args.tokens * 4 if args.command == "context" else None
    if budget is not None and budget < 4:
        raise ValueError("Token budget must be positive")
    printed = 0
    for hit in search_bodies(path, args.query, args.k):
        owner = f"  {hit.scope}" if hit.scope else ""
        block = f"## {hit.path}:{hit.start_line}-{hit.end_line}{owner}\n```\n{hit.body}\n```\n\n"
        if budget is not None:
            if len(block) > budget:
                continue
            budget -= len(block)
        print(block, end="")
        printed += 1
    if not printed:
        print(
            "No matching passage fits." if budget is not None else "No matches.",
            file=sys.stderr,
        )
    return 0 if printed else 1


def _dispatch_store(args, root, path, writable):
    ref_kinds = None
    if (
        args.command in {"embed", "symbols"}
        or args.command == "search"
        and args.mode in {"lexical", "semantic"}
    ):
        ref_kinds = set()
    elif args.command == "search":
        ref_kinds = {"extends", "implements", "anonymous_base"}
    store = Store(
        path,
        root,
        readonly=not writable,
        recover=args.command == "index" and args.force,
        ref_kinds=ref_kinds,
    )
    if args.command == "index":
        from .index import index_files

        if args.force:
            store.clear()
        stats = index_files(store, root, bodies=args.bodies, rebuild_bodies=args.force)
        if args.stats:
            print(json.dumps({**stats.to_dict(), **store.stats()}))
        else:
            print(
                f"Indexed {root}: {stats.indexed_files} new, {stats.reindexed} changed, {stats.unchanged} unchanged, {stats.code_files} code files.\nIndex: {path}"
            )
    elif args.command == "symbols":
        file = Path(args.file)
        rel = (root / file).resolve().relative_to(root).as_posix()
        symbols = store.symbols_for_file(rel)
        if args.json:
            print(json.dumps([s.to_dict() for s in symbols]))
        else:
            for s in symbols:
                print(
                    f"{s.kind:<10} {s.start_line:>5}-{s.end_line:<5} {s.name}  {s.signature or ''}"
                    + (" [parse-error]" if not s.parse_ok else "")
                )
        return 0 if symbols else 1
    elif args.command == "embed":
        from .semantic import _env_model_name, embed_symbols

        if (
            not args.force
            and store.get_meta("vector_model_id") == _env_model_name()
            and store.get_meta("vector_fingerprint") == store.fingerprint()
        ):
            print("Embeddings already current.")
            return 0
        n = embed_symbols(store, [s for s in store.all_symbols() if s.parse_ok])
        store.commit()
        print(f"Embedded {n} symbols with {_env_model_name()}.")
    elif args.command == "search":
        from importlib import import_module

        module, func = {
            "lexical": ("search", "search_lexical"),
            "semantic": ("semantic", "search_semantic"),
            "hybrid": ("hybrid", "search_hybrid"),
        }[args.mode]
        hits = getattr(import_module("." + module, __package__), func)(store, args.query, args.k)
        for hit in hits:
            s = store.symbol_by_id(hit.symbol_id)
            ranks = ""
            if args.mode == "hybrid":
                ranks = f" [L{hit.lexical_rank + 1 if hit.lexical_rank is not None else '-'}+S{hit.semantic_rank + 1 if hit.semantic_rank is not None else '-'}]"
            print(
                f"{hit.score:8.5f}  {s.kind:<10} {s.file_path}:{s.start_line} {s.qualified_name}{ranks}"
            )
        if not hits:
            print("No matches.", file=sys.stderr)
            return 1
    elif args.command == "graph":
        from . import graph

        s = graph.resolve_symbol(store, args.symbol)
        print(f"# {s.qualified_name} ({s.kind}, {s.file_path}:{s.start_line})")
        operations = [
            kind
            for kind in (
                "callers",
                "callees",
                "supertypes",
                "subtypes",
                "overrides",
                "overridden_by",
            )
            if getattr(args, kind)
        ]
        if not operations:
            operations = ["callees", "callers"] + (
                ["supertypes", "subtypes"] if s.kind == "class" else []
            )
        for kind in operations:
            print("## " + kind)
            hops = getattr(graph, kind)(store, s.id, args.depth)
            for hop in hops:
                target = hop.target
                citation = (
                    f"{target.file_path}:{target.start_line} {target.qualified_name}"
                    if target
                    else hop.ref.source_qualifier
                    if kind in {"callers", "subtypes"}
                    else hop.ref.target_qualified or hop.ref.target_name
                )
                ref = hop.ref
                site = f"{ref.file_path}:{ref.line}"
                detail = ", ".join(
                    filter(
                        None,
                        [
                            ref.evidence if ref.evidence != ref.resolution_kind else None,
                            f"receiver={ref.receiver}" if ref.receiver else None,
                            f"type={ref.receiver_type}" if ref.receiver_type else None,
                        ],
                    )
                )
                print(
                    f"  {ref.kind:<10} {citation} [{ref.resolution_kind}, {ref.candidate_count} candidates] at {site}"
                    + (f" ({detail})" if detail else "")
                )
            if not hops:
                print("  (none)")
    elif args.command == "context":
        from .context import build_context

        pack = build_context(
            store, args.query, root=root, token_budget=args.tokens, graph_depth=args.depth, k=args.k
        )
        print(pack.text, end="")
        print(
            f"--- {pack.symbol_count} symbols, ~{pack.token_estimate} tokens, truncated={pack.truncated}, sources={pack.sources} ---",
            file=sys.stderr,
        )
        return 0 if pack.symbol_count else 1
    elif args.command == "coverage":
        from dataclasses import asdict

        from .rg_tools import differential_coverage

        gaps = differential_coverage(store, root, args.sample)
        print(json.dumps([asdict(gap) for gap in gaps], indent=2))
        return int(bool(gaps))
    return 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return 2
    try:
        return dispatch(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, KeyError) as e:
        print(f"codectx: error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
