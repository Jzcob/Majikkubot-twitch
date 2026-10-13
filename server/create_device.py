import getpass, sqlite3, hashlib, secrets, sys
from server.app import DB
if len(sys.argv)!=2: raise SystemExit('Usage: python create_device.py twitch_channel')
channel=sys.argv[1].lower().strip()
if not channel.replace('_','').isalnum():raise SystemExit('Invalid channel')
token=secrets.token_urlsafe(36)
with sqlite3.connect(DB) as db:
    db.execute('INSERT OR REPLACE INTO devices(channel,token_hash) VALUES(?,?)',(channel,hashlib.sha256(token.encode()).hexdigest()))
print('Channel:',channel,'\nCompanion token (shown once):',token)
print('Keep this secret. Running this again revokes the old token.')
