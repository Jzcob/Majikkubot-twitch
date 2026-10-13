import os, sqlite3, hashlib, secrets, time, re
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

DB=os.getenv('MUSIC_DB','music.sqlite3')
BOT_KEY=os.getenv('MUSIC_BOT_KEY','')
app=FastAPI(title='Majikku Music API',version='0.1.0')

def digest(s): return hashlib.sha256(s.encode()).hexdigest()
@contextmanager
def conn():
    db=sqlite3.connect(DB,timeout=20,isolation_level=None)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    try: yield db
    finally: db.close()

def init():
    with conn() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS devices(channel TEXT PRIMARY KEY, token_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT NOT NULL, video_id TEXT NOT NULL, viewer TEXT NOT NULL, source_id TEXT UNIQUE, status TEXT NOT NULL DEFAULT 'queued', created_at INTEGER NOT NULL, claimed_at INTEGER);
        CREATE INDEX IF NOT EXISTS ix_requests ON requests(channel,status,id);''')
init()
class Request(BaseModel):
    channel:str
    video_id:str
    viewer:str='viewer'
    source_id:str|None=None

def video_id(value):
    value=value.strip()
    match=re.search(r'(?:[?&]v=|youtu\.be/|music\.youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})',value)
    result=match.group(1) if match else value
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',result): raise HTTPException(422,'Use a YouTube/YouTube Music video link or 11-character video ID')
    return result

def auth(channel, authorization):
    token=authorization.removeprefix('Bearer ').strip()
    with conn() as db: row=db.execute('SELECT token_hash FROM devices WHERE channel=?',(channel,)).fetchone()
    if not row or not secrets.compare_digest(row['token_hash'],digest(token)): raise HTTPException(401,'Invalid companion token')

def bot_auth(authorization):
    if not BOT_KEY or not secrets.compare_digest(authorization, 'Bearer '+BOT_KEY): raise HTTPException(401,'Invalid bot key')

@app.get('/health')
def health(): return {'status':'ok'}

@app.post('/v1/music/requests')
def submit(req:Request,authorization:str=Header(default='')):
    bot_auth(authorization)
    channel=req.channel.strip().lower()
    if not re.fullmatch('[a-z0-9_]{2,25}',channel): raise HTTPException(422,'Invalid channel')
    vid=video_id(req.video_id)
    with conn() as db:
        if req.source_id:
            existing=db.execute('SELECT id FROM requests WHERE source_id=?',(req.source_id,)).fetchone()
            if existing:return {'id':existing['id'],'duplicate':True}
        cur=db.execute('INSERT INTO requests(channel,video_id,viewer,source_id,created_at) VALUES(?,?,?,?,?)',(channel,vid,req.viewer[:80],req.source_id,int(time.time())))
        return {'id':cur.lastrowid,'duplicate':False}

@app.get('/v1/music/{channel}/queue')
def queue(channel:str,authorization:str=Header(default='')):
    auth(channel.lower(),authorization)
    with conn() as db:
        rows=db.execute("SELECT id,video_id,viewer,status FROM requests WHERE channel=? AND status IN ('queued','claimed') ORDER BY id LIMIT 100",(channel.lower(),)).fetchall()
        return {'requests':[dict(r) for r in rows]}

@app.post('/v1/music/{channel}/claim')
def claim(channel:str,authorization:str=Header(default='')):
    channel=channel.lower();auth(channel,authorization)
    with conn() as db:
        db.execute('BEGIN IMMEDIATE')
        # Claim is idempotent: a pending claim is returned until acknowledged.
        row=db.execute("SELECT id,video_id,viewer FROM requests WHERE channel=? AND status='claimed' ORDER BY id LIMIT 1",(channel,)).fetchone()
        if row:return dict(row)
        row=db.execute("SELECT id,video_id,viewer FROM requests WHERE channel=? AND status='queued' ORDER BY id LIMIT 1",(channel,)).fetchone()
        if row:db.execute("UPDATE requests SET status='claimed',claimed_at=? WHERE id=?",(int(time.time()),row['id']))
        return dict(row) if row else {'empty':True}

@app.post('/v1/music/{channel}/requests/{request_id}/complete')
def complete(channel:str,request_id:int,authorization:str=Header(default='')):
    channel=channel.lower();auth(channel,authorization)
    with conn() as db:
        cur=db.execute("UPDATE requests SET status='completed' WHERE id=? AND channel=? AND status='claimed'",(request_id,channel))
        if not cur.rowcount:raise HTTPException(404,'Claim not found')
    return {'ok':True}

@app.post('/v1/music/{channel}/requests/{request_id}/release')
def release(channel:str,request_id:int,authorization:str=Header(default='')):
    channel=channel.lower();auth(channel,authorization)
    with conn() as db:
        db.execute("UPDATE requests SET status='queued',claimed_at=NULL WHERE id=? AND channel=? AND status='claimed'",(request_id,channel))
    return {'ok':True}
