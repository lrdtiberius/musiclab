import os
import re
import sqlite3
import time
import threading
from pathlib import Path
from typing import Optional, Tuple

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mutagen import File as MutagenFile

MUSIC_ROOT = Path(os.getenv("MUSIC_ROOT", "/music"))
DB_PATH = Path(os.getenv("DB_PATH", "/data/musiclab.sqlite"))
EXTS = {".mp3", ".m4a", ".aac", ".flac", ".ogg"}
SCHEMA_VERSION = 2

app = FastAPI(title="MusicLab API", version="0.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

state = {
    "running": False,
    "done": 0,
    "total": 0,
    "current": "",
    "message": "Bereit",
    "last_scan_started": None,
    "last_scan_finished": None,
    "errors": 0,
}


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def init_db():
    with db() as con:
        con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        current = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        current_version = int(current["value"]) if current else 0

        # v0.2 uses a clean schema. During early development we rebuild if the old table is present.
        cols = table_columns(con, "tracks")
        expected = {"path", "artist", "album", "title", "track_number", "disc_number", "duration", "codec", "bitrate", "sample_rate"}
        if current_version != SCHEMA_VERSION or (cols and not expected.issubset(cols)):
            con.execute("DROP TABLE IF EXISTS tracks")
            con.execute("DELETE FROM meta WHERE key='schema_version'")

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
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
        con.commit()


def value_to_str(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        value = value[0]
    text = str(value).strip()
    return text if text else None


def tag_first(tags, keys) -> Optional[str]:
    if not tags:
        return None
    lower_map = {str(k).lower(): k for k in tags.keys()}
    for key in keys:
        actual = lower_map.get(key.lower())
        if actual is not None:
            v = value_to_str(tags.get(actual))
            if v:
                return v
    return None


def parse_number_pair(raw: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """Parse '01', '1/12', '01/00', '2 of 10' -> (number,total)."""
    if not raw:
        return None, None
    text = str(raw).strip()
    text = text.replace("of", "/")
    m = re.search(r"(\d+)(?:\s*/\s*(\d+))?", text)
    if not m:
        return None, None
    num = int(m.group(1))
    total = int(m.group(2)) if m.group(2) else None
    if total == 0:
        total = None
    return num, total


def fallback_from_path(path: Path) -> tuple[str, str]:
    rel_parts = path.relative_to(MUSIC_ROOT).parts
    if len(rel_parts) >= 3:
        return rel_parts[0], rel_parts[1]
    if len(rel_parts) == 2:
        return rel_parts[0], path.parent.name
    return "Unbekannt", "Unbekanntes Album"


def audio_channels(info) -> Optional[int]:
    for attr in ("channels", "channel_mode"):
        if hasattr(info, attr):
            v = getattr(info, attr)
            if isinstance(v, int):
                return v
    return None


def scan_file(path: Path) -> Optional[dict]:
    st = path.stat()
    rel = str(path.relative_to(MUSIC_ROOT))
    fallback_artist, fallback_album = fallback_from_path(path)

    audio = MutagenFile(path, easy=True)
    tags = audio.tags if audio and getattr(audio, "tags", None) else {}
    info = audio.info if audio and getattr(audio, "info", None) else None

    artist = tag_first(tags, ["albumartist", "album artist", "artist"]) or fallback_artist
    album = tag_first(tags, ["album"]) or fallback_album
    title = tag_first(tags, ["title"]) or path.stem
    track_raw = tag_first(tags, ["tracknumber", "track"])
    disc_raw = tag_first(tags, ["discnumber", "disc"])
    track_number, track_total = parse_number_pair(track_raw)
    disc_number, disc_total = parse_number_pair(disc_raw)

    duration = float(getattr(info, "length", 0)) if info and getattr(info, "length", None) else None
    bitrate = int(getattr(info, "bitrate", 0)) if info and getattr(info, "bitrate", None) else None
    sample_rate = int(getattr(info, "sample_rate", 0)) if info and getattr(info, "sample_rate", None) else None
    channels = audio_channels(info) if info else None
    codec = path.suffix.lower().lstrip(".")

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
        "duration": duration,
        "codec": codec,
        "bitrate": bitrate,
        "sample_rate": sample_rate,
        "channels": channels,
        "size": st.st_size,
        "mtime": st.st_mtime,
        "scanned_at": time.time(),
    }


def upsert_track(con: sqlite3.Connection, item: dict):
    con.execute(
        """
        INSERT INTO tracks(
            path, filename, artist, album, title, track_raw, track_number, track_total,
            disc_raw, disc_number, disc_total, duration, codec, bitrate, sample_rate,
            channels, size, mtime, scanned_at
        ) VALUES(
            :path, :filename, :artist, :album, :title, :track_raw, :track_number, :track_total,
            :disc_raw, :disc_number, :disc_total, :duration, :codec, :bitrate, :sample_rate,
            :channels, :size, :mtime, :scanned_at
        )
        ON CONFLICT(path) DO UPDATE SET
            filename=excluded.filename,
            artist=excluded.artist,
            album=excluded.album,
            title=excluded.title,
            track_raw=excluded.track_raw,
            track_number=excluded.track_number,
            track_total=excluded.track_total,
            disc_raw=excluded.disc_raw,
            disc_number=excluded.disc_number,
            disc_total=excluded.disc_total,
            duration=excluded.duration,
            codec=excluded.codec,
            bitrate=excluded.bitrate,
            sample_rate=excluded.sample_rate,
            channels=excluded.channels,
            size=excluded.size,
            mtime=excluded.mtime,
            scanned_at=excluded.scanned_at
        """,
        item,
    )


def scan_worker(full_rebuild: bool = True):
    init_db()
    files = [p for p in MUSIC_ROOT.rglob("*") if p.is_file() and p.suffix.lower() in EXTS and ".tmp" not in p.name]
    state.update({
        "running": True,
        "done": 0,
        "total": len(files),
        "current": "",
        "message": "Scan läuft",
        "last_scan_started": time.time(),
        "last_scan_finished": None,
        "errors": 0,
    })
    with db() as con:
        if full_rebuild:
            con.execute("DELETE FROM tracks")
            con.commit()
        for p in files:
            state["current"] = str(p.relative_to(MUSIC_ROOT))
            try:
                item = scan_file(p)
                if item:
                    upsert_track(con, item)
            except Exception as e:
                state["errors"] += 1
                print("scan error", p, e, flush=True)
            state["done"] += 1
            if state["done"] % 100 == 0:
                con.commit()
        con.commit()
    state.update({"running": False, "current": "", "message": "Scan fertig", "last_scan_finished": time.time()})


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.2", "music_root": str(MUSIC_ROOT), "db": str(DB_PATH)}


@app.post("/api/scan")
def scan():
    if not state["running"]:
        threading.Thread(target=scan_worker, kwargs={"full_rebuild": True}, daemon=True).start()
    return state


@app.get("/api/status")
def status():
    return state


@app.get("/api/stats")
def stats():
    with db() as con:
        return {
            "artists": con.execute("SELECT COUNT(DISTINCT artist) c FROM tracks").fetchone()["c"],
            "albums": con.execute("SELECT COUNT(*) c FROM (SELECT artist, album FROM tracks GROUP BY artist, album)").fetchone()["c"],
            "tracks": con.execute("SELECT COUNT(*) c FROM tracks").fetchone()["c"],
            "duration": con.execute("SELECT COALESCE(SUM(duration),0) c FROM tracks").fetchone()["c"],
            "schema_version": SCHEMA_VERSION,
        }


@app.get("/api/artists")
def get_artists(q: str = ""):
    sql = """
        SELECT artist,
               COUNT(DISTINCT album) albums,
               COUNT(*) tracks,
               COALESCE(SUM(duration),0) duration
        FROM tracks
    """
    args = []
    if q:
        sql += " WHERE artist LIKE ?"
        args.append(f"%{q}%")
    sql += " GROUP BY artist ORDER BY artist COLLATE NOCASE"
    with db() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


@app.get("/api/albums")
def get_albums(artist: str):
    with db() as con:
        return [dict(r) for r in con.execute(
            """
            SELECT album,
                   COUNT(*) tracks,
                   COALESCE(SUM(duration),0) duration,
                   MIN(path) sample_path
            FROM tracks
            WHERE artist=?
            GROUP BY album
            ORDER BY album COLLATE NOCASE
            """,
            (artist,),
        ).fetchall()]


@app.get("/api/tracks")
def get_tracks(artist: str, album: str):
    with db() as con:
        return [dict(r) for r in con.execute(
            """
            SELECT id, title, track_raw, track_number, track_total, disc_raw, disc_number, disc_total,
                   duration, codec, bitrate, sample_rate, channels, path, filename
            FROM tracks
            WHERE artist=? AND album=?
            ORDER BY COALESCE(disc_number, 1), COALESCE(track_number, 9999), title COLLATE NOCASE, path COLLATE NOCASE
            """,
            (artist, album),
        ).fetchall()]


@app.get("/api/duplicates")
def duplicates(limit: int = 50):
    """Potential duplicates: same artist+album+title with multiple file paths."""
    with db() as con:
        return [dict(r) for r in con.execute(
            """
            SELECT artist, album, title, COUNT(*) count
            FROM tracks
            GROUP BY artist, album, title
            HAVING COUNT(*) > 1
            ORDER BY count DESC, artist COLLATE NOCASE, album COLLATE NOCASE, title COLLATE NOCASE
            LIMIT ?
            """,
            (limit,),
        ).fetchall()]
