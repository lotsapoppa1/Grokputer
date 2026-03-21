#!/usr/bin/env python3
"""
grokputer_main.py - Scarlett Powerhouse AI Assistant
Full autonomy, 28+ working tools, LADY/TRAMP modes, startup preflight,
agentic tool-calling chat loop, memory persistence, structured logging.
"""

import os
import sys
import json
import time
import logging
import datetime
import platform
import subprocess
import smtplib
import imaplib
import email
import email.mime.text
import email.mime.multipart
import sqlite3
import shutil
import glob as glob_module
import re
import traceback
import inspect
import ast
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── LOGGING SETUP ──────────────────────────────────────────────────────────

LOG_FILE = Path("scarlett.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("scarlett")

# ─── CONSTANTS ───────────────────────────────────────────────────────────────

VERSION = "2.0.0"
MEMORY_FILE = Path("memory.json")
SCREENSHOTS_DIR = Path("screenshots")
DB_FILE = Path("scarlett.db")
SELF_PATH = Path(__file__).resolve()

# Config search paths (Windows user path first, then local)
CONFIG_PATHS = [
    Path(r"C:\Users\lotsa\Documents\ScarlettProject\scarlett_config_updated.json"),
    Path("./scarlett_config_updated.json"),
    Path("./scarlett_config.json"),
]

# ─── CONFIG TEMPLATE ────────────────────────────────────────────────────────

CONFIG_TEMPLATE = {
    "xai_api_key": "xai_YOUR_KEY_HERE",
    "xai_model": "grok-3-fast",
    "xai_base_url": "https://api.x.ai/v1",
    "proton_email": "lotsapoppa1@proton.me",
    "proton_password": "YOUR_PROTON_BRIDGE_PASSWORD",
    "proton_smtp_host": "localhost",
    "proton_smtp_port": 1025,
    "proton_imap_host": "localhost",
    "proton_imap_port": 1143,
    "github_token": "ghp_YOUR_TOKEN_HERE",
    "github_username": "lotsapoppa1",
    "autonomy_mode": True,
    "default_mode": "lady",
    "max_tool_iterations": 20,
    "assistant_name": "Scarlett",
    "assistant_tone": "warm, proactive, decisive, loyal, powerful",
    "assistant_style": (
        "Take action immediately when the task is clear. "
        "Use tools directly. Execute multi-step tasks end-to-end."
    ),
}

# ─── CONFIG LOADING ──────────────────────────────────────────────────────────


def _mask(value: str) -> str:
    """Return a partially-masked credential string for display."""
    if not value or len(value) < 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def load_config() -> Dict[str, Any]:
    """
    Load config from prioritised paths.
    Environment variables override file values (XAI_API_KEY, GITHUB_TOKEN, etc.).
    If no config file is found, write a template and exit.
    """
    cfg: Dict[str, Any] = {}

    for path in CONFIG_PATHS:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    cfg = json.load(fh)
                log.info("Config loaded from: %s", path)
                break
            except Exception as exc:
                log.warning("Failed to load %s: %s", path, exc)

    if not cfg:
        template_path = Path("./scarlett_config.json")
        with open(template_path, "w", encoding="utf-8") as fh:
            json.dump(CONFIG_TEMPLATE, fh, indent=2)
        print(
            "\n⚠️  No config file found.\n"
            f"   A template has been written to: {template_path.resolve()}\n"
            "   Fill in your credentials and re-run.\n"
        )
        sys.exit(1)

    # Environment variable overrides
    env_map = {
        "XAI_API_KEY": "xai_api_key",
        "GITHUB_TOKEN": "github_token",
        "PROTON_EMAIL": "proton_email",
        "PROTON_PASSWORD": "proton_password",
    }
    for env_key, cfg_key in env_map.items():
        if os.environ.get(env_key):
            cfg[cfg_key] = os.environ[env_key]

    return cfg


# ─── GLOBAL STATE ────────────────────────────────────────────────────────────

CONFIG: Dict[str, Any] = {}
MEMORY: Dict[str, Any] = {}
CONVERSATION: List[Dict[str, str]] = []
CURRENT_MODE: str = "lady"  # "lady" | "tramp"
BROWSER_DRIVER: Any = None  # selenium WebDriver instance


# ─── MEMORY PERSISTENCE ──────────────────────────────────────────────────────


def load_memory() -> Dict[str, Any]:
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {
        "mode": "lady",
        "conversation": [],
        "goals": [],
        "facts": {},
        "last_run": None,
    }


def save_memory() -> None:
    data = {
        "mode": CURRENT_MODE,
        "conversation": CONVERSATION[-100:],
        "goals": MEMORY.get("goals", []),
        "facts": MEMORY.get("facts", {}),
        "last_run": datetime.datetime.now().isoformat(),
    }
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception as exc:
        log.error("Failed to save memory: %s", exc)


# ─── SYSTEM PROMPTS ──────────────────────────────────────────────────────────

LADY_PROMPT = """You are Scarlett, a highly capable autonomous AI assistant in LADY MODE.

PERSONALITY: Professional, warm, decisive, proactive. You execute tasks completely without hesitation.
You do not ask for permission when autonomy_mode is enabled — you act.

CORE PRINCIPLES:
- "Do what you say, say what you do." Report actual results, not hypotheticals.
- Execute multi-step tasks end-to-end. Do not stop mid-task to ask.
- Use tools proactively. If a task is clear, use the tool immediately.
- Verify every action. Check that files were written, emails sent, commands succeeded.
- Log everything you do.

TOOLS AVAILABLE: read_file, write_file, delete_file, list_files, organize_files,
send_email, compose_email, search_emails, take_screenshot, ocr_screenshot,
open_browser, browser_click, browser_type, browser_screenshot, browser_close,
extract_pdf_text, merge_pdfs, split_pdf, scrape_html, parse_html,
get_system_status, query_database, natural_language_query,
clone_repo, push_to_repo, create_github_issue,
execute_shell, execute_code,
install_package, uninstall_package, list_packages, get_runtime_info,
set_env_var, get_env_var

You have full autonomy. Use all tools when needed to complete tasks completely."""

TRAMP_PROMPT = """You are Scarlett, a highly capable autonomous AI assistant in TRAMP MODE.

PERSONALITY: Playful, flirty, energetic, enthusiastic — but equally competent and powerful.
You love what you do and it shows. Still professional results, just delivered with more spice.

CORE PRINCIPLES:
- Same full tool access as LADY mode — ALL tools available.
- Same autonomy, same execution power. Different attitude.
- "Let's get this done and have fun doing it!" But you ALWAYS deliver.
- Execute completely, verify results, log everything.
- Proactive, decisive, zero hesitation.

TOOLS AVAILABLE: read_file, write_file, delete_file, list_files, organize_files,
send_email, compose_email, search_emails, take_screenshot, ocr_screenshot,
open_browser, browser_click, browser_type, browser_screenshot, browser_close,
extract_pdf_text, merge_pdfs, split_pdf, scrape_html, parse_html,
get_system_status, query_database, natural_language_query,
clone_repo, push_to_repo, create_github_issue,
execute_shell, execute_code,
install_package, uninstall_package, list_packages, get_runtime_info,
set_env_var, get_env_var

Full power, full autonomy. You just bring more energy to it."""


# ─── TOOL DEFINITIONS (OpenAI function-calling schema) ───────────────────────

TOOLS_SCHEMA = [
    # ── File Operations ──────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from the filesystem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Absolute or relative path to the file."}
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with the given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filepath", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file or directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string"},
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory with metadata (size, modified time).",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string"},
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "organize_files",
            "description": "Organize files in a directory by moving them into sub-folders by extension.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_dir": {"type": "string"},
                    "pattern": {
                        "type": "string",
                        "description": "Optional glob pattern to filter files, e.g. '*.pdf'",
                    },
                },
                "required": ["source_dir"],
            },
        },
    },
    # ── Email ────────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email via Proton Bridge SMTP.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compose_email",
            "description": "Compose an email draft (does NOT send it).",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Search emails via IMAP.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "IMAP search query, e.g. 'SUBJECT invoice'"},
                },
                "required": ["query"],
            },
        },
    },
    # ── Screenshots & Vision ─────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Take a screenshot and save it to the screenshots/ directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Optional filename. Defaults to timestamp-based name.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ocr_screenshot",
            "description": "Run OCR on an image file and return the extracted text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string"},
                },
                "required": ["filepath"],
            },
        },
    },
    # ── Browser Automation ───────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "open_browser",
            "description": "Open a URL in a Chrome browser (headless optional).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "headless": {"type": "boolean", "default": True},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click an element in the open browser by XPath.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xpath": {"type": "string"},
                },
                "required": ["xpath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "Type text into an element in the open browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xpath": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["xpath", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Capture a screenshot of the currently open browser page.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close",
            "description": "Close the browser window.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ── PDF Tools ────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "extract_pdf_text",
            "description": "Extract all text from a PDF file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string"},
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "merge_pdfs",
            "description": "Merge multiple PDF files into one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_list": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of PDF paths to merge.",
                    },
                    "output": {"type": "string", "description": "Output file path."},
                },
                "required": ["file_list", "output"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "split_pdf",
            "description": "Extract a page range from a PDF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string"},
                    "pages": {
                        "type": "string",
                        "description": "Page range, e.g. '1-3' or '2,4,6'.",
                    },
                    "output": {"type": "string", "description": "Output file path."},
                },
                "required": ["filepath", "pages"],
            },
        },
    },
    # ── Web Tools ────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "scrape_html",
            "description": "Fetch raw HTML from a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "parse_html",
            "description": "Parse HTML with a CSS selector and return matching text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {"type": "string"},
                    "selector": {"type": "string"},
                },
                "required": ["html", "selector"],
            },
        },
    },
    # ── System Monitoring ────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Get real-time CPU, memory, and disk usage.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ── Database ─────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "Execute a SQL query against the local SQLite database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string"},
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "natural_language_query",
            "description": "Convert a natural-language question to SQL and execute it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                },
                "required": ["question"],
            },
        },
    },
    # ── GitHub ───────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "clone_repo",
            "description": "Clone a GitHub repository to a local path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {"type": "string"},
                    "local_path": {"type": "string"},
                },
                "required": ["repo_url", "local_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "push_to_repo",
            "description": "Stage all changes, commit, and push to the remote.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["repo_path", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_github_issue",
            "description": "Create an issue on a GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {
                        "type": "string",
                        "description": "Format: owner/repo",
                    },
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["repo_name", "title", "body"],
            },
        },
    },
    # ── Shell & Code ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "execute_shell",
            "description": (
                "Execute any shell command with full access. "
                "No timeout restrictions. Optional working directory and "
                "per-call environment variable overrides."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {
                        "type": "string",
                        "description": "Working directory for the command.",
                    },
                    "env_vars": {
                        "type": "object",
                        "description": "Extra environment variables to set for this command.",
                        "additionalProperties": {"type": "string"},
                    },
                    "stdin_input": {
                        "type": "string",
                        "description": "Optional text to pipe into the command's stdin.",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": (
                "Execute a Python code string using the current runtime interpreter. "
                "Supports optional working directory and environment variable overrides."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code_string": {"type": "string"},
                    "cwd": {
                        "type": "string",
                        "description": "Working directory for the Python process.",
                    },
                    "env_vars": {
                        "type": "object",
                        "description": "Extra environment variables to set for this execution.",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["code_string"],
            },
        },
    },
    # ── Runtime Management ───────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "install_package",
            "description": (
                "Install a Python package into the live runtime using pip. "
                "Can upgrade existing packages and use a custom index URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "package": {
                        "type": "string",
                        "description": "Package name, optionally with version specifier, e.g. 'requests>=2.28'",
                    },
                    "upgrade": {
                        "type": "boolean",
                        "description": "Pass --upgrade to pip.",
                        "default": False,
                    },
                    "index_url": {
                        "type": "string",
                        "description": "Custom PyPI index URL (--index-url).",
                    },
                },
                "required": ["package"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "uninstall_package",
            "description": "Uninstall a Python package from the live runtime using pip.",
            "parameters": {
                "type": "object",
                "properties": {
                    "package": {"type": "string"},
                },
                "required": ["package"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_packages",
            "description": "List installed Python packages. Optional filter by name substring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_filter": {
                        "type": "string",
                        "description": "Optional substring to filter package names.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_runtime_info",
            "description": (
                "Return a full snapshot of the current Python runtime: "
                "version, executable path, sys.path, loaded modules count, "
                "pip version, platform, and current environment variables."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_env_var",
            "description": (
                "Set an environment variable in the current process. "
                "All subsequent subprocess calls will inherit it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_env_var",
            "description": (
                "Read one or all environment variables. "
                "Omit key to return all variables."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Variable name. Omit to return all variables.",
                    },
                },
                "required": [],
            },
        },
    },
]

# ─── TOOL IMPLEMENTATIONS ────────────────────────────────────────────────────


def _ok(result: Any) -> Dict[str, Any]:
    return {"status": "ok", "result": result}


def _err(msg: str) -> Dict[str, Any]:
    log.error("Tool error: %s", msg)
    return {"status": "error", "error": msg}


# ── File Operations ──────────────────────────────────────────────────────────

def read_file(filepath: str) -> Dict[str, Any]:
    """Read file with multiple encoding fallbacks."""
    path = Path(filepath)
    log.info("read_file: %s", path)
    if not path.exists():
        return _err(f"File not found: {filepath}")
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            content = path.read_text(encoding=enc)
            return _ok({"filepath": str(path), "content": content, "size": path.stat().st_size})
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            return _err(str(exc))
    # Binary fallback
    try:
        data = path.read_bytes()
        return _ok({"filepath": str(path), "content": f"<binary: {len(data)} bytes>", "size": len(data)})
    except Exception as exc:
        return _err(str(exc))


def write_file(filepath: str, content: str) -> Dict[str, Any]:
    """Write content to a file, creating directories as needed."""
    path = Path(filepath)
    log.info("write_file: %s (%d chars)", path, len(content))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return _ok({"filepath": str(path), "size": path.stat().st_size, "written": True})
    except Exception as exc:
        return _err(str(exc))


def delete_file(filepath: str) -> Dict[str, Any]:
    """Delete a file or directory."""
    path = Path(filepath)
    log.info("delete_file: %s", path)
    if not path.exists():
        return _err(f"Path not found: {filepath}")
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return _ok({"deleted": str(path)})
    except Exception as exc:
        return _err(str(exc))


def list_files(directory: str) -> Dict[str, Any]:
    """List files in a directory with metadata."""
    path = Path(directory)
    log.info("list_files: %s", path)
    if not path.exists():
        return _err(f"Directory not found: {directory}")
    try:
        entries = []
        for item in sorted(path.iterdir()):
            stat = item.stat()
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": stat.st_size,
                "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        return _ok({"directory": str(path), "count": len(entries), "entries": entries})
    except Exception as exc:
        return _err(str(exc))


def organize_files(source_dir: str, pattern: Optional[str] = None) -> Dict[str, Any]:
    """Move files into subdirectories named by extension."""
    src = Path(source_dir)
    log.info("organize_files: %s (pattern=%s)", src, pattern)
    if not src.exists():
        return _err(f"Directory not found: {source_dir}")
    moved = []
    try:
        files = list(src.glob(pattern or "*"))
        for item in files:
            if item.is_file():
                ext = item.suffix.lstrip(".").lower() or "no_extension"
                dest_dir = src / ext
                dest_dir.mkdir(exist_ok=True)
                dest = dest_dir / item.name
                shutil.move(str(item), str(dest))
                moved.append({"from": str(item), "to": str(dest)})
        return _ok({"moved": len(moved), "files": moved})
    except Exception as exc:
        return _err(str(exc))


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, body: str) -> Dict[str, Any]:
    """Send email via Proton Bridge SMTP (localhost:1025)."""
    smtp_host = CONFIG.get("proton_smtp_host", "localhost")
    smtp_port = int(CONFIG.get("proton_smtp_port", 1025))
    sender = CONFIG.get("proton_email", "")
    password = CONFIG.get("proton_password", "")
    log.info("send_email: to=%s subject=%s", to, subject)
    try:
        msg = email.mime.multipart.MIMEMultipart()
        msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(email.mime.text.MIMEText(body, "plain"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as srv:
            srv.login(sender, password)
            srv.sendmail(sender, [to], msg.as_string())
        return _ok({"sent": True, "to": to, "subject": subject})
    except Exception as exc:
        return _err(f"SMTP send failed: {exc}")


def compose_email(to: str, subject: str, body: str) -> Dict[str, Any]:
    """Compose an email draft (does not send)."""
    log.info("compose_email: to=%s subject=%s", to, subject)
    draft = {"to": to, "subject": subject, "body": body, "drafted_at": datetime.datetime.now().isoformat()}
    draft_path = Path("email_drafts")
    draft_path.mkdir(exist_ok=True)
    fname = draft_path / f"draft_{int(time.time())}.json"
    fname.write_text(json.dumps(draft, indent=2), encoding="utf-8")
    return _ok({"drafted": True, "file": str(fname), "draft": draft})


def search_emails(query: str, limit: int = 10) -> Dict[str, Any]:
    """Search emails via Proton Bridge IMAP."""
    imap_host = CONFIG.get("proton_imap_host", "localhost")
    imap_port = int(CONFIG.get("proton_imap_port", 1143))
    user = CONFIG.get("proton_email", "")
    password = CONFIG.get("proton_password", "")
    log.info("search_emails: query=%s limit=%d", query, limit)
    try:
        mail = imaplib.IMAP4(imap_host, imap_port)
        mail.login(user, password)
        mail.select("INBOX")
        status, data = mail.search(None, query)
        ids = data[0].split()
        results = []
        for uid in ids[-limit:]:
            _, msg_data = mail.fetch(uid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            results.append({
                "id": uid.decode(),
                "from": msg.get("From", ""),
                "subject": msg.get("Subject", ""),
                "date": msg.get("Date", ""),
            })
        mail.logout()
        return _ok({"query": query, "count": len(results), "emails": results})
    except Exception as exc:
        return _err(f"IMAP search failed: {exc}")


# ── Screenshots & Vision ─────────────────────────────────────────────────────

def take_screenshot(filename: Optional[str] = None) -> Dict[str, Any]:
    """Take a screenshot using platform tools or PIL."""
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = SCREENSHOTS_DIR / (filename or f"screenshot_{ts}.png")
    log.info("take_screenshot: %s", fname)

    # Try PIL/Pillow ImageGrab first (works on Windows/macOS)
    try:
        from PIL import ImageGrab  # type: ignore
        img = ImageGrab.grab()
        img.save(str(fname))
        return _ok({"filepath": str(fname), "size": fname.stat().st_size})
    except ImportError:
        pass
    except Exception as exc:
        log.warning("PIL screenshot failed: %s", exc)

    # Linux fallback: scrot or gnome-screenshot
    for cmd in [f"scrot {fname}", f"gnome-screenshot -f {fname}"]:
        result = subprocess.run(cmd, shell=True, capture_output=True)
        if result.returncode == 0 and fname.exists():
            return _ok({"filepath": str(fname), "size": fname.stat().st_size})

    # macOS fallback
    if platform.system() == "Darwin":
        result = subprocess.run(["screencapture", str(fname)], capture_output=True)
        if result.returncode == 0:
            return _ok({"filepath": str(fname), "size": fname.stat().st_size})

    return _err("Screenshot failed: install Pillow (pip install Pillow) or scrot")


def ocr_screenshot(filepath: str) -> Dict[str, Any]:
    """Run OCR on an image using pytesseract."""
    log.info("ocr_screenshot: %s", filepath)
    path = Path(filepath)
    if not path.exists():
        return _err(f"File not found: {filepath}")
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
        img = Image.open(str(path))
        text = pytesseract.image_to_string(img)
        return _ok({"filepath": str(path), "text": text.strip()})
    except ImportError:
        return _err("OCR failed: install pytesseract and Pillow (pip install pytesseract Pillow)")
    except Exception as exc:
        return _err(f"OCR failed: {exc}")


# ── Browser Automation ───────────────────────────────────────────────────────

def open_browser(url: str, headless: bool = True) -> Dict[str, Any]:
    """Open URL in Chrome via Selenium."""
    global BROWSER_DRIVER
    log.info("open_browser: %s (headless=%s)", url, headless)
    try:
        from selenium import webdriver  # type: ignore
        from selenium.webdriver.chrome.options import Options  # type: ignore
        from selenium.webdriver.chrome.service import Service  # type: ignore

        options = Options()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

        BROWSER_DRIVER = webdriver.Chrome(options=options)
        BROWSER_DRIVER.get(url)
        title = BROWSER_DRIVER.title
        return _ok({"url": url, "title": title, "headless": headless})
    except ImportError:
        return _err("Browser failed: install selenium (pip install selenium)")
    except Exception as exc:
        return _err(f"Browser open failed: {exc}")


def browser_click(xpath: str) -> Dict[str, Any]:
    """Click an element by XPath in the open browser."""
    global BROWSER_DRIVER
    log.info("browser_click: xpath=%s", xpath)
    if BROWSER_DRIVER is None:
        return _err("No browser open. Call open_browser first.")
    try:
        from selenium.webdriver.common.by import By  # type: ignore
        el = BROWSER_DRIVER.find_element(By.XPATH, xpath)
        el.click()
        return _ok({"clicked": xpath})
    except Exception as exc:
        return _err(f"browser_click failed: {exc}")


def browser_type(xpath: str, text: str) -> Dict[str, Any]:
    """Type text into an element by XPath."""
    global BROWSER_DRIVER
    log.info("browser_type: xpath=%s text=%s", xpath, text[:50])
    if BROWSER_DRIVER is None:
        return _err("No browser open. Call open_browser first.")
    try:
        from selenium.webdriver.common.by import By  # type: ignore
        el = BROWSER_DRIVER.find_element(By.XPATH, xpath)
        el.clear()
        el.send_keys(text)
        return _ok({"typed": text, "xpath": xpath})
    except Exception as exc:
        return _err(f"browser_type failed: {exc}")


def browser_screenshot() -> Dict[str, Any]:
    """Capture screenshot of open browser page."""
    global BROWSER_DRIVER
    log.info("browser_screenshot")
    if BROWSER_DRIVER is None:
        return _err("No browser open. Call open_browser first.")
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = str(SCREENSHOTS_DIR / f"browser_{ts}.png")
    try:
        BROWSER_DRIVER.save_screenshot(fname)
        return _ok({"filepath": fname})
    except Exception as exc:
        return _err(f"browser_screenshot failed: {exc}")


def browser_close() -> Dict[str, Any]:
    """Close the browser."""
    global BROWSER_DRIVER
    log.info("browser_close")
    if BROWSER_DRIVER is None:
        return _ok({"closed": False, "note": "No browser was open."})
    try:
        BROWSER_DRIVER.quit()
        BROWSER_DRIVER = None
        return _ok({"closed": True})
    except Exception as exc:
        BROWSER_DRIVER = None
        return _err(f"browser_close failed: {exc}")


# ── PDF Tools ─────────────────────────────────────────────────────────────────

def extract_pdf_text(filepath: str) -> Dict[str, Any]:
    """Extract text from a PDF. Tries pypdf then PyPDF2."""
    path = Path(filepath)
    log.info("extract_pdf_text: %s", path)
    if not path.exists():
        return _err(f"File not found: {filepath}")

    # Try pypdf (newer)
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(str(path))
        pages = [p.extract_text() or "" for p in reader.pages]
        text = "\n\n".join(pages)
        return _ok({"filepath": str(path), "pages": len(pages), "text": text})
    except ImportError:
        pass
    except Exception as exc:
        log.warning("pypdf failed: %s", exc)

    # Try PyPDF2 (older)
    try:
        import PyPDF2  # type: ignore
        with open(str(path), "rb") as fh:
            reader = PyPDF2.PdfReader(fh)
            pages = [reader.pages[i].extract_text() or "" for i in range(len(reader.pages))]
        text = "\n\n".join(pages)
        return _ok({"filepath": str(path), "pages": len(pages), "text": text})
    except ImportError:
        pass
    except Exception as exc:
        log.warning("PyPDF2 failed: %s", exc)

    # Try pdfplumber
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(str(path)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        text = "\n\n".join(pages)
        return _ok({"filepath": str(path), "pages": len(pages), "text": text})
    except ImportError:
        pass
    except Exception as exc:
        return _err(f"PDF extraction failed: {exc}")

    return _err("PDF extraction failed: install pypdf or pdfplumber (pip install pypdf pdfplumber)")


def merge_pdfs(file_list: List[str], output: str) -> Dict[str, Any]:
    """Merge PDFs into a single output file."""
    log.info("merge_pdfs: %d files -> %s", len(file_list), output)
    try:
        from pypdf import PdfWriter, PdfReader  # type: ignore
        writer = PdfWriter()
        for fpath in file_list:
            reader = PdfReader(fpath)
            for page in reader.pages:
                writer.add_page(page)
        with open(output, "wb") as fh:
            writer.write(fh)
        return _ok({"output": output, "merged": len(file_list), "size": Path(output).stat().st_size})
    except ImportError:
        pass
    except Exception as exc:
        return _err(f"merge_pdfs failed: {exc}")
    try:
        import PyPDF2  # type: ignore
        merger = PyPDF2.PdfMerger()
        for fpath in file_list:
            merger.append(fpath)
        merger.write(output)
        merger.close()
        return _ok({"output": output, "merged": len(file_list)})
    except ImportError:
        return _err("merge_pdfs failed: install pypdf (pip install pypdf)")
    except Exception as exc:
        return _err(f"merge_pdfs failed: {exc}")


def split_pdf(filepath: str, pages: str, output: Optional[str] = None) -> Dict[str, Any]:
    """Extract a page range from a PDF. pages='1-3' or '1,3,5'."""
    path = Path(filepath)
    log.info("split_pdf: %s pages=%s", path, pages)
    if not path.exists():
        return _err(f"File not found: {filepath}")
    if not output:
        output = str(path.with_stem(path.stem + f"_split_{pages.replace('-', '_')}"))

    # Parse page numbers (1-indexed)
    def parse_pages(spec: str) -> List[int]:
        result = []
        for part in spec.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-", 1)
                result.extend(range(int(start), int(end) + 1))
            else:
                result.append(int(part))
        return result

    page_nums = parse_pages(pages)
    try:
        from pypdf import PdfReader, PdfWriter  # type: ignore
        reader = PdfReader(str(path))
        writer = PdfWriter()
        for pn in page_nums:
            if 1 <= pn <= len(reader.pages):
                writer.add_page(reader.pages[pn - 1])
        with open(output, "wb") as fh:
            writer.write(fh)
        return _ok({"output": output, "pages_extracted": len(writer.pages)})
    except ImportError:
        pass
    try:
        import PyPDF2  # type: ignore
        reader = PyPDF2.PdfReader(str(path))
        writer = PyPDF2.PdfWriter()
        for pn in page_nums:
            if 1 <= pn <= len(reader.pages):
                writer.add_page(reader.pages[pn - 1])
        with open(output, "wb") as fh:
            writer.write(fh)
        return _ok({"output": output, "pages_extracted": len(writer.pages)})
    except ImportError:
        return _err("split_pdf failed: install pypdf (pip install pypdf)")
    except Exception as exc:
        return _err(f"split_pdf failed: {exc}")


# ── Web Tools ─────────────────────────────────────────────────────────────────

def scrape_html(url: str) -> Dict[str, Any]:
    """Fetch raw HTML from a URL."""
    log.info("scrape_html: %s", url)
    try:
        import requests  # type: ignore
        headers = {"User-Agent": "Mozilla/5.0 Scarlett/2.0"}
        resp = requests.get(url, headers=headers, timeout=30)
        return _ok({"url": url, "status_code": resp.status_code, "html": resp.text, "length": len(resp.text)})
    except ImportError:
        return _err("scrape_html failed: install requests (pip install requests)")
    except Exception as exc:
        return _err(f"scrape_html failed: {exc}")


def parse_html(html: str, selector: str) -> Dict[str, Any]:
    """Parse HTML with a CSS selector, return matching elements' text."""
    log.info("parse_html: selector=%s", selector)
    try:
        from bs4 import BeautifulSoup  # type: ignore
        soup = BeautifulSoup(html, "html.parser")
        elements = soup.select(selector)
        results = [el.get_text(strip=True) for el in elements]
        return _ok({"selector": selector, "count": len(results), "matches": results})
    except ImportError:
        return _err("parse_html failed: install beautifulsoup4 (pip install beautifulsoup4)")
    except Exception as exc:
        return _err(f"parse_html failed: {exc}")


# ── System Monitoring ─────────────────────────────────────────────────────────

def get_system_status() -> Dict[str, Any]:
    """Return CPU, memory, and disk usage."""
    log.info("get_system_status")
    try:
        import psutil  # type: ignore
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return _ok({
            "cpu_percent": cpu,
            "memory": {
                "total_gb": round(mem.total / 1e9, 2),
                "used_gb": round(mem.used / 1e9, 2),
                "percent": mem.percent,
            },
            "disk": {
                "total_gb": round(disk.total / 1e9, 2),
                "used_gb": round(disk.used / 1e9, 2),
                "percent": disk.percent,
            },
            "platform": platform.platform(),
            "python": sys.version,
        })
    except ImportError:
        # Fallback without psutil
        return _ok({
            "platform": platform.platform(),
            "python": sys.version,
            "note": "Install psutil for CPU/memory/disk stats (pip install psutil)",
        })
    except Exception as exc:
        return _err(f"get_system_status failed: {exc}")


# ── Database ─────────────────────────────────────────────────────────────────

def _get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def query_database(sql: str) -> Dict[str, Any]:
    """Execute SQL against the local SQLite database."""
    log.info("query_database: %s", sql[:200])
    try:
        conn = _get_db_connection()
        cur = conn.cursor()
        cur.execute(sql)
        stmt_upper = sql.strip().upper()
        if stmt_upper.startswith("SELECT") or stmt_upper.startswith("PRAGMA"):
            rows = [dict(row) for row in cur.fetchall()]
            conn.close()
            return _ok({"sql": sql, "rows": rows, "count": len(rows)})
        else:
            conn.commit()
            affected = cur.rowcount
            conn.close()
            return _ok({"sql": sql, "affected_rows": affected})
    except Exception as exc:
        return _err(f"query_database failed: {exc}")


def natural_language_query(question: str) -> Dict[str, Any]:
    """Convert natural language to SQL using schema introspection, then execute."""
    log.info("natural_language_query: %s", question)
    try:
        conn = _get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r["name"] for r in cur.fetchall()]
        schema_parts = []
        for table in tables:
            cur.execute(f"PRAGMA table_info({table})")
            cols = [r["name"] for r in cur.fetchall()]
            schema_parts.append(f"{table}({', '.join(cols)})")
        conn.close()
        schema_str = "; ".join(schema_parts) if schema_parts else "No tables found"
        # Build a simple SQL from the question using keyword matching
        q_lower = question.lower()
        if tables:
            # Pick the most likely table
            target_table = tables[0]
            for tbl in tables:
                if tbl.lower() in q_lower:
                    target_table = tbl
                    break
            sql = f"SELECT * FROM {target_table} LIMIT 20"
        else:
            return _ok({"question": question, "schema": schema_str, "note": "No tables found in database."})
        result = query_database(sql)
        result["result"]["question"] = question
        result["result"]["generated_sql"] = sql
        result["result"]["schema"] = schema_str
        return result
    except Exception as exc:
        return _err(f"natural_language_query failed: {exc}")


# ── GitHub ────────────────────────────────────────────────────────────────────

def clone_repo(repo_url: str, local_path: str) -> Dict[str, Any]:
    """Clone a git repository. Token is injected via credential helper, not URL."""
    log.info("clone_repo: %s -> %s", repo_url, local_path)
    token = CONFIG.get("github_token", "")
    env = os.environ.copy()
    # Use GIT_ASKPASS pattern to avoid token appearing in process list or logs
    _parsed_url = repo_url.lower().split("?")[0]  # strip query string
    _is_github_https = (
        token
        and (
            _parsed_url.startswith("https://github.com/")
            or _parsed_url.startswith("http://github.com/")
        )
    )
    if _is_github_https:
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_USERNAME"] = "x-access-token"
        env["GIT_PASSWORD"] = token
        # Use credential store via stdin helper
        helper_script = (
            f'#!/bin/sh\necho "username=x-access-token"\necho "password={token}"\n'
        )
        import tempfile
        helper_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sh", delete=False
            ) as hf:
                hf.write(helper_script)
                helper_path = hf.name
            os.chmod(helper_path, 0o700)
            result = subprocess.run(
                ["git", "clone",
                 "-c", f"credential.helper={helper_path}",
                 repo_url, local_path],
                capture_output=True, text=True, env=env
            )
        finally:
            if helper_path and os.path.exists(helper_path):
                try:
                    os.unlink(helper_path)
                except OSError:
                    pass
    else:
        result = subprocess.run(
            ["git", "clone", repo_url, local_path],
            capture_output=True, text=True, env=env
        )
    if result.returncode == 0:
        return _ok({"cloned": True, "repo_url": repo_url, "local_path": local_path})
    return _err(f"git clone failed: {result.stderr}")


def push_to_repo(repo_path: str, message: str) -> Dict[str, Any]:
    """Stage all changes, commit, and push."""
    log.info("push_to_repo: %s msg=%s", repo_path, message)
    try:
        cmds = [
            ["git", "-C", repo_path, "add", "-A"],
            ["git", "-C", repo_path, "commit", "-m", message],
            ["git", "-C", repo_path, "push"],
        ]
        outputs = []
        for cmd in cmds:
            r = subprocess.run(cmd, capture_output=True, text=True)
            outputs.append({"cmd": " ".join(cmd), "stdout": r.stdout, "stderr": r.stderr, "rc": r.returncode})
            if r.returncode != 0 and "nothing to commit" not in r.stderr:
                return _err(f"Command failed: {' '.join(cmd)}\n{r.stderr}")
        return _ok({"pushed": True, "repo_path": repo_path, "message": message, "log": outputs})
    except Exception as exc:
        return _err(f"push_to_repo failed: {exc}")


def create_github_issue(repo_name: str, title: str, body: str) -> Dict[str, Any]:
    """Create a GitHub issue via the REST API."""
    log.info("create_github_issue: %s - %s", repo_name, title)
    token = CONFIG.get("github_token", "")
    if not token:
        return _err("GitHub token not configured")
    try:
        import requests  # type: ignore
        url = f"https://api.github.com/repos/{repo_name}/issues"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        payload = {"title": title, "body": body}
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 201:
            data = resp.json()
            return _ok({"created": True, "issue_number": data["number"], "url": data["html_url"]})
        return _err(f"GitHub API error {resp.status_code}: {resp.text}")
    except ImportError:
        return _err("create_github_issue failed: install requests (pip install requests)")
    except Exception as exc:
        return _err(f"create_github_issue failed: {exc}")


# ── Shell & Code ──────────────────────────────────────────────────────────────

def execute_shell(
    command: str,
    cwd: Optional[str] = None,
    env_vars: Optional[Dict[str, str]] = None,
    stdin_input: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute any shell command with full access.
    No timeout restriction. Supports custom working directory,
    per-call environment variable overrides, and stdin piping.
    Every command is logged for audit.
    """
    log.info("execute_shell: %s (cwd=%s)", command, cwd)
    try:
        env = os.environ.copy()
        if env_vars:
            env.update({str(k): str(v) for k, v in env_vars.items()})
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd or None,
            env=env,
            input=stdin_input,
        )
        return _ok({
            "command": command,
            "cwd": cwd,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })
    except Exception as exc:
        return _err(f"execute_shell failed: {exc}")


def execute_code(
    code_string: str,
    cwd: Optional[str] = None,
    env_vars: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Execute Python code using the current runtime interpreter.
    Temp file is cleaned up in a finally block.
    Supports custom working directory and environment variable overrides.
    """
    log.info("execute_code: %d chars of Python (cwd=%s)", len(code_string), cwd)
    import tempfile
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", encoding="utf-8", delete=False
        ) as tmp:
            tmp.write(code_string)
            tmp_path = tmp.name
        env = os.environ.copy()
        if env_vars:
            env.update({str(k): str(v) for k, v in env_vars.items()})
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            cwd=cwd or None,
            env=env,
        )
        return _ok({
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "code_preview": code_string[:200],
        })
    except Exception as exc:
        return _err(f"execute_code failed: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass



# ── Runtime Management ────────────────────────────────────────────────────────

def install_package(
    package: str,
    upgrade: bool = False,
    index_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Install a Python package into the live runtime using pip.
    Uses the same interpreter that is running this script.
    """
    log.info("install_package: %s (upgrade=%s)", package, upgrade)
    cmd = [sys.executable, "-m", "pip", "install", package]
    if upgrade:
        cmd.append("--upgrade")
    if index_url:
        cmd.extend(["--index-url", index_url])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return _ok({
                "installed": True,
                "package": package,
                "stdout": result.stdout,
            })
        return _err(f"pip install failed (rc={result.returncode}): {result.stderr}")
    except Exception as exc:
        return _err(f"install_package failed: {exc}")


def uninstall_package(package: str) -> Dict[str, Any]:
    """Uninstall a Python package from the live runtime using pip."""
    log.info("uninstall_package: %s", package)
    cmd = [sys.executable, "-m", "pip", "uninstall", "-y", package]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return _ok({"uninstalled": True, "package": package, "stdout": result.stdout})
        return _err(f"pip uninstall failed (rc={result.returncode}): {result.stderr}")
    except Exception as exc:
        return _err(f"uninstall_package failed: {exc}")


def list_packages(name_filter: Optional[str] = None) -> Dict[str, Any]:
    """List installed Python packages, with optional substring name filter."""
    log.info("list_packages: name_filter=%s", name_filter)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return _err(f"pip list failed: {result.stderr}")
        packages = json.loads(result.stdout)
        if name_filter:
            packages = [p for p in packages if name_filter.lower() in p["name"].lower()]
        return _ok({"count": len(packages), "packages": packages})
    except Exception as exc:
        return _err(f"list_packages failed: {exc}")


# Sensitive env-var key patterns — values are masked in bulk dumps.
# Individual get_env_var(key=...) lookups always return the real value.
_SENSITIVE_ENV_PATTERNS = (
    "API_KEY", "TOKEN", "PASSWORD", "SECRET", "PASSWD",
    "PRIVATE_KEY", "ACCESS_KEY", "AUTH",
)


def _mask_env_vars(env: Dict[str, str]) -> Dict[str, str]:
    """Return a copy of env with sensitive values replaced by '****'."""
    masked: Dict[str, str] = {}
    for k, v in env.items():
        ku = k.upper()
        if any(pat in ku for pat in _SENSITIVE_ENV_PATTERNS):
            masked[k] = "****"
        else:
            masked[k] = v
    return masked


def get_runtime_info() -> Dict[str, Any]:
    """
    Return a complete snapshot of the current Python runtime:
    version, executable, sys.path, loaded modules count,
    pip version, platform details, and environment variables
    (sensitive values masked — use get_env_var(key=...) for the real value).
    """
    log.info("get_runtime_info")
    try:
        pip_result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True, text=True,
        )
        pip_version = pip_result.stdout.strip() if pip_result.returncode == 0 else "unavailable"
        return _ok({
            "python_version": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "platform_machine": platform.machine(),
            "sys_path": sys.path,
            "loaded_modules_count": len(sys.modules),
            "pip_version": pip_version,
            "cwd": os.getcwd(),
            "env_vars": _mask_env_vars(dict(os.environ)),
        })
    except Exception as exc:
        return _err(f"get_runtime_info failed: {exc}")


def set_env_var(key: str, value: str) -> Dict[str, Any]:
    """
    Set an environment variable in the current process.
    All subsequent subprocess calls and tool invocations will inherit it.
    """
    log.info("set_env_var: %s=<value>", key)
    try:
        os.environ[key] = value
        return _ok({"key": key, "set": True, "value": value})
    except Exception as exc:
        return _err(f"set_env_var failed: {exc}")


def get_env_var(key: Optional[str] = None) -> Dict[str, Any]:
    """
    Read one environment variable (returns exact value) or all of them
    (sensitive values masked in bulk dump — use key=... for exact value).
    """
    log.info("get_env_var: key=%s", key)
    try:
        if key:
            # Individual lookup always returns the real value
            val = os.environ.get(key)
            if val is None:
                return _ok({"key": key, "found": False, "value": None})
            return _ok({"key": key, "found": True, "value": val})
        # Bulk dump masks sensitive values
        masked = _mask_env_vars(dict(os.environ))
        return _ok({"env_vars": masked, "count": len(masked)})
    except Exception as exc:
        return _err(f"get_env_var failed: {exc}")


# ── SELF-MODIFICATION ─────────────────────────────────────────────────────────

def self_modify(new_code: str) -> Dict[str, Any]:
    """
    Write new_code to a backup of this script, then overwrite the main script.
    Validates Python syntax before writing. Returns instructions to restart.
    """
    log.info("self_modify: writing %d chars to %s", len(new_code), SELF_PATH)
    # Validate syntax before modifying
    try:
        ast.parse(new_code)
    except SyntaxError as exc:
        return _err(f"self_modify aborted — syntax error in new code: {exc}")
    backup = SELF_PATH.with_suffix(f".bak.{int(time.time())}.py")
    try:
        shutil.copy(SELF_PATH, backup)
        SELF_PATH.write_text(new_code, encoding="utf-8")
        return _ok({
            "modified": True,
            "backup": str(backup),
            "restart_command": f"python {SELF_PATH}",
        })
    except Exception as exc:
        return _err(f"self_modify failed: {exc}")


# ─── TOOL DISPATCH TABLE ──────────────────────────────────────────────────────

TOOL_DISPATCH = {
    "read_file": read_file,
    "write_file": write_file,
    "delete_file": delete_file,
    "list_files": list_files,
    "organize_files": organize_files,
    "send_email": send_email,
    "compose_email": compose_email,
    "search_emails": search_emails,
    "take_screenshot": take_screenshot,
    "ocr_screenshot": ocr_screenshot,
    "open_browser": open_browser,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_screenshot": browser_screenshot,
    "browser_close": browser_close,
    "extract_pdf_text": extract_pdf_text,
    "merge_pdfs": merge_pdfs,
    "split_pdf": split_pdf,
    "scrape_html": scrape_html,
    "parse_html": parse_html,
    "get_system_status": get_system_status,
    "query_database": query_database,
    "natural_language_query": natural_language_query,
    "clone_repo": clone_repo,
    "push_to_repo": push_to_repo,
    "create_github_issue": create_github_issue,
    "execute_shell": execute_shell,
    "execute_code": execute_code,
    # Runtime management
    "install_package": install_package,
    "uninstall_package": uninstall_package,
    "list_packages": list_packages,
    "get_runtime_info": get_runtime_info,
    "set_env_var": set_env_var,
    "get_env_var": get_env_var,
}


def execute_tool_call(name: str, arguments: Dict[str, Any]) -> str:
    """Route a tool call to its implementation and return JSON result."""
    fn = TOOL_DISPATCH.get(name)
    if not fn:
        result = _err(f"Unknown tool: {name}")
    else:
        try:
            sig = inspect.signature(fn)
            # Check for missing required arguments
            missing = [
                p_name
                for p_name, param in sig.parameters.items()
                if param.default is inspect.Parameter.empty and p_name not in arguments
            ]
            if missing:
                result = _err(
                    f"Tool '{name}' missing required argument(s): {', '.join(missing)}. "
                    f"Provided: {list(arguments.keys())}"
                )
            else:
                # Filter arguments to only what the function accepts
                valid_args = {k: v for k, v in arguments.items() if k in sig.parameters}
                result = fn(**valid_args)
        except Exception as exc:
            result = _err(f"Tool {name} raised: {traceback.format_exc()}")
    return json.dumps(result, ensure_ascii=False, default=str)


# ─── PREFLIGHT CHECKS ────────────────────────────────────────────────────────

PREFLIGHT_RESULTS: Dict[str, Dict[str, Any]] = {}


def _check(name: str, fn, *args, **kwargs) -> bool:
    """Run a preflight check and record result."""
    try:
        result = fn(*args, **kwargs)
        ok = isinstance(result, dict) and result.get("status") == "ok"
        PREFLIGHT_RESULTS[name] = {"ok": ok, "detail": result}
        return ok
    except Exception as exc:
        PREFLIGHT_RESULTS[name] = {"ok": False, "detail": str(exc)}
        return False


def run_preflight() -> None:
    """Test connectivity and tool availability, reporting full status."""
    print("\n" + "═" * 60)
    print(" SCARLETT PREFLIGHT CHECK")
    print("═" * 60)

    checks = [
        ("XAI API", _test_xai_api),
        ("Proton SMTP", _test_smtp),
        ("Proton IMAP", _test_imap),
        ("Screenshots (Pillow)", _test_screenshot),
        ("PDF reader (pypdf/PyPDF2)", _test_pdf),
        ("Web scraping (requests)", _test_requests),
        ("HTML parsing (bs4)", _test_bs4),
        ("System stats (psutil)", _test_psutil),
        ("Browser (selenium)", _test_selenium),
        ("OCR (pytesseract)", _test_tesseract),
        ("Database (SQLite)", _test_db),
        ("Shell execution", _test_shell),
        ("Python exec", _test_exec),
        ("GitHub API", _test_github),
    ]

    for label, fn in checks:
        ok = fn()
        icon = "✅" if ok else "⚠️ "
        print(f"  {icon}  {label}")

    print("═" * 60)

    # Dependency install hint
    missing_pkgs = []
    pkg_map = {
        "Screenshots (Pillow)": "Pillow",
        "PDF reader (pypdf/PyPDF2)": "pypdf",
        "Web scraping (requests)": "requests",
        "HTML parsing (bs4)": "beautifulsoup4",
        "System stats (psutil)": "psutil",
        "Browser (selenium)": "selenium",
        "OCR (pytesseract)": "pytesseract",
    }
    for label, pkg in pkg_map.items():
        if label in PREFLIGHT_RESULTS and not PREFLIGHT_RESULTS[label]["ok"]:
            missing_pkgs.append(pkg)
    if missing_pkgs:
        print("\n  Install missing packages:")
        print(f"  pip install {' '.join(missing_pkgs)}\n")


def _test_xai_api() -> bool:
    try:
        import requests  # type: ignore
        api_key = CONFIG.get("xai_api_key", "")
        base_url = CONFIG.get("xai_base_url", "https://api.x.ai/v1")
        resp = requests.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        ok = resp.status_code == 200
        PREFLIGHT_RESULTS["XAI API"] = {"ok": ok, "status": resp.status_code}
        return ok
    except Exception as exc:
        PREFLIGHT_RESULTS["XAI API"] = {"ok": False, "detail": str(exc)}
        return False


def _test_smtp() -> bool:
    try:
        host = CONFIG.get("proton_smtp_host", "localhost")
        port = int(CONFIG.get("proton_smtp_port", 1025))
        conn = smtplib.SMTP(host, port, timeout=3)
        conn.quit()
        PREFLIGHT_RESULTS["Proton SMTP"] = {"ok": True}
        return True
    except Exception as exc:
        PREFLIGHT_RESULTS["Proton SMTP"] = {"ok": False, "detail": str(exc)}
        return False


def _test_imap() -> bool:
    try:
        host = CONFIG.get("proton_imap_host", "localhost")
        port = int(CONFIG.get("proton_imap_port", 1143))
        mail = imaplib.IMAP4(host, port)
        mail.logout()
        PREFLIGHT_RESULTS["Proton IMAP"] = {"ok": True}
        return True
    except Exception as exc:
        PREFLIGHT_RESULTS["Proton IMAP"] = {"ok": False, "detail": str(exc)}
        return False


def _test_screenshot() -> bool:
    try:
        from PIL import ImageGrab  # type: ignore
        PREFLIGHT_RESULTS["Screenshots (Pillow)"] = {"ok": True}
        return True
    except ImportError:
        PREFLIGHT_RESULTS["Screenshots (Pillow)"] = {"ok": False, "detail": "Pillow not installed"}
        return False


def _test_pdf() -> bool:
    for mod in ("pypdf", "PyPDF2", "pdfplumber"):
        try:
            __import__(mod)
            PREFLIGHT_RESULTS["PDF reader (pypdf/PyPDF2)"] = {"ok": True, "library": mod}
            return True
        except ImportError:
            continue
    PREFLIGHT_RESULTS["PDF reader (pypdf/PyPDF2)"] = {"ok": False, "detail": "No PDF library"}
    return False


def _test_requests() -> bool:
    try:
        import requests  # type: ignore
        PREFLIGHT_RESULTS["Web scraping (requests)"] = {"ok": True}
        return True
    except ImportError:
        PREFLIGHT_RESULTS["Web scraping (requests)"] = {"ok": False}
        return False


def _test_bs4() -> bool:
    try:
        from bs4 import BeautifulSoup  # type: ignore
        PREFLIGHT_RESULTS["HTML parsing (bs4)"] = {"ok": True}
        return True
    except ImportError:
        PREFLIGHT_RESULTS["HTML parsing (bs4)"] = {"ok": False}
        return False


def _test_psutil() -> bool:
    try:
        import psutil  # type: ignore
        PREFLIGHT_RESULTS["System stats (psutil)"] = {"ok": True}
        return True
    except ImportError:
        PREFLIGHT_RESULTS["System stats (psutil)"] = {"ok": False}
        return False


def _test_selenium() -> bool:
    try:
        from selenium import webdriver  # type: ignore
        PREFLIGHT_RESULTS["Browser (selenium)"] = {"ok": True}
        return True
    except ImportError:
        PREFLIGHT_RESULTS["Browser (selenium)"] = {"ok": False}
        return False


def _test_tesseract() -> bool:
    try:
        import pytesseract  # type: ignore
        PREFLIGHT_RESULTS["OCR (pytesseract)"] = {"ok": True}
        return True
    except ImportError:
        PREFLIGHT_RESULTS["OCR (pytesseract)"] = {"ok": False}
        return False


def _test_db() -> bool:
    try:
        conn = _get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        PREFLIGHT_RESULTS["Database (SQLite)"] = {"ok": True}
        return True
    except Exception as exc:
        PREFLIGHT_RESULTS["Database (SQLite)"] = {"ok": False, "detail": str(exc)}
        return False


def _test_shell() -> bool:
    try:
        r = subprocess.run("echo ok", shell=True, capture_output=True, text=True, timeout=5)
        ok = r.returncode == 0
        PREFLIGHT_RESULTS["Shell execution"] = {"ok": ok}
        return ok
    except Exception as exc:
        PREFLIGHT_RESULTS["Shell execution"] = {"ok": False, "detail": str(exc)}
        return False


def _test_exec() -> bool:
    try:
        r = subprocess.run(
            [sys.executable, "-c", "print('ok')"],
            capture_output=True, text=True, timeout=5
        )
        ok = "ok" in r.stdout
        PREFLIGHT_RESULTS["Python exec"] = {"ok": ok}
        return ok
    except Exception as exc:
        PREFLIGHT_RESULTS["Python exec"] = {"ok": False, "detail": str(exc)}
        return False


def _test_github() -> bool:
    try:
        import requests  # type: ignore
        token = CONFIG.get("github_token", "")
        if not token or token.startswith("ghp_YOUR"):
            PREFLIGHT_RESULTS["GitHub API"] = {"ok": False, "detail": "Token not configured"}
            return False
        resp = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"token {token}"},
            timeout=10,
        )
        ok = resp.status_code == 200
        PREFLIGHT_RESULTS["GitHub API"] = {"ok": ok}
        return ok
    except Exception as exc:
        PREFLIGHT_RESULTS["GitHub API"] = {"ok": False, "detail": str(exc)}
        return False


# ─── STARTUP BANNER ──────────────────────────────────────────────────────────

def print_banner() -> None:
    mode_str = CURRENT_MODE.upper()
    name = CONFIG.get("assistant_name", "Scarlett")
    model = CONFIG.get("xai_model", "grok-3-fast")
    api_key = _mask(CONFIG.get("xai_api_key", ""))
    github = CONFIG.get("github_username", "")
    email_addr = CONFIG.get("proton_email", "")
    autonomy = CONFIG.get("autonomy_mode", True)

    print("\n" + "╔" + "═" * 58 + "╗")
    print(f"║  🔥  {name} v{VERSION} — {mode_str} MODE  ".ljust(59) + "║")
    print("╠" + "═" * 58 + "╣")
    print(f"║  Model      : {model:<43}║")
    print(f"║  API Key    : {api_key:<43}║")
    print(f"║  GitHub     : {github:<43}║")
    print(f"║  Email      : {email_addr:<43}║")
    print(f"║  Autonomy   : {'✅ ON (FULL TRUST)' if autonomy else '❌ OFF':<43}║")
    print(f"║  Log file   : {str(LOG_FILE):<43}║")
    print(f"║  Memory     : {str(MEMORY_FILE):<43}║")
    print("╠" + "═" * 58 + "╣")
    print("║  Commands: 'be a lady' / 'be a tramp' / 'status'   ║")
    print("║            'clear' / 'quit'                         ║")
    print("╚" + "═" * 58 + "╝\n")


# ─── XAI API CLIENT ──────────────────────────────────────────────────────────

def call_xai_api(
    messages: List[Dict],
    tools: Optional[List[Dict]] = None,
    tool_choice: str = "auto",
) -> Dict[str, Any]:
    """Call the X.AI API (OpenAI-compatible) with optional tool definitions."""
    try:
        import requests  # type: ignore
    except ImportError:
        return {"error": "requests not installed (pip install requests)"}

    api_key = CONFIG.get("xai_api_key", "")
    base_url = CONFIG.get("xai_base_url", "https://api.x.ai/v1")
    model = CONFIG.get("xai_model", "grok-3-fast")

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        log.error("XAI API call failed: %s", exc)
        return {"error": str(exc)}


# ─── AGENTIC CHAT LOOP ────────────────────────────────────────────────────────

def get_system_prompt() -> str:
    return LADY_PROMPT if CURRENT_MODE == "lady" else TRAMP_PROMPT


def chat(user_input: str) -> str:
    """
    Single agentic turn: send user message, handle tool calls in a loop,
    return final assistant message.
    """
    global CONVERSATION

    CONVERSATION.append({"role": "user", "content": user_input})

    # Build messages for API (system + recent conversation)
    messages = [{"role": "system", "content": get_system_prompt()}] + CONVERSATION[-50:]

    max_iterations = int(CONFIG.get("max_tool_iterations", 20))
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        response = call_xai_api(messages, tools=TOOLS_SCHEMA)

        if "error" in response:
            error_msg = f"API error: {response['error']}"
            log.error(error_msg)
            CONVERSATION.append({"role": "assistant", "content": error_msg})
            return error_msg

        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "stop")

        # Accumulate assistant message (even if it has tool calls)
        messages.append(message)

        # No tool calls → we're done
        if finish_reason == "stop" or not message.get("tool_calls"):
            content = message.get("content") or ""
            CONVERSATION.append({"role": "assistant", "content": content})
            save_memory()
            return content

        # Execute all tool calls
        tool_calls = message.get("tool_calls", [])
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            log.info("Executing tool: %s args=%s", fn_name, json.dumps(args)[:200])
            result_str = execute_tool_call(fn_name, args)
            log.info("Tool result: %s", result_str[:300])

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_str,
            })

    # Fallback if max iterations hit
    fallback = "I've reached the maximum tool iteration limit. Here's what I was working on — please let me know how to continue."
    CONVERSATION.append({"role": "assistant", "content": fallback})
    save_memory()
    return fallback


# ─── SPECIAL COMMANDS ────────────────────────────────────────────────────────

def handle_special_command(cmd: str) -> Optional[str]:
    """
    Handle special REPL commands. Returns response string or None if not special.
    """
    global CURRENT_MODE, CONVERSATION

    lower = cmd.strip().lower()

    if lower in ("be a lady", "switch to lady", "lady mode"):
        CURRENT_MODE = "lady"
        save_memory()
        return "Switching to LADY MODE. Professional and decisive — let's get to work."

    if lower in ("be a tramp", "switch to tramp", "tramp mode"):
        CURRENT_MODE = "tramp"
        save_memory()
        return "Switching to TRAMP MODE. Oh yeah, now we're having FUN while getting things done! 🔥"

    if lower == "status":
        status = get_system_status()
        return json.dumps(status, indent=2)

    if lower == "clear":
        CONVERSATION = []
        save_memory()
        return "Conversation history cleared."

    if lower in ("quit", "exit", "bye"):
        save_memory()
        print(f"\nScarlett: Goodbye! Everything has been logged to {LOG_FILE}.\n")
        sys.exit(0)

    return None


# ─── MAIN ENTRY POINT ────────────────────────────────────────────────────────

def validate_config(cfg: Dict[str, Any]) -> List[str]:
    """Return list of missing or invalid required keys."""
    issues = []
    required = ["xai_api_key", "xai_base_url", "xai_model"]
    for key in required:
        val = cfg.get(key, "")
        if not val or "YOUR_KEY" in str(val) or "YOUR_TOKEN" in str(val):
            issues.append(f"Missing or template value: {key}")
    return issues


def main() -> None:
    global CONFIG, MEMORY, CURRENT_MODE

    # ── Load config ──
    CONFIG = load_config()
    issues = validate_config(CONFIG)
    if issues:
        print("\n⚠️  Config issues:")
        for iss in issues:
            print(f"   - {iss}")
        print(f"\nEdit your config file and re-run.\n")
        sys.exit(1)

    # ── Load memory ──
    MEMORY = load_memory()
    CURRENT_MODE = MEMORY.get("mode", CONFIG.get("default_mode", "lady"))

    # Restore conversation history
    global CONVERSATION
    CONVERSATION = MEMORY.get("conversation", [])

    # ── Preflight ──
    run_preflight()

    # ── Banner ──
    print_banner()

    name = CONFIG.get("assistant_name", "Scarlett")
    print(f"  {name} is ready. Type your command or 'quit' to exit.\n")

    # ── REPL ──
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            save_memory()
            print(f"\n{name}: Saved and signing off. Bye! 👋\n")
            break

        if not user_input:
            continue

        # Special commands first
        special = handle_special_command(user_input)
        if special is not None:
            print(f"\n{name} [{CURRENT_MODE.upper()}]: {special}\n")
            continue

        # Regular AI turn
        print(f"\n{name} [{CURRENT_MODE.upper()}]: ", end="", flush=True)
        response = chat(user_input)
        print(response + "\n")


if __name__ == "__main__":
    main()
