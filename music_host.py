"""Run Majikku Music API and an optional Cloudflare Tunnel beside the bots."""
import asyncio
import logging
import os
import platform
from pathlib import Path

async def _start_tunnel():
    if os.getenv('CLOUDFLARE_TUNNEL_ENABLED', '0').lower() not in ('1', 'true', 'yes'):
        return None
    if platform.system() != 'Linux':
        print('Cloudflare Tunnel skipped: Linux cloudflared binary cannot run on this OS.')
        return None
    token = os.getenv('CLOUDFLARE_TUNNEL_TOKEN', '').strip()
    if not token:
        print('Cloudflare Tunnel skipped: CLOUDFLARE_TUNNEL_TOKEN is missing.')
        return None
    binary = Path(__file__).resolve().parent / 'tools' / 'cloudflared'
    if not binary.is_file():
        print('Cloudflare Tunnel skipped: tools/cloudflared was not found.')
        return None
    try:
        binary.chmod(binary.stat().st_mode | 0o111)
        # Prevent cloudflared diagnostic logs from dumping the tunnel token.
        tunnel_env = os.environ.copy()
        tunnel_env.pop('CLOUDFLARE_TUNNEL_TOKEN', None)
        process = await asyncio.create_subprocess_exec(
            str(binary), 'tunnel', '--no-autoupdate', 'run', '--token', token,
            stdin=asyncio.subprocess.DEVNULL,
            env=tunnel_env,
        )
        print(f'Cloudflare Tunnel process started (PID {process.pid}); waiting for connector logs.')
        return process
    except Exception as exc:
        print(f'Cloudflare Tunnel could not start: {type(exc).__name__}: {exc}')
        return None

async def _stop_tunnel(process):
    if process is None or process.returncode is not None:
        return
    try:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=8)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
    except ProcessLookupError:
        pass

async def run_with_music_api(*bot_coroutines):
    # Tunnel is optional and cannot block normal bot startup.
    tunnel = await _start_tunnel()
    server = None
    api_task = None
    try:
        enabled = os.getenv('MUSIC_API_ENABLED', '1').lower() not in ('0', 'false', 'no')
        if enabled and os.getenv('MUSIC_BOT_KEY'):
            try:
                import uvicorn
                from server.app import app
                port = int(os.getenv('MUSIC_API_PORT', os.getenv('SERVER_PORT', os.getenv('PORT', '8000'))))
                host = os.getenv('MUSIC_API_BIND', '0.0.0.0')
                config = uvicorn.Config(app, host=host, port=port, log_level='info', access_log=False, lifespan='on')
                server = uvicorn.Server(config)
                async def api_runner():
                    try:
                        await server.serve()
                        if not server.started:
                            print('Music API did not start; check port allocation and startup logs.')
                    except Exception as exc:
                        logging.exception('Music API stopped unexpectedly: %s', exc)
                api_task = asyncio.create_task(api_runner(), name='music-api')
            except Exception as exc:
                print(f'Music API unavailable ({type(exc).__name__}: {exc}); bots will still run.')
        elif enabled:
            print('Music API disabled: MUSIC_BOT_KEY is not set.')
        return await asyncio.gather(*bot_coroutines)
    finally:
        if server is not None:
            server.should_exit = True
        if api_task is not None:
            try:
                await asyncio.wait_for(api_task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                api_task.cancel()
        await _stop_tunnel(tunnel)
