import json
import os
import re
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mutagen import File as MutagenFile

MUSIC_ROOT = Path(os.getenv("MUSIC_ROOT", "/music"))
DB_PATH = Path(os.getenv("DB_PATH", "/data/musiclab.sqlite"))
EXTS = {".mp3", ".m4a", ".aac", ".flac", ".ogg"}
SCHEMA_VERSION = 6

app = FastAPI(title="MusicLab API", version="0.6.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
}


def add_log(message: str, is_error: bool = False):
    line = f"{time.strftime('%H:%M:%S')} | {message}"
    state["log"].append(line)
    state["log"] = state["log"][-200:]
    if is_error:
        state["recent_errors"].append(line)
        state["recent_errors"] = state["recent_errors"][-50:]
    print(line, flush=True)


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
        defaults = {"target_lufs": "-16", "true_peak": "-1.5", "lra": "11"}
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
        for k in ["target_lufs", "true_peak", "lra"]:
            if k in data:
                con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, str(data[k])))
        con.commit()


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


def fallback_from_path(path: Path):
    rel = path.relative_to(MUSIC_ROOT).parts
    if len(rel) >= 3:
        return rel[0], rel[1]
    if len(rel) == 2:
        return rel[0], path.parent.name
    return "Unbekannt", "Unbekanntes Album"


def audio_channels(info):
    v = getattr(info, "channels", None)
    return v if isinstance(v, int) else None


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
        INSERT INTO tracks(path,filename,artist,album,title,track_raw,track_number,track_total,disc_raw,disc_number,disc_total,duration,codec,bitrate,sample_rate,channels,size,mtime,scanned_at)
        VALUES(:path,:filename,:artist,:album,:title,:track_raw,:track_number,:track_total,:disc_raw,:disc_number,:disc_total,:duration,:codec,:bitrate,:sample_rate,:channels,:size,:mtime,:scanned_at)
        ON CONFLICT(path) DO UPDATE SET
        filename=excluded.filename,artist=excluded.artist,album=excluded.album,title=excluded.title,track_raw=excluded.track_raw,track_number=excluded.track_number,track_total=excluded.track_total,disc_raw=excluded.disc_raw,disc_number=excluded.disc_number,disc_total=excluded.disc_total,duration=excluded.duration,codec=excluded.codec,bitrate=excluded.bitrate,sample_rate=excluded.sample_rate,channels=excluded.channels,size=excluded.size,mtime=excluded.mtime,scanned_at=excluded.scanned_at
        """,
        item,
    )


def scan_worker():
    init_db()
    files = [p for p in MUSIC_ROOT.rglob("*") if p.is_file() and p.suffix.lower() in EXTS and ".tmp" not in p.name]
    state.update({"running": True, "mode": "scan", "done": 0, "total": len(files), "current": "", "message": "Scan läuft", "errors": 0, "recent_errors": []})
    add_log(f"Scan gestartet: {len(files)} Dateien")
    with db() as con:
        con.execute("DELETE FROM analysis")
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
                add_log(f"Scanfehler: {p.relative_to(MUSIC_ROOT)} - {e}", True)
            state["done"] += 1
            if state["done"] % 100 == 0:
                con.commit()
        con.commit()
    add_log(f"Scan fertig: {state['done']}/{state['total']} Dateien, Fehler {state['errors']}")
    state.update({"running": False, "mode": "idle", "current": "", "message": "Scan fertig", "last_finished": time.time()})


def parse_loudnorm_json(stderr: str) -> Optional[dict]:
    matches = re.findall(r"\{[\s\S]*?\}", stderr)
    if not matches:
        return None
    return json.loads(matches[-1])


def analyze_track_file(path: Path) -> dict:
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "loudnorm=print_format=json", "-f", "null", "-"]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
    data = parse_loudnorm_json(res.stderr)
    if not data:
        raise RuntimeError((res.stderr or "Keine loudnorm-Daten")[-1200:])
    return {
        "input_i": float(data["input_i"]),
        "input_tp": float(data["input_tp"]),
        "input_lra": float(data["input_lra"]),
        "input_thresh": float(data["input_thresh"]),
        "target_offset": float(data.get("target_offset", 0)),
    }


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
    sql = "SELECT id,path,title FROM tracks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY artist COLLATE NOCASE, album COLLATE NOCASE, COALESCE(disc_number,1), COALESCE(track_number,9999), title COLLATE NOCASE"
    with db() as con:
        return [dict(r) for r in con.execute(sql, args).fetchall()]


def analysis_worker(artist: Optional[str] = None, album: Optional[str] = None):
    init_db()
    rows = selected_rows(artist, album)
    state.update({"running": True, "mode": "analysis", "done": 0, "total": len(rows), "current": "", "message": "Analyse läuft", "errors": 0, "recent_errors": []})
    add_log(f"Analyse gestartet: {len(rows)} Titel")
    with db() as con:
        for row in rows:
            state["current"] = row["path"]
            try:
                result = analyze_track_file(MUSIC_ROOT / row["path"])
                upsert_analysis(con, row["id"], result)
            except Exception as e:
                state["errors"] += 1
                upsert_analysis(con, row["id"], None, str(e))
                add_log(f"Analysefehler: {row['path']} - {e}", True)
            state["done"] += 1
            con.commit()
    add_log(f"Analyse fertig: {state['done']}/{state['total']} Titel, Fehler {state['errors']}")
    state.update({"running": False, "mode": "idle", "current": "", "message": "Analyse fertig", "last_finished": time.time()})


def loudnorm_filter(first: dict, settings: dict) -> str:
    return (
        f"loudnorm=I={settings['target_lufs']}:TP={settings['true_peak']}:LRA={settings['lra']}:"
        f"measured_I={first['input_i']}:measured_TP={first['input_tp']}:measured_LRA={first['input_lra']}:"
        f"measured_thresh={first['input_thresh']}:offset={first['target_offset']}:linear=true:print_format=summary"
    )


def normalize_file(rel_path: str, settings: dict) -> bool:
    file = MUSIC_ROOT / rel_path
    tmp = file.with_name(file.stem + ".tmp" + file.suffix)
    if tmp.exists():
        tmp.unlink()
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
    return True


def normalize_worker(artist: Optional[str] = None, album: Optional[str] = None):
    init_db()
    settings = get_settings()
    rows = selected_rows(artist, album)
    state.update({"running": True, "mode": "normalize", "done": 0, "total": len(rows), "current": "", "message": f"Normalisiere auf {settings.get('target_lufs')} LUFS", "errors": 0, "recent_errors": []})
    add_log(f"Normalisierung gestartet: {len(rows)} Titel auf {settings.get('target_lufs')} LUFS")
    with db() as con:
        for row in rows:
            state["current"] = row["path"]
            try:
                normalize_file(row["path"], settings)
                result = analyze_track_file(MUSIC_ROOT / row["path"])
                upsert_analysis(con, row["id"], result)
            except Exception as e:
                state["errors"] += 1
                upsert_analysis(con, row["id"], None, str(e))
                add_log(f"Analysefehler: {row['path']} - {e}", True)
            state["done"] += 1
            con.commit()
    add_log(f"Normalisierung fertig: {state['done']}/{state['total']} Titel, Fehler {state['errors']}")
    state.update({"running": False, "mode": "idle", "current": "", "message": "Normalisierung fertig", "last_finished": time.time()})


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.6.1", "music_root": str(MUSIC_ROOT), "db": str(DB_PATH)}


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
def normalize(artist: Optional[str] = None, album: Optional[str] = None):
    if not state["running"]:
        threading.Thread(target=normalize_worker, kwargs={"artist": artist, "album": album}, daemon=True).start()
    return state


@app.get("/api/settings")
def api_settings():
    return get_settings()


@app.post("/api/settings")
def api_save_settings(data: dict):
    save_settings(data)
    return get_settings()


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
            SELECT t.id,t.title,t.track_number,t.track_total,t.disc_number,t.disc_total,t.duration,t.codec,t.bitrate,t.sample_rate,t.channels,t.path,t.filename,
            a.input_i,a.input_tp,a.input_lra,a.status AS analysis_status
            FROM tracks t LEFT JOIN analysis a ON a.track_id=t.id
            {where}
            ORDER BY t.artist COLLATE NOCASE, COALESCE(t.disc_number,1), COALESCE(t.track_number,9999), t.title COLLATE NOCASE, t.path COLLATE NOCASE
            """, args,
        ).fetchall()]


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


@app.get("/api/log")
def api_log():
    return {"lines": state.get("log", []), "errors": state.get("recent_errors", [])}
