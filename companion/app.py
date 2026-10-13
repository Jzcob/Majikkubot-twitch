"""Majikku Music Companion - standalone dark desktop client."""
import json
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import requests
import secrets
import webbrowser
HOME = Path(os.getenv('APPDATA', str(Path.home()))) / 'MajikkuMusic'
SETTINGS = HOME / 'settings.json'
YT = 'http://127.0.0.1:9863/api/v1'
APPID = 'majikkumusic'
BG = '#090e1b'
SIDE = '#0e1526'
PANEL = '#131c30'
CARD = '#1a2540'
FG = '#f2f5ff'
MUTED = '#9cabc9'
PURPLE = '#8357f6'
GREEN = '#32d6a0'
RED = '#ff7487'
FONT = 'Segoe UI'

class Companion:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Majikku Music Companion')
        self.root.geometry('1050x690')
        self.root.minsize(850, 570)
        self.root.configure(bg=BG)
        self.events = queue.Queue()
        self.busy = False
        self.running = True
        try:
            self.settings = json.loads(SETTINGS.read_text(encoding='utf-8')) if SETTINGS.exists() else {}
        except (ValueError, OSError):
            self.settings = {}
        self.api = tk.StringVar(value=self.settings.get('api', 'https://twitch.majikku.org'))
        self.channel = tk.StringVar(value=self.settings.get('channel', ''))
        self.token = tk.StringVar(value=self.settings.get('token', ''))
        self.yt_token = self.settings.get('yt_token', '')
        self.twitch_client_id = tk.StringVar(value=self.settings.get('twitch_client_id', ''))
        self.status = tk.StringVar(value='Ready to connect')
        self.api_state = tk.StringVar(value='Not connected')
        self.yt_state = tk.StringVar(value='Authorized (saved)' if self.yt_token else 'Not connected')
        self.requests = []
        self.page = 'Dashboard'
        self.nav_buttons = {}
        self._build()
        self.show_page('Dashboard')
        self.root.after(150, self.drain)
        self.root.after(4000, self.poll)
        self.root.protocol('WM_DELETE_WINDOW', self.close)

    def label(self, parent, text, size=11, color=FG, bold=False, **kw):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                        font=(FONT, size, 'bold' if bold else 'normal'), **kw)

    def button(self, parent, text, command, accent=False, width=None):
        return tk.Button(parent, text=text, command=command, bg=PURPLE if accent else CARD,
                         fg='white', activebackground='#6d42dd' if accent else '#293855',
                         activeforeground='white', relief='flat', bd=0, cursor='hand2',
                         font=(FONT, 10, 'bold'), padx=15, pady=10, width=width)

    def panel(self, parent, **kw):
        return tk.Frame(parent, bg=PANEL, padx=18, pady=16, **kw)

    def _build(self):
        self.sidebar = tk.Frame(self.root, bg=SIDE, width=205)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar, text='♫', bg=SIDE, fg=PURPLE, font=(FONT, 29, 'bold')).pack(anchor='w', padx=22, pady=(25, 2))
        self.label(self.sidebar, 'MAJIKKU MUSIC', 14, bold=True).pack(anchor='w', padx=22)
        self.label(self.sidebar, 'COMPANION', 9, MUTED).pack(anchor='w', padx=22, pady=(0, 34))
        for name in ('Dashboard', 'Queue', 'Connections', 'Settings', 'About'):
            b = tk.Button(self.sidebar, text='   ' + name, anchor='w', bg=SIDE, fg=MUTED,
                          activebackground=CARD, activeforeground=FG, relief='flat', bd=0,
                          font=(FONT, 11), padx=16, pady=13, cursor='hand2',
                          command=lambda n=name: self.show_page(n))
            b.pack(fill='x', padx=10, pady=3)
            self.nav_buttons[name] = b
        self.label(self.sidebar, 'Independent desktop project', 9, MUTED).pack(side='bottom', pady=18)
        self.main = tk.Frame(self.root, bg=BG)
        self.main.pack(side='left', fill='both', expand=True)
        self.header = tk.Frame(self.main, bg=BG)
        self.header.pack(fill='x', padx=26, pady=(24, 10))
        self.heading = self.label(self.header, 'Dashboard', 21, bold=True)
        self.heading.pack(side='left')
        self.connection_badge = tk.Label(self.header, text='●  API disconnected', bg=BG, fg=RED, font=(FONT, 10))
        self.connection_badge.pack(side='right')
        self.content = tk.Frame(self.main, bg=BG)
        self.content.pack(fill='both', expand=True, padx=26, pady=8)
        self.footer = tk.Frame(self.main, bg=SIDE, height=40)
        self.footer.pack(side='bottom', fill='x')
        tk.Label(self.footer, textvariable=self.status, bg=SIDE, fg=MUTED, font=(FONT, 10),
                 anchor='w', wraplength=760).pack(fill='x', padx=18, pady=11)

    def clear(self):
        for child in self.content.winfo_children():
            child.destroy()

    def show_page(self, name):
        self.page = name
        self.heading.configure(text=name)
        for key, b in self.nav_buttons.items():
            b.configure(bg=PURPLE if key == name else SIDE, fg=FG if key == name else MUTED)
        self.clear()
        {'Dashboard': self.dashboard, 'Queue': self.queue_page, 'Connections': self.connections,
         'Settings': self.settings_page, 'About': self.about}[name]()

    def dashboard(self):
        hero = self.panel(self.content)
        hero.pack(fill='x', pady=(0, 16))
        self.label(hero, 'NOW PLAYING', 10, PURPLE, True).pack(anchor='w')
        self.label(hero, 'YouTube Music Desktop', 20, bold=True).pack(anchor='w', pady=(8, 4))
        self.label(hero, 'Track metadata and artwork are not yet available in this version.', 10, MUTED).pack(anchor='w')
        controls = tk.Frame(hero, bg=PANEL)
        controls.pack(anchor='w', pady=(20, 2))
        for text, action, accent in [('▶  Resume', lambda: self.yt_command('play'), True),
                                     ('Ⅱ  Pause', lambda: self.yt_command('pause'), False),
                                     ('⏭  Play next request', self.play_next, False)]:
            self.button(controls, text, action, accent).pack(side='left', padx=(0, 10))
        state = self.panel(self.content)
        state.pack(fill='x', pady=(0, 16))
        self.label(state, 'CONNECTIONS', 10, PURPLE, True).pack(anchor='w', pady=(0, 10))
        self.label(state, 'Music API', 11, bold=True).pack(anchor='w')
        tk.Label(state, textvariable=self.api_state, bg=PANEL, fg=MUTED, font=(FONT, 10)).pack(anchor='w', pady=(0, 9))
        self.label(state, 'YouTube Music Desktop', 11, bold=True).pack(anchor='w')
        tk.Label(state, textvariable=self.yt_state, bg=PANEL, fg=MUTED, font=(FONT, 10)).pack(anchor='w')
        q = self.panel(self.content)
        q.pack(fill='both', expand=True)
        head = tk.Frame(q, bg=PANEL)
        head.pack(fill='x')
        self.label(head, 'UPCOMING REQUESTS', 11, PURPLE, True).pack(side='left')
        self.button(head, 'Refresh', self.refresh).pack(side='right')
        self.queue_rows(q, limit=4)

    def queue_rows(self, parent, limit=None):
        items = self.requests if limit is None else self.requests[:limit]
        if not items:
            self.label(parent, 'No requests loaded. Connect your device and refresh the queue.',
                       11, MUTED, wraplength=600, justify='left').pack(anchor='w', pady=20)
            return
        for idx, item in enumerate(items, 1):
            row = tk.Frame(parent, bg=CARD, padx=14, pady=12)
            row.pack(fill='x', pady=4)
            self.label(row, f'{idx:02d}', 11, PURPLE, True).pack(side='left', padx=(0, 14))
            details = tk.Frame(row, bg=CARD)
            details.pack(side='left', fill='x', expand=True)
            self.label(details, str(item.get('video_id', 'Unknown video')), 11, bold=True).pack(anchor='w')
            self.label(details, f"Requested by {item.get('viewer', 'viewer')}", 9, MUTED).pack(anchor='w')
            self.label(row, str(item.get('status', 'queued')).upper(), 9, GREEN).pack(side='right')

    def queue_page(self):
        head = self.panel(self.content)
        head.pack(fill='x', pady=(0, 12))
        self.label(head, 'Song requests', 17, bold=True).pack(side='left')
        self.button(head, 'Refresh queue', self.refresh).pack(side='right', padx=(8, 0))
        self.button(head, 'Play next', self.play_next, True).pack(side='right')
        body = self.panel(self.content)
        body.pack(fill='both', expand=True)
        self.queue_rows(body)
        self.label(self.content, 'Play Next currently replaces the playing track; automatic advancement is not enabled.',
                   10, MUTED).pack(anchor='w', pady=12)

    def connections(self):
        p = self.panel(self.content)
        p.pack(fill='x', pady=(0, 16))
        self.label(p, 'YouTube Music Desktop', 17, bold=True).pack(anchor='w')
        self.label(p, 'Connect to the local companion server running on your computer.', 10, MUTED).pack(anchor='w', pady=7)
        tk.Label(p, textvariable=self.yt_state, bg=PANEL, fg=GREEN, font=(FONT, 10)).pack(anchor='w', pady=(0, 12))
        self.button(p, 'Connect YouTube Music', self.connect_yt, True).pack(anchor='w')
        a = self.panel(self.content)
        a.pack(fill='x')
        self.label(a, 'Hosted Music API', 17, bold=True).pack(anchor='w')
        self.label(a, 'Sign in with Twitch to securely register this computer.', 10, MUTED).pack(anchor='w', pady=7)
        tk.Label(a, textvariable=self.api_state, bg=PANEL, fg=MUTED, font=(FONT, 10)).pack(anchor='w', pady=(0, 12))
        self.button(a, 'Connect with Twitch', self.connect_twitch, True).pack(anchor='w', pady=(0, 9))
        self.button(a, 'Test API connection', self.refresh).pack(anchor='w')

    def settings_page(self):
        p = self.panel(self.content)
        p.pack(fill='x')
        self.label(p, 'Connection settings', 17, bold=True).pack(anchor='w', pady=(0, 15))
        for title, var, secret in [('API URL', self.api, False), ('Twitch channel', self.channel, False),
                                   ('Companion device token (automatic)', self.token, True),
                                   ('Twitch application Client ID (legacy, not required)', self.twitch_client_id, False)]:
            self.label(p, title, 10, MUTED).pack(anchor='w', pady=(7, 5))
            entry = tk.Entry(p, textvariable=var, show='•' if secret else '', bg=CARD,
                             fg=FG, insertbackground=FG, relief='flat', font=(FONT, 11), bd=0)
            entry.pack(fill='x', ipady=10)
        self.label(p, 'Use Connections → Connect with Twitch. No Client ID or Client Secret is required on this PC.',
                   10, MUTED, wraplength=650, justify='left').pack(anchor='w', pady=(15, 15))
        self.button(p, 'Save settings', self.save, True).pack(anchor='w')

    def about(self):
        p = self.panel(self.content)
        p.pack(fill='x')
        self.label(p, 'Majikku Music Companion', 20, bold=True).pack(anchor='w')
        self.label(p, 'A personal desktop project for Twitch song requests and YouTube Music Desktop.',
                   11, MUTED, wraplength=630, justify='left').pack(anchor='w', pady=15)
        self.label(p, 'Version 0.3.1 · HTTPS Twitch sign-in', 10, PURPLE).pack(anchor='w')
        self.label(p, 'Automatic song advancement is not implemented yet.',
                   10, MUTED, wraplength=630, justify='left').pack(anchor='w', pady=12)

    def save(self):
        HOME.mkdir(parents=True, exist_ok=True)
        self.settings = {'api': self.api.get().rstrip('/'), 'channel': self.channel.get().strip().lower(),
                         'token': self.token.get().strip(), 'yt_token': self.yt_token,
                         'twitch_client_id': self.twitch_client_id.get().strip()}
        SETTINGS.write_text(json.dumps(self.settings, indent=2), encoding='utf-8')
        self.status.set('Settings saved in your Windows profile.')

    def work(self, fn):
        if self.busy:
            return
        self.busy = True
        def run():
            try:
                fn()
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 401:
                    self.events.put(('api_state', 'Unauthorized — check the device token in Settings'))
                    self.events.put(('status', 'Device not linked: token rejected by hosted API.'))
                else:
                    self.events.put(('status', str(exc)))
            except Exception as exc:
                self.events.put(('status', str(exc)))
            finally:
                self.events.put(('done', None))
        threading.Thread(target=run, daemon=True).start()

    def headers(self):
        return {'Authorization': 'Bearer ' + self.token.get().strip()}

    def url(self, suffix):
        return self.api.get().rstrip('/') + '/v1/music/' + self.channel.get().strip().lower() + suffix

    def fetch_queue(self):
        r = requests.get(self.url('/queue'), headers=self.headers(), timeout=12)
        r.raise_for_status()
        self.events.put(('queue', r.json()['requests']))

    def refresh(self):
        if not self.channel.get().strip() or not self.token.get().strip():
            self.status.set('Use Connections → Connect with Twitch to link this computer first.')
            self.show_page('Settings')
            return
        self.work(self.fetch_queue)

    def poll(self):
        if self.running:
            if not self.busy and self.channel.get() and self.token.get():
                self.refresh()
            self.root.after(5000, self.poll)

    def connect_twitch(self):
        api_base = self.api.get().rstrip('/')
        if not api_base.startswith('https://'):
            messagebox.showerror('Secure connection required', 'The hosted API URL must use HTTPS.')
            return
        def do():
            poll_secret = secrets.token_urlsafe(48)
            start = requests.post(api_base + '/v1/music/auth/start',
                                  json={'poll_secret': poll_secret}, timeout=15)
            start.raise_for_status()
            session = start.json()
            self.events.put(('status', 'Complete Twitch sign-in in your browser (5-minute timeout).'))
            from urllib.parse import urlparse, parse_qs
            params = parse_qs(urlparse(session['authorize_url']).query)
            print("Twitch Client ID:", params.get("client_id", ["NOT FOUND"])[0])
            print("Twitch Redirect URI:", params.get("redirect_uri", ["NOT FOUND"])[0])
            webbrowser.open(session['authorize_url'])
            deadline = time.monotonic() + min(int(session.get('expires_in', 300)), 300)
            while time.monotonic() < deadline and self.running:
                response = requests.post(api_base + '/v1/music/auth/poll', json={
                    'state':session['state'], 'poll_secret':poll_secret}, timeout=12)
                response.raise_for_status()
                data = response.json()
                if data['status'] == 'complete':
                    self.events.put(('twitch_linked', (data['channel'], data['device_token'])))
                    return
                if data['status'] == 'failed':
                    raise RuntimeError(data.get('error') or 'Twitch sign-in failed')
                time.sleep(2)
            raise RuntimeError('Twitch sign-in timed out. Please try again.')
        self.work(do)

    def yt_headers(self):
        return {'Authorization': self.yt_token}

    def connect_yt(self):
        def do():
            code = requests.post(YT + '/auth/requestcode', json={
                'appId': APPID, 'appName': 'Majikku Music Companion', 'appVersion': '0.2.0'}, timeout=12)
            code.raise_for_status()
            self.events.put(('status', 'Approve Majikku Music Companion in YouTube Music Desktop.'))
            resp = requests.post(YT + '/auth/request', json={
                'appId': APPID, 'code': code.json()['code']}, timeout=50)
            resp.raise_for_status()
            self.yt_token = resp.json()['token']
            self.events.put(('yt_state', 'Authorized'))
            self.events.put(('status', 'YouTube Music authorized. Save settings to keep this connection.'))
        self.work(do)

    def yt_command(self, command):
        def do():
            if not self.yt_token:
                raise RuntimeError('Connect YouTube Music Desktop first.')
            r = requests.post(YT + '/command', headers=self.yt_headers(),
                              json={'command': command}, timeout=12)
            r.raise_for_status()
            self.events.put(('status', f'YouTube Music: {command} sent.'))
        self.work(do)

    def play_next(self):
        def do():
            if not self.yt_token:
                raise RuntimeError('Connect YouTube Music Desktop first.')
            r = requests.post(self.url('/claim'), headers=self.headers(), timeout=12)
            r.raise_for_status()
            item = r.json()
            if item.get('empty'):
                self.events.put(('status', 'Song request queue is empty.'))
                return
            try:
                play = requests.post(YT + '/command', headers=self.yt_headers(),
                                     json={'command': 'changeVideo', 'data': {
                                         'videoId': item['video_id'], 'playlistId': None}}, timeout=15)
                play.raise_for_status()
            except Exception:
                try:
                    requests.post(self.url(f"/requests/{item['id']}/release"),
                                  headers=self.headers(), timeout=12)
                except requests.RequestException:
                    pass
                raise
            ack = requests.post(self.url(f"/requests/{item['id']}/complete"),
                                headers=self.headers(), timeout=12)
            ack.raise_for_status()
            self.events.put(('status', f"Sent {item['video_id']} to YouTube Music Desktop."))
            self.fetch_queue()
        self.work(do)

    def drain(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'status':
                    self.status.set(value)
                elif kind == 'queue':
                    self.requests = value
                    self.api_state.set(f'Connected — {len(value)} pending requests')
                    self.status.set(f'Queue refreshed — {len(value)} pending requests.')
                    self.connection_badge.configure(text='●  API connected', fg=GREEN)
                    if self.page in ('Dashboard', 'Queue'):
                        self.show_page(self.page)
                elif kind == 'api_state':
                    self.api_state.set(value)
                    self.connection_badge.configure(text='●  API disconnected', fg=RED)
                elif kind == 'twitch_linked':
                    channel, device_token = value
                    self.channel.set(channel)
                    self.token.set(device_token)
                    self.save()
                    self.status.set(f'Twitch @{channel} connected. Device registered.')
                    self.api_state.set(f'Twitch @{channel} linked')
                    self.root.after(300, self.refresh)
                elif kind == 'yt_state':
                    self.yt_state.set(value)
                elif kind == 'done':
                    self.busy = False
        except queue.Empty:
            pass
        if self.running:
            self.root.after(150, self.drain)

    def close(self):
        self.running = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == '__main__':
    Companion().run()
