import json
import os
import re
import sqlite3
import subprocess
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Tuple

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from mutagen import File as MutagenFile

DEFAULT_MUSIC_ROOT = Path(os.getenv("MUSIC_ROOT", "/music"))
DB_PATH = Path(os.getenv("DB_PATH", "/data/musiclab.sqlite"))
LOG_DIR = Path(os.getenv("LOG_DIR", str(DB_PATH.parent / "logs")))
LOG_PATH = LOG_DIR / "musiclab.log"
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
EXTS = {".mp3", ".m4a", ".aac", ".flac", ".ogg"}
SCHEMA_VERSION = 15

app = FastAPI(title="MusicLab API", version="1.3.7")
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
    line = f"{time.strftime('%H:%M:%S')} | {message}"
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
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_tracks_path ON tracks(path)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist COLLATE NOCASE)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(artist COLLATE NOCASE, album COLLATE NOCASE)")
        cols = {r["name"] for r in con.execute("PRAGMA table_info(tracks)").fetchall()}
        if "genre" not in cols:
            con.execute("ALTER TABLE tracks ADD COLUMN genre TEXT")
        if "year" not in cols:
            con.execute("ALTER TABLE tracks ADD COLUMN year TEXT")
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
        defaults = {"target_lufs": "-16", "true_peak": "-1.5", "lra": "11", "backup_mode": "on", "parallel_analysis": "2", "music_root": str(DEFAULT_MUSIC_ROOT), "watch_mode": "off"}
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
        for k in ["target_lufs", "true_peak", "lra", "backup_mode", "parallel_analysis", "music_root", "watch_mode"]:
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
    artist = tag_first(tags, ["albumartist", "album artist", "artist"]) or fallback_artist
    album = tag_first(tags, ["album"]) or fallback_album
    title = tag_first(tags, ["title"]) or path.stem
    track_raw = tag_first(tags, ["tracknumber", "track"])
    disc_raw = tag_first(tags, ["discnumber", "disc"])
    genre = tag_first(tags, ["genre"])
    year = tag_first(tags, ["date", "year"])
    track_number, track_total = parse_number_pair(track_raw)
    disc_number, disc_total = parse_number_pair(disc_raw)
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
        summary = album_summary(con, artist, album) if album else {}
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
        for raw in items:
            item = normalize_album_item(raw)
            summary = album_summary(con, item.get("artist"), item.get("album"))
            tracks = summary.get("tracks") or 0
            analyzed = summary.get("analyzed") or 0
            current = summary.get("avg_lufs")
            delta = round(target - float(current), 2) if current is not None else None
            can = bool(tracks and analyzed == tracks and current is not None)
            reason = None
            if not tracks:
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
                "reason": reason,
            })
    return out


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
    blocked = [p for p in previews if not p.get("can_normalize")]
    if blocked:
        names = "; ".join(f"{p['label']}: {p.get('reason') or 'nicht möglich'}" for p in blocked[:5])
        state.update({"running": False, "mode": "idle", "done": 0, "total": 0, "current": "", "message": "Batch-Normalisierung abgebrochen", "errors": len(blocked), "recent_errors": []})
        add_log(f"Batch-Normalisierung abgebrochen: {names}", True)
        return
    albums = [normalize_album_item(p) for p in previews]
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

@app.on_event("startup")
def startup():
    init_db()
    if not getattr(app.state, "watcher_started", False):
        app.state.watcher_started = True
        threading.Thread(target=watcher_loop, daemon=True).start()


@app.get("/api/health")
def health():
    return {"ok": True, "version": "1.3.7", "music_root": str(get_music_root()), "db": str(DB_PATH)}


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
        "can_normalize": all(p.get("can_normalize") for p in preview),
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


def folder_display_name(folder: str) -> str:
    if not folder:
        return "Musik"
    name = Path(folder).name
    return name or folder


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
def get_tracks_by_folder(folder: str):
    folder = str(folder or "").strip().strip("/")
    with db() as con:
        rows = [dict(r) for r in con.execute(
            """
            SELECT t.id,t.artist,t.album,t.title,t.track_raw,t.track_number,t.track_total,t.disc_raw,t.disc_number,t.disc_total,t.genre,t.year,t.duration,t.codec,t.bitrate,t.sample_rate,t.channels,t.path,t.filename,
            a.input_i,a.input_tp,a.input_lra,a.status AS analysis_status
            FROM tracks t LEFT JOIN analysis a ON a.track_id=t.id
            ORDER BY COALESCE(t.disc_number,1), COALESCE(t.track_number,9999), t.title COLLATE NOCASE, t.path COLLATE NOCASE
            """
        ).fetchall()]
    return [r for r in rows if parent_folder_key(r.get("path") or "") == folder]


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

    Expected payload: {"updates":[{"path":"Artist/Album/01.mp3", "title":"...", "artist":"...", "album":"...", "tracknumber":"1/12", "discnumber":"1/2", "year":"2024", "genre":"Rock"}]}
    """
    updates = payload.get("updates") if isinstance(payload, dict) else None
    if not isinstance(updates, list):
        raise HTTPException(status_code=400, detail="updates fehlt")
    root = get_music_root().resolve()
    updated = 0
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
                audio = MutagenFile(p, easy=True)
                if audio is None:
                    raise ValueError("Datei kann nicht gelesen werden")
                changed = {}
                mapping = {
                    "title": "title",
                    "artist": "artist",
                    "album": "album",
                    "tracknumber": "tracknumber",
                    "discnumber": "discnumber",
                    "year": "date",
                    "genre": "genre",
                }
                for src, tag in mapping.items():
                    if src in item:
                        val = str(item.get(src) or "").strip()
                        if val:
                            audio[tag] = [val]
                            changed[src] = val
                audio.save()
                db_updates = []
                args = []
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
                    st = p.stat()
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
        add_log(f"Tags gespeichert: {updated}/{len(updates)} Dateien" + (f", Fehler {len(errors)}" if errors else ""), bool(errors))
    return {"updated": updated, "total": len(updates), "errors": errors[:50]}


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
