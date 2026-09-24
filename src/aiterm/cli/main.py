"""aiterm command line."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import List, Optional

from aiterm import __version__
from aiterm.ai.engine import AIEngine
from aiterm.analyzers.base import all_analyzers, known_extensions
from aiterm.core.config import DEFAULT_TOML, Config, load_config
from aiterm.core.engine import DiagnosticEngine
from aiterm.core.history import History
from aiterm.core.models import Diagnostic
from aiterm.core.monitor import Monitor
from aiterm.core.project import detect_project, find_root
from aiterm.core.watcher import is_relevant
from aiterm.notifications.manager import (DesktopSink, FileSink, NotificationManager, TerminalSink, render_box)
from aiterm.patches.manager import PatchError, PatchManager


def _ctx(args):
    root = find_root(Path(getattr(args, "path", None) or ".") if Path(getattr(args, "path", None) or ".").is_dir() else Path("."))
    cfg = load_config(root)
    return root, cfg


def _files(root: Path, cfg: Config, only: Optional[Path] = None) -> List[Path]:
    if only and only.is_file():
        return [only.resolve()]
    base = only.resolve() if only else root
    out = []
    for dp, dns, fns in os.walk(base):
        dns[:] = [d for d in dns if d not in cfg.ignore_dirs]
        out += [Path(dp, f) for f in fns if is_relevant(Path(dp, f), root, cfg.ignore_dirs)]
    return out


def _print_diag(d: Diagnostic, ai=None) -> None:
    print(render_box(d, ai))


def cmd_analyze(args) -> int:
    target = Path(args.path or ".")
    root, cfg = _ctx(args)
    eng = DiagnosticEngine(root, cfg)
    hist = History(root)
    ai = AIEngine(cfg.ai) if args.ai else None
    if ai:
        cfg.ai.enabled = True
    diags = eng.analyze_paths(_files(root, cfg, target))
    for d in diags:
        hist.record(d)
    if args.json:
        print(json.dumps([d.to_dict() for d in diags], indent=2))
    else:
        for d in sorted(diags, key=lambda d: (-d.rank, d.file, d.line)):
            res = ai.explain(d, root) if ai and d.rank >= 2 else None
            if res:
                hist.record_ai(d.id, res.to_dict())
            _print_diag(d, res)
        if ai and ai.last_error:
            print(f"\nAI unavailable: {ai.last_error}\nLocal diagnostics remain active.")
        print(f"\n{len(diags)} problem(s) found." if diags else "No problems found.")
    return 1 if any(d.severity in ("error", "critical") for d in diags) else 0


def cmd_watch(args, with_shell: bool = False) -> int:
    root, cfg = _ctx(args)
    info = detect_project(root, cfg.ignore_dirs)
    eng = DiagnosticEngine(root, cfg)
    sinks = []
    if cfg.notifications.terminal:
        sinks.append(TerminalSink(sys.stderr))
    if cfg.notifications.desktop:
        sinks.append(DesktopSink())
    sinks.append(FileSink(root / ".aiterm" / "notifications.log"))
    ai = AIEngine(cfg.ai)
    mon = Monitor(root, cfg, eng, NotificationManager(cfg.notifications, sinks), ai, History(root), info.languages)
    print(f"AI Terminal started.\n\nProject:\n{root}\n\nLanguages:\n{', '.join(info.languages) or '(none detected)'}\n")
    backend = "inotify (watchdog)" if cfg.watch_backend != "polling" and _has_watchdog() else "polling"
    print(f"Monitoring:\n✓ Files ({backend})\n✓ Compiler/linters\n✓ Terminal output\n"
          f"{'✓' if cfg.ai.enabled else '✗'} AI assistance"
          f"{'' if cfg.ai.enabled else ' (off - local diagnostics only)'}\n\nReady.\n")
    mon.start()
    try:
        if with_shell and sys.stdin.isatty():
            from aiterm.terminal.shell import run_shell
            return run_shell(mon.feed_output)
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0
    finally:
        mon.stop()


def _has_watchdog() -> bool:
    try:
        import watchdog  # noqa: F401
        return True
    except ImportError:
        return False


def cmd_run(args) -> int:
    from aiterm.terminal.shell import run_command
    root, cfg = _ctx(args)
    eng = DiagnosticEngine(root, cfg)
    sinks = [TerminalSink(sys.stderr), FileSink(root / ".aiterm" / "notifications.log")]
    mon = Monitor(root, cfg, eng, NotificationManager(cfg.notifications, sinks), AIEngine(cfg.ai), History(root))
    cmd = [c for c in args.command if c != "--"]
    if not cmd:
        print("usage: aiterm run -- <command>", file=sys.stderr)
        return 2
    rc = run_command(cmd, lambda t: mon.process_output_now(t))
    return rc


def cmd_doctor(args) -> int:
    root, cfg = _ctx(args)
    ok = lambda b: "✓" if b else "✗"
    print(f"aiterm {__version__} | Python {sys.version.split()[0]} | project: {root}")
    print(f"config: {cfg.source_path or '(defaults)'}\n")
    print("Language analyzers:")
    for a in all_analyzers():
        tool = getattr(a, "tool", "") or "built-in"
        print(f"  {ok(a.available())} {a.name:<11} {tool}")
    print(f"\n{ok(shutil.which('ruff'))} ruff (optional Python linter)")
    print(f"{ok(_has_watchdog())} watchdog (inotify events; else polling every {cfg.poll_interval}s)")
    print(f"{ok(shutil.which('notify-send'))} notify-send (desktop notifications)")
    print(f"{ok(shutil.which('git'))} git")
    a = cfg.ai
    print(f"\nAI: {'enabled' if a.enabled else 'disabled (local diagnostics only)'} | provider={a.provider} model={a.model or '-'}")
    if a.enabled and a.provider in ("gemini", "openai"):
        env = a.api_key_env or {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}[a.provider]
        print(f"  {ok(os.environ.get(env))} API key env var {env} {'is set' if os.environ.get(env) else 'is NOT set'}")
    return 0


def cmd_config(args) -> int:
    root, cfg = _ctx(args)
    target = root / "aiterm.toml"
    if args.init:
        if target.exists():
            print(f"{target} already exists; not overwriting.")
            return 1
        target.write_text(DEFAULT_TOML, encoding="utf-8")
        print(f"Wrote {target}")
        return 0
    from dataclasses import asdict
    print(json.dumps(asdict(cfg), indent=2))
    return 0


def cmd_history(args) -> int:
    root, _ = _ctx(args)
    entries = History(root).entries()[-args.limit:]
    if not entries:
        print("No history yet.")
    for e in entries:
        print(f'{e["id"]}  {e["timestamp"]}  {e["severity"]:<8} {e["file"]}:{e["line"]}  {e["message"][:70]}')
    return 0


def _lookup(args):
    root, cfg = _ctx(args)
    d = History(root).get(args.id)
    if not d:
        print(f"No problem with id '{args.id}'. See `aiterm history`.", file=sys.stderr)
        return root, cfg, None
    return root, cfg, d


def cmd_explain(args) -> int:
    root, cfg, d = _lookup(args)
    if not d:
        return 1
    ai = AIEngine(cfg.ai)
    res = ai.explain(d, root, detect_project(root, cfg.ignore_dirs).languages)
    if res:
        History(root).record_ai(d.id, res.to_dict())
    _print_diag(d, res)
    if not res:
        print(f"\nAI unavailable: {ai.last_error}\nLocal diagnostics remain active.")
    return 0


def cmd_fix(args) -> int:
    root, cfg, d = _lookup(args)
    if not d:
        return 1
    new_line, origin = d.fix_line, "deterministic fix"
    if new_line is None:
        ai = AIEngine(cfg.ai)
        res = ai.explain(d, root)
        if res and res.fixed_line:
            new_line, origin = res.fixed_line, f"AI suggestion (confidence {res.confidence:.0%}) - review carefully"
        else:
            print("No automatic fix available." + (f" ({ai.last_error})" if ai.last_error else ""))
            return 1
    pm = PatchManager(root)
    try:
        prop = pm.propose_line_fix(d.file, d.line, new_line, origin)
    except PatchError as e:
        print(f"Cannot build patch: {e}")
        return 1
    if not prop.diff:
        print("Nothing to change (already fixed?).")
        return 0
    print(f"AI Terminal proposes the following change ({origin}):\n\n{d.file}:{d.line}\n\n{prop.diff}")
    ans = input("[Apply] [Reject]  Apply this patch? [y/N] ").strip().lower() if sys.stdin.isatty() or args.stdin else "n"
    if ans not in ("y", "yes", "apply"):
        print("Rejected. No files were modified.")
        return 0
    try:
        backup = pm.apply(prop, approved=True)
    except PatchError as e:
        print(f"Not applied: {e}")
        return 1
    print(f"Applied. Backup: {backup}")
    remaining = DiagnosticEngine(root, cfg).analyze_file(root / d.file)
    print("Re-check: " + ("no problems remain in this file." if not remaining else f"{len(remaining)} problem(s) remain."))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aiterm", description="Continuous code-aware terminal with an AI debugging layer.")
    p.add_argument("--version", action="version", version=f"aiterm {__version__}")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("start", help="interactive shell + continuous monitoring (default)")
    sub.add_parser("watch", help="monitor only, print notifications (no shell)")
    a = sub.add_parser("analyze", help="analyze the project or one file once")
    a.add_argument("path", nargs="?", default=".")
    a.add_argument("--json", action="store_true")
    a.add_argument("--ai", action="store_true", help="add AI explanations for errors (needs [ai] configured)")
    r = sub.add_parser("run", help="run a command and analyse its output")
    r.add_argument("command", nargs=argparse.REMAINDER)
    sub.add_parser("doctor", help="check environment")
    c = sub.add_parser("config", help="show effective config, or --init")
    c.add_argument("--init", action="store_true")
    h = sub.add_parser("history")
    h.add_argument("-n", "--limit", type=int, default=20)
    e = sub.add_parser("explain")
    e.add_argument("id")
    f = sub.add_parser("fix")
    f.add_argument("id")
    f.add_argument("--stdin", action="store_true", help=argparse.SUPPRESS)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    cmd = args.cmd or "start"
    if not hasattr(args, "path"):
        args.path = "."
    try:
        return {"start": lambda a: cmd_watch(a, True), "watch": cmd_watch, "analyze": cmd_analyze, "run": cmd_run,
                "doctor": cmd_doctor, "config": cmd_config, "history": cmd_history, "explain": cmd_explain,
                "fix": cmd_fix}[cmd](args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
