import os, sqlite3, time, threading
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mutagen import File as MutagenFile

MUSIC_ROOT = Path(os.getenv("MUSIC_ROOT", "/music"))
DB_PATH = Path(os.getenv("DB_PATH", "/data/musiclab.sqlite"))
EXTS = {".mp3", ".m4a", ".aac", ".flac", ".ogg"}

app = FastAPI(title="MusicLab API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

state = {"running": False, "done": 0, "total": 0, "current": "", "message": "Bereit"}

def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE,
            artist TEXT,
            album TEXT,
            title TEXT,
            track_no TEXT,
            duration REAL,
            codec TEXT,
            bitrate INTEGER,
            sample_rate INTEGER,
            size INTEGER,
            mtime REAL,
            scanned_at REAL
        )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album)")

def tag_first(tags, keys):
    if not tags: return None
    for k in keys:
        if k in tags:
            v = tags[k]
            if isinstance(v, list): return str(v[0])
            return str(v)
    return None

def scan_worker():
    init_db()
    files = [p for p in MUSIC_ROOT.rglob("*") if p.is_file() and p.suffix.lower() in EXTS and ".tmp" not in p.name]
    state.update({"running": True, "done": 0, "total": len(files), "message": "Scan läuft"})
    with db() as con:
        for p in files:
            state["current"] = str(p.relative_to(MUSIC_ROOT))
            try:
                st = p.stat()
                rel = str(p.relative_to(MUSIC_ROOT))
                audio = MutagenFile(p, easy=True)
                tags = audio.tags if audio else {}
                artist = tag_first(tags, ["artist", "albumartist"]) or p.parent.parent.name if len(p.relative_to(MUSIC_ROOT).parts) >= 3 else "Unbekannt"
                album = tag_first(tags, ["album"]) or p.parent.name
                title = tag_first(tags, ["title"]) or p.stem
                track = tag_first(tags, ["tracknumber"])
                duration = float(audio.info.length) if audio and audio.info and hasattr(audio.info, "length") else None
                bitrate = int(getattr(audio.info, "bitrate", 0)) if audio and audio.info else None
                sample_rate = int(getattr(audio.info, "sample_rate", 0)) if audio and audio.info and hasattr(audio.info, "sample_rate") else None
                codec = p.suffix.lower().replace(".", "")
                con.execute("""
                INSERT INTO tracks(path, artist, album, title, track_no, duration, codec, bitrate, sample_rate, size, mtime, scanned_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET
                  artist=excluded.artist, album=excluded.album, title=excluded.title, track_no=excluded.track_no,
                  duration=excluded.duration, codec=excluded.codec, bitrate=excluded.bitrate, sample_rate=excluded.sample_rate,
                  size=excluded.size, mtime=excluded.mtime, scanned_at=excluded.scanned_at
                """, (rel, artist, album, title, track, duration, codec, bitrate, sample_rate, st.st_size, st.st_mtime, time.time()))
            except Exception as e:
                print("scan error", p, e, flush=True)
            state["done"] += 1
        con.commit()
    state.update({"running": False, "current": "", "message": "Scan fertig"})

@app.on_event("startup")
def startup(): init_db()

@app.get("/api/health")
def health(): return {"ok": True, "music_root": str(MUSIC_ROOT), "db": str(DB_PATH)}

@app.post("/api/scan")
def scan():
    if not state["running"]:
        threading.Thread(target=scan_worker, daemon=True).start()
    return state

@app.get("/api/status")
def status(): return state

@app.get("/api/stats")
def stats():
    with db() as con:
        return {
            "artists": con.execute("SELECT COUNT(DISTINCT artist) c FROM tracks").fetchone()["c"],
            "albums": con.execute("SELECT COUNT(DISTINCT artist || '|' || album) c FROM tracks").fetchone()["c"],
            "tracks": con.execute("SELECT COUNT(*) c FROM tracks").fetchone()["c"],
            "duration": con.execute("SELECT COALESCE(SUM(duration),0) c FROM tracks").fetchone()["c"],
        }

@app.get("/api/artists")
def artists(q: str = ""):
    sql = "SELECT artist, COUNT(DISTINCT album) albums, COUNT(*) tracks FROM tracks"
    args=[]
    if q:
        sql += " WHERE artist LIKE ?"; args.append(f"%{q}%")
    sql += " GROUP BY artist ORDER BY artist COLLATE NOCASE"
    with db() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]

@app.get("/api/albums")
def albums(artist: str):
    with db() as con:
        return [dict(r) for r in con.execute("""
        SELECT album, COUNT(*) tracks, COALESCE(SUM(duration),0) duration
        FROM tracks WHERE artist=? GROUP BY album ORDER BY album COLLATE NOCASE
        """, (artist,)).fetchall()]

@app.get("/api/tracks")
def tracks(artist: str, album: str):
    with db() as con:
        return [dict(r) for r in con.execute("""
        SELECT title, track_no, duration, codec, bitrate, sample_rate, path
        FROM tracks WHERE artist=? AND album=? ORDER BY CAST(track_no AS INTEGER), title COLLATE NOCASE
        """, (artist, album)).fetchall()]
