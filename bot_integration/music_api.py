"""Call submit_song() from your existing Twitch reward-redemption handler.
This is a bridge, NOT an EventSub subscription or OAuth implementation.
"""
import os, aiohttp

async def submit_song(channel:str, viewer:str, user_input:str, redemption_id:str):
    base=os.environ['MUSIC_API_URL'].rstrip('/')
    key=os.environ['MUSIC_BOT_KEY']
    payload={'channel':channel,'viewer':viewer,'video_id':user_input,'source_id':redemption_id}
    timeout=aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(base+'/v1/music/requests',json=payload,headers={'Authorization':'Bearer '+key}) as response:
            result=await response.json()
            if response.status>=400:raise RuntimeError(f'Music API {response.status}: {result}')
            return result
