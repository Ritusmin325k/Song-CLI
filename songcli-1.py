#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║              songcli — YouTube Music Downloader              ║
║         Advanced CLI Music Tool | Author: songcli            ║
╚══════════════════════════════════════════════════════════════╝

Dependencies:
    pip install yt-dlp rich InquirerPy requests

Optional system tools:
    mpv  (for playback)
    ffmpeg (for audio conversion)
"""

import os
import re
import sys
import json
import time
import shutil
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

# ── Rich ────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.progress import (
        Progress, BarColumn, TextColumn,
        DownloadColumn, TransferSpeedColumn,
        TimeRemainingColumn, SpinnerColumn,
    )
    from rich.align import Align
    from rich import box
    from rich.prompt import Prompt, Confirm
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.live import Live
    from rich.padding import Padding
except ImportError:
    print("ERROR: 'rich' is not installed. Run: pip install rich")
    sys.exit(1)

# ── InquirerPy ──────────────────────────────────────────────
try:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator
    from InquirerPy.utils import get_style
except ImportError:
    print("ERROR: 'InquirerPy' is not installed. Run: pip install InquirerPy")
    sys.exit(1)

# ── yt-dlp ──────────────────────────────────────────────────
try:
    import yt_dlp
except ImportError:
    print("ERROR: 'yt-dlp' is not installed. Run: pip install yt-dlp")
    sys.exit(1)

# ── requests (optional, for Genius) ─────────────────────────
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ════════════════════════════════════════════════════════════
#  GLOBAL CONSOLE & STYLE
# ════════════════════════════════════════════════════════════

console = Console()

THEMES: Dict[str, Dict[str, str]] = {
    "cyan": {
        "label": "Cyan",
        "primary": "#00d7ff",
        "accent": "#00ff87",
        "separator": "#444444",
    },
    "green": {
        "label": "Green",
        "primary": "#00ff87",
        "accent": "#afff5f",
        "separator": "#3a4a3a",
    },
    "magenta": {
        "label": "Magenta",
        "primary": "#ff5fd7",
        "accent": "#ffd7ff",
        "separator": "#554455",
    },
    "amber": {
        "label": "Amber",
        "primary": "#ffaf00",
        "accent": "#ffd75f",
        "separator": "#554422",
    },
    "blue": {
        "label": "Blue",
        "primary": "#5fafff",
        "accent": "#87d7ff",
        "separator": "#334455",
    },
}

CURRENT_THEME = "cyan"


def _build_menu_style(theme_name: str):
    theme = THEMES.get(theme_name, THEMES["cyan"])
    return get_style({
        "question":         f"{theme['primary']} bold",
        "answer":           f"{theme['accent']} bold",
        "pointer":          f"{theme['primary']} bold",
        "highlighted":      f"{theme['primary']} bold",
        "selected":         f"{theme['accent']} bold",
        "separator":        theme["separator"],
        "instruction":      "#777777 italic",
        "long_instruction": "#777777 italic",
        "input":            "#ffffff",
        "checkbox":         theme["primary"],
    })


MENU_STYLE = _build_menu_style(CURRENT_THEME)


def apply_theme(theme_name: str) -> str:
    global CURRENT_THEME, MENU_STYLE
    if theme_name not in THEMES:
        theme_name = "cyan"
    CURRENT_THEME = theme_name
    MENU_STYLE = _build_menu_style(theme_name)
    return theme_name


def theme_primary() -> str:
    return THEMES.get(CURRENT_THEME, THEMES["cyan"])["primary"]


def theme_accent() -> str:
    return THEMES.get(CURRENT_THEME, THEMES["cyan"])["accent"]

# ════════════════════════════════════════════════════════════
#  PATHS & CONSTANTS
# ════════════════════════════════════════════════════════════

APP_DIR      = Path.home() / ".songcli"
CONFIG_FILE  = APP_DIR / "config.json"
HISTORY_FILE = APP_DIR / "history.json"
CACHE_DIR    = APP_DIR / "cache"

VERSION      = "1.0.0"
MAX_HISTORY  = 500

QUALITY_CHOICES = [
    Choice("128",  " 128 kbps  [Low]"),
    Choice("192",  " 192 kbps  [Standard]"),
    Choice("256",  " 256 kbps  [High]"),
    Choice("320",  " 320 kbps  [Best MP3]"),
    Choice("flac", " FLAC      [Lossless]"),
]

STREAM_QUALITY_CHOICES = [
    Choice("128",  " 128 kbps  [Low]"),
    Choice("192",  " 192 kbps  [Standard]"),
    Choice("256",  " 256 kbps  [High]"),
    Choice("320",  " 320 kbps  [Best Available]"),
]

FORMAT_CHOICES = [
    Choice("mp3",  " MP3   — Universal compatibility"),
    Choice("m4a",  " M4A   — Apple / iTunes"),
    Choice("flac", " FLAC  — Lossless audio"),
    Choice("wav",  " WAV   — Uncompressed"),
    Choice("opus", " OPUS  — Efficient streaming"),
]

THEME_CHOICES = [
    Choice("cyan",    " Cyan     -> bright and clean"),
    Choice("green",   " Green    -> terminal style"),
    Choice("magenta", " Magenta  -> vivid accent"),
    Choice("amber",   " Amber    -> warm contrast"),
    Choice("blue",    " Blue     -> cool contrast"),
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "download_path":   str(Path.home() / "Music" / "songcli"),
    "default_quality": "192",
    "default_format":  "mp3",
    "embed_thumbnail": True,
    "add_metadata":    True,
    "max_results":     10,
    "genius_api_key":  "",
    "theme":           "cyan",
}

# ════════════════════════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════════════════════════

def ensure_dirs() -> None:
    for d in [APP_DIR, CACHE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict:
    ensure_dirs()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            cfg["theme"] = apply_theme(cfg.get("theme", "cyan"))
            return cfg
        except Exception:
            pass
    cfg = DEFAULT_CONFIG.copy()
    cfg["theme"] = apply_theme(cfg.get("theme", "cyan"))
    return cfg


def save_config(cfg: Dict) -> None:
    ensure_dirs()
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

# ════════════════════════════════════════════════════════════
#  HISTORY
# ════════════════════════════════════════════════════════════

def load_history() -> Dict:
    ensure_dirs()
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE) as f:
                h = json.load(f)
            h.setdefault("downloads", [])
            h.setdefault("searches", [])
            return h
        except Exception:
            pass
    return {"downloads": [], "searches": []}


def save_history(history: Dict) -> None:
    ensure_dirs()
    history["downloads"] = history["downloads"][-MAX_HISTORY:]
    history["searches"]  = history["searches"][-MAX_HISTORY:]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def log_download(entry: Dict) -> None:
    h = load_history()
    h["downloads"].append({**entry, "timestamp": datetime.now().isoformat()})
    save_history(h)


def log_search(query: str, result_count: int) -> None:
    h = load_history()
    h["searches"].append({
        "query": query,
        "result_count": result_count,
        "timestamp": datetime.now().isoformat(),
    })
    save_history(h)

# ════════════════════════════════════════════════════════════
#  BANNER
# ════════════════════════════════════════════════════════════

ASCII_LOGO = r"""
  ██████╗  ██████╗ ███╗   ██╗ ██████╗   ██████╗██╗      ██╗
 ██╔════╝ ██╔═══██╗████╗  ██║██╔════╝  ██╔════╝██║      ██║
 ╚█████╗  ██║   ██║██╔██╗ ██║██║  ███ ╗██║     ██║      ██║
  ╚═══██╗ ██║   ██║██║╚████ ║██║   ██ ║██║     ██║      ██║
 ██████╔╝ ╚██████╔╝██║ ╚███║╚██████╔╝  ╚██████╗███████╗ ██║
 ╚═════╝   ╚═════╝ ╚═╝  ╚══╝ ╚═════╝    ╚═════╝╚══════╝ ╚═╝
"""

TAGLINE = "  YouTube Music Downloader and Player  |  v" + VERSION
DIVIDER  = "  " + "─" * 62
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".wav", ".opus"}


def print_banner(animated: bool = False) -> None:
    console.clear()
    logo = Text(ASCII_LOGO, style="bold white")
    if animated:
        for line in ASCII_LOGO.strip("\n").splitlines():
            console.print(Text(line, style="bold white"), justify="center")
            time.sleep(0.04)
    else:
        console.print(logo, justify="center")
    console.print(Text(TAGLINE, style="bold white"), justify="center")
    console.print(Text(DIVIDER, style="dim white"), justify="center")
    console.print()

# ════════════════════════════════════════════════════════════
#  UTILITIES
# ════════════════════════════════════════════════════════════

def fmt_duration(seconds: Any) -> str:
    try:
        s = int(float(seconds))
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
    except Exception:
        return "N/A"


def fmt_views(n: Any) -> str:
    try:
        n = int(n)
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n/1_000:.0f}K"
        return str(n)
    except Exception:
        return "N/A"


def truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def check_tool(name: str) -> bool:
    return shutil.which(name) is not None


def press_enter(msg: str = "Press [Enter] to continue") -> None:
    console.print(f"\n[dim]  {msg}[/dim]")
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass


def playback_controls_panel() -> Panel:
    primary = theme_primary()
    controls = Table.grid(expand=True)
    controls.add_column(justify="left")
    controls.add_column(justify="left")
    controls.add_column(justify="left")
    controls.add_row(
        f"[bold {primary}]SPACE[/] Play/Pause",
        f"[bold {primary}]q[/] Stop",
        f"[bold {primary}]<- ->[/] Seek",
    )
    controls.add_row(
        f"[bold {primary}]L[/] Loop",
        f"[bold {primary}]M[/] Mute",
        f"[bold {primary}]9/0[/] Volume",
    )
    return Panel(
        controls,
        title="[bold cyan]Controls[/bold cyan]",
        border_style="dim",
        padding=(0, 2),
    )

# ════════════════════════════════════════════════════════════
#  SEARCH
# ════════════════════════════════════════════════════════════

def search_youtube(query: str, max_results: int = 10) -> List[Dict]:
    results: List[Dict] = []
    opts = {
        "quiet":        True,
        "no_warnings":  True,
        "extract_flat": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            if info and "entries" in info:
                for e in info["entries"]:
                    if e:
                        results.append({
                            "title":      e.get("title", "Unknown"),
                            "url":        f"https://www.youtube.com/watch?v={e.get('id','')}",
                            "id":         e.get("id", ""),
                            "duration":   fmt_duration(e.get("duration", 0)),
                            "uploader":   e.get("uploader", "Unknown"),
                            "view_count": fmt_views(e.get("view_count", 0)),
                            "thumbnail":  e.get("thumbnail", ""),
                        })
    except Exception as exc:
        console.print(f"[red]  [!] Search error: {exc}[/red]")
    return results


def fetch_video_info(url: str) -> Optional[Dict]:
    opts = {"quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title":      info.get("title", "Unknown"),
                "uploader":   info.get("uploader", "Unknown"),
                "duration":   fmt_duration(info.get("duration", 0)),
                "view_count": fmt_views(info.get("view_count", 0)),
                "url":        url,
            }
    except Exception as exc:
        console.print(f"[red]  [!] Error: {exc}[/red]")
        return None

# ════════════════════════════════════════════════════════════
#  DOWNLOAD ENGINE
# ════════════════════════════════════════════════════════════

class _ProgressState:
    def __init__(self):
        self.total      = 0
        self.downloaded = 0
        self.speed      = ""
        self.eta        = ""
        self.progress   = None
        self.task_id    = None

    def hook(self, d: Dict) -> None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            done  = d.get("downloaded_bytes", 0)
            if self.progress and self.task_id is not None:
                if total and self.total == 0:
                    self.total = total
                    self.progress.update(self.task_id, total=total)
                self.progress.update(self.task_id, completed=done)


def _build_ydl_opts(
    quality: str,
    fmt: str,
    download_path: str,
    embed_thumb: bool,
    add_meta: bool,
    hook,
) -> Dict:
    postprocessors: List[Dict] = []

    if fmt == "flac" or quality == "flac":
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": "flac",
        })
        final_fmt = "flac"
    else:
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": fmt,
            "preferredquality": quality,
        })
        final_fmt = fmt

    if add_meta:
        postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})

    if embed_thumb:
        postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})

    return {
        "format":         "bestaudio/best",
        "postprocessors": postprocessors,
        "outtmpl":        str(Path(download_path) / "%(title)s.%(ext)s"),
        "quiet":          True,
        "no_warnings":    True,
        "progress_hooks": [hook],
        "writethumbnail": embed_thumb,
    }


def find_downloaded_file(title: str, directory: str, fmt: str) -> Optional[str]:
    """Try to locate the output file yt-dlp produced."""
    directory_path = Path(directory)
    exts = [fmt, "mp3", "flac", "m4a", "wav", "opus"]
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
    for ext in exts:
        p = directory_path / f"{safe_title}.{ext}"
        if p.exists():
            return str(p)
    # Broader glob fallback
    for ext in exts:
        matches = list(directory_path.glob(f"*.{ext}"))
        if matches:
            matches.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            return str(matches[0])
    return None


def download_song(
    url: str,
    config: Dict,
    quality: str,
    fmt: str,
    download_path: str,
    song_info: Optional[Dict] = None,
) -> Optional[str]:
    """Core download function. Returns path to downloaded file or None."""
    Path(download_path).mkdir(parents=True, exist_ok=True)

    if song_info is None:
        console.print("\n[cyan]  [*][/cyan] Fetching song info…")
        song_info = fetch_video_info(url)
        if not song_info:
            return None

    title = song_info.get("title", "Unknown")
    uploader = song_info.get("uploader") or song_info.get("channel") or "Unknown"
    duration = song_info.get("duration", "Unknown")

    # ── Info panel ──────────────────────────────────────────
    q_label = f"{quality} kbps" if quality != "flac" else "FLAC"
    info_tbl = Table(box=None, show_header=False, padding=(0, 2))
    info_tbl.add_column("K", style="dim cyan",  no_wrap=True, width=14)
    info_tbl.add_column("V", style="white",      no_wrap=False)
    info_tbl.add_row("[*] Title",    title)
    info_tbl.add_row("[*] Artist",   uploader)
    info_tbl.add_row("[*] Duration", duration)
    info_tbl.add_row("[*] Quality",  q_label)
    info_tbl.add_row("[*] Format",   fmt.upper())
    info_tbl.add_row("[*] Saving to", download_path)
    console.print(Panel(info_tbl, title="[bold cyan]Song Info[/bold cyan]",
                        border_style="cyan", padding=(1, 1)))
    console.print()
    console.print(f"  [dim]Title:[/dim] [white]{truncate(title, 86)}[/white]")
    console.print()

    ps = _ProgressState()
    opts = _build_ydl_opts(
        quality, fmt, download_path,
        config.get("embed_thumbnail", True),
        config.get("add_metadata", True),
        ps.hook,
    )

    downloaded_file: Optional[str] = None

    with Progress(
        SpinnerColumn(spinner_name="dots", style="cyan"),
        TextColumn("  [bold cyan]Downloading[/bold cyan]"),
        BarColumn(bar_width=None, style="dim cyan", complete_style="bright_cyan"),
        "[progress.percentage]{task.percentage:>3.0f}%",
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    ) as prog:
        task = prog.add_task("download", total=None)
        ps.progress = prog
        ps.task_id  = task

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            prog.update(task, completed=prog.tasks[task].total or 100,
                        total=prog.tasks[task].total or 100)
        except yt_dlp.utils.DownloadError as exc:
            console.print(f"\n[red]  [!] Download error: {exc}[/red]")
            return None

    downloaded_file = find_downloaded_file(title, download_path, fmt)

    if downloaded_file:
        console.print(f"\n[green]  [+] Download complete![/green]")
        console.print(f"[dim]      Saved to: {downloaded_file}[/dim]\n")
        log_download({
            "title":    title,
            "artist":   uploader,
            "url":      url,
            "quality":  quality,
            "format":   fmt,
            "path":     downloaded_file,
            "duration": duration,
        })
    else:
        console.print("\n[yellow]  [~] Download may have completed but file not located.[/yellow]")

    return downloaded_file

# ════════════════════════════════════════════════════════════
#  LYRICS
# ════════════════════════════════════════════════════════════

def _extract_artist(title: str) -> str:
    """Try to pull artist from 'Artist - Title' format."""
    if " - " in title:
        return title.split(" - ")[0].strip()
    return "Unknown"


def fetch_genius_lyrics(title: str, artist: str, api_key: str) -> Optional[str]:
    if not HAS_REQUESTS or not api_key:
        return None
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        r = requests.get(
            "https://api.genius.com/search",
            headers=headers,
            params={"q": f"{artist} {title}"},
            timeout=6,
        )
        if r.status_code != 200:
            return None
        hits = r.json().get("response", {}).get("hits", [])
        if not hits:
            return None
        song_path = hits[0]["result"]["path"]
        page = requests.get(f"https://genius.com{song_path}", timeout=8)
        blocks = re.findall(
            r'data-lyrics-container="true"[^>]*>(.*?)</div>',
            page.text, re.DOTALL,
        )
        if blocks:
            raw = "\n".join(blocks)
            clean = re.sub(r"<br\s*/?>", "\n", raw)
            clean = re.sub(r"<[^>]+>", "", clean)
            clean = re.sub(r"\n{3,}", "\n\n", clean)
            return clean.strip()
    except Exception:
        pass
    return None


def fallback_lyrics(title: str, artist: str) -> str:
    return (
        f"  Lyrics not available for:\n"
        f"  {title}\n"
        f"  by {artist}\n\n"
        f"  Tip: Add a Genius API key in Settings to enable lyrics.\n"
        f"  Visit: https://genius.com/api-clients\n"
    )

# ════════════════════════════════════════════════════════════
#  PLAYER
# ════════════════════════════════════════════════════════════

def play_song(filepath: str, title: str, artist: str, config: Dict) -> None:
    if not check_tool("mpv"):
        console.print(
            Panel(
                "[red]  [!] mpv is not installed or not in PATH.\n"
                "      Install mpv: https://mpv.io/installation/[/red]",
                border_style="red",
            )
        )
        press_enter()
        return

    print_banner()
    console.print(Rule("[bold cyan][ FETCHING LYRICS ][/bold cyan]", style="dim cyan"))
    console.print()

    api_key = config.get("genius_api_key", "")
    lyrics  = fetch_genius_lyrics(title, artist, api_key)
    lyric_src = "Genius"
    if not lyrics:
        lyrics    = fallback_lyrics(title, artist)
        lyric_src = "Fallback"

    lyric_lines   = lyrics.split("\n")
    lyric_display = "\n".join(
        f"  [white]{ln}[/white]" if ln.strip() else ""
        for ln in lyric_lines[:22]
    )

    print_banner()

    # Now-playing panel
    np_content = (
        f"  [bold white]{title}[/bold white]\n"
        f"  [dim cyan]Artist:[/dim cyan]  [cyan]{artist}[/cyan]\n"
        f"  [dim cyan]File:[/dim cyan]    [dim]{Path(filepath).name}[/dim]\n"
        f"  [dim cyan]Lyrics:[/dim cyan]  [dim]{lyric_src}[/dim]\n\n"
        f"  [dim]{'─' * 50}[/dim]\n\n"
        f"{lyric_display}"
    )
    console.print(Panel(
        np_content,
        title="[bold cyan][ NOW PLAYING ][/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    ))

    console.print(playback_controls_panel())
    console.print()

    try:
        subprocess.run([
            "mpv",
            "--no-video",
            "--term-osd-bar",
            "--term-osd-bar-chars=━━ ━━",
            "--term-playing-msg=  Duration: ${=duration} | Bitrate: ${=audio-bitrate}",
            filepath,
        ])
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        console.print(f"[red]  [!] Playback error: {exc}[/red]")

    press_enter()


def _stream_format_selector(quality: str) -> str:
    if quality == "320":
        return "bestaudio/best"
    return f"bestaudio[abr<={quality}]/bestaudio/best"


def play_stream(url: str, title: str, artist: str, quality: str, config: Dict) -> None:
    if not check_tool("mpv"):
        console.print(
            Panel(
                "[red]  [!] mpv is not installed or not in PATH.\n"
                "      Install mpv: https://mpv.io/installation/[/red]",
                border_style="red",
            )
        )
        press_enter()
        return

    if not check_tool("yt-dlp"):
        console.print(
            Panel(
                "[red]  [!] yt-dlp command is not installed or not in PATH.\n"
                "      Install/upgrade yt-dlp: python3 -m pip install -U yt-dlp[/red]",
                border_style="red",
            )
        )
        press_enter()
        return

    print_banner()
    console.print(Rule("[bold cyan][ FETCHING LYRICS ][/bold cyan]", style="dim cyan"))
    console.print()

    api_key = config.get("genius_api_key", "")
    lyrics = fetch_genius_lyrics(title, artist, api_key)
    lyric_src = "Genius"
    if not lyrics:
        lyrics = fallback_lyrics(title, artist)
        lyric_src = "Fallback"

    lyric_lines = lyrics.split("\n")
    lyric_display = "\n".join(
        f"  [white]{ln}[/white]" if ln.strip() else ""
        for ln in lyric_lines[:22]
    )

    q_label = f"{quality} kbps" if quality != "320" else "Best available"
    print_banner()
    np_content = (
        f"  [bold white]{title}[/bold white]\n"
        f"  [dim cyan]Artist:[/dim cyan]   [cyan]{artist}[/cyan]\n"
        f"  [dim cyan]Source:[/dim cyan]   [dim]YouTube stream[/dim]\n"
        f"  [dim cyan]Quality:[/dim cyan]  [white]{q_label}[/white]\n"
        f"  [dim cyan]Lyrics:[/dim cyan]   [dim]{lyric_src}[/dim]\n\n"
        f"  [dim]{'─' * 50}[/dim]\n\n"
        f"{lyric_display}"
    )
    console.print(Panel(
        np_content,
        title="[bold cyan][ NOW STREAMING ][/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    ))

    console.print(playback_controls_panel())
    console.print()

    try:
        subprocess.run([
            "mpv",
            "--no-video",
            "--term-osd-bar",
            "--term-osd-bar-chars=━━ ━━",
            "--term-playing-msg=  Duration: ${=duration} | Bitrate: ${=audio-bitrate}",
            f"--ytdl-format={_stream_format_selector(quality)}",
            url,
        ])
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        console.print(f"[red]  [!] Streaming error: {exc}[/red]")

    press_enter()


def _find_downloaded_songs(directory: str) -> List[Path]:
    base = Path(directory).expanduser()
    if not base.exists() or not base.is_dir():
        return []

    songs = [
        p for p in base.rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    ]
    songs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return songs


def _normalize_song_name(filepath: Path) -> str:
    name = filepath.stem.lower()
    name = re.sub(r"\s*[\(\[]\d+[\)\]]\s*$", "", name)
    name = re.sub(r"\s+copy(?:\s+\d+)?$", "", name)
    name = re.sub(r"[^a-z0-9]+", " ", name)
    return " ".join(name.split())


def _history_match_for_file(filepath: Path) -> Optional[Dict]:
    try:
        resolved = str(filepath.resolve())
    except Exception:
        resolved = str(filepath)

    downloads = load_history().get("downloads", [])
    for entry in reversed(downloads):
        entry_path = entry.get("path", "")
        try:
            if entry_path and str(Path(entry_path).expanduser().resolve()) == resolved:
                return entry
        except Exception:
            if entry_path == str(filepath):
                return entry
    return None


def flow_play_downloaded_songs(config: Dict) -> None:
    while True:
        print_banner()
        download_dir = config.get("download_path", str(Path.home() / "Music" / "songcli"))
        songs = _find_downloaded_songs(download_dir)
        console.print(Panel(
            f"[bold white]Downloaded Songs[/bold white]\n\n"
            f"  [dim]Folder[/dim]  [white]{download_dir}[/white]\n"
            f"  [dim]Found[/dim]   [white]{len(songs)} audio file(s)[/white]",
            border_style="cyan",
            padding=(1, 2),
        ))

        if not songs:
            console.print(
                "  [yellow]No downloaded songs were found in this folder.[/yellow]\n"
                "  [dim]Change the download path in Settings or download a song first.[/dim]"
            )
            press_enter()
            return

        choices = []
        for i, song in enumerate(songs[:100], 1):
            label = f"  {i:02d}  {truncate(song.stem, 54)}  [dim]{song.suffix.lower()}[/dim]"
            choices.append(Choice(str(song), label))
        choices.append(Separator())
        choices.append(Choice("back", "  <- Back"))

        picked = inquirer.select(
            message="Choose a downloaded song:",
            choices=choices,
            style=MENU_STYLE,
        ).execute()

        if picked == "back":
            return

        filepath = Path(picked)
        history_entry = _history_match_for_file(filepath)
        title = history_entry.get("title", filepath.stem) if history_entry else filepath.stem
        artist = history_entry.get("artist", "Unknown") if history_entry else "Unknown"
        play_song(str(filepath), title, artist, config)


def _download_stream_selection(
    url: str,
    config: Dict,
    quality: str,
    song_info: Optional[Dict],
) -> None:
    fmt = pick_format(config.get("default_format", "mp3"))
    path = pick_path(config.get("download_path", str(Path.home() / "Music" / "songcli")))
    result = download_song(url, config, quality, fmt, path, song_info=song_info)
    if result:
        title = song_info["title"] if song_info else Path(result).stem
        artist = song_info["uploader"] if song_info else "Unknown"
        _offer_playback(result, title, artist, config)
    else:
        press_enter()


def flow_play_stream_songs(config: Dict) -> None:
    while True:
        print_banner()
        console.print(Panel(
            "[bold white]Stream Songs[/bold white]\n\n"
            "  [dim]Search YouTube, choose a result, select quality, then play with mpv.[/dim]",
            border_style="cyan",
            padding=(1, 2),
        ))

        query = Prompt.ask("\n  [cyan]Search song[/cyan]  [dim](blank = back)[/dim]").strip()
        if not query:
            return

        console.print(f"\n  [cyan]Searching[/cyan] [white]{query!r}[/white]\n")
        max_r = config.get("max_results", 10)
        results = search_youtube(query, max_r)
        log_search(query, len(results))

        if not results:
            console.print("  [red]No results found. Try a more specific artist or song title.[/red]")
            press_enter()
            continue

        tbl = Table(
            box=box.SIMPLE_HEAD,
            border_style="dim cyan",
            show_header=True,
            header_style="bold cyan",
            padding=(0, 1),
        )
        tbl.add_column("#", width=4, justify="right")
        tbl.add_column("Title", width=42, no_wrap=True)
        tbl.add_column("Artist", width=22, no_wrap=True)
        tbl.add_column("Time", width=7, justify="right")
        tbl.add_column("Views", width=7, justify="right")

        for i, r in enumerate(results, 1):
            tbl.add_row(
                f"[dim]{i}[/dim]",
                truncate(r["title"], 41),
                truncate(r["uploader"], 21),
                r["duration"],
                r["view_count"],
            )
        console.print(tbl)
        console.print()

        song_choices = [
            Choice(
                r["url"],
                f"  -> {i:02d}  {truncate(r['title'],44)}  [dim]{truncate(r['uploader'],20)} | {r['duration']}[/dim]",
            )
            for i, r in enumerate(results, 1)
        ]
        song_choices.append(Separator())
        song_choices.append(Choice("back", "  <- Back"))

        picked_url = inquirer.select(
            message="Select a song to stream:",
            choices=song_choices,
            style=MENU_STYLE,
        ).execute()

        if picked_url == "back":
            continue

        picked_info = next((r for r in results if r["url"] == picked_url), None)
        if picked_info:
            console.print(Panel(
                f"[bold white]{picked_info['title']}[/bold white]\n"
                f"  [dim]Artist[/dim]    [cyan]{picked_info['uploader']}[/cyan]\n"
                f"  [dim]Duration[/dim]  [white]{picked_info['duration']}[/white]\n"
                f"  [dim]Views[/dim]     [white]{picked_info['view_count']}[/white]",
                title="[bold cyan]Selected Track[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            ))
        quality = inquirer.select(
            message="Choose streaming quality:",
            choices=STREAM_QUALITY_CHOICES,
            default=config.get("default_quality", "192")
            if config.get("default_quality") != "flac"
            else "192",
            style=MENU_STYLE,
        ).execute()

        title = picked_info["title"] if picked_info else "Unknown"
        artist = picked_info["uploader"] if picked_info else "Unknown"

        action = inquirer.select(
            message="Choose action:",
            choices=[
                Choice("stream",          "  -> Stream now"),
                Choice("stream_download", "  -> Stream now, then download"),
                Choice("download",        "  -> Download without streaming"),
                Choice("back",            "  <- Back to results"),
            ],
            style=MENU_STYLE,
        ).execute()

        if action == "back":
            continue
        if action in {"stream", "stream_download"}:
            play_stream(picked_url, title, artist, quality, config)
        if action == "stream" and Confirm.ask("  Download this song now?", default=False):
            _download_stream_selection(picked_url, config, quality, picked_info)
        elif action in {"stream_download", "download"}:
            _download_stream_selection(picked_url, config, quality, picked_info)


def flow_play_or_stream_songs(config: Dict) -> None:
    while True:
        print_banner()
        download_dir = config.get("download_path", str(Path.home() / "Music" / "songcli"))
        console.print(Panel(
            "[bold white]Play/Stream Songs[/bold white]\n\n"
            "  [dim]Stream from YouTube or play files already saved on this machine.[/dim]\n"
            f"  [dim]Downloads[/dim]  [white]{download_dir}[/white]",
            border_style="cyan",
            padding=(1, 2),
        ))
        choice = inquirer.select(
            message="Choose playback mode:",
            choices=[
                Choice("stream", "  -> [1]  Stream songs from YouTube"),
                Choice("local",  "  -> [2]  Play downloaded songs"),
                Choice("back",   "  <- Back to Main Menu"),
            ],
            style=MENU_STYLE,
        ).execute()

        if choice == "stream":
            flow_play_stream_songs(config)
        elif choice == "local":
            flow_play_downloaded_songs(config)
        elif choice == "back":
            return


def flow_check_ytdlp_update() -> None:
    print_banner()
    console.print(Panel("[bold white][ YT-DLP UPDATE CHECK ][/bold white]",
                        border_style="white", padding=(0, 2)))

    current = getattr(yt_dlp.version, "__version__", "Unknown")
    console.print(f"\n  [cyan][*][/cyan] Installed yt-dlp: [white]{current}[/white]")

    if not HAS_REQUESTS:
        console.print("  [red][!] Cannot check online: requests is not installed.[/red]")
        press_enter()
        return

    try:
        console.print("  [cyan][*][/cyan] Checking latest release…")
        response = requests.get(
            "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest",
            timeout=8,
        )
        response.raise_for_status()
        latest = response.json().get("tag_name", "").lstrip("v")
    except Exception as exc:
        console.print(f"  [red][!] Update check failed: {exc}[/red]")
        press_enter()
        return

    if not latest:
        console.print("  [yellow][~] Could not read latest yt-dlp version.[/yellow]")
    elif current == latest:
        console.print(f"  [green][+] yt-dlp is up to date: {latest}[/green]")
    else:
        console.print(
            f"  [yellow][~] Update available:[/yellow] "
            f"[white]{current}[/white] -> [green]{latest}[/green]"
        )
        console.print("  [dim]Run: python3 -m pip install -U yt-dlp[/dim]")

    press_enter()


def flow_duplicate_finder(config: Dict) -> None:
    print_banner()
    download_dir = config.get("download_path", str(Path.home() / "Music" / "songcli"))
    console.print(Panel(
        f"[bold white][ DUPLICATE FINDER ][/bold white]\n\n"
        f"  [dim]Location:[/dim] [white]{download_dir}[/white]",
        border_style="white",
        padding=(1, 2),
    ))

    songs = _find_downloaded_songs(download_dir)
    if not songs:
        console.print("  [yellow][~] No downloaded songs found in the default location.[/yellow]")
        press_enter()
        return

    groups: Dict[str, List[Path]] = {}
    for song in songs:
        key = _normalize_song_name(song)
        if key:
            groups.setdefault(key, []).append(song)

    duplicates = [paths for paths in groups.values() if len(paths) > 1]
    duplicates.sort(key=lambda paths: paths[0].stem.lower())

    if not duplicates:
        console.print(f"  [green][+] No duplicate songs found among {len(songs)} audio files.[/green]")
        press_enter()
        return

    tbl = Table(
        title="[bold yellow]Possible Duplicate Songs[/bold yellow]",
        box=box.SIMPLE_HEAD,
        border_style="yellow",
        show_header=True,
        header_style="bold yellow",
        padding=(0, 1),
    )
    tbl.add_column("#", width=4, justify="right")
    tbl.add_column("Song", width=38, no_wrap=True)
    tbl.add_column("Files", width=7, justify="right")
    tbl.add_column("Locations", width=58)

    for i, paths in enumerate(duplicates[:50], 1):
        locations = "\n".join(f"[dim]{p.name}[/dim]" for p in paths[:4])
        if len(paths) > 4:
            locations += f"\n[dim]… {len(paths) - 4} more[/dim]"
        tbl.add_row(
            str(i),
            truncate(paths[0].stem, 37),
            str(len(paths)),
            locations,
        )

    console.print(tbl)
    console.print(
        f"\n  [yellow][~][/yellow] Found [white]{len(duplicates)}[/white] duplicate group(s) "
        f"among [white]{len(songs)}[/white] audio files."
    )
    press_enter()

# ════════════════════════════════════════════════════════════
#  QUALITY / FORMAT / PATH PICKER
# ════════════════════════════════════════════════════════════

def pick_quality(default: str) -> str:
    return inquirer.select(
        message="Select audio quality:",
        choices=QUALITY_CHOICES,
        default=default,
        style=MENU_STYLE,
    ).execute()


def pick_format(default: str) -> str:
    return inquirer.select(
        message="Select audio format:",
        choices=FORMAT_CHOICES,
        default=default,
        style=MENU_STYLE,
    ).execute()


def pick_path(default_path: str) -> str:
    console.print(f"\n[dim]  Default path: {default_path}[/dim]")
    raw = Prompt.ask(
        "  [cyan][?][/cyan] Download path  [dim](Enter = use default)[/dim]",
        default="",
    ).strip()
    return raw if raw else default_path


def pick_qfp(config: Dict) -> Tuple[str, str, str]:
    quality = pick_quality(config.get("default_quality", "192"))
    fmt     = pick_format(config.get("default_format", "mp3"))
    path    = pick_path(config.get("download_path", str(Path.home() / "Music")))
    return quality, fmt, path

# ════════════════════════════════════════════════════════════
#  FLOW — DOWNLOAD SONG
# ════════════════════════════════════════════════════════════

def flow_download_song(config: Dict) -> None:
    while True:
        print_banner()
        console.print(Panel("[bold cyan]Download Song[/bold cyan]",
                            border_style="cyan", padding=(0, 2)))

        method = inquirer.select(
            message="Select download method:",
            choices=[
                Choice("search", "  -> [1]  Search YouTube by song name"),
                Choice("link",   "  -> [2]  Download from YouTube link"),
                Choice("back",   "  <- Back to Main Menu"),
            ],
            style=MENU_STYLE,
        ).execute()

        if method == "back":
            break

        # ── Direct link ─────────────────────────────────────
        if method == "link":
            url = Prompt.ask("\n  [cyan][?][/cyan] Paste YouTube URL").strip()
            if not url:
                continue

            quality, fmt, path = pick_qfp(config)
            result = download_song(url, config, quality, fmt, path)

            if result:
                _offer_playback(result, Path(result).stem, "Unknown", config)
            else:
                press_enter()
            continue

        # ── Search ──────────────────────────────────────────
        if method == "search":
            query = Prompt.ask("\n  [cyan][?][/cyan] Search song").strip()
            if not query:
                continue

            console.print(f"\n  [cyan]Searching[/cyan] [white]{query!r}[/white]\n")
            max_r   = config.get("max_results", 10)
            results = search_youtube(query, max_r)
            log_search(query, len(results))

            if not results:
                console.print("  [red][!] No results found.[/red]")
                press_enter()
                continue

            # Display result table
            tbl = Table(
                box=box.SIMPLE_HEAD, border_style="dim cyan",
                show_header=True, header_style="bold cyan",
                padding=(0, 1),
            )
            tbl.add_column("#",       width=4,  justify="right")
            tbl.add_column("Title",   width=42, no_wrap=True)
            tbl.add_column("Artist",  width=22, no_wrap=True)
            tbl.add_column("Time",    width=7,  justify="right")
            tbl.add_column("Views",   width=7,  justify="right")

            for i, r in enumerate(results, 1):
                tbl.add_row(
                    f"[dim]{i}[/dim]",
                    truncate(r["title"],   41),
                    truncate(r["uploader"], 21),
                    r["duration"],
                    r["view_count"],
                )
            console.print(tbl)
            console.print()

            song_choices = [
                Choice(
                    r["url"],
                    f"  -> {i:02d}  {truncate(r['title'],44)}  [dim]{truncate(r['uploader'],20)} | {r['duration']}[/dim]",
                )
                for i, r in enumerate(results, 1)
            ]
            song_choices.append(Separator())
            song_choices.append(Choice("back", "  <- Back"))

            picked_url = inquirer.select(
                message="Select a song:",
                choices=song_choices,
                style=MENU_STYLE,
            ).execute()

            if picked_url == "back":
                continue

            picked_info = next((r for r in results if r["url"] == picked_url), None)
            quality, fmt, path = pick_qfp(config)
            result = download_song(
                picked_url, config, quality, fmt, path,
                song_info=picked_info,
            )

            if result:
                title  = picked_info["title"]    if picked_info else Path(result).stem
                artist = picked_info["uploader"] if picked_info else "Unknown"
                _offer_playback(result, title, artist, config)
            else:
                press_enter()


def _offer_playback(filepath: str, title: str, artist: str, config: Dict) -> None:
    choice = inquirer.select(
        message="Song downloaded! What would you like to do?",
        choices=[
            Choice("play",  "  -> Play now with mpv"),
            Choice("skip",  "  -> Skip playback"),
        ],
        style=MENU_STYLE,
    ).execute()
    if choice == "play":
        play_song(filepath, title, artist, config)

# ════════════════════════════════════════════════════════════
#  FLOW — DOWNLOAD PLAYLIST
# ════════════════════════════════════════════════════════════

def flow_download_playlist(config: Dict) -> None:
    print_banner()
    console.print(Panel("[bold cyan][ DOWNLOAD PLAYLIST ][/bold cyan]",
                        border_style="cyan", padding=(0, 2)))

    url = Prompt.ask("\n  [cyan][?][/cyan] Paste playlist URL").strip()
    if not url:
        return

    console.print("\n  [cyan][*][/cyan] Fetching playlist info… this may take a moment.\n")

    entries: List[Dict] = []
    playlist_title = "Unknown Playlist"

    try:
        opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                playlist_title = info.get("title", "Unknown Playlist")
                for e in (info.get("entries") or []):
                    if e:
                        entries.append({
                            "title":    e.get("title", "Unknown"),
                            "id":       e.get("id", ""),
                            "url":      f"https://www.youtube.com/watch?v={e.get('id','')}",
                            "duration": fmt_duration(e.get("duration", 0)),
                            "uploader":  e.get("uploader") or e.get("channel") or "Unknown",
                        })
    except Exception as exc:
        console.print(f"  [red][!] Error fetching playlist: {exc}[/red]")
        press_enter()
        return

    if not entries:
        console.print("  [red][!] No tracks found in this playlist.[/red]")
        press_enter()
        return

    console.print(f"  [green][+][/green] Found [bold]{len(entries)}[/bold] tracks in [cyan]{playlist_title}[/cyan]\n")

    mode = inquirer.select(
        message="How would you like to download?",
        choices=[
            Choice("all",    f"  -> [1]  Download all {len(entries)} songs"),
            Choice("select", "  -> [2]  Select individual songs"),
            Choice("back",   "  <- Back"),
        ],
        style=MENU_STYLE,
    ).execute()

    if mode == "back":
        return

    to_download = entries

    if mode == "select":
        checkboxes = [
            Choice(i, f"  {i+1:02d}.  {truncate(e['title'], 48)}  [{e['duration']}]")
            for i, e in enumerate(entries)
        ]
        chosen_idxs = inquirer.checkbox(
            message="Select tracks  [Space=toggle, Enter=confirm]:",
            choices=checkboxes,
            style=MENU_STYLE,
        ).execute()

        if not chosen_idxs:
            console.print("  [yellow][~] No songs selected.[/yellow]")
            press_enter()
            return
        to_download = [entries[i] for i in chosen_idxs]

    quality, fmt, path = pick_qfp(config)

    console.print(f"\n  [cyan][*][/cyan] Downloading [bold]{len(to_download)}[/bold] songs…\n")
    failed = 0
    for idx, song in enumerate(to_download, 1):
        console.rule(
            f"[dim cyan]  Track {idx}/{len(to_download)}: {truncate(song['title'], 45)}[/dim cyan]",
            style="dim cyan",
        )
        result = download_song(song["url"], config, quality, fmt, path, song_info=song)
        if not result:
            failed += 1

    console.print()
    console.print(
        f"  [green][+] Playlist download complete![/green]  "
        f"[white]{len(to_download) - failed}[/white] succeeded"
        + (f"  [red]{failed} failed[/red]" if failed else "")
    )
    press_enter()

# ════════════════════════════════════════════════════════════
#  FLOW — HISTORY
# ════════════════════════════════════════════════════════════

def flow_history(config: Dict) -> None:
    while True:
        print_banner()
        h = load_history()

        choice = inquirer.select(
            message="History Menu:",
            choices=[
                Choice("dl",     f"  -> [1]  Download history  ({len(h['downloads'])} entries)"),
                Choice("search", f"  -> [2]  Search history    ({len(h['searches'])} entries)"),
                Choice("export", "  -> [3]  Export history to JSON file"),
                Choice("clear",  "  -> [4]  Clear all history"),
                Choice("back",   "  <- Back to Main Menu"),
            ],
            style=MENU_STYLE,
        ).execute()

        if choice == "back":
            break

        if choice == "dl":
            _show_download_history(h)
        elif choice == "search":
            _show_search_history(h)
        elif choice == "export":
            _export_history(h)
        elif choice == "clear":
            if Confirm.ask("  [red]Clear ALL history? This cannot be undone.[/red]"):
                save_history({"downloads": [], "searches": []})
                console.print("  [green][+] History cleared.[/green]")
                time.sleep(1)


def _show_download_history(h: Dict) -> None:
    console.clear()
    print_banner()
    entries = h.get("downloads", [])
    if not entries:
        console.print(Panel("  [yellow]No download history found.[/yellow]",
                            border_style="yellow"))
        press_enter()
        return

    tbl = Table(
        title="[bold cyan]Download History[/bold cyan]",
        box=box.ROUNDED, border_style="cyan",
        show_lines=False, padding=(0, 1),
    )
    tbl.add_column("#",       width=4,  justify="right", style="dim")
    tbl.add_column("Title",   width=36, no_wrap=True)
    tbl.add_column("Artist",  width=22, no_wrap=True, style="cyan")
    tbl.add_column("Quality", width=9,  justify="center", style="green")
    tbl.add_column("Fmt",     width=6,  justify="center", style="yellow")
    tbl.add_column("Date",    width=19, style="dim")

    shown = list(reversed(entries[-50:]))
    for i, e in enumerate(shown, 1):
        ts = e.get("timestamp", "")[:19].replace("T", " ")
        tbl.add_row(
            str(i),
            truncate(e.get("title", "N/A"), 35),
            truncate(e.get("artist", "N/A"), 21),
            e.get("quality", "N/A"),
            e.get("format", "N/A").upper(),
            ts,
        )

    console.print(tbl)
    console.print(f"\n  [dim]Showing last 50 of {len(entries)} downloads[/dim]")
    press_enter()


def _show_search_history(h: Dict) -> None:
    console.clear()
    print_banner()
    entries = h.get("searches", [])
    if not entries:
        console.print(Panel("  [yellow]No search history found.[/yellow]",
                            border_style="yellow"))
        press_enter()
        return

    tbl = Table(
        title="[bold cyan]Search History[/bold cyan]",
        box=box.ROUNDED, border_style="cyan",
        show_lines=False, padding=(0, 1),
    )
    tbl.add_column("#",       width=4,  justify="right", style="dim")
    tbl.add_column("Query",   width=44)
    tbl.add_column("Results", width=9,  justify="center", style="green")
    tbl.add_column("Date",    width=19, style="dim")

    shown = list(reversed(entries[-50:]))
    for i, e in enumerate(shown, 1):
        ts = e.get("timestamp", "")[:19].replace("T", " ")
        tbl.add_row(
            str(i),
            truncate(e.get("query", "N/A"), 43),
            str(e.get("result_count", "N/A")),
            ts,
        )

    console.print(tbl)
    console.print(f"\n  [dim]Showing last 50 of {len(entries)} searches[/dim]")
    press_enter()


def _export_history(h: Dict) -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out   = Path.home() / f"songcli_history_{stamp}.json"
    try:
        with open(out, "w") as f:
            json.dump(h, f, indent=2)
        console.print(f"  [green][+] Exported to:[/green] {out}")
    except Exception as exc:
        console.print(f"  [red][!] Export failed: {exc}[/red]")
    press_enter()

# ════════════════════════════════════════════════════════════
#  FLOW — SETTINGS
# ════════════════════════════════════════════════════════════

def flow_settings(config: Dict) -> Dict:
    while True:
        print_banner()

        q_label = f"{config['default_quality']} kbps" \
            if config["default_quality"] != "flac" else "FLAC"

        status_panel = (
            f"  [dim]Download Path[/dim]       [white]{config['download_path']}[/white]\n"
            f"  [dim]Default Quality[/dim]     [white]{q_label}[/white]\n"
            f"  [dim]Default Format[/dim]      [white]{config['default_format'].upper()}[/white]\n"
            f"  [dim]Embed Thumbnail[/dim]     [white]{'Yes' if config['embed_thumbnail'] else 'No'}[/white]\n"
            f"  [dim]Add Metadata[/dim]        [white]{'Yes' if config['add_metadata'] else 'No'}[/white]\n"
            f"  [dim]Max Search Results[/dim]  [white]{config['max_results']}[/white]\n"
            f"  [dim]Theme[/dim]               [white]{THEMES.get(config.get('theme', 'cyan'), THEMES['cyan'])['label']}[/white]\n"
            f"  [dim]Genius API Key[/dim]      "
            + ("[green]Set[/green]" if config.get("genius_api_key") else "[red]Not set[/red]")
        )
        console.print(Panel(status_panel,
                            title="[bold cyan]Current Settings[/bold cyan]",
                            border_style="cyan", padding=(1, 2)))

        action = inquirer.select(
            message="What would you like to change?",
            choices=[
                Choice("path",      "  -> [1]  Change download path"),
                Choice("quality",   "  -> [2]  Change default quality"),
                Choice("format",    "  -> [3]  Change default format"),
                Choice("thumb",     "  -> [4]  Toggle embed thumbnail"),
                Choice("meta",      "  -> [5]  Toggle metadata"),
                Choice("results",   "  -> [6]  Max search results"),
                Choice("theme",     "  -> [7]  Change theme"),
                Choice("genius",    "  -> [8]  Set Genius API key"),
                Separator(),
                Choice("back",      "  <- Save and Back"),
            ],
            style=MENU_STYLE,
        ).execute()

        if action == "back":
            save_config(config)
            console.print("  [green][+] Settings saved.[/green]")
            time.sleep(0.8)
            break

        if action == "path":
            raw = Prompt.ask(
                f"  [cyan]New download path[/cyan]",
                default=config["download_path"],
            ).strip()
            try:
                resolved = str(Path(raw).expanduser().resolve())
                Path(resolved).mkdir(parents=True, exist_ok=True)
                config["download_path"] = resolved
                console.print(f"  [green][+] Path set:[/green] {resolved}")
            except Exception as exc:
                console.print(f"  [red][!] Invalid path: {exc}[/red]")
            save_config(config)
            time.sleep(0.8)

        elif action == "quality":
            config["default_quality"] = pick_quality(config["default_quality"])
            save_config(config)

        elif action == "format":
            config["default_format"] = pick_format(config["default_format"])
            save_config(config)

        elif action == "thumb":
            config["embed_thumbnail"] = not config["embed_thumbnail"]
            save_config(config)
            state = "enabled" if config["embed_thumbnail"] else "disabled"
            console.print(f"  [green][+] Embed thumbnail {state}.[/green]")
            time.sleep(0.8)

        elif action == "meta":
            config["add_metadata"] = not config["add_metadata"]
            save_config(config)
            state = "enabled" if config["add_metadata"] else "disabled"
            console.print(f"  [green][+] Metadata embedding {state}.[/green]")
            time.sleep(0.8)

        elif action == "results":
            raw = Prompt.ask(
                "  [cyan]Max search results (1–20)[/cyan]",
                default=str(config["max_results"]),
            ).strip()
            try:
                n = int(raw)
                if 1 <= n <= 20:
                    config["max_results"] = n
                    save_config(config)
                    console.print(f"  [green][+] Max results set to {n}.[/green]")
                else:
                    console.print("  [red][!] Must be 1–20.[/red]")
            except ValueError:
                console.print("  [red][!] Invalid number.[/red]")
            time.sleep(0.8)

        elif action == "theme":
            picked_theme = inquirer.select(
                message="Choose theme:",
                choices=THEME_CHOICES,
                default=config.get("theme", "cyan"),
                style=MENU_STYLE,
            ).execute()
            config["theme"] = apply_theme(picked_theme)
            save_config(config)
            console.print(
                f"  [green][+] Theme changed to {THEMES[config['theme']]['label']}.[/green]"
            )
            time.sleep(0.8)

        elif action == "genius":
            key = Prompt.ask(
                "  [cyan]Genius API key[/cyan]  [dim](blank to clear)[/dim]",
                default=config.get("genius_api_key", ""),
                password=True,
            ).strip()
            config["genius_api_key"] = key
            save_config(config)
            console.print(f"  [green][+] Genius API key {'saved' if key else 'cleared'}.[/green]")
            time.sleep(0.8)

    return config

# ════════════════════════════════════════════════════════════
#  DEPENDENCY CHECK
# ════════════════════════════════════════════════════════════

def check_dependencies() -> None:
    missing: List[str] = []

    if not check_tool("ffmpeg"):
        missing.append("ffmpeg  (required for audio conversion — https://ffmpeg.org)")
    if not check_tool("mpv"):
        missing.append("mpv     (optional, for playback — https://mpv.io)")
    if not HAS_REQUESTS:
        missing.append("requests  (optional, for Genius lyrics — pip install requests)")

    if missing:
        console.print(Panel(
            "  [yellow][~] Some optional/required tools are missing:[/yellow]\n\n"
            + "\n".join(f"  [dim]•  {m}[/dim]" for m in missing)
            + "\n\n  [dim]ffmpeg is required for format conversion.[/dim]",
            title="[bold yellow][ DEPENDENCY CHECK ][/bold yellow]",
            border_style="yellow", padding=(1, 2),
        ))
        time.sleep(2)

# ════════════════════════════════════════════════════════════
#  MAIN MENU
# ════════════════════════════════════════════════════════════

def main_menu(config: Dict) -> None:
    while True:
        print_banner()
        q_label = f"{config.get('default_quality', '192')} kbps"
        if config.get("default_quality") == "flac":
            q_label = "FLAC"
        theme_label = THEMES.get(config.get("theme", "cyan"), THEMES["cyan"])["label"]
        status = (
            f"  [dim]Download folder[/dim]  [white]{config.get('download_path')}[/white]\n"
            f"  [dim]Default quality[/dim]  [white]{q_label}[/white]    "
            f"[dim]Format[/dim]  [white]{config.get('default_format', 'mp3').upper()}[/white]    "
            f"[dim]Theme[/dim]  [white]{theme_label}[/white]"
        )
        console.print(Panel(
            status,
            title="[bold cyan]Current Setup[/bold cyan]",
            border_style="dim cyan",
            padding=(0, 2),
        ))

        choice = inquirer.select(
            message="Main Menu:",
            choices=[
                Separator("  ─── MUSIC ───────────────────────────────────"),
                Choice("song",     "   -> [1]  Download song"),
                Choice("playlist", "   -> [2]  Download playlist"),
                Choice("play",     "   -> [3]  Play/Stream songs"),
                Choice("dupes",    "   -> [4]  Find duplicate downloads"),
                Separator("  ─── DATA ────────────────────────────────────"),
                Choice("update",   "   -> [5]  Check yt-dlp update"),
                Choice("history",  "   -> [6]  Download and search history"),
                Choice("settings", "   -> [7]  Settings"),
                Separator("  ─────────────────────────────────────────────"),
                Choice("exit",     "   <- [8]  Exit"),
            ],
            style=MENU_STYLE,
        ).execute()

        if choice == "song":
            flow_download_song(config)
        elif choice == "playlist":
            flow_download_playlist(config)
        elif choice == "play":
            flow_play_or_stream_songs(config)
        elif choice == "dupes":
            flow_duplicate_finder(config)
        elif choice == "update":
            flow_check_ytdlp_update()
        elif choice == "history":
            flow_history(config)
        elif choice == "settings":
            config = flow_settings(config)
        elif choice == "exit":
            print_banner()
            console.print(Align.center(
                Text("\n  Thanks for using songcli!  Stay musical.\n",
                     style="bold white")
            ))
            sys.exit(0)

# ════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════

def main() -> None:
    try:
        config = load_config()
        print_banner(animated=True)
        check_dependencies()
        main_menu(config)
    except KeyboardInterrupt:
        console.print("\n\n  [cyan]Interrupted. Goodbye![/cyan]\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
