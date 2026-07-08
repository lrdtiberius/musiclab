import json
import io
import os
import re
import sqlite3
import subprocess
import shutil
import difflib
import tempfile
import zipfile
import hashlib
import unicodedata
from urllib.parse import quote
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from mutagen import File as MutagenFile
from mutagen.id3 import ID3, APIC, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.flac import FLAC, Picture
try:
    from mutagen.oggvorbis import OggVorbis
except Exception:
    OggVorbis = None

DEFAULT_MUSIC_ROOT = Path(os.getenv("MUSIC_ROOT", "/music"))
DB_PATH = Path(os.getenv("DB_PATH", "/data/musiclab.sqlite"))
LOG_DIR = Path(os.getenv("LOG_DIR", str(DB_PATH.parent / "logs")))
LOG_PATH = LOG_DIR / "musiclab.log"
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
EXTS = {".mp3", ".m4a", ".aac", ".flac", ".ogg"}
SCHEMA_VERSION = 24
LOG_TZ = os.getenv("TZ") or os.getenv("LOG_TZ") or "Europe/Berlin"

def local_log_time() -> str:
    try:
        if ZoneInfo:
            return datetime.now(ZoneInfo(LOG_TZ)).strftime("%H:%M:%S")
    except Exception:
        pass
    return time.strftime("%H:%M:%S")

app = FastAPI(title="MusicLab API", version="1.8.17")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

stop_event = threading.Event()

state = {
    "running": False,
    "mode": "idle",
    "done": 0,
    "total": 0,
    "current": "",
    "message": "Bereit",
    "errors": 0,
    "log": [],
    "recent_errors": [],
    "last_finished": None,
    "stop_requested": False,
}


def rotate_log_if_needed():
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size >= LOG_MAX_BYTES:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            for i in range(4, 0, -1):
                src = LOG_DIR / f"musiclab.{i}.log"
                dst = LOG_DIR / f"musiclab.{i + 1}.log"
                if src.exists():
                    if dst.exists():
                        dst.unlink()
                    src.rename(dst)
            dst = LOG_DIR / "musiclab.1.log"
            if dst.exists():
                dst.unlink()
            LOG_PATH.rename(dst)
    except Exception as e:
        print(f"Logrotation fehlgeschlagen: {e}", flush=True)


def add_log(message: str, is_error: bool = False):
    line = f"{local_log_time()} | {message}"
    state["log"].append(line)
    state["log"] = state["log"][-200:]
    if is_error:
        state["recent_errors"].append(line)
        state["recent_errors"] = state["recent_errors"][-50:]
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        rotate_log_if_needed()
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"Logdatei konnte nicht geschrieben werden: {e}", flush=True)
    print(line, flush=True)


def read_log_text(errors_only: bool = False) -> str:
    lines = []
    try:
        if LOG_PATH.exists():
            lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        lines = []
    if not lines:
        lines = list(state.get("log", []))
    if errors_only:
        lines = [l for l in lines if "fehler" in l.lower() or "abgebrochen" in l.lower()]
    return "\n".join(lines) + ("\n" if lines else "")


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                filename TEXT NOT NULL,
                artist TEXT NOT NULL,
                album TEXT NOT NULL,
                title TEXT NOT NULL,
                track_raw TEXT,
                track_number INTEGER,
                track_total INTEGER,
                disc_raw TEXT,
                disc_number INTEGER,
                disc_total INTEGER,
                genre TEXT,
                year TEXT,
                duration REAL,
                codec TEXT,
                bitrate INTEGER,
                sample_rate INTEGER,
                channels INTEGER,
                size INTEGER,
                mtime REAL,
                scanned_at REAL
            )
            """
        )
        cols = {r["name"] for r in con.execute("PRAGMA table_info(tracks)").fetchall()}
        # Robust migrations for installations that started with older MusicLab versions.
        # SQLite does not modify an existing CREATE TABLE IF NOT EXISTS table, so every
        # column added over time must be checked individually. Missing columns caused
        # scans to fail in older databases after newer tag/media features were added.
        required_track_cols = {
            "filename": "TEXT",
            "artist": "TEXT",
            "album": "TEXT",
            "title": "TEXT",
            "track_raw": "TEXT",
            "track_number": "INTEGER",
            "track_total": "INTEGER",
            "disc_raw": "TEXT",
            "disc_number": "INTEGER",
            "disc_total": "INTEGER",
            "genre": "TEXT",
            "year": "TEXT",
            "duration": "REAL",
            "codec": "TEXT",
            "bitrate": "INTEGER",
            "sample_rate": "INTEGER",
            "channels": "INTEGER",
            "size": "INTEGER",
            "mtime": "REAL",
            "scanned_at": "REAL",
        }
        for col, typ in required_track_cols.items():
            if col not in cols:
                con.execute(f"ALTER TABLE tracks ADD COLUMN {col} {typ}")
        # Normalize legacy NULLs so older rows are still readable and sortable.
        con.execute("UPDATE tracks SET filename=COALESCE(filename, path), artist=COALESCE(NULLIF(artist,''),'Unbekannter Interpret'), album=COALESCE(NULLIF(album,''),'Unbekanntes Album'), title=COALESCE(NULLIF(title,''), filename, path)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_tracks_path ON tracks(path)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist COLLATE NOCASE)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(artist COLLATE NOCASE, album COLLATE NOCASE)")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis (
                track_id INTEGER PRIMARY KEY,
                input_i REAL,
                input_tp REAL,
                input_lra REAL,
                input_thresh REAL,
                target_offset REAL,
                analyzed_at REAL,
                status TEXT NOT NULL DEFAULT 'ok',
                error TEXT,
                FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                artist TEXT,
                album TEXT NOT NULL,
                path TEXT NOT NULL,
                backup_path TEXT,
                backup_mode TEXT,
                target_lufs TEXT,
                true_peak TEXT,
                lra TEXT,
                before_i REAL,
                before_tp REAL,
                before_lra REAL,
                after_i REAL,
                after_tp REAL,
                after_lra REAL,
                restored_at REAL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_history_job ON history(job_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at)")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS duplicate_confirmations (
                pair_key TEXT PRIMARY KEY,
                path_a TEXT NOT NULL,
                path_b TEXT NOT NULL,
                reason TEXT,
                created_at REAL NOT NULL
            )
            """
        )
        defaults = {"target_lufs": "-16", "true_peak": "-1.5", "lra": "11", "backup_mode": "on", "parallel_analysis": "2", "music_root": str(DEFAULT_MUSIC_ROOT), "watch_mode": "off", "sort_after_tags": "off", "smb_base_url": "smb://DS923/Musik"}
        for k, v in defaults.items():
            con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
        con.commit()


def get_settings():
    with db() as con:
        rows = con.execute("SELECT key,value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def save_settings(data: dict):
    with db() as con:
        for k in ["target_lufs", "true_peak", "lra", "backup_mode", "parallel_analysis", "music_root", "watch_mode", "sort_after_tags", "smb_base_url"]:
            if k in data:
                con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, str(data[k])))
        con.commit()



def get_music_root() -> Path:
    """Return the currently configured container music path.

    The path must be visible inside the container, usually because docker-compose
    mounts the NAS music folder to it, e.g. /volume1/DS420/Musik:/music.
    """
    try:
        val = get_settings().get("music_root") or str(DEFAULT_MUSIC_ROOT)
    except Exception:
        val = str(DEFAULT_MUSIC_ROOT)
    val = str(val).strip() or str(DEFAULT_MUSIC_ROOT)
    return Path(val)


def duplicate_pair_key(paths) -> str:
    """Stable key for a duplicate candidate, independent of item order."""
    clean = [str(x or "").strip().replace("\\", "/") for x in (paths or []) if str(x or "").strip()]
    clean = sorted(dict.fromkeys(clean))
    joined = "\n".join(clean[:2])
    return hashlib.sha1(joined.encode("utf-8", errors="replace")).hexdigest()


def get_confirmed_duplicate_keys() -> set:
    try:
        with db() as con:
            return {r["pair_key"] for r in con.execute("SELECT pair_key FROM duplicate_confirmations").fetchall()}
    except Exception:
        return set()


def safe_music_path_info(rel_or_abs: str, request: Request) -> dict:
    """Return NAS/Finder friendly path information for a track or folder below MUSIC_ROOT.

    v1.8.6: Browser können lokale/NAS-Ordner oft nicht direkt öffnen. Deshalb liefern
    wir mehrere saubere Varianten zurück: anklickbare SMB-URL, kopierbaren SMB-Link,
    Finder-Befehl und NAS-/Container-Pfad.
    """
    root = get_music_root().resolve()
    raw = str(rel_or_abs or "").strip().replace("\\", "/")
    if not raw:
        raise HTTPException(status_code=400, detail="Pfad fehlt")

    root_str = root.as_posix().rstrip("/")
    if raw.startswith(root_str + "/"):
        rel = raw[len(root_str) + 1:]
    elif raw == root_str:
        rel = ""
    elif raw.startswith("/music/"):
        rel = raw[len("/music/"):]
    elif raw == "/music":
        rel = ""
    else:
        rel = raw.lstrip("/")

    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(status_code=400, detail="Pfad liegt außerhalb der Musikbibliothek")

    is_file = target.is_file()
    folder = target.parent if is_file else target
    try:
        rel_target = target.relative_to(root).as_posix()
    except Exception:
        rel_target = rel
    try:
        rel_folder = folder.relative_to(root).as_posix()
    except Exception:
        rel_folder = str(Path(rel).parent.as_posix()) if rel else ""

    settings = get_settings()
    # Einstellbarer Basislink. Beispiele:
    #   smb://DS923/Musik
    #   smb://192.168.178.50/Musik
    #   smb://DS923/DS420/Musik
    smb_base = str(settings.get("smb_base_url") or os.getenv("SMB_BASE_URL") or "smb://DS923/Musik").strip().rstrip("/")
    if not smb_base.lower().startswith("smb://"):
        smb_base = "smb://" + smb_base.lstrip("/")

    def enc_rel(p: str) -> str:
        return "/".join(quote(part) for part in str(p or "").split("/") if part not in ("", "."))

    def join_smb(base: str, rel_path: str) -> str:
        suffix = enc_rel(rel_path)
        return base + (("/" + suffix) if suffix else "")

    folder_smb_url = join_smb(smb_base, rel_folder)
    file_smb_url = join_smb(smb_base, rel_target)

    # Fallbacks für alte Variablen, falls jemand sie in docker-compose gesetzt hat.
    host = request.url.hostname or os.getenv("NAS_HOST", "localhost")
    smb_share = os.getenv("SMB_SHARE", "").strip("/")
    smb_prefix = os.getenv("SMB_PREFIX", "").strip("/")
    legacy_folder_smb_url = ""
    legacy_file_smb_url = ""
    if smb_share:
        legacy_base = f"smb://{host}/{quote(smb_share)}"
        if smb_prefix:
            legacy_base += "/" + enc_rel(smb_prefix)
        legacy_folder_smb_url = join_smb(legacy_base, rel_folder)
        legacy_file_smb_url = join_smb(legacy_base, rel_target)

    nas_base = os.getenv("NAS_MUSIC_PATH", smb_base).rstrip("/")
    finder_open_folder_command = f'open "{folder_smb_url}"'
    finder_open_file_command = f'open "{file_smb_url}"'
    return {
        "path": rel_target,
        "folder": rel_folder,
        "container_path": target.as_posix(),
        "container_folder": folder.as_posix(),
        "nas_path": f"{nas_base}/{rel_target}" if rel_target and not nas_base.lower().startswith("smb://") else file_smb_url,
        "nas_folder": f"{nas_base}/{rel_folder}" if rel_folder and not nas_base.lower().startswith("smb://") else folder_smb_url,
        "is_file": is_file,
        "smb_base_url": smb_base,
        "folder_smb_url": folder_smb_url,
        "file_smb_url": file_smb_url,
        "legacy_folder_smb_url": legacy_folder_smb_url,
        "legacy_file_smb_url": legacy_file_smb_url,
        "alt_folder_smb_url": legacy_folder_smb_url or folder_smb_url,
        "alt_file_smb_url": legacy_file_smb_url or file_smb_url,
        "finder_open_folder_command": finder_open_folder_command,
        "finder_open_file_command": finder_open_file_command,
    }


def check_music_root(path_value: Optional[str] = None) -> dict:
    root = Path((path_value or str(get_music_root())).strip() or str(DEFAULT_MUSIC_ROOT))
    exists = root.exists()
    is_dir = root.is_dir() if exists else False
    readable = os.access(root, os.R_OK) if exists else False
    audio_count = 0
    error = None
    if exists and is_dir and readable:
        try:
            for p in root.rglob("*"):
                if is_audio_candidate(p):
                    audio_count += 1
                    if audio_count >= 20:
                        break
        except Exception as e:
            error = str(e)
    return {
        "path": str(root),
        "exists": exists,
        "is_dir": is_dir,
        "readable": readable,
        "ok": bool(exists and is_dir and readable),
        "sample_audio_files": audio_count,
        "error": error,
    }

def value_to_str(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    text = str(value).strip() if value is not None else ""
    return text or None


def tag_first(tags, keys) -> Optional[str]:
    if not tags:
        return None
    lower = {str(k).lower(): k for k in tags.keys()}
    for key in keys:
        actual = lower.get(key.lower())
        if actual is not None:
            val = value_to_str(tags.get(actual))
            if val:
                return val
    return None


def fold_ascii(value: Optional[str]) -> str:
    """Accent-insensitive comparison key, e.g. Die Ärzte == Die Arzte."""
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def accent_score(value: Optional[str]) -> int:
    """Prefer the spelling that actually keeps umlauts/diacritics when two tags mean the same artist."""
    score = 0
    for ch in str(value or ""):
        decomp = unicodedata.normalize("NFD", ch)
        if any(unicodedata.category(c) == "Mn" for c in decomp):
            score += 2
        elif ord(ch) > 127:
            score += 1
    return score


def choose_artist_tag(tags, fallback_artist: str) -> str:
    """Resolve artist for DB/sorting without letting stale albumartist tags undo manual fixes.

    Older files often have both Artist and Album Artist. In the tag editor the visible
    field is called "Interpret". If the user fixes "Die Arzte" to "Die Ärzte", some
    files may still contain the old Album Artist value. Since scan/sort previously
    preferred albumartist blindly, the library sorter could move the files back to
    the old ASCII folder. If Artist and Album Artist are the same after removing
    accents, use the spelling with the richer diacritics. Otherwise keep the usual
    Album Artist preference for compilations.
    """
    album_artist = tag_first(tags, ["albumartist", "album artist"])
    artist = tag_first(tags, ["artist"])
    if album_artist and artist:
        if fold_ascii(album_artist) == fold_ascii(artist) and accent_score(artist) > accent_score(album_artist):
            return artist
        return album_artist
    return album_artist or artist or fallback_artist


def parse_number_pair(raw: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    if not raw:
        return None, None
    text = str(raw).strip().lower().replace("of", "/")
    m = re.search(r"(\d+)(?:\s*/\s*(\d+))?", text)
    if not m:
        return None, None
    n = int(m.group(1))
    total = int(m.group(2)) if m.group(2) else None
    if total == 0:
        total = None
    return n, total


def fallback_from_path(path: Path, root: Optional[Path] = None):
    root = root or get_music_root()
    rel = path.relative_to(root).parts
    if len(rel) >= 3:
        return rel[0], rel[1]
    if len(rel) == 2:
        return rel[0], path.parent.name
    return "Unbekannt", "Unbekanntes Album"


def audio_channels(info):
    v = getattr(info, "channels", None)
    return v if isinstance(v, int) else None


def scan_file(path: Path, root: Optional[Path] = None) -> Optional[dict]:
    root = root or get_music_root()
    st = path.stat()
    rel = str(path.relative_to(root))
    fallback_artist, fallback_album = fallback_from_path(path, root)
    audio = MutagenFile(path, easy=True)
    tags = audio.tags if audio and getattr(audio, "tags", None) else {}
    info = audio.info if audio and getattr(audio, "info", None) else None
    artist = choose_artist_tag(tags, fallback_artist)
    album = tag_first(tags, ["album"]) or fallback_album
    title = tag_first(tags, ["title"]) or path.stem
    track_raw = tag_first(tags, ["tracknumber", "track"])
    disc_raw = tag_first(tags, ["discnumber", "disc"])
    genre = tag_first(tags, ["genre"])
    year = tag_first(tags, ["date", "year"])
    if isinstance(year, str) and year.strip() in {"0", "00", "000", "0000"}:
        year = ""
    track_number, track_total = parse_number_pair(track_raw)
    disc_number, disc_total = parse_number_pair(disc_raw)
    # Ein einzelnes Album soll keine Disc-Gesamtzahl 1/1 tragen.
    # Nur echte Mehrfach-CDs bekommen ein Disc-Total.
    if disc_total is not None and disc_total <= 1:
        disc_total = None
    return {
        "path": rel,
        "filename": path.name,
        "artist": artist.strip() or "Unbekannt",
        "album": album.strip() or "Unbekanntes Album",
        "title": title.strip() or path.stem,
        "track_raw": track_raw,
        "track_number": track_number,
        "track_total": track_total,
        "disc_raw": disc_raw,
        "disc_number": disc_number,
        "disc_total": disc_total,
        "genre": genre.strip() if isinstance(genre, str) else genre,
        "year": year.strip() if isinstance(year, str) else year,
        "duration": float(getattr(info, "length", 0)) if info and getattr(info, "length", None) else None,
        "codec": path.suffix.lower().lstrip("."),
        "bitrate": int(getattr(info, "bitrate", 0)) if info and getattr(info, "bitrate", None) else None,
        "sample_rate": int(getattr(info, "sample_rate", 0)) if info and getattr(info, "sample_rate", None) else None,
        "channels": audio_channels(info) if info else None,
        "size": st.st_size,
        "mtime": st.st_mtime,
        "scanned_at": time.time(),
    }


def upsert_track(con, item):
    con.execute(
        """
        INSERT INTO tracks(path,filename,artist,album,title,track_raw,track_number,track_total,disc_raw,disc_number,disc_total,genre,year,duration,codec,bitrate,sample_rate,channels,size,mtime,scanned_at)
        VALUES(:path,:filename,:artist,:album,:title,:track_raw,:track_number,:track_total,:disc_raw,:disc_number,:disc_total,:genre,:year,:duration,:codec,:bitrate,:sample_rate,:channels,:size,:mtime,:scanned_at)
        ON CONFLICT(path) DO UPDATE SET
        filename=excluded.filename,artist=excluded.artist,album=excluded.album,title=excluded.title,track_raw=excluded.track_raw,track_number=excluded.track_number,track_total=excluded.track_total,disc_raw=excluded.disc_raw,disc_number=excluded.disc_number,disc_total=excluded.disc_total,genre=excluded.genre,year=excluded.year,duration=excluded.duration,codec=excluded.codec,bitrate=excluded.bitrate,sample_rate=excluded.sample_rate,channels=excluded.channels,size=excluded.size,mtime=excluded.mtime,scanned_at=excluded.scanned_at
        """,
        item,
    )


def is_audio_candidate(path: Path) -> bool:
    # macOS/SMB AppleDouble files look like audio files (e.g. ._Song.mp3),
    # but contain metadata/resource forks and ffmpeg/mutagen will fail with
    # messages like "can't sync to MPEG frame". They are intentionally skipped.
    if not path.is_file():
        return False
    if path.name.startswith("._"):
        return False
    if path.name.startswith(".") and path.suffix.lower() not in EXTS:
        return False
    if ".tmp" in path.name:
        return False
    return path.suffix.lower() in EXTS


def begin_job(mode: str, total: int, message: str):
    stop_event.clear()
    state.update({
        "running": True,
        "mode": mode,
        "done": 0,
        "total": total,
        "current": "",
        "message": message,
        "errors": 0,
        "recent_errors": [],
        "stop_requested": False,
    })


def finish_job(message: str, stopped: bool = False):
    state.update({
        "running": False,
        "mode": "idle",
        "current": "",
        "message": message,
        "last_finished": time.time(),
        "stop_requested": False,
    })
    if stopped:
        add_log(message, True)


def analysis_parallelism() -> int:
    try:
        v = int(get_settings().get("parallel_analysis", "2"))
    except Exception:
        v = 2
    return max(1, min(v, 6))


def reset_stop() -> None:
    """Clear a previously requested stop before starting a new job."""
    stop_event.clear()
    state["stop_requested"] = False

def stop_requested() -> bool:
    return stop_event.is_set()


def music_snapshot() -> tuple:
    root = get_music_root()
    if not root.exists() or not root.is_dir():
        return (str(root), 0, 0.0)
    count = 0
    newest = 0.0
    try:
        for p in root.rglob("*"):
            if is_audio_candidate(p):
                count += 1
                try:
                    newest = max(newest, p.stat().st_mtime)
                except Exception:
                    pass
    except Exception:
        pass
    return (str(root), count, newest)


def selected_unanalyzed_rows(limit: Optional[int] = None):
    sql = """
        SELECT t.id,t.path,t.title,t.artist,t.album FROM tracks t
        LEFT JOIN analysis a ON a.track_id=t.id AND a.status='ok'
        WHERE a.track_id IS NULL
        ORDER BY t.artist COLLATE NOCASE, t.album COLLATE NOCASE, COALESCE(t.disc_number,1), COALESCE(t.track_number,9999), t.title COLLATE NOCASE
    """
    args = []
    if limit:
        sql += " LIMIT ?"
        args.append(int(limit))
    with db() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def analyze_missing_worker():
    init_db()
    rows = selected_unanalyzed_rows()
    workers = analysis_parallelism()
    begin_job("analysis", len(rows), f"Analyse neuer Titel läuft ({workers} parallel)")
    add_log(f"Analyse neuer Titel gestartet: {len(rows)} Titel, parallel: {workers}")
    def work(row):
        return row, analyze_track_file(get_music_root() / row["path"])
    with db() as con:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(work, row): row for row in rows}
            for fut in as_completed(futures):
                if stop_requested():
                    for pending in futures:
                        pending.cancel()
                    break
                row = futures[fut]
                state["current"] = row["path"]
                try:
                    _, result = fut.result()
                    upsert_analysis(con, row["id"], result)
                except Exception as e:
                    state["errors"] += 1
                    upsert_analysis(con, row["id"], None, str(e))
                    add_log(f"Analysefehler: {row['path']} - {e}", True)
                state["done"] += 1
                con.commit()
    if stop_requested():
        add_log(f"Analyse neuer Titel abgebrochen: {state['done']}/{state['total']} Titel, Fehler {state['errors']}", True)
        finish_job("Analyse neuer Titel abgebrochen", True)
    else:
        add_log(f"Analyse neuer Titel fertig: {state['done']}/{state['total']} Titel, Fehler {state['errors']}")
        finish_job("Analyse neuer Titel fertig")



def safe_name(value: str, fallback: str = "Unbekannt") -> str:
    """Filesystem-safe name for artist/album/title folders and files."""
    v = str(value or "").strip() or fallback
    v = re.sub(r'[\\/:*?"<>|]+', ' - ', v)
    v = re.sub(r'\s+', ' ', v).strip(' .')
    return v or fallback


def unique_target_path(root: Path, rel_target: Path, source: Path) -> Path:
    """Return a non-destructive target path, adding Duplikat suffix if needed."""
    target = (root / rel_target).resolve()
    try:
        if target == source.resolve():
            return target
    except Exception:
        pass
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    i = 1
    while True:
        cand = parent / f"{stem} (Duplikat {i}){suffix}"
        if not cand.exists():
            return cand
        i += 1


def prune_empty_dirs(start: Path, root: Path):
    try:
        cur = start
        root = root.resolve()
        while cur.resolve() != root and cur.exists():
            try:
                cur.rmdir()
            except OSError:
                break
            cur = cur.parent
    except Exception:
        pass

def watcher_loop():
    last = music_snapshot()
    while True:
        time.sleep(60)
        try:
            settings = get_settings()
            mode = settings.get("watch_mode", "off")
            if mode == "off":
                last = music_snapshot()
                continue
            cur = music_snapshot()
            if cur != last:
                add_log(f"Überwachung: Änderung im Musikordner erkannt ({cur[1]} Dateien)")
                last = cur
                if not state.get("running") and mode in {"scan", "scan_analyze"}:
                    scan_worker()
                    if mode == "scan_analyze" and not state.get("running") and not stop_requested():
                        missing = selected_unanalyzed_rows(limit=1)
                        if missing:
                            analyze_missing_worker()
            else:
                last = cur
        except Exception as e:
            add_log(f"Überwachung Fehler: {e}", True)


def scan_worker():
    init_db()
    root = get_music_root()
    if not root.exists() or not root.is_dir():
        begin_job("scan", 0, "Musikpfad nicht gefunden")
        state["errors"] += 1
        add_log(f"Scanfehler: Musikpfad nicht gefunden oder kein Ordner: {root}", True)
        finish_job("Musikpfad nicht gefunden", True)
        return
    files = [p for p in root.rglob("*") if is_audio_candidate(p)]
    begin_job("scan", len(files), "Scan läuft")
    add_log(f"Scan gestartet: {len(files)} Dateien")

    seen_paths = set()
    changed_paths = []
    with db() as con:
        existing = {r["path"]: dict(r) for r in con.execute("SELECT id,path,size,mtime FROM tracks").fetchall()}
        for p in files:
            if stop_requested():
                add_log("Scan abgebrochen")
                break
            rel = str(p.relative_to(root))
            seen_paths.add(rel)
            state["current"] = rel
            try:
                item = scan_file(p, root)
                if item:
                    old = existing.get(item["path"])
                    changed = bool(old and (old.get("size") != item.get("size") or float(old.get("mtime") or 0) != float(item.get("mtime") or 0)))
                    upsert_track(con, item)
                    if changed:
                        changed_paths.append(item["path"])
            except Exception as e:
                state["errors"] += 1
                add_log(f"Scanfehler: {rel} - {e}", True)
            state["done"] += 1
            if state["done"] % 100 == 0:
                con.commit()

        # Invalidate analyses only for files that actually changed. Keep old
        # analysis data for unchanged files so a normal rescan does not wipe
        # hours of LUFS work.
        if changed_paths:
            qmarks = ",".join("?" for _ in changed_paths)
            con.execute(f"DELETE FROM analysis WHERE track_id IN (SELECT id FROM tracks WHERE path IN ({qmarks}))", changed_paths)
            add_log(f"Analysewerte für {len(changed_paths)} geänderte Datei(en) zurückgesetzt")

        missing = [path for path in existing.keys() if path not in seen_paths]
        if missing:
            qmarks = ",".join("?" for _ in missing)
            con.execute(f"DELETE FROM analysis WHERE track_id IN (SELECT id FROM tracks WHERE path IN ({qmarks}))", missing)
            con.execute(f"DELETE FROM tracks WHERE path IN ({qmarks})", missing)
            add_log(f"Entfernte Dateien aus Datenbank gelöscht: {len(missing)}")

        con.commit()
    if stop_requested():
        add_log(f"Scan abgebrochen: {state['done']}/{state['total']} Dateien, Fehler {state['errors']}", True)
        finish_job("Scan abgebrochen", True)
    else:
        add_log(f"Scan fertig: {state['done']}/{state['total']} Dateien, Fehler {state['errors']}")
        finish_job("Scan fertig")


def parse_loudnorm_json(stderr: str) -> Optional[dict]:
    """Extract only the JSON object emitted by ffmpeg's loudnorm filter.

    Important: ffmpeg writes normal progress, stream metadata, ReplayGain tags and
    embedded cover information to stderr even on success. Some ID3 private tags
    also contain literal braces/backslashes, so a generic ``{...}`` regex can
    accidentally consume junk before the real loudnorm object.

    We therefore locate the loudnorm block by its required keys and parse the
    nearest surrounding JSON object.
    """
    text = stderr or ""
    required = ['"input_i"', '"input_tp"', '"input_lra"']

    # Usually there is exactly one loudnorm JSON block. Start from input_i and
    # take the closest enclosing braces around that block. This avoids ID3 values
    # like ``AverageLevel: {\x1c...`` being treated as JSON.
    idx = text.rfind('"input_i"')
    if idx >= 0:
        start = text.rfind("{", 0, idx)
        end = text.find("}", idx)
        if start >= 0 and end > idx:
            candidate = text[start:end + 1]
            try:
                data = json.loads(candidate)
                if isinstance(data, dict) and all(k.strip('"') in data for k in required):
                    return data
            except Exception:
                pass

    # Fallback: parse line-based blocks that look like JSON. This is deliberately
    # stricter than a global non-greedy regex.
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "{":
            block = []
            for j in range(i, min(i + 40, len(lines))):
                block.append(lines[j])
                if lines[j].strip() == "}":
                    candidate = "\n".join(block)
                    try:
                        data = json.loads(candidate)
                        if isinstance(data, dict) and "input_i" in data and "input_tp" in data and "input_lra" in data:
                            return data
                    except Exception:
                        pass
                    break
    return None


def concise_ffmpeg_error(stderr: str, returncode: int) -> str:
    text = stderr or ""
    interesting = []
    noise_prefixes = (
        "Input #", "Metadata:", "Duration:", "Stream #", "Side data:",
        "encoder", "id3v2_priv", "replaygain:", "[Parsed_loudnorm",
        "{", "}", '"input_', '"output_', '"normalization_', '"target_offset"',
        "size=", "video:", "audio:", "frame=", "Press [q]"
    )
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(line.startswith(p) for p in noise_prefixes):
            continue
        if "Error" in line or "Invalid" in line or "failed" in line.lower() or "can't" in line.lower():
            interesting.append(line)
    if interesting:
        return " | ".join(interesting[-3:])[:500]
    return f"ffmpeg returncode {returncode}, keine loudnorm-Daten" if returncode else "Keine loudnorm-Daten gefunden"


def analyze_track_file(path: Path) -> dict:
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", str(path),
        "-map", "0:a:0",
        "-af", "loudnorm=print_format=json",
        "-f", "null", "-"
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    stderr = (res.stderr or b"").decode("utf-8", errors="replace")
    data = parse_loudnorm_json(stderr)

    # ffmpeg can write lots of stderr on success. A valid loudnorm JSON block is
    # considered success even if stderr contains metadata or warnings.
    if data:
        return {
            "input_i": float(data["input_i"]),
            "input_tp": float(data["input_tp"]),
            "input_lra": float(data["input_lra"]),
            "input_thresh": float(data["input_thresh"]),
            "target_offset": float(data.get("target_offset", 0)),
        }

    raise RuntimeError(concise_ffmpeg_error(stderr, res.returncode))


def upsert_analysis(con, track_id: int, result: Optional[dict], error: Optional[str] = None):
    if result:
        con.execute(
            """
            INSERT INTO analysis(track_id,input_i,input_tp,input_lra,input_thresh,target_offset,analyzed_at,status,error)
            VALUES(?,?,?,?,?,?,?,'ok',NULL)
            ON CONFLICT(track_id) DO UPDATE SET input_i=excluded.input_i,input_tp=excluded.input_tp,input_lra=excluded.input_lra,input_thresh=excluded.input_thresh,target_offset=excluded.target_offset,analyzed_at=excluded.analyzed_at,status='ok',error=NULL
            """,
            (track_id, result["input_i"], result["input_tp"], result["input_lra"], result["input_thresh"], result["target_offset"], time.time()),
        )
    else:
        con.execute(
            """
            INSERT INTO analysis(track_id,analyzed_at,status,error)
            VALUES(?,?,'error',?)
            ON CONFLICT(track_id) DO UPDATE SET analyzed_at=excluded.analyzed_at,status='error',error=excluded.error
            """,
            (track_id, time.time(), (error or "Unbekannter Fehler")[:2000]),
        )


def selected_rows(artist: Optional[str], album: Optional[str]):
    where, args = [], []
    if artist:
        where.append("artist=?")
        args.append(artist)
    if album:
        where.append("album=?")
        args.append(album)
    sql = "SELECT id,path,title,artist,album FROM tracks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY artist COLLATE NOCASE, album COLLATE NOCASE, COALESCE(disc_number,1), COALESCE(track_number,9999), title COLLATE NOCASE"
    with db() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def analysis_worker(artist: Optional[str] = None, album: Optional[str] = None):
    init_db()
    rows = selected_rows(artist, album)
    workers = analysis_parallelism()
    begin_job("analysis", len(rows), f"Analyse läuft ({workers} parallel)")
    add_log(f"Analyse gestartet: {len(rows)} Titel, parallel: {workers}")

    def work(row):
        return row, analyze_track_file(get_music_root() / row["path"])

    with db() as con:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(work, row): row for row in rows}
            for fut in as_completed(futures):
                if stop_requested():
                    for pending in futures:
                        pending.cancel()
                    break
                row = futures[fut]
                state["current"] = row["path"]
                try:
                    _, result = fut.result()
                    upsert_analysis(con, row["id"], result)
                except Exception as e:
                    state["errors"] += 1
                    upsert_analysis(con, row["id"], None, str(e))
                    add_log(f"Analysefehler: {row['path']} - {e}", True)
                state["done"] += 1
                con.commit()

    if stop_requested():
        add_log(f"Analyse abgebrochen: {state['done']}/{state['total']} Titel, Fehler {state['errors']}", True)
        finish_job("Analyse abgebrochen", True)
    else:
        add_log(f"Analyse fertig: {state['done']}/{state['total']} Titel, Fehler {state['errors']}")
        finish_job("Analyse fertig")


def loudnorm_filter(first: dict, settings: dict) -> str:
    return (
        f"loudnorm=I={settings['target_lufs']}:TP={settings['true_peak']}:LRA={settings['lra']}:"
        f"measured_I={first['input_i']}:measured_TP={first['input_tp']}:measured_LRA={first['input_lra']}:"
        f"measured_thresh={first['input_thresh']}:offset={first['target_offset']}:linear=true:print_format=summary"
    )


def backup_file(file: Path, rel_path: str, mode: str) -> Optional[str]:
    if mode not in {"on", "sidecar"}:
        return None
    if mode == "sidecar":
        bak = file.with_name(file.name + ".bak")
        if not bak.exists():
            shutil.copy2(file, bak)
        return str(bak)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = DB_PATH.parent / "backups" / stamp / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(file, dest)
    return str(dest)


def normalize_file(rel_path: str, settings: dict, backup_mode: Optional[str] = None) -> bool:
    file = get_music_root() / rel_path
    if not file.exists():
        raise RuntimeError("Datei nicht gefunden")
    if not os.access(file, os.W_OK):
        raise RuntimeError("Datei ist nicht schreibbar")

    tmp = file.with_name(file.stem + ".tmp" + file.suffix)
    if tmp.exists():
        tmp.unlink()

    backup_mode = backup_mode if backup_mode is not None else settings.get("backup_mode", "on")
    backup_path = backup_file(file, rel_path, backup_mode)
    if backup_path:
        add_log(f"Backup erstellt: {rel_path}")

    first = analyze_track_file(file)
    suffix = file.suffix.lower()
    cmd = ["ffmpeg", "-y", "-hide_banner", "-i", str(file), "-af", loudnorm_filter(first, settings), "-map", "0", "-map_metadata", "0", "-c:v", "copy"]
    if suffix == ".mp3":
        cmd += ["-c:a", "libmp3lame", "-q:a", "2", "-f", "mp3"]
    elif suffix in [".m4a", ".aac"]:
        cmd += ["-c:a", "aac", "-b:a", "256k", "-f", "mp4"]
    elif suffix == ".flac":
        cmd += ["-c:a", "flac", "-f", "flac"]
    elif suffix == ".ogg":
        cmd += ["-c:a", "libvorbis", "-q:a", "5", "-f", "ogg"]
    else:
        return False
    cmd.append(str(tmp))
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1200)
    if res.returncode != 0:
        if tmp.exists():
            tmp.unlink()
        raise RuntimeError(res.stderr[-2000:])
    tmp.replace(file)
    return backup_path



def history_job_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time()*1000)%100000:05d}"


def insert_history(con, job_id: str, row, album_artist: Optional[str], album_name: str, backup_path: Optional[str], backup_mode: str, settings: dict, before: Optional[dict], after: Optional[dict]):
    con.execute(
        """
        INSERT INTO history(job_id,created_at,artist,album,path,backup_path,backup_mode,target_lufs,true_peak,lra,
        before_i,before_tp,before_lra,after_i,after_tp,after_lra,restored_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
        """,
        (
            job_id, time.time(), album_artist, album_name, row["path"], backup_path, backup_mode,
            str(settings.get("target_lufs", "")), str(settings.get("true_peak", "")), str(settings.get("lra", "")),
            (before or {}).get("input_i"), (before or {}).get("input_tp"), (before or {}).get("input_lra"),
            (after or {}).get("input_i"), (after or {}).get("input_tp"), (after or {}).get("input_lra"),
        ),
    )


def analyze_and_store(con, track_id: int, rel_path: str) -> dict:
    result = analyze_track_file(get_music_root() / rel_path)
    upsert_analysis(con, track_id, result)
    return result

def normalize_worker(artist: Optional[str] = None, album: Optional[str] = None, backup_mode: Optional[str] = None):
    init_db()
    settings = get_settings()
    if backup_mode is not None:
        settings["backup_mode"] = backup_mode
    rows = selected_rows(artist, album)

    with db() as con:
        ref = get_reference_tuple(con)
        summary = album_summary(con, artist, album) if album else {}
    if album and is_reference_album({"artist": artist, "album": album}, ref):
        state.update({"running": False, "mode": "idle", "done": 0, "total": 0, "current": "", "message": "Normalisierung abgebrochen: Referenzalbum wird nicht verändert", "errors": 1})
        add_log(f"Normalisierung blockiert: Referenzalbum {artist or 'Verschiedene Interpreten'} - {album} wird nicht verändert", True)
        return
    if album and summary.get("tracks") and summary.get("analyzed") != summary.get("tracks"):
        state.update({"running": False, "mode": "idle", "done": 0, "total": 0, "current": "", "message": "Normalisierung abgebrochen: Album zuerst vollständig analysieren", "errors": 1})
        add_log(f"Normalisierung abgebrochen: {artist or 'global'} - {album} ist nicht vollständig analysiert", True)
        return

    job_id = history_job_id()
    begin_job("normalize", len(rows), f"Normalisiere auf {settings.get('target_lufs')} LUFS")
    add_log(f"Normalisierung gestartet: {len(rows)} Titel auf {settings.get('target_lufs')} LUFS, Backup: {settings.get('backup_mode','on')}")
    with db() as con:
        for row in rows:
            if stop_requested():
                add_log("Normalisierung abgebrochen")
                break
            state["current"] = row["path"]
            try:
                before = analyze_track_file(get_music_root() / row["path"])
                backup_path = normalize_file(row["path"], settings, settings.get("backup_mode", "on"))
                result = analyze_and_store(con, row["id"], row["path"])
                insert_history(con, job_id, row, artist, album or row["album"], backup_path, settings.get("backup_mode", "on"), settings, before, result)
                add_log(f"Normalisiert: {row['path']}")
            except Exception as e:
                state["errors"] += 1
                upsert_analysis(con, row["id"], None, str(e))
                add_log(f"Normalisierungsfehler: {row['path']} - {e}", True)
            state["done"] += 1
            con.commit()
    if stop_requested():
        add_log(f"Normalisierung abgebrochen: {state['done']}/{state['total']} Titel, Fehler {state['errors']}", True)
        finish_job("Normalisierung abgebrochen", True)
    else:
        add_log(f"Normalisierung fertig: {state['done']}/{state['total']} Titel, Fehler {state['errors']}")
        finish_job("Normalisierung fertig")


def album_label(artist: Optional[str], album: str) -> str:
    return f"{artist} - {album}" if artist else album


def normalize_album_item(item: dict) -> dict:
    album = str(item.get("album", "")).strip()
    artist_raw = item.get("artist")
    artist = str(artist_raw).strip() if artist_raw is not None and str(artist_raw).strip() else None
    if not album:
        raise ValueError("Album fehlt")
    return {"artist": artist, "album": album}


def rows_for_album_item(item: dict):
    return selected_rows(item.get("artist"), item.get("album"))


def rows_for_paths(paths: list):
    clean = []
    for p in paths or []:
        rel = str(p or "").strip()
        if rel.startswith("/music/"):
            rel = rel[7:]
        if rel and rel not in clean:
            clean.append(rel)
    if not clean:
        return []
    placeholders = ",".join(["?"] * len(clean))
    sql = f"SELECT id,path,title,artist,album FROM tracks WHERE path IN ({placeholders}) ORDER BY artist COLLATE NOCASE, album COLLATE NOCASE, COALESCE(disc_number,1), COALESCE(track_number,9999), title COLLATE NOCASE"
    with db() as con:
        found = [dict(r) for r in con.execute(sql, clean).fetchall()]
    order = {path: i for i, path in enumerate(clean)}
    found.sort(key=lambda r: order.get(r["path"], 999999))
    return found

def tracks_preview(paths: list) -> dict:
    settings = get_settings()
    try:
        target = float(settings.get("target_lufs", "-16"))
    except Exception:
        target = -16.0
    rows = rows_for_paths(paths)
    out = []
    with db() as con:
        for row in rows:
            a = con.execute("SELECT input_i,input_tp,input_lra,status FROM analysis WHERE track_id=?", (row["id"],)).fetchone()
            current = a["input_i"] if a and a["status"] == "ok" else None
            delta = round(target - float(current), 2) if current is not None else None
            can = current is not None
            out.append({
                "path": row["path"],
                "artist": row["artist"],
                "album": row["album"],
                "title": row["title"],
                "current_lufs": current,
                "target_lufs": target,
                "gain_delta": delta,
                "can_normalize": can,
                "reason": None if can else "Titel zuerst analysieren",
            })
    missing = len(set(str(p).replace('/music/','') for p in (paths or []))) - len(rows)
    return {
        "count_tracks": len(rows),
        "missing": max(0, missing),
        "target_lufs": target,
        "true_peak": settings.get("true_peak"),
        "lra": settings.get("lra"),
        "backup_mode": settings.get("backup_mode", "on"),
        "can_normalize": bool(rows) and all(x.get("can_normalize") for x in out),
        "items": out,
    }

def normalize_tracks_worker(paths: list, backup_mode: Optional[str] = None):
    init_db()
    settings = get_settings()
    if backup_mode is not None:
        settings["backup_mode"] = backup_mode
    rows = rows_for_paths(paths)
    blocked = [x for x in tracks_preview([r["path"] for r in rows]).get("items", []) if not x.get("can_normalize")]
    if blocked:
        names = "; ".join(f"{p['path']}: {p.get('reason') or 'nicht möglich'}" for p in blocked[:5])
        state.update({"running": False, "mode": "idle", "done": 0, "total": 0, "current": "", "message": "Titel-Normalisierung abgebrochen", "errors": len(blocked), "recent_errors": []})
        add_log(f"Titel-Normalisierung abgebrochen: {names}", True)
        return
    job_id = history_job_id()
    begin_job("track_normalize", len(rows), f"Titel-Normalisierung auf {settings.get('target_lufs')} LUFS")
    add_log(f"Titel-Normalisierung gestartet: {len(rows)} Titel auf {settings.get('target_lufs')} LUFS, Backup: {settings.get('backup_mode','on')}")
    with db() as con:
        for row in rows:
            if stop_requested():
                add_log("Titel-Normalisierung abgebrochen")
                break
            state["current"] = row["path"]
            try:
                before = analyze_track_file(get_music_root() / row["path"])
                backup_path = normalize_file(row["path"], settings, settings.get("backup_mode", "on"))
                result = analyze_and_store(con, row["id"], row["path"])
                insert_history(con, job_id, row, row.get("artist"), row.get("album"), backup_path, settings.get("backup_mode", "on"), settings, before, result)
                add_log(f"Titel normalisiert: {row['path']}")
            except Exception as e:
                state["errors"] += 1
                upsert_analysis(con, row["id"], None, str(e))
                add_log(f"Titel-Normalisierungsfehler: {row['path']} - {e}", True)
            state["done"] += 1
            con.commit()
    if stop_requested():
        add_log(f"Titel-Normalisierung abgebrochen: {state['done']}/{state['total']} Titel, Fehler {state['errors']}", True)
        finish_job("Titel-Normalisierung abgebrochen", True)
    else:
        add_log(f"Titel-Normalisierung fertig: {state['done']}/{state['total']} Titel, Fehler {state['errors']}")
        finish_job("Titel-Normalisierung fertig")


def batch_preview_items(items: list) -> list:
    settings = get_settings()
    try:
        target = float(settings.get("target_lufs", "-16"))
    except Exception:
        target = -16.0
    out = []
    with db() as con:
        ref = get_reference_tuple(con)
        for raw in items:
            item = normalize_album_item(raw)
            summary = album_summary(con, item.get("artist"), item.get("album"))
            tracks = summary.get("tracks") or 0
            analyzed = summary.get("analyzed") or 0
            current = summary.get("avg_lufs")
            delta = round(target - float(current), 2) if current is not None else None
            ref_skip = is_reference_album(item, ref)
            can = bool(tracks and analyzed == tracks and current is not None and not ref_skip)
            reason = None
            if ref_skip:
                reason = "Referenzalbum wird übersprungen"
            elif not tracks:
                reason = "Album nicht gefunden"
            elif analyzed != tracks:
                reason = "Album zuerst vollständig analysieren"
            elif current is None:
                reason = "Keine Analysewerte vorhanden"
            out.append({
                "artist": item.get("artist"),
                "album": item.get("album"),
                "label": album_label(item.get("artist"), item.get("album")),
                "tracks": tracks,
                "analyzed": analyzed,
                "current_lufs": current,
                "target_lufs": target,
                "gain_delta": delta,
                "can_normalize": can,
                "skip_reference": ref_skip,
                "reason": reason,
            })
    return out


def all_album_items_for_normalize() -> list:
    """Alle eindeutigen Interpret/Album-Gruppen als Batch-Auswahl.
    Bewusst nach artist+album gruppiert, damit gleichnamige Alben verschiedener
    Interpreten nicht vermischt werden.
    """
    with db() as con:
        rows = con.execute(
            """
            SELECT artist, album, COUNT(*) tracks
            FROM tracks
            WHERE COALESCE(TRIM(album),'') <> ''
            GROUP BY artist, album
            ORDER BY artist COLLATE NOCASE, album COLLATE NOCASE
            """
        ).fetchall()
        return [{"artist": r["artist"], "album": r["album"]} for r in rows]


def all_normalize_preview() -> dict:
    settings = get_settings()
    items = all_album_items_for_normalize()
    preview = batch_preview_items(items) if items else []
    normalizable = [p for p in preview if p.get("can_normalize")]
    skipped_reference = [p for p in preview if p.get("skip_reference")]
    blocked = [p for p in preview if (not p.get("can_normalize") and not p.get("skip_reference"))]
    return {
        "items": preview,
        "normalizable": normalizable,
        "blocked": blocked,
        "skipped_reference": skipped_reference,
        "count_albums_total": len(preview),
        "count_albums": len(normalizable),
        "count_blocked": len(blocked),
        "count_skipped_reference": len(skipped_reference),
        "count_tracks": sum(int(p.get("tracks") or 0) for p in normalizable),
        "target_lufs": settings.get("target_lufs"),
        "true_peak": settings.get("true_peak"),
        "lra": settings.get("lra"),
        "backup_mode": settings.get("backup_mode", "on"),
        "can_normalize": bool(normalizable),
    }


def normalize_all_worker(backup_mode: Optional[str] = None):
    init_db()
    pv = all_normalize_preview()
    items = [{"artist": p.get("artist"), "album": p.get("album")} for p in pv.get("normalizable", [])]
    if not items:
        state.update({"running": False, "mode": "idle", "done": 0, "total": 0, "current": "", "message": "Keine vollständig analysierten Alben zu normalisieren", "errors": 0, "recent_errors": []})
        add_log("Alles normalisieren: keine vollständig analysierten Alben gefunden", True)
        return
    if pv.get("count_blocked"):
        add_log(f"Alles normalisieren: {pv.get('count_blocked')} Album/Alben übersprungen, weil sie noch nicht vollständig analysiert sind")
    if pv.get("count_skipped_reference"):
        add_log(f"Alles normalisieren: {pv.get('count_skipped_reference')} Referenzalbum/Alben übersprungen")
    normalize_batch_worker(items, backup_mode)


def analyze_batch_worker(items: list):
    init_db()
    albums = []
    for raw in items:
        try:
            albums.append(normalize_album_item(raw))
        except Exception as e:
            state["errors"] += 1
            add_log(f"Batch-Auswahl übersprungen: {e}", True)
    all_rows = []
    for item in albums:
        rows = rows_for_album_item(item)
        for row in rows:
            row["_album_label"] = album_label(item.get("artist"), item.get("album"))
        all_rows.extend(rows)

    workers = analysis_parallelism()
    begin_job("batch_analysis", len(all_rows), f"Batch-Analyse läuft ({workers} parallel)")
    add_log(f"Batch-Analyse gestartet: {len(albums)} Album/Alben, {len(all_rows)} Titel, parallel: {workers}")

    def work(row):
        return row, analyze_track_file(get_music_root() / row["path"])

    with db() as con:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(work, row): row for row in all_rows}
            for fut in as_completed(futures):
                if stop_requested():
                    for pending in futures:
                        pending.cancel()
                    break
                row = futures[fut]
                state["current"] = f"{row.get('_album_label','')} / {row['path']}".strip(" /")
                try:
                    _, result = fut.result()
                    upsert_analysis(con, row["id"], result)
                except Exception as e:
                    state["errors"] += 1
                    upsert_analysis(con, row["id"], None, str(e))
                    add_log(f"Analysefehler: {row['path']} - {e}", True)
                state["done"] += 1
                con.commit()

    if stop_requested():
        add_log(f"Batch-Analyse abgebrochen: {state['done']}/{state['total']} Titel, Fehler {state['errors']}", True)
        finish_job("Batch-Analyse abgebrochen", True)
    else:
        add_log(f"Batch-Analyse fertig: {state['done']}/{state['total']} Titel, Fehler {state['errors']}")
        finish_job("Batch-Analyse fertig")


def normalize_batch_worker(items: list, backup_mode: Optional[str] = None):
    init_db()
    settings = get_settings()
    if backup_mode is not None:
        settings["backup_mode"] = backup_mode
    previews = batch_preview_items(items)
    skipped_ref = [p for p in previews if p.get("skip_reference")]
    blocked = [p for p in previews if (not p.get("can_normalize") and not p.get("skip_reference"))]
    if blocked:
        names = "; ".join(f"{p['label']}: {p.get('reason') or 'nicht möglich'}" for p in blocked[:5])
        state.update({"running": False, "mode": "idle", "done": 0, "total": 0, "current": "", "message": "Batch-Normalisierung abgebrochen", "errors": len(blocked), "recent_errors": []})
        add_log(f"Batch-Normalisierung abgebrochen: {names}", True)
        return
    albums = [normalize_album_item(p) for p in previews if p.get("can_normalize")]
    if skipped_ref:
        add_log("Referenzalbum übersprungen: " + "; ".join(p.get("label") or p.get("album") for p in skipped_ref))
    if not albums:
        state.update({"running": False, "mode": "idle", "done": 0, "total": 0, "current": "", "message": "Keine Alben zu normalisieren", "errors": 0, "recent_errors": []})
        return
    all_rows = []
    for item in albums:
        rows = rows_for_album_item(item)
        for row in rows:
            row["_album_label"] = album_label(item.get("artist"), item.get("album"))
        all_rows.extend(rows)
    job_id = history_job_id()
    begin_job("batch_normalize", len(all_rows), f"Batch-Normalisierung auf {settings.get('target_lufs')} LUFS")
    add_log(f"Batch-Normalisierung gestartet: {len(albums)} Album/Alben, {len(all_rows)} Titel auf {settings.get('target_lufs')} LUFS, Backup: {settings.get('backup_mode','on')}")
    with db() as con:
        for row in all_rows:
            if stop_requested():
                add_log("Batch-Normalisierung abgebrochen")
                break
            state["current"] = f"{row.get('_album_label','')} / {row['path']}".strip(" /")
            try:
                before = analyze_track_file(get_music_root() / row["path"])
                backup_path = normalize_file(row["path"], settings, settings.get("backup_mode", "on"))
                # Direkt nach jedem normalisierten Titel neu analysieren, damit Albumkarte
                # und Titelliste nach Abschluss aktuelle Werte zeigen.
                result = analyze_and_store(con, row["id"], row["path"])
                insert_history(con, job_id, row, row.get("artist"), row.get("album"), backup_path, settings.get("backup_mode", "on"), settings, before, result)
                add_log(f"Normalisiert: {row['path']}")
            except Exception as e:
                state["errors"] += 1
                upsert_analysis(con, row["id"], None, str(e))
                add_log(f"Normalisierungsfehler: {row['path']} - {e}", True)
            state["done"] += 1
            con.commit()
    if stop_requested():
        add_log(f"Batch-Normalisierung abgebrochen: {state['done']}/{state['total']} Titel, Fehler {state['errors']}", True)
        finish_job("Batch-Normalisierung abgebrochen", True)
    else:
        add_log(f"Batch-Normalisierung fertig: {state['done']}/{state['total']} Titel, Fehler {state['errors']}")
        finish_job("Batch-Normalisierung fertig")


def build_sort_plan(limit_preview: int = 100):
    root = get_music_root().resolve()
    plan = []
    skipped = 0
    conflicts = 0
    with db() as con:
        rows = [dict(r) for r in con.execute(
            """
            SELECT id,path,filename,title,artist,album,size,mtime
            FROM tracks
            ORDER BY artist COLLATE NOCASE, album COLLATE NOCASE, title COLLATE NOCASE, path COLLATE NOCASE
            """
        ).fetchall()]
    groups = {}
    for r in rows:
        try:
            rel = str(r.get("path") or "").lstrip("/")
            current = (root / rel).resolve()
            if not current.exists() or not current.is_file():
                skipped += 1
                continue

            # v1.8.12: Die Sortierung darf NICHT mehr blind den Datenbankwerten
            # vertrauen. Nach manuellen Tag-Änderungen kann die DB kurzzeitig/stale
            # sein. Würden wir dann nach DB sortieren, kann MusicLab Dateien wieder
            # in die alte Struktur zurückschieben. Deshalb liest die Sortierplanung
            # immer die aktuellen Tags aus der Datei und nutzt nur bei Lesefehlern
            # die DB als Fallback.
            live = None
            try:
                live = scan_file(current, root)
            except Exception:
                live = None
            artist = (live or {}).get("artist") or r.get("artist") or "Unbekannter Interpret"
            album = (live or {}).get("album") or r.get("album") or "Unbekanntes Album"
            title = (live or {}).get("title") or r.get("title") or current.stem
            ext = current.suffix or Path(r.get("filename") or current.name).suffix or ".mp3"
            target_rel = Path(safe_name(artist, "Unbekannter Interpret")) / safe_name(album, "Unbekanntes Album") / f"{safe_name(title, current.stem)}{ext}"
            target = (root / target_rel).resolve()
            if target == current:
                continue
            if target.exists():
                conflicts += 1
                target = unique_target_path(root, target_rel, current)
            item = {"id": r.get("id"), "from": rel, "to": target.relative_to(root).as_posix(), "artist": artist, "album": album}
            key = (artist, album)
            g = groups.setdefault(key, {"artist": artist, "album": album, "count": 0})
            g["count"] += 1
            if len(plan) < limit_preview:
                plan.append(item)
            else:
                plan.append({"id": r.get("id"), "from": rel, "to": item["to"], "hidden": True, "artist": artist, "album": album})
        except Exception:
            skipped += 1
    group_list = sorted(groups.values(), key=lambda x: (-x["count"], (x.get("artist") or "").lower(), (x.get("album") or "").lower()))[:20]
    return {"total": len(rows), "move_count": len(plan), "groups": group_list, "preview": [p for p in plan if not p.get("hidden")], "hidden": max(0, len(plan) - limit_preview), "conflicts": conflicts, "skipped": skipped, "_plan": plan}


def sort_library_worker():
    reset_stop()
    try:
        full = build_sort_plan(limit_preview=10**9)
        plan = full.get("_plan", [])
        state.update({"running": True, "mode": "Bibliothek sortieren", "total": len(plan), "done": 0, "errors": 0, "current": "", "message": "Bibliothek wird anhand der Tags sortiert"})
        add_log(f"Bibliothek sortieren gestartet: {len(plan)} Dateien")
        root = get_music_root().resolve()
        moved = 0
        with db() as con:
            for it in plan:
                if stop_requested():
                    break
                try:
                    src = (root / it["from"]).resolve()
                    dst = (root / it["to"]).resolve()
                    state["current"] = it["from"]
                    if not src.exists():
                        state["errors"] += 1
                        add_log(f"Sortierfehler: {it['from']} - Datei fehlt", True)
                    else:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        final = unique_target_path(root, dst.relative_to(root), src)
                        shutil.move(str(src), str(final))
                        prune_empty_dirs(src.parent, root)
                        rel = final.relative_to(root).as_posix()
                        # Nach dem Verschieben direkt neu aus der Datei lesen und DB
                        # synchronisieren. So bleibt die Sortierung tag-basiert und
                        # alte DB-Werte können spätere Sortierläufe nicht zurückdrehen.
                        try:
                            fresh = scan_file(final, root)
                            con.execute("DELETE FROM tracks WHERE path=? AND path<>?", (it["from"], rel))
                            upsert_track(con, fresh)
                        except Exception:
                            st = final.stat()
                            con.execute("UPDATE tracks SET path=?, filename=?, size=?, mtime=? WHERE path=?", (rel, final.name, st.st_size, st.st_mtime, it["from"]))
                        moved += 1
                except Exception as e:
                    state["errors"] += 1
                    add_log(f"Sortierfehler: {it.get('from')} - {e}", True)
                state["done"] += 1
                con.commit()
        if stop_requested():
            add_log(f"Bibliothek sortieren abgebrochen: {state['done']}/{state['total']} Dateien, Fehler {state['errors']}", True)
            finish_job("Bibliothek sortieren abgebrochen", True)
        else:
            add_log(f"Bibliothek sortieren fertig: {moved} Dateien verschoben, Fehler {state['errors']}")
            finish_job("Bibliothek sortieren fertig")
    except Exception as e:
        add_log(f"Bibliothek sortieren fehlgeschlagen: {e}", True)
        finish_job("Bibliothek sortieren fehlgeschlagen", True)


@app.get("/api/fs/browse")
def api_fs_browse(path: str = "/music"):
    # Simple container-side folder picker. The browser cannot access NAS paths directly;
    # it can only choose paths mounted into the container.
    try:
        p = Path(path or "/music")
        if not p.is_absolute():
            p = Path("/") / p
        p = p.resolve()
        if not p.exists() or not p.is_dir():
            raise HTTPException(status_code=404, detail="Ordner nicht gefunden")
        dirs = []
        try:
            for child in p.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    dirs.append({"name": child.name, "path": child.as_posix()})
        except PermissionError:
            pass
        dirs.sort(key=lambda x: x["name"].lower())
        return {"path": p.as_posix(), "parent": p.parent.as_posix(), "dirs": dirs[:500]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/library/sort_preview")
def api_library_sort_preview():
    p = build_sort_plan(limit_preview=50)
    p.pop("_plan", None)
    return p




@app.get("/api/library/sort_preview_export")
def api_library_sort_preview_export():
    p = build_sort_plan(limit_preview=10**9)
    rows = p.get("_plan", [])
    out = io.StringIO()
    out.write("from;to;artist;album\n")
    for r in rows:
        def cell(v):
            return '"' + str(v or '').replace('"', '""') + '"'
        out.write(';'.join([cell(r.get("from")), cell(r.get("to")), cell(r.get("artist")), cell(r.get("album"))]) + "\n")
    filename = f"musiclab_sort_preview_{time.strftime('%Y-%m-%d_%H-%M-%S')}.csv"
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.post("/api/library/sort")
def api_library_sort():
    if state.get("running"):
        return {"ok": False, "error": "Es läuft bereits ein Vorgang. Bitte erst stoppen oder warten."}
    begin_job("Bibliothek sortieren", 0, "Sortierung wird vorbereitet")
    threading.Thread(target=sort_library_worker, daemon=True).start()
    return {"ok": True, "started": True}


# ---------------------------------------------------------------------------
# Credits / Integrität
# ---------------------------------------------------------------------------
CREDIT_TEXT = "Idea & Umsetzung by Lrd.Tiberius"
COPYRIGHT_TEXT = "Copyright © 2026 Lrd.Tiberius"

@app.get("/api/about")
def api_about():
    # Credits intentionally come from the backend as well as the frontend so
    # the attribution is not a purely cosmetic UI string.
    return {
        "name": "MusicLab",
        "version": "1.8.12",
        "credit": CREDIT_TEXT,
        "copyright": COPYRIGHT_TEXT,
        "integrity": "ok",
    }


def norm_text(v: str) -> str:
    v = (v or "").lower()
    v = re.sub(r"\b(remaster(?:ed)?|deluxe|explicit|radio edit|bonus track|version)\b", " ", v)
    v = re.sub(r"[\[\](){}_.\-]+", " ", v)
    v = re.sub(r"\s+", " ", v).strip()
    return v


def similarity(a: str, b: str) -> float:
    a, b = norm_text(a), norm_text(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def intended_rel_path_for_row(r) -> str:
    artist = safe_name(r["artist"], "Unbekannter Interpret")
    album = safe_name(r["album"], "Unbekanntes Album")
    title = safe_name(r["title"], Path(r["path"]).stem)
    ext = Path(r["path"]).suffix or ".mp3"
    return (Path(artist) / album / f"{title}{ext}").as_posix()


def check_album_cover(paths: list) -> bool:
    root = get_music_root()
    for rel in paths[:3]:
        try:
            p = root / rel
            if p.exists() and _embedded_cover_from_file(p):
                return True
        except Exception:
            continue
    return False


@app.get("/api/library_check")
def api_library_check(threshold: float = 0.90):
    threshold = max(0.50, min(float(threshold or 0.90), 1.0))
    with db() as con:
        rows = [dict(r) for r in con.execute("""
            SELECT id,path,artist,album,title,track_number,track_total,disc_number,disc_total,genre,year,duration,size,bitrate,codec
            FROM tracks
            ORDER BY artist COLLATE NOCASE, album COLLATE NOCASE, disc_number, track_number, title COLLATE NOCASE
        """).fetchall()]

    confirmed_keys = get_confirmed_duplicate_keys()

    # 1) Echte Duplikate: gleicher Interpret + Album, ähnlicher Titel, ähnliche Dauer.
    by_album = {}
    for r in rows:
        key = (norm_text(r.get("artist") or ""), norm_text(r.get("album") or ""))
        by_album.setdefault(key, []).append(r)
    real_duplicates = []
    for (_, _), items in by_album.items():
        n = len(items)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = items[i], items[j]
                score = similarity(a.get("title") or "", b.get("title") or "")
                if score < threshold:
                    continue
                # v1.8.5: Sebastian wollte die Duplikatregel bewusst einfach und sichtbar:
                # gleicher Interpret + gleiches Album + mindestens 90 % ähnlicher Titel.
                # Dauer und Tracknummer werden NICHT mehr als Ausschlusskriterium genutzt.
                pair_paths = [a.get("path"), b.get("path")]
                pair_key = duplicate_pair_key(pair_paths)
                if pair_key in confirmed_keys:
                    continue
                real_duplicates.append({
                    "title": a.get("title") or b.get("title"),
                    "artist": a.get("artist"),
                    "album": a.get("album"),
                    "score": round(score, 3),
                    "pair_key": pair_key,
                    "items": [
                        {"path": a.get("path"), "duration": a.get("duration"), "bitrate": a.get("bitrate")},
                        {"path": b.get("path"), "duration": b.get("duration"), "bitrate": b.get("bitrate")},
                    ],
                })
                if len(real_duplicates) >= 200:
                    break
            if len(real_duplicates) >= 200:
                break
        if len(real_duplicates) >= 200:
            break

    # 2) Mehrfach vorhandene Titel: gleicher Interpret + Titel in mehreren Alben = Hinweis, kein Fehler.
    title_groups = {}
    for r in rows:
        key = (norm_text(r.get("artist") or ""), norm_text(r.get("title") or ""))
        if not key[0] or not key[1]:
            continue
        g = title_groups.setdefault(key, {"title": r.get("title"), "artist": r.get("artist"), "albums": {}, "items": []})
        g["albums"].setdefault(r.get("album") or "", 0)
        g["albums"][r.get("album") or ""] += 1
        if len(g["items"]) < 12:
            g["items"].append({"path": r.get("path"), "album": r.get("album")})
    repeated_titles = []
    for g in title_groups.values():
        if len(g["albums"]) > 1:
            repeated_titles.append({
                "title": g["title"],
                "artist": g["artist"],
                "album": f"{len(g['albums'])} Alben",
                "score": 1.0,
                "items": g["items"],
            })
    repeated_titles.sort(key=lambda x: (-len(x.get("items", [])), (x.get("artist") or "").lower(), (x.get("title") or "").lower()))
    repeated_titles = repeated_titles[:200]

    # 3) Dateikonflikte nach Sortierung: mehrere aktuelle Dateien würden auf denselben Zielpfad zeigen.
    targets = {}
    for r in rows:
        targets.setdefault(intended_rel_path_for_row(r), []).append(r)
    file_conflicts = []
    for target, items in targets.items():
        if len(items) > 1:
            file_conflicts.append({
                "title": target,
                "name": target,
                "score": 1.0,
                "items": [{"path": x.get("path")} for x in items[:20]],
            })
    file_conflicts.sort(key=lambda x: x["title"].lower())
    file_conflicts = file_conflicts[:200]

    missing_year = [r for r in rows if not str(r.get("year") or "").strip()]
    missing_genre = [r for r in rows if not str(r.get("genre") or "").strip()]

    # Missing cover is checked per album/folder group to avoid scanning all files repeatedly.
    album_paths = {}
    for r in rows:
        folder = str(Path(r["path"]).parent.as_posix())
        album_paths.setdefault(folder, {"album": r.get("album"), "artist": r.get("artist"), "paths": []})["paths"].append(r["path"])
    missing_cover = []
    for folder, g in album_paths.items():
        if not check_album_cover(g["paths"]):
            missing_cover.append({"path": folder, "artist": g.get("artist"), "album": g.get("album")})
        if len(missing_cover) >= 50:
            break

    root = get_music_root()
    broken = []
    for r in rows:
        p = root / r["path"]
        if not p.exists() or not p.is_file() or int(r.get("size") or 0) <= 0:
            broken.append({"path": r["path"], "reason": "Datei fehlt oder ist leer"})
        if len(broken) >= 100:
            break

    return {
        "tracks": len(rows),
        "threshold_percent": int(threshold * 100),
        "real_duplicates": real_duplicates,
        "repeated_titles": repeated_titles,
        "file_conflicts": file_conflicts,
        "missing_year": {"count": len(missing_year), "examples": [{"path": r["path"]} for r in missing_year[:20]]},
        "missing_genre": {"count": len(missing_genre), "examples": [{"path": r["path"]} for r in missing_genre[:20]]},
        "missing_cover": {"count": len(missing_cover), "examples": missing_cover[:20]},
        "broken_files": broken,
        "confirmed_false_duplicates": len(confirmed_keys),
    }


@app.get("/api/duplicates")
def api_duplicates(threshold: float = 0.90):
    """Schneller, klar benannter Endpunkt für den Duplikate-Tab.

    Regel: gleicher Interpret + gleiches Album + Titelähnlichkeit >= threshold.
    Titel auf verschiedenen Alben werden nicht als echte Duplikate gezählt.
    """
    data = api_library_check(threshold)
    real = data.get("real_duplicates", [])
    return {
        "tracks": data.get("tracks", 0),
        "threshold_percent": data.get("threshold_percent", int(float(threshold or 0.90) * 100)),
        "duplicates": real,
        "real_duplicates": real,
        "repeated_titles": data.get("repeated_titles", []),
        "file_conflicts": data.get("file_conflicts", []),
        "missing_year": data.get("missing_year", {"count": 0, "examples": []}),
        "missing_genre": data.get("missing_genre", {"count": 0, "examples": []}),
        "missing_cover": data.get("missing_cover", {"count": 0, "examples": []}),
        "broken_files": data.get("broken_files", []),
        "confirmed_false_duplicates": data.get("confirmed_false_duplicates", 0),
    }


@app.post("/api/duplicates/confirm")
def api_confirm_non_duplicate(payload: dict):
    """Mark a duplicate candidate as checked/false positive so it no longer appears."""
    init_db()
    paths = payload.get("paths") or []
    if len(paths) < 2:
        raise HTTPException(status_code=400, detail="Mindestens zwei Pfade erforderlich")
    paths = [str(x or "").strip().replace("\\", "/") for x in paths if str(x or "").strip()]
    paths = sorted(dict.fromkeys(paths))
    if len(paths) < 2:
        raise HTTPException(status_code=400, detail="Mindestens zwei unterschiedliche Pfade erforderlich")
    pair_key = duplicate_pair_key(paths[:2])
    reason = str(payload.get("reason") or "Kein Duplikat bestätigt").strip()[:300]
    with db() as con:
        con.execute(
            "INSERT OR REPLACE INTO duplicate_confirmations(pair_key,path_a,path_b,reason,created_at) VALUES(?,?,?,?,?)",
            (pair_key, paths[0], paths[1], reason, time.time()),
        )
        con.commit()
    add_log(f"Duplikat als geprüft/kein Duplikat bestätigt: {paths[0]} <-> {paths[1]}")
    return {"ok": True, "pair_key": pair_key}


@app.get("/api/duplicates/confirmed")
def api_confirmed_non_duplicates():
    init_db()
    with db() as con:
        rows = [dict(r) for r in con.execute("SELECT pair_key,path_a,path_b,reason,created_at FROM duplicate_confirmations ORDER BY created_at DESC").fetchall()]
    return {"count": len(rows), "items": rows}


@app.delete("/api/duplicates/confirmed")
def api_clear_confirmed_non_duplicates(pair_key: Optional[str] = None):
    init_db()
    with db() as con:
        if pair_key:
            con.execute("DELETE FROM duplicate_confirmations WHERE pair_key=?", (pair_key,))
        else:
            con.execute("DELETE FROM duplicate_confirmations")
        con.commit()
    return {"ok": True}


@app.get("/api/path_info")
def api_path_info(path: str, request: Request):
    return safe_music_path_info(path, request)


@app.get("/api/library_check/export")
def api_library_check_export():
    data = api_library_check()
    out = io.StringIO()
    out.write("category;title;artist;album;path\n")
    def cell(v):
        return '"' + str(v or '').replace('"', '""') + '"'
    for cat, key in [("echte_duplikate", "real_duplicates"), ("mehrfach_vorhanden", "repeated_titles"), ("dateikonflikt", "file_conflicts")]:
        for g in data.get(key, []):
            for item in g.get("items", []):
                out.write(';'.join([cell(cat), cell(g.get("title") or g.get("name")), cell(g.get("artist")), cell(g.get("album")), cell(item.get("path"))]) + "\n")
    for cat in ["missing_year", "missing_genre", "missing_cover"]:
        for item in data.get(cat, {}).get("examples", []):
            out.write(';'.join([cell(cat), cell(""), cell(item.get("artist")), cell(item.get("album")), cell(item.get("path"))]) + "\n")
    for item in data.get("broken_files", []):
        out.write(';'.join([cell("broken_file"), cell(item.get("reason")), cell(""), cell(""), cell(item.get("path"))]) + "\n")
    filename = f"musiclab_bibliothekspruefung_{time.strftime('%Y-%m-%d_%H-%M-%S')}.csv"
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.on_event("startup")
def startup():
    init_db()
    if not getattr(app.state, "watcher_started", False):
        app.state.watcher_started = True
        threading.Thread(target=watcher_loop, daemon=True).start()


@app.get("/api/health")
def health():
    return {"ok": True, "version": "1.8.12", "music_root": str(get_music_root()), "db": str(DB_PATH)}


@app.post("/api/scan")
def scan():
    if not state["running"]:
        threading.Thread(target=scan_worker, daemon=True).start()
    return state


@app.post("/api/analyze")
def analyze(artist: Optional[str] = None, album: Optional[str] = None):
    if not state["running"]:
        threading.Thread(target=analysis_worker, kwargs={"artist": artist, "album": album}, daemon=True).start()
    return state


@app.post("/api/normalize")
def normalize(artist: Optional[str] = None, album: Optional[str] = None, backup: Optional[str] = None):
    if not state["running"]:
        threading.Thread(target=normalize_worker, kwargs={"artist": artist, "album": album, "backup_mode": backup}, daemon=True).start()
    return state


@app.get("/api/normalize_preview")
def normalize_preview(album: str, artist: Optional[str] = None):
    settings = get_settings()
    with db() as con:
        summary = album_summary(con, artist, album)
    tracks = summary.get("tracks") or 0
    analyzed = summary.get("analyzed") or 0
    current = summary.get("avg_lufs")
    try:
        target = float(settings.get("target_lufs", "-16"))
    except Exception:
        target = -16.0
    delta = round(target - float(current), 2) if current is not None else None
    can = bool(tracks and analyzed == tracks and current is not None)
    reason = None
    if not tracks:
        reason = "Album nicht gefunden"
    elif analyzed != tracks:
        reason = "Album zuerst vollständig analysieren"
    elif current is None:
        reason = "Keine Analysewerte vorhanden"
    return {
        "artist": artist,
        "album": album,
        "tracks": tracks,
        "analyzed": analyzed,
        "current_lufs": current,
        "target_lufs": target,
        "gain_delta": delta,
        "true_peak": settings.get("true_peak"),
        "lra": settings.get("lra"),
        "backup_mode": settings.get("backup_mode", "on"),
        "can_normalize": can,
        "reason": reason,
    }


@app.post("/api/analyze_batch")
def analyze_batch(data: dict):
    items = data.get("albums") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="Keine Alben übergeben")
    if not state["running"]:
        threading.Thread(target=analyze_batch_worker, args=(items,), daemon=True).start()
    return state


@app.post("/api/normalize_preview_batch")
def normalize_preview_batch(data: dict):
    items = data.get("albums") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="Keine Alben übergeben")
    settings = get_settings()
    preview = batch_preview_items(items)
    return {
        "items": preview,
        "count_albums": len(preview),
        "count_tracks": sum(int(p.get("tracks") or 0) for p in preview),
        "can_normalize": any(p.get("can_normalize") for p in preview) and all((p.get("can_normalize") or p.get("skip_reference")) for p in preview),
        "skipped_reference": [p for p in preview if p.get("skip_reference")],
        "target_lufs": settings.get("target_lufs"),
        "true_peak": settings.get("true_peak"),
        "lra": settings.get("lra"),
        "backup_mode": settings.get("backup_mode", "on"),
    }


@app.post("/api/normalize_batch")
def normalize_batch(data: dict):
    items = data.get("albums") or []
    backup = data.get("backup")
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="Keine Alben übergeben")
    if not state["running"]:
        threading.Thread(target=normalize_batch_worker, args=(items, backup), daemon=True).start()
    return state


@app.get("/api/normalize_preview_all")
def normalize_preview_all():
    return all_normalize_preview()


@app.post("/api/normalize_all")
def normalize_all(data: dict = None):
    data = data or {}
    backup = data.get("backup") if isinstance(data, dict) else None
    if not state["running"]:
        threading.Thread(target=normalize_all_worker, args=(backup,), daemon=True).start()
    return state


@app.post("/api/normalize_preview_tracks")
def normalize_preview_tracks(data: dict):
    return tracks_preview(data.get("paths") or [])


@app.post("/api/normalize_tracks")
def normalize_tracks(data: dict):
    paths = data.get("paths") or []
    backup = data.get("backup")
    if not state["running"]:
        threading.Thread(target=normalize_tracks_worker, args=(paths, backup), daemon=True).start()
    return state


@app.post("/api/stop")
def stop_job():
    if state.get("running"):
        stop_event.set()
        state["stop_requested"] = True
        state["message"] = "Abbruch angefordert"
        add_log("Abbruch angefordert")
    return state


@app.get("/api/settings")
def api_settings():
    return get_settings()


@app.post("/api/settings")
def api_save_settings(data: dict):
    save_settings(data)
    return get_settings()


@app.get("/api/settings/check_music_root")
def api_check_music_root(path: Optional[str] = None):
    return check_music_root(path)


@app.get("/api/status")
def status():
    return state


@app.get("/api/stats")
def stats():
    with db() as con:
        return {
            "artists": con.execute("SELECT COUNT(DISTINCT artist) c FROM tracks").fetchone()["c"],
            "albums": con.execute("SELECT COUNT(*) c FROM (SELECT album FROM tracks GROUP BY album)").fetchone()["c"],
            "tracks": con.execute("SELECT COUNT(*) c FROM tracks").fetchone()["c"],
            "duration": con.execute("SELECT COALESCE(SUM(duration),0) c FROM tracks").fetchone()["c"],
            "analyzed": con.execute("SELECT COUNT(*) c FROM analysis WHERE status='ok'").fetchone()["c"],
            "schema_version": SCHEMA_VERSION,
        }


@app.get("/api/artists")
def get_artists(q: str = ""):
    sql = "SELECT artist, COUNT(DISTINCT album) albums, COUNT(*) tracks, COALESCE(SUM(duration),0) duration FROM tracks"
    args = []
    if q:
        sql += " WHERE artist LIKE ?"
        args.append(f"%{q}%")
    sql += " GROUP BY artist ORDER BY artist COLLATE NOCASE"
    with db() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


@app.get("/api/albums")
def get_albums(artist: str, q: str = ""):
    where = "WHERE t.artist=?"
    args = [artist]
    if q:
        where += " AND t.album LIKE ?"
        args.append(f"%{q}%")
    with db() as con:
        return [dict(r) for r in con.execute(
            f"""
            SELECT t.album, COUNT(*) tracks, COALESCE(SUM(t.duration),0) duration,
            COUNT(a.track_id) analyzed, ROUND(AVG(a.input_i),2) avg_lufs,
            ROUND(MAX(a.input_tp),2) max_true_peak, ROUND(AVG(a.input_lra),2) avg_lra
            FROM tracks t LEFT JOIN analysis a ON a.track_id=t.id AND a.status='ok'
            {where} GROUP BY t.album ORDER BY t.album COLLATE NOCASE
            """, args,
        ).fetchall()]


@app.get("/api/library_albums")
def get_library_albums(q: str = ""):
    where = ""
    args = []
    if q:
        where = "WHERE t.album LIKE ? OR t.artist LIKE ?"
        args.extend([f"%{q}%", f"%{q}%"])
    with db() as con:
        rows = con.execute(
            f"""
            SELECT
              t.album,
              CASE WHEN COUNT(DISTINCT t.artist)=1 THEN MIN(t.artist) ELSE 'Verschiedene Interpreten' END AS artist,
              COUNT(DISTINCT t.artist) AS artist_count,
              COUNT(*) tracks, COALESCE(SUM(t.duration),0) duration,
              COUNT(a.track_id) analyzed, ROUND(AVG(a.input_i),2) avg_lufs,
              ROUND(MAX(a.input_tp),2) max_true_peak, ROUND(AVG(a.input_lra),2) avg_lra
            FROM tracks t LEFT JOIN analysis a ON a.track_id=t.id AND a.status='ok'
            {where}
            GROUP BY t.album
            ORDER BY t.album COLLATE NOCASE
            LIMIT 1000
            """, args,
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/new_albums")
def get_new_albums(q: str = ""):
    """Work queue for new/open albums: albums with at least one not-yet-analyzed track."""
    where = ""
    args = []
    if q:
        where = "WHERE t.album LIKE ? OR t.artist LIKE ?"
        args.extend([f"%{q}%", f"%{q}%"])
    with db() as con:
        rows = con.execute(
            f"""
            SELECT
              t.album,
              CASE WHEN COUNT(DISTINCT t.artist)=1 THEN MIN(t.artist) ELSE 'Verschiedene Interpreten' END AS artist,
              COUNT(DISTINCT t.artist) AS artist_count,
              COUNT(*) tracks, COALESCE(SUM(t.duration),0) duration,
              COUNT(a.track_id) analyzed, ROUND(AVG(a.input_i),2) avg_lufs,
              ROUND(MAX(a.input_tp),2) max_true_peak, ROUND(AVG(a.input_lra),2) avg_lra,
              MAX(t.scanned_at) last_seen
            FROM tracks t LEFT JOIN analysis a ON a.track_id=t.id AND a.status='ok'
            {where}
            GROUP BY t.album
            HAVING analyzed < tracks
            ORDER BY last_seen DESC, t.album COLLATE NOCASE
            LIMIT 1000
            """, args,
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/library_album")
def get_library_album(album: str):
    with db() as con:
        row = con.execute(
            """
            SELECT
              t.album,
              CASE WHEN COUNT(DISTINCT t.artist)=1 THEN MIN(t.artist) ELSE 'Verschiedene Interpreten' END AS artist,
              COUNT(DISTINCT t.artist) AS artist_count,
              COUNT(*) tracks, COALESCE(SUM(t.duration),0) duration,
              COUNT(a.track_id) analyzed, ROUND(AVG(a.input_i),2) avg_lufs,
              ROUND(MAX(a.input_tp),2) max_true_peak, ROUND(AVG(a.input_lra),2) avg_lra
            FROM tracks t LEFT JOIN analysis a ON a.track_id=t.id AND a.status='ok'
            WHERE t.album=?
            GROUP BY t.album
            """, (album,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Album nicht gefunden")
        return dict(row)




def parent_folder_key(rel_path: str) -> str:
    try:
        parent = Path(str(rel_path)).parent.as_posix()
        return "" if parent == "." else parent
    except Exception:
        return ""


def _is_disc_folder_name(name: str) -> bool:
    s = (name or "").strip().lower()
    # Mehrfach-CDs werden oft als "CD1", "Disc 1" oder auch
    # "Disc 4 Worte der Freiheit" abgelegt. Für die Medienansicht sollen
    # diese Unterordner zu EINEM Album zusammengefasst werden.
    return bool(
        re.match(r"^(cd|disc|disk|dvd)\s*[-_. ]*\d+\b", s)
        or re.match(r"^d\d+$", s)
        or re.match(r"^\d+$", s)
    )


def media_album_folder_key(rel_path: str) -> str:
    folder = parent_folder_key(rel_path)
    if not folder:
        return folder
    p = Path(folder)
    if _is_disc_folder_name(p.name):
        parent = p.parent.as_posix()
        return "" if parent == "." else parent
    return folder


def folder_display_name(folder: str) -> str:
    if not folder:
        return "Musik"
    name = Path(folder).name
    return name or folder


def _media_rows():
    with db() as con:
        return [dict(r) for r in con.execute(
            """
            SELECT t.id,t.artist,t.album,t.title,t.track_raw,t.track_number,t.track_total,t.disc_raw,t.disc_number,t.disc_total,t.genre,t.year,t.duration,t.codec,t.bitrate,t.sample_rate,t.channels,t.path,t.filename,
            a.input_i,a.input_tp,a.input_lra,a.status AS analysis_status
            FROM tracks t LEFT JOIN analysis a ON a.track_id=t.id
            ORDER BY t.artist COLLATE NOCASE, t.album COLLATE NOCASE, COALESCE(t.disc_number,1), COALESCE(t.track_number,9999), t.title COLLATE NOCASE, t.path COLLATE NOCASE
            """
        ).fetchall()]


def _folder_matches(row, folder: str, artist: Optional[str] = None):
    wanted = str(folder or "").strip().strip("/")
    parent = parent_folder_key(row.get("path") or "")
    album_folder = media_album_folder_key(row.get("path") or "")
    # Medienansicht: Ein Album kann Unterordner für mehrere Discs haben.
    # Deshalb passt neben dem exakten Albumordner auch jeder Unterordner
    # darunter, z. B. ".../Lieder wie Orkane/Disc 1 ...".
    if album_folder != wanted and parent != wanted and not (wanted and parent.startswith(wanted + "/")):
        return False
    if artist and (row.get("artist") or "").strip().lower() != artist.strip().lower():
        return False
    return True




@app.get("/api/tag_issues")
def api_tag_issues(q: str = "", kind: str = "all"):
    """Return physical album folders that likely need tag cleanup.

    Used by the Tags page as a focused repair list. We group by folder so a click
    opens the same editor the user already uses for album/tag repair.
    """
    q_norm = (q or "").strip().lower()
    kind = (kind or "all").strip().lower()
    with db() as con:
        rows = [dict(r) for r in con.execute("""
            SELECT path,artist,album,title,genre,year,track_number,track_total,disc_number,disc_total,duration
            FROM tracks
            ORDER BY path COLLATE NOCASE
        """).fetchall()]

    def clean(v):
        return str(v or "").strip()

    def bad_year(v):
        v = clean(v)
        if not v or v in {"0", "0000"}:
            return True
        # allow normal date tags such as 2006-05-12, but require a plausible leading year
        m = re.match(r"^(\d{4})", v)
        if not m:
            return True
        y = int(m.group(1))
        return y < 1900 or y > datetime.now().year + 1

    groups = {}
    for r in rows:
        folder = parent_folder_key(r.get("path") or "")
        g = groups.setdefault(folder, {"folder": folder, "items": [], "artists": set(), "albums": set(), "genres": set(), "years": set(), "issues": set()})
        g["items"].append(r)
        for key, setname in [("artist","artists"),("album","albums"),("genre","genres"),("year","years")]:
            v = clean(r.get(key))
            if v:
                g[setname].add(v)

        if not clean(r.get("artist")):
            g["issues"].add("Interpret fehlt")
        if not clean(r.get("album")):
            g["issues"].add("Album fehlt")
        if not clean(r.get("title")):
            g["issues"].add("Titel fehlt")
        if not clean(r.get("genre")):
            g["issues"].add("Genre fehlt")
        if bad_year(r.get("year")):
            g["issues"].add("Jahr fehlt/ungültig")
        if not r.get("track_number"):
            g["issues"].add("Tracknummer fehlt")

    out = []
    for folder, g in groups.items():
        if len(g["artists"]) > 1:
            g["issues"].add("mehrere Interpreten im Ordner")
        if len(g["albums"]) > 1:
            g["issues"].add("mehrere Album-Tags im Ordner")
        if len(g["genres"]) > 1:
            g["issues"].add("mehrere Genres im Album")
        years_clean = {y for y in g["years"] if y and y not in {"0", "0000"}}
        if len(years_clean) > 1:
            g["issues"].add("mehrere Jahre im Album")

        # Flag exact folder/tag spelling differences, but do not block editing.
        parts = Path(folder).parts
        folder_artist = parts[0] if len(parts) >= 2 else ""
        folder_album = parts[-1] if parts else ""
        tag_artist = sorted(g["artists"], key=lambda x: x.lower())[0] if len(g["artists"]) == 1 else ""
        tag_album = sorted(g["albums"], key=lambda x: x.lower())[0] if len(g["albums"]) == 1 else ""
        if folder_artist and tag_artist and folder_artist != tag_artist:
            g["issues"].add("Ordner/Interpret-Schreibweise abweichend")
        if folder_album and tag_album and folder_album != tag_album:
            g["issues"].add("Ordner/Album-Schreibweise abweichend")

        issues = sorted(g["issues"], key=lambda x: x.lower())
        if not issues:
            continue
        if kind != "all":
            kmap = {
                "missing": ["fehlt", "ungültig"],
                "mixed": ["mehrere"],
                "folder": ["Ordner/"],
                "track": ["Tracknummer"],
                "year": ["Jahr"],
                "genre": ["Genre"],
            }
            needles = kmap.get(kind, [kind])
            if not any(any(n.lower() in issue.lower() for n in needles) for issue in issues):
                continue
        artists = sorted(g["artists"], key=lambda x: x.lower())
        albums = sorted(g["albums"], key=lambda x: x.lower())
        examples = []
        for r in g["items"][:8]:
            examples.append({
                "path": r.get("path"),
                "title": r.get("title") or Path(r.get("path") or "").stem,
                "artist": r.get("artist"),
                "album": r.get("album"),
                "year": r.get("year"),
                "genre": r.get("genre"),
            })
        hay = " ".join([folder, " ".join(artists), " ".join(albums), " ".join(issues)]).lower()
        if q_norm and q_norm not in hay:
            continue
        out.append({
            "folder": folder,
            "artist": artists[0] if len(artists) == 1 else ("Verschiedene Interpreten" if artists else ""),
            "album": albums[0] if len(albums) == 1 else (folder_display_name(folder) if not albums else "Mehrere Album-Tags"),
            "tracks": len(g["items"]),
            "issues": issues,
            "issue_count": len(issues),
            "examples": examples,
        })
    out.sort(key=lambda x: (-int(x.get("issue_count") or 0), (x.get("artist") or "").lower(), (x.get("album") or "").lower(), (x.get("folder") or "").lower()))
    return out[:500]

@app.get("/api/tag_albums")
def get_tag_albums(q: str = "", artist: Optional[str] = None, genre: Optional[str] = None, year: Optional[str] = None):
    """Folder-based album list for the tag editor.

    This deliberately groups by the physical album folder instead of existing
    album tags. It prevents broken/foreign tags from merging unrelated files
    into one pseudo album while the user is trying to repair metadata. Optional
    filters (artist/genre/year) are applied to the contained tracks.
    """
    q_norm = (q or "").strip().lower()
    artist_norm = (artist or "").strip().lower()
    genre_norm = (genre or "").strip().lower()
    year_norm = (year or "").strip().lower()
    with db() as con:
        rows = [dict(r) for r in con.execute(
            """
            SELECT t.path,t.artist,t.album,t.title,t.genre,t.year,t.duration,a.track_id AS analyzed
            FROM tracks t LEFT JOIN analysis a ON a.track_id=t.id AND a.status='ok'
            ORDER BY t.path COLLATE NOCASE
            """
        ).fetchall()]
    groups = {}
    for r in rows:
        folder = parent_folder_key(r.get("path") or "")
        hay = " ".join([folder, r.get("artist") or "", r.get("album") or "", r.get("title") or "", r.get("genre") or "", r.get("year") or ""]).lower()
        if q_norm and q_norm not in hay:
            continue
        if artist_norm and (r.get("artist") or "").strip().lower() != artist_norm:
            continue
        if genre_norm and (r.get("genre") or "").strip().lower() != genre_norm:
            continue
        if year_norm and not str(r.get("year") or "").strip().lower().startswith(year_norm):
            continue
        g = groups.setdefault(folder, {"folder": folder, "album": folder_display_name(folder), "artists": set(), "tag_albums": set(), "genres": set(), "years": set(), "tracks": 0, "analyzed": 0, "duration": 0.0})
        if r.get("artist"):
            g["artists"].add(r.get("artist"))
        if r.get("album"):
            g["tag_albums"].add(r.get("album"))
        if r.get("genre"):
            g["genres"].add(r.get("genre"))
        if r.get("year"):
            g["years"].add(str(r.get("year")))
        g["tracks"] += 1
        g["analyzed"] += 1 if r.get("analyzed") is not None else 0
        g["duration"] += float(r.get("duration") or 0)
    out = []
    for g in groups.values():
        artists = sorted(g.pop("artists"), key=lambda x: x.lower())
        tag_albums = sorted(g.pop("tag_albums"), key=lambda x: x.lower())
        genres = sorted(g.pop("genres"), key=lambda x: x.lower())
        years = sorted(g.pop("years"), key=lambda x: x.lower())
        g["artist"] = artists[0] if len(artists) == 1 else ("Verschiedene Interpreten" if artists else "")
        g["artist_count"] = len(artists)
        g["tag_album"] = tag_albums[0] if len(tag_albums) == 1 else ("Mehrere Album-Tags" if tag_albums else "")
        g["genre"] = genres[0] if len(genres) == 1 else ("Verschiedene Genres" if genres else "")
        g["year"] = years[0] if len(years) == 1 else ("Verschiedene Jahre" if years else "")
        out.append(g)
    out.sort(key=lambda x: (x.get("album") or "").lower())
    return out[:1000]


@app.get("/api/tracks_by_folder")
def get_tracks_by_folder(folder: str, artist: Optional[str] = None, genre: Optional[str] = None, year: Optional[str] = None, q: str = ""):
    """Return tracks from one physical folder, optionally limited by the active tag-browser context.

    This matters for repair cases like many root-level/unknown-album files: a folder
    entry shown under a selected artist must not expand to all other artists that
    happen to live in the same physical folder.
    """
    folder = str(folder or "").strip().strip("/")
    artist_norm = (artist or "").strip().lower()
    genre_norm = (genre or "").strip().lower()
    year_norm = (year or "").strip().lower()
    q_norm = (q or "").strip().lower()
    with db() as con:
        rows = [dict(r) for r in con.execute(
            """
            SELECT t.id,t.artist,t.album,t.title,t.track_raw,t.track_number,t.track_total,t.disc_raw,t.disc_number,t.disc_total,t.genre,t.year,t.duration,t.codec,t.bitrate,t.sample_rate,t.channels,t.path,t.filename,
            a.input_i,a.input_tp,a.input_lra,a.status AS analysis_status
            FROM tracks t LEFT JOIN analysis a ON a.track_id=t.id
            ORDER BY COALESCE(t.disc_number,1), COALESCE(t.track_number,9999), t.title COLLATE NOCASE, t.path COLLATE NOCASE
            """
        ).fetchall()]
    out = []
    for r in rows:
        if parent_folder_key(r.get("path") or "") != folder:
            continue
        if artist_norm and (r.get("artist") or "").strip().lower() != artist_norm:
            continue
        if genre_norm and (r.get("genre") or "").strip().lower() != genre_norm:
            continue
        if year_norm and not str(r.get("year") or "").strip().lower().startswith(year_norm):
            continue
        if q_norm:
            hay = " ".join([r.get("artist") or "", r.get("album") or "", r.get("title") or "", r.get("genre") or "", r.get("year") or "", r.get("path") or ""]).lower()
            if q_norm not in hay:
                continue
        out.append(r)
    return out


@app.get("/api/tracks")
def get_tracks(album: str, artist: Optional[str] = None):
    where = "WHERE t.album=?"
    args = [album]
    if artist:
        where += " AND t.artist=?"
        args.append(artist)
    with db() as con:
        return [dict(r) for r in con.execute(
            f"""
            SELECT t.id,t.artist,t.album,t.title,t.track_raw,t.track_number,t.track_total,t.disc_raw,t.disc_number,t.disc_total,t.genre,t.year,t.duration,t.codec,t.bitrate,t.sample_rate,t.channels,t.path,t.filename,
            a.input_i,a.input_tp,a.input_lra,a.status AS analysis_status
            FROM tracks t LEFT JOIN analysis a ON a.track_id=t.id
            {where}
            ORDER BY t.artist COLLATE NOCASE, COALESCE(t.disc_number,1), COALESCE(t.track_number,9999), t.title COLLATE NOCASE, t.path COLLATE NOCASE
            """, args,
        ).fetchall()]


@app.get("/api/genres")
def get_genres():
    with db() as con:
        rows = con.execute("SELECT DISTINCT genre FROM tracks WHERE genre IS NOT NULL AND TRIM(genre)<>'' ORDER BY genre COLLATE NOCASE").fetchall()
        return [r["genre"] for r in rows]


@app.get("/api/years")
def get_years():
    with db() as con:
        rows = con.execute("SELECT DISTINCT year FROM tracks WHERE year IS NOT NULL AND TRIM(year)<>'' ORDER BY year COLLATE NOCASE DESC").fetchall()
        return [r["year"] for r in rows]


@app.post("/api/tags/update")
def update_tags(payload: dict):
    """Update common audio tags for selected files and keep the DB in sync.

    Optional payload flag `sort_files` moves/renames files after writing tags to:
    Artist/Album/Title.ext. The filename intentionally equals the title so
    duplicates are easy to spot. Existing files are never overwritten.
    """
    updates = payload.get("updates") if isinstance(payload, dict) else None
    sort_files = bool(payload.get("sort_files")) if isinstance(payload, dict) else False
    if not isinstance(updates, list):
        raise HTTPException(status_code=400, detail="updates fehlt")
    root = get_music_root().resolve()
    updated = 0
    moved = 0
    album_exists = False
    move_preview = []
    errors = []
    with db() as con:
        for item in updates:
            if not isinstance(item, dict):
                continue
            rel = str(item.get("path") or "").strip().lstrip("/")
            if not rel:
                errors.append("Leerer Pfad")
                continue
            try:
                p = (root / rel).resolve()
                if not p.is_relative_to(root):
                    raise ValueError("Pfad außerhalb der Musikbibliothek")
                if not p.exists():
                    raise FileNotFoundError(rel)
                dbrow = con.execute("SELECT * FROM tracks WHERE path=?", (rel,)).fetchone()
                old = dict(dbrow) if dbrow else {}
                audio = MutagenFile(p, easy=True)
                if audio is None:
                    raise ValueError("Datei kann nicht gelesen werden")
                changed = {}
                mapping = {
                    "title": ["title"],
                    # Das sichtbare Feld heißt "Interpret". Damit spätere Scans und
                    # "Bibliothek anhand der Tags neu sortieren" nicht wieder den alten
                    # Album-Artist bevorzugen, schreiben wir den Wert bewusst in beide
                    # Tags: Artist und Album Artist.
                    "artist": ["artist", "albumartist"],
                    "album": ["album"],
                    "tracknumber": ["tracknumber"],
                    "discnumber": ["discnumber"],
                    "year": ["date"],
                    "genre": ["genre"],
                }
                for src, tag_names in mapping.items():
                    if src in item:
                        val = str(item.get(src) or "").strip()
                        for tag in tag_names:
                            if val:
                                audio[tag] = [val]
                            else:
                                # Leeres Feld bedeutet bewusst entfernen/leeren (wichtig z. B. für falsche Genres).
                                try:
                                    if tag in audio:
                                        del audio[tag]
                                except Exception:
                                    audio[tag] = []
                        changed[src] = val
                audio.save()

                current_rel = rel
                current_path = p
                if sort_files:
                    final_artist = changed.get("artist", old.get("artist") or "Unbekannter Interpret")
                    final_album = changed.get("album", old.get("album") or "Unbekanntes Album")
                    final_title = changed.get("title", old.get("title") or p.stem)
                    target_dir_rel = Path(safe_name(final_artist, "Unbekannter Interpret")) / safe_name(final_album, "Unbekanntes Album")
                    target_dir = (root / target_dir_rel).resolve()
                    if target_dir.exists() and target_dir != current_path.parent.resolve():
                        album_exists = True
                    ext = current_path.suffix or Path(old.get("filename") or current_path.name).suffix or ".mp3"
                    target_rel = target_dir_rel / f"{safe_name(final_title, current_path.stem)}{ext}"
                    target = unique_target_path(root, target_rel, current_path)
                    if target != current_path:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        before_rel = current_path.relative_to(root).as_posix()
                        shutil.move(str(current_path), str(target))
                        prune_empty_dirs(current_path.parent, root)
                        current_path = target
                        current_rel = target.relative_to(root).as_posix()
                        moved += 1
                        if len(move_preview) < 20:
                            move_preview.append({"from": before_rel, "to": current_rel})

                db_updates = []
                args = []
                if current_rel != rel:
                    db_updates.append("path=?"); args.append(current_rel)
                    db_updates.append("filename=?"); args.append(current_path.name)
                if "title" in changed:
                    db_updates.append("title=?"); args.append(changed["title"])
                if "artist" in changed:
                    db_updates.append("artist=?"); args.append(changed["artist"])
                if "album" in changed:
                    db_updates.append("album=?"); args.append(changed["album"])
                if "tracknumber" in changed:
                    tn, tt = parse_number_pair(changed["tracknumber"])
                    db_updates += ["track_raw=?", "track_number=?", "track_total=?"]
                    args += [changed["tracknumber"], tn, tt]
                if "discnumber" in changed:
                    dn, dt = parse_number_pair(changed["discnumber"])
                    db_updates += ["disc_raw=?", "disc_number=?", "disc_total=?"]
                    args += [changed["discnumber"], dn, dt]
                if "genre" in changed:
                    db_updates.append("genre=?"); args.append(changed["genre"])
                if "year" in changed:
                    db_updates.append("year=?"); args.append(changed["year"])
                try:
                    st = current_path.stat()
                    db_updates += ["size=?", "mtime=?"]
                    args += [st.st_size, st.st_mtime]
                except Exception:
                    pass
                if db_updates:
                    args.append(rel)
                    con.execute("UPDATE tracks SET " + ",".join(db_updates) + " WHERE path=?", args)
                updated += 1
            except Exception as e:
                errors.append(f"{rel}: {e}")
        con.commit()
    if updated:
        msg = f"Tags gespeichert: {updated}/{len(updates)} Dateien"
        if moved:
            msg += f", verschoben {moved}"
        if album_exists:
            msg += ", Albumordner existierte bereits"
        if errors:
            msg += f", Fehler {len(errors)}"
        add_log(msg, bool(errors))
    return {"updated": updated, "total": len(updates), "moved": moved, "album_exists": album_exists, "moves": move_preview, "errors": errors[:50]}



@app.get("/api/media/artists")
def api_media_artists(sort: str = "artist"):
    groups = {}
    for r in _media_rows():
        artist = r.get("artist") or "Unbekannter Interpret"
        folder = parent_folder_key(r.get("path") or "")
        g = groups.setdefault(artist, {"artist": artist, "tracks": 0, "albums": set(), "duration": 0.0})
        g["tracks"] += 1
        g["albums"].add(folder)
        g["duration"] += float(r.get("duration") or 0)
    out = []
    for g in groups.values():
        out.append({"artist": g["artist"], "tracks": g["tracks"], "albums": len(g["albums"]), "duration": g["duration"]})
    if sort == "album":
        out.sort(key=lambda x: (x["albums"], x["artist"].lower()))
    else:
        out.sort(key=lambda x: x["artist"].lower())
    return out[:5000]


@app.get("/api/media/artist_albums")
def api_media_artist_albums(artist: str, sort: str = "artist"):
    artist_norm = (artist or "").strip().lower()
    groups = {}
    for r in _media_rows():
        if artist_norm and (r.get("artist") or "").strip().lower() != artist_norm:
            continue
        folder = media_album_folder_key(r.get("path") or "")
        album = r.get("album") or folder_display_name(folder) or "Unbekanntes Album"
        key = folder
        g = groups.setdefault(key, {"artist": artist or r.get("artist") or "Unbekannter Interpret", "album": album, "folder": folder, "tracks": 0, "analyzed": 0, "duration": 0.0, "first_path": r.get("path") or ""})
        g["tracks"] += 1
        g["analyzed"] += 1 if r.get("analysis_status") == "ok" else 0
        g["duration"] += float(r.get("duration") or 0)
    out = list(groups.values())
    if sort == "album":
        out.sort(key=lambda x: ((x.get("album") or "").lower(), (x.get("folder") or "").lower()))
    else:
        out.sort(key=lambda x: ((x.get("artist") or "").lower(), (x.get("album") or "").lower(), (x.get("folder") or "").lower()))
    return out[:5000]


@app.get("/api/media/album_tracks")
def api_media_album_tracks(folder: str, artist: Optional[str] = None):
    folder = str(folder or "").strip().strip("/")
    if folder.startswith("__album__:"):
        album_name = folder[len("__album__:"):].strip()
        out = [r for r in _media_rows() if (r.get("album") or "Unbekanntes Album").strip().lower() == album_name.lower()]
    else:
        out = [r for r in _media_rows() if _folder_matches(r, folder, artist)]
    out.sort(key=lambda r: (int(r.get("disc_number") or 1), int(r.get("track_number") or 9999), (r.get("artist") or "").lower(), (r.get("title") or "").lower(), (r.get("path") or "").lower()))
    return out




def _album_audio_paths(folder: str):
    """Resolve audio files for an album folder safely below MUSIC_ROOT.

    The database is the source of truth. As a fallback, the physical folder is
    scanned directly. Covers are read only from embedded metadata, never from
    folder images, because the user's music folders should stay clean.
    """
    root = get_music_root().resolve()
    safe_folder = str(folder or "").strip().strip("/")
    paths = []

    # 1) Database rows for the exact physical album folder.
    try:
        rows = [r for r in _media_rows() if media_album_folder_key(r.get("path") or "") == safe_folder or parent_folder_key(r.get("path") or "") == safe_folder]
        for r in rows:
            rel = r.get("path") or ""
            p = (root / rel).resolve()
            if p.is_relative_to(root) and p.exists() and p.is_file() and p.suffix.lower() in EXTS:
                paths.append(p)
    except Exception:
        pass

    # 2) Fallback: directly scan the folder. This also helps when the database
    # has just been migrated or after files were moved by tag sorting.
    if not paths:
        try:
            base = (root / safe_folder).resolve()
            if base.is_relative_to(root) and base.exists() and base.is_dir():
                for p in sorted(base.iterdir(), key=lambda x: x.name.lower()):
                    if p.name.startswith("._"):
                        continue
                    if p.is_file() and p.suffix.lower() in EXTS:
                        paths.append(p.resolve())
        except Exception:
            pass
    return paths


def _embedded_cover_from_file(p: Path):
    """Return (mime, bytes) for an embedded cover, or None.

    MP3/APIC is read first and explicitly because it is the common case here
    and is more reliable than generic mutagen access for edge cases.
    """
    try:
        if p.suffix.lower() == ".mp3":
            try:
                tags = ID3(str(p))
                frames = tags.getall("APIC")
                # Prefer front cover (type 3), otherwise use the first APIC.
                frames = sorted(frames, key=lambda f: 0 if getattr(f, "type", None) == 3 else 1)
                for frame in frames:
                    data = getattr(frame, "data", None)
                    if data:
                        return (getattr(frame, "mime", None) or "image/jpeg", data)
            except Exception:
                pass

        mf = MutagenFile(str(p))
        if not mf:
            return None
        tags = getattr(mf, "tags", None)
        if tags:
            # MP3 variants through generic mutagen.
            try:
                for key, val in tags.items():
                    if str(key).startswith("APIC") and getattr(val, "data", None):
                        return (getattr(val, "mime", None) or "image/jpeg", val.data)
            except Exception:
                pass
            # MP4/M4A cover atom.
            try:
                covr = tags.get("covr") if hasattr(tags, "get") else None
                if covr:
                    data = bytes(covr[0])
                    return ("image/jpeg", data)
            except Exception:
                pass
        # FLAC/Vorbis pictures.
        pics = getattr(mf, "pictures", None)
        if pics:
            pic = pics[0]
            return (pic.mime or "image/jpeg", pic.data)
    except Exception:
        return None
    return None



def _safe_audio_path_from_rel(rel: str):
    """Resolve one relative audio path below MUSIC_ROOT, or return None."""
    root = get_music_root().resolve()
    rel = str(rel or "").strip().lstrip("/").replace("\\", "/")
    if rel.startswith("music/"):
        rel = rel[len("music/"):]
    if rel.startswith("/music/"):
        rel = rel[len("/music/"):]
    if not rel:
        return None
    try:
        p = (root / rel).resolve()
        if p.is_relative_to(root) and p.exists() and p.is_file() and p.suffix.lower() in EXTS:
            return p
    except Exception:
        return None
    return None


def _unique_paths(paths):
    out = []
    seen = set()
    for p in paths or []:
        try:
            key = str(p.resolve())
        except Exception:
            key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _audio_paths_from_cover_payload(payload: dict, folder: str):
    """Resolve the exact tracks visible in the Tags UI first.

    This is safer than guessing by album name or folder, especially for:
    - duplicate album names,
    - compilations,
    - virtual selections such as __album__:Name,
    - albums where the folder name and Album tag differ.
    """
    paths = []
    raw_paths = payload.get("paths") or payload.get("track_paths") or []
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    for rel in raw_paths:
        p = _safe_audio_path_from_rel(rel)
        if p is not None:
            paths.append(p)
    paths = _unique_paths(paths)
    if paths:
        return paths

    # Fallback for older frontend builds.
    folder = str(folder or "").strip().strip("/")
    if folder.startswith("__album__:"):
        album_name = folder[len("__album__:"):].strip().lower()
        rows = [r for r in _media_rows() if (r.get("album") or "Unbekanntes Album").strip().lower() == album_name]
        for r in rows:
            p = _safe_audio_path_from_rel(r.get("path") or "")
            if p is not None:
                paths.append(p)
        return _unique_paths(paths)

    return _album_audio_paths(folder)


def _cover_folder_candidates(files):
    """Return physical album folders that contain the selected files."""
    folders = []
    seen = set()
    for f in files or []:
        try:
            parent = f.parent.resolve()
            key = str(parent)
            if key not in seen:
                seen.add(key)
                folders.append(parent)
        except Exception:
            continue
    return folders


def _write_folder_cover_files(folders, raw: bytes, mime: str):
    """Write a folder cover next to the selected tracks as a compatibility fallback.

    Embedding is still the main operation. The folder file helps Finder, Synology,
    Jellyfin/Infuse and other tools that prefer cover.jpg/folder.jpg.
    """
    written = []
    errors = []
    if not folders:
        return written, errors
    if mime == "image/png":
        names = ["cover.png", "folder.png"]
    else:
        names = ["cover.jpg", "folder.jpg"]
    root = get_music_root().resolve()
    for folder in folders:
        for name in names:
            try:
                target = folder / name
                target.write_bytes(raw)
                written.append(str(target.relative_to(root)))
            except Exception as e:
                if len(errors) < 20:
                    errors.append(f"{folder.name}/{name}: {e}")
    return written, errors


@app.post("/api/tags/cover")
async def api_tags_cover(request: Request):
    """Embed an uploaded cover into exactly the tracks currently shown in Tags.

    v1.8.12: The frontend now sends the concrete visible track paths. That avoids
    wrong albums when the UI selection is virtual, when album names exist more
    than once, or when folder names differ from Album tags. A folder cover file is
    also written as a compatibility fallback.
    """
    import base64
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige Cover-Daten")

    folder = str(payload.get("folder") or "").strip().strip("/")
    filename = str(payload.get("filename") or "cover").lower()
    ctype = str(payload.get("content_type") or "").lower()
    data_url = str(payload.get("data") or "")

    if not folder and not payload.get("paths") and not payload.get("track_paths"):
        raise HTTPException(status_code=400, detail="folder oder paths fehlen")

    if "," in data_url and data_url.startswith("data:"):
        data_url = data_url.split(",", 1)[1]
    try:
        raw = base64.b64decode(data_url, validate=False)
    except Exception:
        raise HTTPException(status_code=400, detail="Cover konnte nicht gelesen werden")
    if not raw:
        raise HTTPException(status_code=400, detail="Leere Datei")

    if "png" in ctype or filename.endswith(".png") or raw.startswith(b"\x89PNG"):
        mime = "image/png"
        mp4_format = MP4Cover.FORMAT_PNG
        flac_pic_type = 3
    elif "jpeg" in ctype or "jpg" in ctype or filename.endswith((".jpg", ".jpeg")) or raw.startswith(b"\xff\xd8"):
        mime = "image/jpeg"
        mp4_format = MP4Cover.FORMAT_JPEG
        flac_pic_type = 3
    else:
        raise HTTPException(status_code=400, detail="Bitte JPG oder PNG verwenden")

    root = get_music_root().resolve()
    files = _audio_paths_from_cover_payload(payload, folder)
    files = _unique_paths(files)
    if not files:
        raise HTTPException(status_code=404, detail=f"Keine passenden Audiodateien gefunden: {folder or 'Auswahl'}")

    try:
        folder = str(files[0].parent.relative_to(root))
    except Exception:
        folder = folder or "Auswahl"

    updated = 0
    skipped = 0
    verified = 0
    errors = []

    for p in files:
        rel = str(p.relative_to(root))
        ext = p.suffix.lower()
        try:
            if ext == ".mp3":
                try:
                    tags = ID3(str(p))
                except ID3NoHeaderError:
                    tags = ID3()
                tags.delall("APIC")
                tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=raw))
                tags.save(str(p), v2_version=3)
                updated += 1

            elif ext in {".m4a", ".mp4", ".aac"}:
                audio = MP4(str(p))
                if audio.tags is None:
                    audio.add_tags()
                audio.tags["covr"] = [MP4Cover(raw, imageformat=mp4_format)]
                audio.save()
                updated += 1

            elif ext == ".flac":
                audio = FLAC(str(p))
                audio.clear_pictures()
                pic = Picture()
                pic.type = flac_pic_type
                pic.mime = mime
                pic.desc = "Cover"
                pic.data = raw
                audio.add_picture(pic)
                audio.save()
                updated += 1

            elif ext == ".ogg" and OggVorbis is not None:
                audio = OggVorbis(str(p))
                pic = Picture()
                pic.type = flac_pic_type
                pic.mime = mime
                pic.desc = "Cover"
                pic.data = raw
                encoded = base64.b64encode(pic.write()).decode("ascii")
                audio["metadata_block_picture"] = [encoded]
                audio.save()
                updated += 1

            else:
                skipped += 1
                continue

            if _embedded_cover_from_file(p):
                verified += 1
            else:
                if len(errors) < 30:
                    errors.append(f"{rel}: Cover wurde geschrieben, konnte danach aber nicht gelesen werden")

        except Exception as e:
            if len(errors) < 30:
                errors.append(f"{rel}: {e}")

    folder_files, folder_file_errors = _write_folder_cover_files(_cover_folder_candidates(files), raw, mime)
    errors.extend(folder_file_errors[: max(0, 30 - len(errors))])

    add_log(
        f"Cover gespeichert: {folder} ({updated}/{len(files)} eingebettet, {verified} geprüft, Folder-Dateien {len(folder_files)}, übersprungen {skipped}, Fehler {len(errors)})",
        bool(errors),
    )
    return {
        "ok": True,
        "folder": folder,
        "updated": updated,
        "verified": verified,
        "total": len(files),
        "skipped": skipped,
        "folder_files": folder_files,
        "errors": errors,
        "paths": [str(p.relative_to(root)) for p in files],
    }

@app.get("/api/media/cover_by_path")
def api_media_cover_by_path(path: str):
    """Return embedded cover for a concrete audio file path.

    This avoids any ambiguity caused by duplicate album names, artist filters,
    or folders with special characters. The frontend uses the first track of an
    album as the cover source. No folder image files are created or required.
    """
    rel = str(path or "").strip().lstrip("/")
    root = get_music_root().resolve()
    headers = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"}
    if not rel:
        raise HTTPException(status_code=404, detail="cover not found")
    try:
        p = (root / rel).resolve()
        if not p.is_relative_to(root) or not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="cover not found")
        hit = _embedded_cover_from_file(p)
        if hit:
            mime, data = hit
            return StreamingResponse(io.BytesIO(data), media_type=mime or "image/jpeg", headers=headers)
    except HTTPException:
        raise
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="cover not found")


@app.get("/api/media/cover")
def api_media_cover(folder: str, artist: Optional[str] = None):
    """Return embedded album cover.

    v1.5.17: intentionally restored to the proven v1.5.1 lookup path:
    query DB rows for the selected album folder/artist and inspect each real
    track file for embedded artwork. A physical-folder fallback remains, but
    no cover.jpg/folder.jpg files are created or required.
    """
    folder = str(folder or "").strip().strip("/")
    root = get_music_root().resolve()
    headers = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"}
    paths = []

    try:
        rows = [r for r in _media_rows() if _folder_matches(r, folder, artist)]
        if not rows:
            rows = [r for r in _media_rows() if parent_folder_key(r.get("path") or "") == folder]
        for r in rows:
            try:
                pp = (root / (r.get("path") or "")).resolve()
                if pp.is_relative_to(root) and pp.exists() and pp.is_file() and pp not in paths:
                    paths.append(pp)
            except Exception:
                continue
    except Exception:
        pass

    # Fallback: scan the exact physical folder if the DB lookup did not find anything.
    if folder:
        try:
            base = (root / folder).resolve()
            if base.is_relative_to(root) and base.exists() and base.is_dir():
                for pp in sorted(base.rglob("*"), key=lambda x: x.as_posix().lower()):
                    if pp.name.startswith("._"):
                        continue
                    if pp.is_file() and pp.suffix.lower() in EXTS and pp not in paths:
                        paths.append(pp.resolve())
        except Exception:
            pass

    for pp in paths:
        # First use the exact old mutagen approach from v1.5.1.
        try:
            mf = MutagenFile(str(pp))
            if mf:
                tags = getattr(mf, "tags", None)
                if tags:
                    for key, val in tags.items():
                        if str(key).startswith("APIC") and getattr(val, "data", None):
                            mime = getattr(val, "mime", None) or "image/jpeg"
                            return StreamingResponse(io.BytesIO(val.data), media_type=mime, headers=headers)
                    covr = tags.get("covr") if hasattr(tags, "get") else None
                    if covr:
                        data = bytes(covr[0])
                        return StreamingResponse(io.BytesIO(data), media_type="image/jpeg", headers=headers)
                pics = getattr(mf, "pictures", None)
                if pics:
                    pic = pics[0]
                    return StreamingResponse(io.BytesIO(pic.data), media_type=pic.mime or "image/jpeg", headers=headers)
        except Exception:
            pass

        # Then explicit ID3 helper as extra safety.
        hit = _embedded_cover_from_file(pp)
        if hit:
            mime, data = hit
            return StreamingResponse(io.BytesIO(data), media_type=mime or "image/jpeg", headers=headers)

    raise HTTPException(status_code=404, detail="Kein Cover gefunden")


@app.get("/api/media_albums")
def api_media_albums(q: str = ""):
    """Global album browser for the media page.

    In album mode, samplers/compilations must be shown once even when tracks
    live under different artist folders. Therefore this groups by the album tag
    instead of by physical folder. The first track path is kept for cover lookup.
    """
    q_norm = (q or "").strip().lower()
    with db() as con:
        rows = [dict(r) for r in con.execute(
            """
            SELECT t.artist,t.album,t.path,t.duration,t.id,a.track_id AS analyzed
            FROM tracks t LEFT JOIN analysis a ON a.track_id=t.id AND a.status='ok'
            ORDER BY t.album COLLATE NOCASE, COALESCE(t.disc_number,1), COALESCE(t.track_number,9999), t.path COLLATE NOCASE
            """
        ).fetchall()]
    groups = {}
    for r in rows:
        artist = r.get("artist") or "Unbekannter Interpret"
        album = (r.get("album") or "Unbekanntes Album").strip() or "Unbekanntes Album"
        path = r.get("path") or ""
        folder = media_album_folder_key(path)
        hay = " ".join([artist, album, folder, path]).lower()
        if q_norm and q_norm not in hay:
            continue
        key = album.lower()
        g = groups.setdefault(key, {"artist": artist, "artists": set(), "album": album, "folder": "__album__:" + album, "tracks": 0, "analyzed": 0, "duration": 0.0, "first_path": path, "folders": set()})
        g["artists"].add(artist)
        g["folders"].add(folder)
        g["tracks"] += 1
        g["analyzed"] += 1 if r.get("analyzed") is not None else 0
        g["duration"] += float(r.get("duration") or 0)
    out = []
    for g in groups.values():
        artists = sorted(g.pop("artists"), key=lambda x: x.lower())
        folders = sorted(g.pop("folders"), key=lambda x: x.lower())
        g["artist"] = artists[0] if len(artists) == 1 else "Verschiedene Interpreten"
        g["folder_hint"] = folders[0] if len(folders) == 1 else f"{len(folders)} Ordner"
        out.append(g)
    out.sort(key=lambda x: ((x.get("album") or "").lower(), (x.get("artist") or "").lower()))
    return out[:2000]


@app.get("/api/media/download_album")
def api_download_album(folder: str):
    folder = str(folder or "").strip().strip("/")
    if not folder:
        raise HTTPException(status_code=400, detail="folder fehlt")
    root = get_music_root().resolve()
    tmpdir = Path(tempfile.mkdtemp(prefix="musiclab_zip_"))
    if folder.startswith("__album__:"):
        album_name = folder[len("__album__:"):].strip()
        rows = [r for r in _media_rows() if (r.get("album") or "Unbekanntes Album").strip().lower() == album_name.lower()]
        if not rows:
            raise HTTPException(status_code=404, detail="Album nicht gefunden")
        name = safe_name(album_name or "album") + ".zip"
        zpath = tmpdir / name
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
            for r in rows:
                rel = r.get("path") or ""
                src = (root / rel).resolve()
                if src.is_relative_to(root) and src.exists() and src.is_file():
                    zf.write(src, rel)
        return FileResponse(zpath, media_type="application/zip", filename=name)
    src = (root / folder).resolve()
    if not src.is_relative_to(root) or not src.exists() or not src.is_dir():
        raise HTTPException(status_code=404, detail="Albumordner nicht gefunden")
    name = safe_name(src.name or "album") + ".zip"
    zpath = tmpdir / name
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in src.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(src.parent))
    return FileResponse(zpath, media_type="application/zip", filename=name)


def album_summary(con, artist: Optional[str], album: str):
    where = "WHERE t.album=?"
    args = [album]
    if artist:
        where += " AND t.artist=?"
        args.append(artist)
    row = con.execute(
        f"""
        SELECT COUNT(t.id) tracks, COUNT(a.track_id) analyzed,
        ROUND(AVG(a.input_i),2) avg_lufs,
        ROUND(MAX(a.input_tp),2) max_true_peak,
        ROUND(AVG(a.input_lra),2) avg_lra
        FROM tracks t LEFT JOIN analysis a ON a.track_id=t.id AND a.status='ok'
        {where}
        """,
        args,
    ).fetchone()
    return dict(row) if row else {}


def get_setting_value(con, key: str):
    r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else None


def get_reference_tuple(con=None):
    """Return the selected reference album as (artist_or_None, album) or None."""
    close_after = False
    if con is None:
        con = db().__enter__()
        close_after = True
    try:
        album = (get_setting_value(con, "reference_album") or "").strip()
        if not album:
            return None
        artist = (get_setting_value(con, "reference_artist") or "").strip() or None
        return artist, album
    finally:
        if close_after:
            con.close()


def is_reference_album(item: dict, ref: Optional[tuple]) -> bool:
    if not ref:
        return False
    ref_artist, ref_album = ref
    album = (item.get("album") or "").strip()
    artist = (item.get("artist") or "").strip() or None
    return album == ref_album and ((ref_artist is None and artist is None) or (ref_artist == artist))


@app.get("/api/reference")
def api_get_reference():
    with db() as con:
        artist = get_setting_value(con, "reference_artist")
        album = get_setting_value(con, "reference_album")
        if not album:
            return {"is_set": False}
        artist = artist or None
        summary = album_summary(con, artist, album)
        exists = bool(summary.get("tracks"))
        return {
            "is_set": exists,
            "artist": artist,
            "album": album,
            "artist_label": artist or "Verschiedene Interpreten",
            **summary,
        }


@app.post("/api/reference")
def api_set_reference(data: dict):
    artist = str(data.get("artist", "")).strip() or None
    album = str(data.get("album", "")).strip()
    if not album:
        raise HTTPException(status_code=400, detail="album erforderlich")
    with db() as con:
        summary = album_summary(con, artist, album)
        if not summary.get("tracks"):
            raise HTTPException(status_code=404, detail="Album nicht gefunden")
        if not summary.get("analyzed"):
            raise HTTPException(status_code=400, detail="Album zuerst analysieren")
        con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('reference_artist',?)", (artist or "",))
        con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('reference_album',?)", (album,))
        if summary.get("avg_lufs") is not None:
            con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('target_lufs',?)", (str(summary["avg_lufs"]),))
        con.commit()
    label = artist or "Verschiedene Interpreten"
    add_log(f"Referenzalbum gesetzt: {label} - {album} ({summary.get('avg_lufs')} LUFS)")
    return {"is_set": True, "artist": artist, "artist_label": label, "album": album, **summary}


@app.get("/api/album_analysis")
def album_analysis(album: str, artist: Optional[str] = None):
    with db() as con:
        return album_summary(con, artist, album)



@app.get("/api/history")
def api_history(limit: int = 50):
    limit = max(1, min(int(limit or 50), 200))
    with db() as con:
        rows = con.execute(
            """
            SELECT job_id, MIN(created_at) created_at, COALESCE(artist,'') artist, album,
                   COUNT(*) tracks,
                   SUM(CASE WHEN backup_path IS NOT NULL AND backup_path!='' THEN 1 ELSE 0 END) backups,
                   ROUND(AVG(before_i),2) before_lufs,
                   ROUND(AVG(after_i),2) after_lufs,
                   MAX(restored_at) restored_at
            FROM history
            GROUP BY job_id, artist, album
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/history/restore")
def api_history_restore(data: dict):
    job_id = str(data.get("job_id", "")).strip()
    artist = str(data.get("artist", "")).strip()
    album = str(data.get("album", "")).strip()
    if not job_id or not album:
        raise HTTPException(status_code=400, detail="job_id und album erforderlich")
    with db() as con:
        rows = con.execute(
            """
            SELECT h.*, t.id AS track_id FROM history h
            LEFT JOIN tracks t ON t.path=h.path
            WHERE h.job_id=? AND COALESCE(h.artist,'')=? AND h.album=?
            ORDER BY h.id
            """,
            (job_id, artist, album),
        ).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="Historieneintrag nicht gefunden")
        restored = 0
        errors = []
        for r in rows:
            bp = r["backup_path"]
            if not bp:
                errors.append(f"Kein Backup für {r['path']}")
                continue
            backup = Path(bp)
            target = get_music_root() / r["path"]
            if not backup.exists():
                errors.append(f"Backup fehlt: {bp}")
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
                if r["track_id"]:
                    result = analyze_track_file(target)
                    upsert_analysis(con, r["track_id"], result)
                restored += 1
            except Exception as e:
                errors.append(f"{r['path']}: {e}")
        con.execute("UPDATE history SET restored_at=? WHERE job_id=? AND COALESCE(artist,'')=? AND album=?", (time.time(), job_id, artist, album))
        con.commit()
    if errors:
        add_log(f"Wiederherstellung mit Fehlern: {album} ({restored}/{len(rows)}) - {'; '.join(errors[:3])}", True)
    else:
        add_log(f"Wiederhergestellt: {artist + ' - ' if artist else ''}{album} ({restored} Dateien)")
    return {"restored": restored, "total": len(rows), "errors": errors}

@app.get("/api/log")
def api_log():
    return {"lines": state.get("log", []), "errors": state.get("recent_errors", [])}


@app.get("/api/log/export")
def api_log_export(errors_only: bool = False):
    text = read_log_text(errors_only=errors_only)
    suffix = "errors" if errors_only else "full"
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"musiclab_{suffix}_{stamp}.log"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=text, media_type="text/plain; charset=utf-8", headers=headers)


@app.post("/api/log/clear")
def api_log_clear():
    state["log"] = []
    state["recent_errors"] = []
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text("", encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Log konnte nicht gelöscht werden: {e}")
    add_log("Log gelöscht")
    return {"ok": True}
