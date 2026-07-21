"""SQLite + FTS5 Library Index (Spec A / ADR 0001).

WHY this exists: the Library is 5,000+ images on an SMB NAS. The old flat-JSON index
re-crawled the whole tree on every tab open, and toggling one folder discarded the cache
(its key was the *enabled-folder set*) → another full NAS re-crawl. That is the #3 perf
regression. This module replaces that with a local SQLite DB:

  - metadata is read ONCE at index time and persisted as columns (never re-read on open),
  - folders are indexed independently and keyed by a change SIGNATURE (name+mtime hash),
  - enabling/disabling a folder is a pure DB flag flip — zero filesystem reads,
  - a warm `list_images()` is a single local-DB query with no NAS access.

It is also the shared substrate Spec C builds tags(#8) + output-indexing(#6) on, so the
schema carries `tags` + an FTS5 virtual table now even though the tag UI lands later.

`sqlite3` + FTS5 ship with CPython — no third-party dependency. FTS5 is probed at open;
if the running SQLite lacks it, search degrades to LIKE (never a crash).

Design note — identity: the media server resolves tiles by BASENAME across roots, and the
old scan de-duped by basename. We keep that: `images.path` is the unique absolute path, but
`list_images` de-dupes by basename so the record shape the JS consumes is unchanged
({file, dir, type, service?, model?, prompt?, category?}).
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

SCHEMA_VERSION = 1
_LIB_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".mov"}
_VID_EXTS = {".mp4", ".webm", ".mov"}
# Sidecar keys we persist as columns (the app's own field names — keeps the JS contract exact).
_META_KEYS = ("service", "model", "prompt", "category", "seed")


def _norm_tag(tag: str) -> str:
    """Tags are a flat, comma-delimited namespace (Spec C #8) — normalize so 'Red', ' red ',
    'red,x' can't create duplicate/ambiguous chips or corrupt the delimiter."""
    return (tag or "").strip().lower().replace(",", " ")


def _auto_tags(meta: dict, mtime) -> set:
    """Metadata auto-tags derived from a generation's own sidecar (AC-8.1): provider, model,
    seed, dimensions, date, has-negative-prompt. The user never types these."""
    tags = set()
    if meta.get("service"):
        tags.add(str(meta["service"]))
    if meta.get("model"):
        tags.add(str(meta["model"]))
    if meta.get("seed") not in (None, ""):
        tags.add(f"seed:{meta['seed']}")
    w, h = meta.get("width"), meta.get("height")
    if w and h:
        tags.add(f"{w}x{h}")
    if meta.get("has_negative"):
        tags.add("has-negative-prompt")
    if mtime:
        tags.add(time.strftime("%Y-%m", time.localtime(mtime)))
    return tags


def folder_signature(base: str) -> str:
    """Cheap per-folder change signature = sha1 over sorted(name|mtime_ns) of every entry.

    Chosen over a bare directory mtime because it ALSO catches renames and deletes (a renamed
    or removed file changes the name set / an mtime), which a dir-mtime misses. Only ever called
    on an explicit refresh — never on a plain list — so it can't reintroduce the open-time stall.
    """
    d = Path(base)
    if not d.exists():
        return ""
    parts = []
    for f in d.rglob("*"):
        try:
            if f.is_file() and f.suffix.lower() in _LIB_EXTS:
                parts.append(f"{f.name}|{f.stat().st_mtime_ns}")
        except OSError:
            continue
    parts.sort()
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()


class LibraryIndex:
    """One SQLite DB backing the Library view. Open once; cheap to reuse."""

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = self._connect_or_rebuild()
        self.fts = self._probe_fts5()
        self._ensure_schema()

    # ---- connection / integrity -------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        # check_same_thread=False: bridge.py's Api caches ONE LibraryIndex (and this connection)
        # for the app's lifetime, but pywebview dispatches EACH JS->Python call on its own worker
        # thread (bridge.py's own docstring: "pywebview runs each call on a worker thread") — so
        # a second call touching the index from a different thread than the one that created it
        # would otherwise raise sqlite3.ProgrammingError. Safe here: CPython's sqlite3 links
        # against SQLite's serialized threading mode (its own internal mutex), and this app never
        # issues two DB calls at the exact same instant (one bridge call in flight at a time).
        db = sqlite3.connect(self.db_path, check_same_thread=False)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")   # first file touch — raises on a corrupt file
        except sqlite3.DatabaseError:
            db.close()                              # release the handle so the caller can delete it
            raise
        return db

    def _connect_or_rebuild(self) -> sqlite3.Connection:
        """Open the DB; if it's corrupt, delete + start fresh (the NAS is source of truth, so a
        rebuild-from-scan loses nothing). This is AC-6's corruption rollback. Note the corruption
        can surface either on the first PRAGMA inside _connect() OR on integrity_check, so the
        guard has to wrap both."""
        db = None
        try:
            db = self._connect()
            ok = db.execute("PRAGMA integrity_check").fetchone()[0]
            if ok != "ok":
                raise sqlite3.DatabaseError("integrity_check failed")
            return db
        except sqlite3.DatabaseError:
            if db is not None:
                try:
                    db.close()
                except sqlite3.Error:
                    pass
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(self.db_path + suffix)
                except OSError:
                    pass
            return self._connect()

    def _probe_fts5(self) -> bool:
        try:
            self._db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
            self._db.execute("DROP TABLE IF EXISTS _fts_probe")
            return True
        except sqlite3.OperationalError:
            return False

    def _ensure_schema(self) -> None:
        db = self._db
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS folders(
                path TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
                sig TEXT, indexed_at REAL);
            CREATE TABLE IF NOT EXISTS images(
                path TEXT PRIMARY KEY, folder TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL,
                service TEXT, model TEXT, seed TEXT, prompt TEXT, category TEXT,
                width INTEGER, height INTEGER, created REAL, tags TEXT DEFAULT '');
            CREATE INDEX IF NOT EXISTS idx_images_folder ON images(folder);
            CREATE INDEX IF NOT EXISTS idx_images_name ON images(name);

            -- Spec C #4 — presets, SAME db as the index (one file to back up). Two distinct
            -- objects (never conflated, research/2026-07-21_preset-tagging-output-modeling.md):
            -- Style = reusable/prompt-optional; Recipe = reproduce-this-exact-image, provider-pinned.
            CREATE TABLE IF NOT EXISTS styles(
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                negative TEXT DEFAULT '', prompt_template TEXT DEFAULT '',
                params_json TEXT DEFAULT '{}', model TEXT,
                is_default INTEGER NOT NULL DEFAULT 0, updated REAL);
            CREATE TABLE IF NOT EXISTS recipes(
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                provider TEXT, model TEXT, seed TEXT,
                prompt TEXT DEFAULT '', negative TEXT DEFAULT '', params_json TEXT DEFAULT '{}',
                is_default INTEGER NOT NULL DEFAULT 0, updated REAL);
            """
        )
        # AC-8.7 vision-tag cache marker — added via ALTER so existing DBs upgrade in place.
        cols = {r["name"] for r in db.execute("PRAGMA table_info(images)")}
        if "vision_tagged_at" not in cols:
            db.execute("ALTER TABLE images ADD COLUMN vision_tagged_at REAL")
        if self.fts:
            db.executescript(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS images_fts USING fts5(
                    name, prompt, service, model, tags, content='images', content_rowid='rowid');
                CREATE TRIGGER IF NOT EXISTS images_ai AFTER INSERT ON images BEGIN
                  INSERT INTO images_fts(rowid,name,prompt,service,model,tags)
                  VALUES (new.rowid,new.name,new.prompt,new.service,new.model,new.tags); END;
                CREATE TRIGGER IF NOT EXISTS images_ad AFTER DELETE ON images BEGIN
                  INSERT INTO images_fts(images_fts,rowid,name,prompt,service,model,tags)
                  VALUES('delete',old.rowid,old.name,old.prompt,old.service,old.model,old.tags); END;
                CREATE TRIGGER IF NOT EXISTS images_au AFTER UPDATE ON images BEGIN
                  INSERT INTO images_fts(images_fts,rowid,name,prompt,service,model,tags)
                  VALUES('delete',old.rowid,old.name,old.prompt,old.service,old.model,old.tags);
                  INSERT INTO images_fts(rowid,name,prompt,service,model,tags)
                  VALUES (new.rowid,new.name,new.prompt,new.service,new.model,new.tags); END;
                """
            )
        db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        db.commit()

    # ---- indexing (the only path that touches the filesystem) -------------------
    def _read_sidecar(self, abs_path: str) -> dict:
        side = Path(abs_path + ".json")
        if not side.exists():
            return {}
        try:
            raw = json.loads(side.read_text(encoding="utf-8"))
        except Exception:
            return {}
        meta = {k: raw[k] for k in _META_KEYS if raw.get(k) is not None}
        if raw.get("width"):
            meta["width"] = raw["width"]
        if raw.get("height"):
            meta["height"] = raw["height"]
        if (raw.get("params") or {}).get("negative_prompt"):
            meta["has_negative"] = True
        return meta

    def index_folder(self, base: str, max_workers: int = 4) -> int:
        """Crawl ONE folder once (names + sidecars), upsert its images, store the signature.
        This is the 'slow' path — it runs on first index and on an explicit refresh of a
        *changed* folder only, never on a plain list().

        Sidecar reads (the NAS-latency-bound part) run on a small (≤4) thread pool — bounded so a
        refresh can't hammer the NAS with 16 threads. The SQLite write stays on THIS thread (a
        connection is thread-affine), so only pure file I/O is parallel."""
        from concurrent.futures import ThreadPoolExecutor

        d = Path(base)
        db = self._db
        db.execute("INSERT OR IGNORE INTO folders(path,enabled) VALUES(?,1)", (base,))
        if not d.exists():
            db.execute("UPDATE folders SET sig=?, indexed_at=? WHERE path=?", ("", time.time(), base))
            db.commit()
            return 0
        # crawl names + mtimes (cheap), collect files to read sidecars for
        files, sig_parts = [], []
        for f in d.rglob("*"):
            try:
                if not (f.is_file() and f.suffix.lower() in _LIB_EXTS):
                    continue
                st = f.stat()
            except OSError:
                continue
            sig_parts.append(f"{f.name}|{st.st_mtime_ns}")
            files.append((f, st.st_mtime))

        # AC-8.5 — tags (and the vision-tag marker) must SURVIVE a re-index: capture what's
        # already known per path before the wholesale delete+reinsert below.
        prior = {r["path"]: (r["tags"] or "", r["vision_tagged_at"])
                 for r in db.execute("SELECT path,tags,vision_tagged_at FROM images WHERE folder=?", (base,))}

        def _row(item):
            f, mtime = item
            path = str(f)
            meta = self._read_sidecar(path)   # pure file I/O, no DB
            prior_tags_str, prior_vta = prior.get(path, ("", None))
            tags = set(t for t in prior_tags_str.split(",") if t)
            if not tags:
                # AC-8.5 re-import recovery: no DB row ever existed for this path (fresh index or
                # a rebuilt DB) — try the durable embedded copy before falling back to auto-tags
                # only. Bounded: only fires when there is nothing already known for this exact path.
                try:
                    from engine.embed_meta import read_embedded_meta
                    embedded = read_embedded_meta(path)
                    if embedded and embedded.get("tags"):
                        tags |= set(str(t) for t in embedded["tags"])
                except Exception:
                    pass
            tags |= _auto_tags(meta, mtime)
            return (path, base, f.name,
                    "video" if f.suffix.lower() in _VID_EXTS else "image",
                    meta.get("service"), meta.get("model"), meta.get("seed"),
                    meta.get("prompt"), meta.get("category"),
                    meta.get("width"), meta.get("height"), mtime,
                    ",".join(sorted(tags)), prior_vta)

        if files:
            with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(files)))) as pool:
                rows = list(pool.map(_row, files))
        else:
            rows = []
        # Replace this folder's rows atomically (handles adds AND deletes/renames).
        db.execute("DELETE FROM images WHERE folder=?", (base,))
        db.executemany(
            "INSERT OR REPLACE INTO images"
            "(path,folder,name,type,service,model,seed,prompt,category,width,height,created,tags,vision_tagged_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        sig_parts.sort()
        sig = hashlib.sha1("\n".join(sig_parts).encode("utf-8")).hexdigest()
        db.execute("UPDATE folders SET sig=?, indexed_at=? WHERE path=?", (sig, time.time(), base))
        db.commit()
        return len(rows)

    def refresh(self, bases: list[str], force: bool = False) -> dict:
        """Index only folders whose signature changed (or all, if force). Folders are indexed
        sequentially (the SQLite write is single-threaded); the I/O concurrency lives inside
        index_folder's sidecar reads. Returns {reindexed:[...], skipped:[...]}."""
        changed = []
        for b in bases:
            row = self._db.execute("SELECT sig FROM folders WHERE path=?", (b,)).fetchone()
            if force or row is None or row["sig"] is None:
                changed.append(b)
            elif folder_signature(b) != row["sig"]:   # cheap recompute — the only refresh-time NAS read
                changed.append(b)
        for b in changed:
            self.index_folder(b)
        return {"reindexed": changed, "skipped": [b for b in bases if b not in changed]}

    def ensure_indexed(self, bases: list[str]) -> None:
        """First-run guarantee: index any base that has never been indexed. Does NOT re-sign
        already-indexed folders (that's refresh()'s job) — so a warm open stays a pure DB read."""
        for b in bases:
            row = self._db.execute("SELECT sig FROM folders WHERE path=?", (b,)).fetchone()
            if row is None or row["sig"] is None:
                self.index_folder(b)

    # ---- reads (pure DB — zero filesystem access) -------------------------------
    @staticmethod
    def _row_to_rec(r) -> dict:
        """Row -> the JS-facing record shape. Adds `tags` (AC-8.3 chip derivation needs it in
        every returned record — the frontend computes its "in view" chip set client-side)."""
        rec = {"file": r["name"], "dir": r["folder"], "type": r["type"]}
        for k in ("service", "model", "prompt", "category"):
            if r[k]:
                rec[k] = r[k]
        tags = (r["tags"] or "").split(",") if "tags" in r.keys() else []
        rec["tags"] = [t for t in tags if t]
        return rec

    def list_images(self, bases: list[str], limit: int = 8000) -> list:
        """Warm Library read: a single local-DB query, de-duped by basename, no NAS access.
        Record shape matches the old scanner exactly so the JS contract is unchanged."""
        if not bases:
            return []
        q = ("SELECT name,folder,type,service,model,prompt,category,tags FROM images "
             f"WHERE folder IN ({','.join('?' * len(bases))}) ORDER BY name COLLATE NOCASE")
        seen, out = set(), []
        for r in self._db.execute(q, bases):
            if r["name"] in seen:
                continue
            seen.add(r["name"])
            out.append(self._row_to_rec(r))
            if len(out) >= limit:
                break
        return out

    def set_folder_enabled(self, base: str, enabled: bool) -> None:
        """Toggle a folder — a pure DB flag flip, ZERO filesystem reads (AC-1)."""
        self._db.execute("INSERT OR IGNORE INTO folders(path,enabled) VALUES(?,1)", (base,))
        self._db.execute("UPDATE folders SET enabled=? WHERE path=?", (1 if enabled else 0, base))
        self._db.commit()

    def search(self, query: str, bases: list[str], limit: int = 8000) -> list:
        """Prompt/tag search — FTS5 when available, LIKE fallback otherwise (AC-5)."""
        if not query.strip():
            return self.list_images(bases, limit)
        ph = ",".join("?" * len(bases))
        if self.fts:
            rows = self._db.execute(
                "SELECT i.name,i.folder,i.type,i.service,i.model,i.prompt,i.category,i.tags "
                "FROM images_fts f JOIN images i ON i.rowid=f.rowid "
                f"WHERE images_fts MATCH ? AND i.folder IN ({ph}) ORDER BY i.name COLLATE NOCASE",
                [query, *bases]).fetchall()
        else:
            like = f"%{query}%"
            rows = self._db.execute(
                "SELECT name,folder,type,service,model,prompt,category,tags FROM images "
                f"WHERE folder IN ({ph}) AND (prompt LIKE ? OR name LIKE ? OR tags LIKE ?) "
                "ORDER BY name COLLATE NOCASE", [*bases, like, like, like]).fetchall()
        seen, out = set(), []
        for r in rows:
            if r["name"] in seen:
                continue
            seen.add(r["name"])
            out.append(self._row_to_rec(r))
            if len(out) >= limit:
                break
        return out

    # ---- tags (Spec C AC-8.2/8.3/8.7) --------------------------------------------
    def ensure_row(self, path: str, folder: str, name: str, type_: str) -> None:
        """Cheap upsert-a-stub so a freshly-generated (not-yet-indexed) image can be tagged from
        the lightbox immediately, without a full folder reindex."""
        self._db.execute(
            "INSERT OR IGNORE INTO images(path,folder,name,type,created) VALUES(?,?,?,?,?)",
            (path, folder, name, type_, time.time()))
        self._db.commit()

    def get_tags(self, path: str) -> list:
        row = self._db.execute("SELECT tags FROM images WHERE path=?", (path,)).fetchone()
        if not row or not row["tags"]:
            return []
        return [t for t in row["tags"].split(",") if t]

    def _set_tags(self, path: str, tags: set) -> None:
        self._db.execute("UPDATE images SET tags=? WHERE path=?",
                          (",".join(sorted(t for t in tags if t)), path))
        self._db.commit()

    def add_tag(self, path: str, tag: str) -> list:
        """AC-8.2 — manual tag from the lightbox. Refires the FTS triggers (a plain UPDATE) so
        tag search (AC-8.4) sees it immediately."""
        tags = set(self.get_tags(path))
        tags.add(_norm_tag(tag))
        self._set_tags(path, tags)
        return sorted(tags)

    def remove_tag(self, path: str, tag: str) -> list:
        tags = set(self.get_tags(path))
        tags.discard(_norm_tag(tag))
        self._set_tags(path, tags)
        return sorted(tags)

    # ---- vision auto-tagging (AC-8.7) --------------------------------------------
    def untagged_paths(self, bases: list, limit: int = 500) -> list:
        """Images with no vision_tagged_at marker yet — the backfill candidate queue."""
        if not bases:
            return []
        ph = ",".join("?" * len(bases))
        rows = self._db.execute(
            f"SELECT path FROM images WHERE folder IN ({ph}) AND vision_tagged_at IS NULL "
            "AND type='image' ORDER BY created DESC LIMIT ?", [*bases, limit]).fetchall()
        return [r["path"] for r in rows]

    def mark_vision_tagged(self, path: str, tags: list) -> None:
        """Cache a vision batch's result once — never re-called for this path again."""
        existing = set(self.get_tags(path))
        existing |= set(str(t) for t in (tags or []))
        self._db.execute("UPDATE images SET tags=?, vision_tagged_at=? WHERE path=?",
                          (",".join(sorted(t for t in existing if t)), time.time(), path))
        self._db.commit()

    # ---- presets (Spec C #4) ------------------------------------------------------
    _PRESET_COLS = {
        "styles": ("name", "negative", "prompt_template", "params_json", "model"),
        "recipes": ("name", "provider", "model", "seed", "prompt", "negative", "params_json"),
    }

    def _preset_row_to_dict(self, table: str, r) -> dict:
        d = {"id": r["id"], "name": r["name"], "is_default": bool(r["is_default"]), "updated": r["updated"]}
        for c in self._PRESET_COLS[table]:
            d[c] = json.loads(r[c]) if c == "params_json" else r[c]
        d["params"] = d.pop("params_json", {}) or {}
        return d

    def save_preset(self, table: str, data: dict) -> int:
        """AC-4.1 — insert one Style or Recipe. `table` is "styles" or "recipes"."""
        cols = self._PRESET_COLS[table]
        vals = []
        for c in cols:
            v = data.get(c, "")
            vals.append(json.dumps(data.get("params") or {}) if c == "params_json" else v)
        ph = ",".join("?" * len(cols))
        cur = self._db.execute(
            f"INSERT INTO {table}({','.join(cols)},is_default,updated) VALUES({ph},0,?)",
            [*vals, time.time()])
        self._db.commit()
        return cur.lastrowid

    def list_presets(self, table: str) -> list:
        rows = self._db.execute(f"SELECT * FROM {table} ORDER BY is_default DESC, name COLLATE NOCASE").fetchall()
        return [self._preset_row_to_dict(table, r) for r in rows]

    def get_preset(self, table: str, preset_id: int):
        r = self._db.execute(f"SELECT * FROM {table} WHERE id=?", (preset_id,)).fetchone()
        return self._preset_row_to_dict(table, r) if r else None

    def rename_preset(self, table: str, preset_id: int, name: str) -> None:
        self._db.execute(f"UPDATE {table} SET name=?, updated=? WHERE id=?", (name, time.time(), preset_id))
        self._db.commit()

    def delete_preset(self, table: str, preset_id: int) -> None:
        self._db.execute(f"DELETE FROM {table} WHERE id=?", (preset_id,))
        self._db.commit()

    def set_default_preset(self, table: str, preset_id: int) -> None:
        """AC-4.2 — one default per type: clear every other row's flag, set this one, atomically."""
        with self._db:
            self._db.execute(f"UPDATE {table} SET is_default=0")
            self._db.execute(f"UPDATE {table} SET is_default=1, updated=? WHERE id=?", (time.time(), preset_id))

    def get_default_preset(self, table: str):
        r = self._db.execute(f"SELECT * FROM {table} WHERE is_default=1 LIMIT 1").fetchone()
        return self._preset_row_to_dict(table, r) if r else None

    # ---- migration --------------------------------------------------------------
    def migrate_from_json(self, json_path: str) -> int:
        """One-time import of the legacy .cache/library_index.json so the first open after the
        upgrade is instant (no initial re-crawl). Returns rows imported (0 if none/absent)."""
        p = Path(json_path)
        if not p.exists() or self._db.execute("SELECT 1 FROM images LIMIT 1").fetchone():
            return 0
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            recs = data.get("files") if isinstance(data, dict) else data
        except Exception:
            return 0
        n = 0
        for rec in recs or []:
            folder = rec.get("dir")
            name = rec.get("file")
            if not (folder and name):
                continue
            self._db.execute("INSERT OR IGNORE INTO folders(path,enabled) VALUES(?,1)", (folder,))
            self._db.execute(
                "INSERT OR REPLACE INTO images"
                "(path,folder,name,type,service,model,seed,prompt,category)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (str(Path(folder) / name), folder, name, rec.get("type", "image"),
                 rec.get("service"), rec.get("model"), rec.get("seed"),
                 rec.get("prompt"), rec.get("category")))
            n += 1
        self._db.commit()
        return n

    def close(self) -> None:
        self._db.close()
