import math

import discord
from discord import app_commands
from discord.ext import commands

from personas import Persona


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def persona(self) -> Persona:
        return self.bot.persona

    def data_embed(self) -> discord.Embed:
        """사실 정보만 담는 표. 대사는 임베드 밖 본문으로 나간다.

        대사를 임베드에 넣으면 캐릭터가 말하는 것이 아니라 프로그램이 출력하는
        것처럼 보인다. 그래서 말은 평범한 메시지로 하고, 임베드는 표로만 쓴다.
        """
        return discord.Embed(color=self.persona.color)

    @app_commands.command(name="ping", description="봇의 응답 속도를 확인합니다.")
    async def ping(self, interaction: discord.Interaction):
        # 첫 heartbeat 전에는 latency가 NaN이라 round()가 ValueError를 낸다.
        latency = self.bot.latency
        latency_ms = 0 if math.isnan(latency) else round(latency * 1000)
        await interaction.response.send_message(
            self.persona.line("ping", latency=latency_ms)
        )

    @app_commands.command(name="userinfo", description="유저 정보를 확인합니다.")
    @app_commands.describe(member="정보를 확인할 유저 (생략 시 본인)")
    @app_commands.guild_only()
    async def userinfo(
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
        target = member or interaction.user
        line = self.persona.line(
            "userinfo_self" if target == interaction.user else "userinfo"
        )
        embed = self.data_embed()
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="이름", value=str(target), inline=True)
        embed.add_field(name="ID", value=target.id, inline=True)
        embed.add_field(
            name="서버 참가",
            value=discord.utils.format_dt(target.joined_at, style="R")
            if target.joined_at
            else "알 수 없음",
            inline=False,
        )
        embed.add_field(
            name="계정 생성",
            value=discord.utils.format_dt(target.created_at, style="R"),
            inline=False,
        )
        roles = [role.mention for role in reversed(target.roles) if role.name != "@everyone"]
        embed.add_field(name="역할", value=", ".join(roles) if roles else "없음", inline=False)
        await interaction.response.send_message(line, embed=embed)

    @app_commands.command(name="serverinfo", description="서버 정보를 확인합니다.")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        line = self.persona.line("serverinfo")
        embed = self.data_embed()
        embed.set_author(name=guild.name)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="서버장", value=str(guild.owner), inline=True)
        embed.add_field(name="멤버", value=guild.member_count, inline=True)
        embed.add_field(name="채널", value=len(guild.channels), inline=True)
        embed.add_field(name="역할", value=len(guild.roles), inline=True)
        embed.add_field(
            name="생성",
            value=discord.utils.format_dt(guild.created_at, style="R"),
            inline=False,
        )
        await interaction.response.send_message(line, embed=embed)

    @app_commands.command(name="avatar", description="유저의 아바타를 확인합니다.")
    @app_commands.describe(member="아바타를 확인할 유저 (생략 시 본인)")
    @app_commands.guild_only()
    async def avatar(
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
        target = member or interaction.user
        embed = self.data_embed()
        embed.set_author(name=target.display_name)
        embed.set_image(url=target.display_avatar.url)
        await interaction.response.send_message(self.persona.line("avatar"), embed=embed)

    @app_commands.command(
        name="clear", description="이 채널에 내가 남긴 메시지를 지웁니다."
    )
    @app_commands.describe(
        amount="거슬러 올라가며 훑어볼 최근 메시지 수 (1~100). 그중 내 것만 지웁니다."
    )
    @app_commands.guild_only()
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100] = 50,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await interaction.channel.purge(
                limit=amount, check=lambda m: m.author.id == interaction.user.id
            )
        except discord.Forbidden:
            await interaction.followup.send(
                self.persona.line("clear_forbidden"), ephemeral=True
            )
            return

        key = "clear" if deleted else "clear_nothing"
        await interaction.followup.send(
            self.persona.line(key, count=len(deleted)), ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
