import os
import discord
from discord import app_commands
from aiohttp import web
import aiohttp

# ──────────────────────────────────────────────
# [설정 영역] 본인의 디스코드 봇 정보와 채널/역할 ID를 입력하세요
# 🚨 토큰은 이제 코드에 직접 적지 않고 Render 환경 변수(DISCORD_TOKEN)에서 안전하게 불러옵니다!
TOKEN = os.environ.get('DISCORD_TOKEN')

CLIENT_ID = "1565957887069659326"
CLIENT_SECRET = "eGG72Szkt9o6Elrsg2xwXDNpJc-xhIF2"
REDIRECT_URI = "http://localhost:5000/callback"

RECOVERY_GUILD_ID = 1565964822628143205   # 복구 대상 디스코드 서버 ID (숫자만)
LOG_CHANNEL_ID = 1565965179336785982      # 인증 완료 로그가 쌓일 채널 ID (숫자만)
ROLE_ID = 1565966286377189457             # 인증 완료 시 부여할 역할 ID (숫자만 입력)
# ──────────────────────────────────────────────

intents = discord.Intents.default()
intents.members = True

class AuthBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

client = AuthBot()

@client.event
async def on_ready():
    print(f"로그인 완료: {client.user} (ID: {client.user.id})")
    print("디스코드 봇이 정상적으로 실행 중입니다.")

# 1. 인증 패널 전송 명령어 (/인증패널) - 채널 선택 기능 추가
@client.tree.command(name="인증패널", description="지정한 채널에 서버 인증 패널을 생성합니다.")
@app_commands.describe(channel="인증 패널을 보낼 채널을 선택하세요")
async def auth_panel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🛡️ 서버 인증 시스템",
        description="아래 버튼을 눌러 디스코드 계정 인증을 진행해 주세요.",
        color=discord.Color.blue()
    )
    
    oauth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify+guilds.join"
    )

    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="인증하기", url=oauth_url, style=discord.ButtonStyle.link))

    # 선택한 채널에 패널 전송
    await channel.send(embed=embed, view=view)
    
    # 명령어 실행한 관리자에게만 처리 완료 메시지 띄우기 (다른 사람에게는 보이지 않음)
    await interaction.response.send_message(f"성공적으로 {channel.mention} 채널에 인증 패널을 보냈습니다!", ephemeral=True)

# 2. 수동 복구 실행 명령어 (/복구실행)
@client.tree.command(name="복구실행", description="지정한 유저를 복구 서버에 강제로 참여시킵니다.")
@app_commands.describe(user_id="복구할 유저의 디스코드 ID")
async def manual_recover(interaction: discord.Interaction, user_id: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return

    guild = client.get_guild(RECOVERY_GUILD_ID)
    if not guild:
        await interaction.response.send_message("설정된 복구 서버를 찾을 수 없습니다.", ephemeral=True)
        return

    try:
        await interaction.response.send_message(f"유저 ID `<@{user_id}>` 복구 처리를 시도합니다.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"오류 발생: {e}", ephemeral=True)

# 3. OAuth2 콜백 및 역할 부여 처리 (aiohttp 웹서버)
async def handle_callback(request):
    code = request.query.get("code")
    if not code:
        return web.Response(text="인증 코드가 존재하지 않습니다.", status=400)

    # 1. 엑세스 토큰 교환
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    async with aiohttp.ClientSession() as session:
        async with session.post('https://discord.com/api/oauth2/token', data=data, headers=headers) as resp:
            if resp.status != 200:
                return web.Response(text="토큰 발급 실패! 관리자에게 문의하세요.", status=400)
            token_json = await resp.json()
            access_token = token_json.get('access_token')

        # 2. 유저 정보 가져오기
        async with session.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {access_token}'}) as resp:
            if resp.status != 200:
                return web.Response(text="유저 정보 조회 실패!", status=400)
            user_json = await resp.json()
            user_id = user_json.get('id')

        # 3. 서버에 유저 추가 및 역할 부여
        add_data = {
            'access_token': access_token,
            'roles': [str(ROLE_ID)]
        }
        async with session.put(f'https://discord.com/api/guilds/{RECOVERY_GUILD_ID}/members/{user_id}', json=add_data, headers={'Authorization': f'Bot {TOKEN}'}) as resp:
            if resp.status not in [200, 201]:
                print(f"서버 참여/역할 부여 실패: {await resp.text()}")

    # 로그 채널에 알림 전송
    channel = client.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"🎉 유저 <@{user_id}>님이 웹 인증을 완료하고 역할을 부여받았습니다!")

    return web.Response(text="<h1>인증 및 역할 부여가 성공적으로 완료되었습니다! 창을 닫으셔도 됩니다.</h1>", content_type="text/html")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/callback', handle_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)  # Render 외부 접속을 위해 0.0.0.0과 포트 8080으로 설정
    await site.start()
    print("인증 콜백 웹 서버가 8080번 포트에서 실행 중입니다.")

# 봇 실행 시 웹서버도 함께 구동
async def main():
    if not TOKEN:
        print("오류: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
        return
    await start_web_server()
    await client.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
