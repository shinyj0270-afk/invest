import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from .core import digest, validate_snapshot

class Store:
    def __init__(self,root,profile,mode):
        if profile not in ('home','work','unknown') or mode not in ('fixture','user_input','live'): raise ValueError('프로필/모드 오류')
        self.mode=mode
        self.path=Path(root)/profile/mode/'research.sqlite3'; self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, created TEXT, status TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY,payload TEXT);
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,first_seen TEXT,payload TEXT);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,created TEXT,payload TEXT);''')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=15)
        try:
            with db: yield db
        finally: db.close()
    def save_snapshot(self,snapshot,complete=True):
        validate_snapshot(snapshot)
        if snapshot['meta']['data_mode']!=self.mode: raise ValueError('실제/가상 자료 혼합 금지')
        sid=digest(snapshot)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?)',(sid,datetime.now(timezone.utc).isoformat(),'complete' if complete else 'staging',json.dumps(snapshot,ensure_ascii=False)))
        return sid
    def latest(self):
        with self.connect() as db: r=db.execute("SELECT payload FROM snapshots WHERE status='complete' ORDER BY created DESC LIMIT 1").fetchone()
        return json.loads(r[0]) if r else None
    def save_setting(self,name,value):
        with self.connect() as db: db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(name,json.dumps(value,ensure_ascii=False)))
    def setting(self,name,default=None):
        with self.connect() as db: r=db.execute('SELECT payload FROM settings WHERE name=?',(name,)).fetchone()
        return json.loads(r[0]) if r else default
    def event(self,event):
        # Event identity excludes weekly evaluation time.
        eid=digest({k:event[k] for k in ('code','path','quarter','model')})
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?)',(eid,datetime.now(timezone.utc).isoformat(),json.dumps(event)))
            db.execute('UPDATE events SET payload=? WHERE id=?',(json.dumps(event),eid))
        return eid
