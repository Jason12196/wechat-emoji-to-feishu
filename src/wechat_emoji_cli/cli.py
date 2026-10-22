"""Unified CLI boundary. Engine stdout is isolated from the NDJSON protocol."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

from . import __version__
from .engines import config
from .state import Task, write_private


class CommandError(Exception):
    def __init__(self, code, message, exit_code=2):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def parser():
    p = argparse.ArgumentParser(
        prog="wechat-emoji", description="WeChat emoji export and Feishu import"
    )
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--json", action="store_true", help="Emit protocol v1 NDJSON events on stdout")
    p.add_argument("--home", help="Private CLI state directory")
    p.add_argument("--wechat-root", help="Override xwechat_files directory")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Read-only dependency and runtime diagnostics")
    sub.add_parser("accounts", help="List local WeChat accounts (no decryption)")
    key = sub.add_parser("key", help="Explicitly obtain a key using a signed WeChat copy")
    key.add_argument("--wxid")
    key.add_argument("--force", action="store_true")
    key.add_argument("--timeout", type=int, default=180)
    extract = sub.add_parser("extract", help="Export, recover, validate and prepare emojis")
    extract.add_argument("--wxid")
    extract.add_argument("--out", required=True)
    extract.add_argument("--no-prepare", action="store_true")
    images = sub.add_parser("images").add_subparsers(dest="action", required=True)
    for name in ("inspect", "prepare"):
        ip = images.add_parser(name)
        ip.add_argument("directory")
        if name == "prepare":
            ip.add_argument("--out", required=True)
    feishu = sub.add_parser("feishu").add_subparsers(dest="action", required=True)
    login = feishu.add_parser("login", help="Open the browser for a named account profile")
    login.add_argument("--account", required=True)
    for name in ("plan", "import"):
        fp = feishu.add_parser(name)
        fp.add_argument("directory")
        fp.add_argument(
            "--account", required=True, help="Named local profile; verify the actual login matches"
        )
        fp.add_argument("--mode", choices=["personal", "enterprise"], default="personal")
        fp.add_argument(
            "--existing-count",
            type=int,
            help="Current personal sticker count, required for personal mode",
        )
        fp.add_argument(
            "--limit", type=int, help="Explicitly select the first N sorted valid files"
        )
        fp.add_argument("--pack-name", default="微信表情包")
        fp.add_argument("--ledger", help="Resume an existing ledger for the SAME account")
        if name == "import":
            fp.add_argument("--batch-size", type=int, default=10)
    tasks = sub.add_parser("tasks").add_subparsers(dest="action", required=True)
    tasks.add_parser("list")
    show = tasks.add_parser("show")
    show.add_argument("id")
    return p


def selected(directory, limit=None):
    from .engines.files import collect_emoji_files
    from .engines.macos_resources import decode

    if limit is not None and limit < 1:
        raise CommandError("INVALID_LIMIT", "--limit must be positive")
    try:
        files = collect_emoji_files(directory)
    except ValueError as exc:
        raise CommandError("DIRECTORY_NOT_FOUND", str(exc)) from exc
    files = files[:limit] if limit else files
    valid, invalid = [], []
    for name in files:
        try:
            fmt, size, frames = decode(Path(name).read_bytes())
            valid.append(
                {
                    "file": name,
                    "format": fmt,
                    "width": size[0],
                    "height": size[1],
                    "frames": frames,
                    "bytes": Path(name).stat().st_size,
                }
            )
        except Exception:
            invalid.append({"file": name, "code": "INVALID_IMAGE"})
    return valid, invalid


def ledger_state(args):
    if not args.ledger:
        return {}
    ledger = Path(args.ledger).expanduser().resolve()
    binding = ledger.with_suffix(".account.json")
    if not binding.is_file():
        raise CommandError("LEDGER_ACCOUNT_UNKNOWN", "Resume ledger has no account binding")
    if json.loads(binding.read_text()).get("account") != args.account:
        raise CommandError("LEDGER_ACCOUNT_MISMATCH", "Ledger belongs to another named account")
    if not ledger.is_file():
        raise CommandError("LEDGER_NOT_FOUND", "Resume ledger does not exist")
    return json.loads(ledger.read_text())


def plan(args):
    valid, invalid = selected(args.directory, args.limit)
    if not valid:
        raise CommandError("NO_VALID_IMAGES", "No decodable images were selected")
    previous = ledger_state(args)
    retained, unresolved, skipped = [], [], 0
    for item in valid:
        digest = hashlib.sha256(Path(item["file"]).read_bytes()).hexdigest()
        record = previous.get(digest)
        if record:
            skipped += 1
            if record.get("status") != "confirmed":
                unresolved.append({"file": item["file"], "status": record.get("status")})
        else:
            retained.append(item)
    oversize = [x["file"] for x in retained if x["bytes"] > config.FEISHU_EMOJI_MAX_SIZE_KB * 1024]
    if args.mode == "personal":
        if args.existing_count is None or not 0 <= args.existing_count <= 1000:
            raise CommandError(
                "CAPACITY_REQUIRED", "Personal mode requires --existing-count between 0 and 1000"
            )
        available = 1000 - args.existing_count
    else:
        available = None
        if args.ledger:
            raise CommandError(
                "ENTERPRISE_RESUME_UNSUPPORTED", "Enterprise automatic resume is not supported"
            )
    remainder = len(retained) % config.FEISHU_EMOJI_PACK_MAX
    enterprise_fits = len(retained) >= 6 and (remainder == 0 or remainder >= 6)
    fits = (
        (len(retained) <= available if available is not None else enterprise_fits)
        and not oversize
        and not invalid
        and not unresolved
    )
    return {
        "account": args.account,
        "mode": args.mode,
        "selected": len(retained),
        "input_count": len(valid),
        "skipped_recorded": skipped,
        "unresolved": unresolved,
        "available": available,
        "fits": fits,
        "invalid": invalid,
        "oversize": oversize,
        "files": [x["file"] for x in retained],
    }


def doctor():
    import shutil

    modules = {
        name: importlib.util.find_spec(name) is not None for name in ("PIL", "Crypto", "playwright")
    }
    from .engines.macos_backend import cli_path

    try:
        engine = cli_path()
        engine_ready = Path(engine).is_file()
    except RuntimeError:
        engine, engine_ready = None, False
    browsers = Path(config.PLAYWRIGHT_USER_DIR)
    chromium = browsers.is_dir() and any(browsers.glob("chromium-*"))
    return {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "modules": modules,
        "wechat_root_exists": Path(config.WECHAT_FILES_ROOT).is_dir(),
        "rust_cli": engine,
        "rust_cli_ready": engine_ready,
        "chromium_ready": chromium,
        "cargo_available": shutil.which("cargo") is not None,
        "ready": sys.platform == "darwin" and all(modules.values()) and engine_ready and chromium,
    }


def dispatch(args, task):
    if args.command == "doctor":
        return doctor()
    if args.command == "accounts":
        from .engines.macos_backend import accounts

        return {"accounts": accounts()}
    if args.command == "key":
        from .engines.macos_backend import run_cli

        task.emit(
            "action_required",
            action="wechat_login",
            message="Quit WeChat; log into the temporary copy and open the emoji panel.",
        )
        values = ["key", "--timeout", str(args.timeout)]
        if args.wxid:
            values += ["--wxid", args.wxid]
        if args.force:
            values += ["--force"]
        run_cli(values)
        return {"key_cached": True}  # Never expose the key through this CLI's protocol.
    if args.command == "extract":
        from .engines.macos_backend import extract

        files = extract(
            wxid=args.wxid,
            output_dir=str(Path(args.out).expanduser().resolve()),
            process=not args.no_prepare,
            progress_callback=task.progress,
        )
        report = Path(args.out).expanduser().resolve() / "export-report.json"
        return {
            "exported": len(files),
            "report": str(report),
            "files": files,
            "failed": json.loads(report.read_text()).get("failed", 0),
        }
    if args.command == "images":
        valid, invalid = selected(args.directory)
        if args.action == "inspect":
            return {
                "valid": len(valid),
                "invalid": len(invalid),
                "images": valid,
                "errors": invalid,
            }
        from .engines.macos_resources import decode, prepare

        out = Path(args.out).expanduser().resolve()
        if out == Path(args.directory).expanduser().resolve():
            raise CommandError(
                "OUTPUT_EQUALS_INPUT", "Prepare into a separate directory to preserve originals"
            )
        out.mkdir(parents=True, exist_ok=True)
        records = []
        for index, item in enumerate(valid, 1):
            source = Path(item["file"])
            try:
                value = prepare(source.read_bytes())
                fmt, _, _ = decode(value)
                ext = {"GIF": "gif", "PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[fmt]
                target = out / f"{source.stem}.{ext}"
                target.write_bytes(value)
                records.append({"file": target.name, "status": "ready", "bytes": len(value)})
            except Exception:
                records.append({"file": source.name, "status": "preparation_failed"})
            task.progress(index, len(valid), "Preparing images")
        report = {
            "total": len(valid) + len(invalid),
            "ready": sum(x["status"] == "ready" for x in records),
            "failed": sum(x["status"] != "ready" for x in records) + len(invalid),
            "files": records,
            "invalid": invalid,
        }
        write_private(out / "export-report.json", report)
        return report
    if args.command == "feishu":
        if args.action == "plan":
            return plan(args)
        if args.action == "import":
            prepared = plan(args)  # No browser starts before this check.
            if not prepared["fits"]:
                code = (
                    "CAPACITY_EXCEEDED"
                    if prepared["available"] is not None
                    and prepared["selected"] > prepared["available"]
                    else "IMPORT_PLAN_INVALID"
                )
                raise CommandError(
                    code,
                    json.dumps(
                        {k: v for k, v in prepared.items() if k != "files"}, ensure_ascii=False
                    ),
                )
            if not prepared["files"]:
                return {
                    "success": 0,
                    "skipped": prepared["skipped_recorded"],
                    "remaining": 0,
                    "unknown": 0,
                }
            if not 1 <= args.batch_size <= 50:
                raise CommandError("INVALID_BATCH_SIZE", "Batch size must be between 1 and 50")
        # A separate persistent browser profile per caller-selected account label.
        home = Path(config.DATA_DIR)
        profile = hashlib.sha256(args.account.encode()).hexdigest()[:24]
        config.configure(home=home / "profiles" / profile)
        from .engines.feishu_uploader import FeishuUploader

        task.emit(
            "action_required",
            action="feishu_login",
            account=args.account,
            message="Verify the browser is logged into the intended Feishu account; no chat messages are sent.",
        )
        with FeishuUploader(progress_callback=task.progress) as uploader:
            if not uploader.login():
                raise CommandError("LOGIN_TIMEOUT", "Feishu login did not complete", 1)
            if args.action == "login":
                return {"logged_in": True, "account_profile": args.account}
            if args.mode == "personal":
                from .engines.personal_import import upload

                ledger = (
                    Path(args.ledger).expanduser().resolve()
                    if args.ledger
                    else home / "imports" / f"{task.id}.json"
                )
                binding = ledger.with_suffix(".account.json")
                if ledger.exists() and not binding.exists():
                    raise CommandError(
                        "LEDGER_ACCOUNT_UNKNOWN", "Resume ledger has no account binding"
                    )
                if (
                    binding.exists()
                    and json.loads(binding.read_text()).get("account") != args.account
                ):
                    raise CommandError(
                        "LEDGER_ACCOUNT_MISMATCH", "Ledger belongs to another named account"
                    )
                write_private(binding, {"account": args.account})
                return upload(
                    uploader, prepared["files"], batch_size=args.batch_size, ledger_path=ledger
                )
            return uploader.upload_enterprise_emojis(prepared["files"], pack_name=args.pack_name)
    if args.command == "tasks":
        home = Path(config.DATA_DIR) / "tasks"
        if args.action == "list":
            return {"tasks": [json.loads(p.read_text()) for p in sorted(home.glob("*.json"))]}
        if not re.fullmatch(r"[a-f0-9-]{36}", args.id):
            raise CommandError("INVALID_TASK_ID", "Expected a UUID task identifier")
        p = home / f"{args.id}.json"
        if not p.is_file():
            raise CommandError("TASK_NOT_FOUND", "Task does not exist")
        return json.loads(p.read_text())
    raise CommandError("UNKNOWN_COMMAND", "Unknown command")


def main(argv=None):
    args = parser().parse_args(argv)
    config.configure(args.home, args.wechat_root)
    task = Task(config.DATA_DIR, args.command, args.json)
    try:
        # Legacy engines may print; JSON protocol owns stdout exclusively.
        with contextlib.redirect_stdout(sys.stderr):
            result = dispatch(args, task)
        partial = bool(result.get("failed") or result.get("unknown") or result.get("remaining"))
        task.finish(result, "partial" if partial else "complete")
        return 3 if partial else 0
    except KeyboardInterrupt:
        task.finish(
            {"message": "Cancelled; do not retry pending imports without reconciliation"},
            "cancelled",
            "CANCELLED",
        )
        return 130
    except CommandError as exc:
        task.finish({"message": str(exc)}, "failed", exc.code)
        return exc.exit_code
    except Exception as exc:
        task.finish({"message": str(exc)}, "failed", "ENGINE_ERROR")
        return 1
