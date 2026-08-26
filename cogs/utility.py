import discord
from discord import app_commands
from discord.ext import commands


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="봇의 응답 속도를 확인합니다.")
    async def ping(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 퐁! 지연 시간: {latency_ms}ms")

    @app_commands.command(name="userinfo", description="유저 정보를 확인합니다.")
    @app_commands.describe(member="정보를 확인할 유저 (생략 시 본인)")
    async def userinfo(
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
        member = member or interaction.user
        embed = discord.Embed(title=f"{member.display_name} 정보", color=discord.Color.blue())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="이름", value=str(member), inline=True)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(
            name="서버 참가일",
            value=discord.utils.format_dt(member.joined_at, style="R") if member.joined_at else "알 수 없음",
            inline=False,
        )
        embed.add_field(
            name="계정 생성일",
            value=discord.utils.format_dt(member.created_at, style="R"),
            inline=False,
        )
        roles = [role.mention for role in reversed(member.roles) if role.name != "@everyone"]
        embed.add_field(name="역할", value=", ".join(roles) if roles else "없음", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="서버 정보를 확인합니다.")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("이 명령어는 서버 안에서만 사용할 수 있습니다.", ephemeral=True)
            return

        embed = discord.Embed(title=guild.name, color=discord.Color.green())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="서버장", value=str(guild.owner), inline=True)
        embed.add_field(name="멤버 수", value=guild.member_count, inline=True)
        embed.add_field(name="채널 수", value=len(guild.channels), inline=True)
        embed.add_field(name="역할 수", value=len(guild.roles), inline=True)
        embed.add_field(
            name="생성일",
            value=discord.utils.format_dt(guild.created_at, style="R"),
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="유저의 아바타를 확인합니다.")
    @app_commands.describe(member="아바타를 확인할 유저 (생략 시 본인)")
    async def avatar(
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
        member = member or interaction.user
        embed = discord.Embed(title=f"{member.display_name}의 아바타", color=discord.Color.purple())
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clear", description="메시지를 지정한 개수만큼 삭제합니다.")
    @app_commands.describe(amount="삭제할 메시지 개수 (1~100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🗑️ 메시지 {len(deleted)}개를 삭제했습니다.", ephemeral=True)

    @clear.error
    async def clear_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "이 명령어를 사용하려면 '메시지 관리' 권한이 필요합니다.", ephemeral=True
            )
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
