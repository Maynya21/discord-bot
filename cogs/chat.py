"""페르소나로 대화하는 기능.

페르소나 문서(personas/<key>.md)를 시스템 프롬프트로 넘긴다. 문서는 캐릭터
설정만 담고 있으므로, 디스코드라는 매체에서 필요한 출력 규칙만 여기서 덧붙인다.
페르소나 문서를 고치지 않아도 되고, 어떤 페르소나를 끼워도 규칙이 따라간다.
"""

import logging
import os
from collections import defaultdict, deque

import anthropic
import discord
from discord.ext import commands

logger = logging.getLogger("bot.chat")

DEFAULT_MODEL = "claude-sonnet-5"
#: low | medium | high | xhigh | max. 대화는 낮은 쪽이 어울리고 저렴하다.
DEFAULT_EFFORT = "low"
#: 채널마다 기억할 발화 수. 늘리면 맥락은 좋아지지만 매 요청 토큰이 늘어난다.
HISTORY = 12
MAX_TOKENS = 2048
#: 디스코드 한 메시지 상한.
DISCORD_LIMIT = 2000
#: 실패 안내에 덧붙일 이유의 길이 상한.
REASON_LIMIT = 800

OUTPUT_RULES = """\
지금 너는 디스코드 채팅에 있다. 아래는 이 매체에서의 출력 규칙이다.

- 짧게 답한다. 세 문장을 넘기지 않는다.
- 마크다운 제목(#)이나 목록(-, 1.)을 쓰지 않는다. 사람이 말하듯 쓴다.
- 서술자 목소리는 '* '로 줄을 시작한다. 표시는 봇이 알아서 바꾼다.
- 여러 사람이 있는 곳이다. 발언 앞의 '이름:'은 말한 사람을 가리키는 표시이니
  그 형식을 흉내 내지 말고, 네 대사만 쓴다."""


class Chat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 워크스페이스에 묶이지 않은 키는 어느 워크스페이스로 쓰는지 함께 보내야 한다.
        # SDK는 이 환경변수를 일반 API 키에는 적용하지 않으므로 직접 헤더로 넘긴다.
        workspace = os.getenv("ANTHROPIC_WORKSPACE_ID")
        self.client = anthropic.AsyncAnthropic(
            default_headers={"anthropic-workspace-id": workspace} if workspace else None
        )
        self.history: dict[int, deque] = defaultdict(lambda: deque(maxlen=HISTORY))
        # 모듈이 아니라 여기서 읽는다. bot.py가 load_dotenv()를 부른 뒤라야 .env가 보인다.
        self.model = os.getenv("PERSONA_MODEL") or DEFAULT_MODEL
        self.effort = os.getenv("PERSONA_EFFORT") or DEFAULT_EFFORT

    def addressed(self, message: discord.Message) -> bool:
        """나에게 건 말인지. 페르소나는 먼저 말을 걸지 않는다.

        이름은 문장 어디에 있든 부른 것으로 본다. '야 차라 이거 봐봐'처럼 앞에
        말이 붙는 쪽이 실제로 더 흔하다. 대신 이름을 입에 올리기만 해도 끼어들게
        되므로, 캐릭터 얘기를 자주 하는 채널이라면 좁힐 필요가 있다.
        """
        if self.bot.user in message.mentions:
            return True
        if self.bot.persona.name in message.content:
            return True
        ref = message.reference
        return bool(
            ref and getattr(ref.resolved, "author", None) == self.bot.user
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not self.addressed(message):
            return

        # 이름을 떼어내지 않고 그대로 넘긴다. '차라는 어때?'에서 이름만 빼면
        # '는 어때?'가 되어 뜻이 무너지는데, 발화를 '이름: 내용' 형태로 넘기고
        # 있어 그대로도 자연스러운 채팅 로그로 읽힌다.
        text = message.clean_content.strip()
        if not text:
            return

        history = self.history[message.channel.id]
        history.append({"role": "user", "content": f"{message.author.display_name}: {text}"})

        async with message.channel.typing():
            try:
                reply = await self.ask(list(history))
            except anthropic.APIError as error:
                # 이유를 디스코드에도 띄운다. 콘솔 로그를 뒤지지 않고 원인을 알 수 있다.
                logger.exception("Claude 호출 실패")
                history.pop()
                detail = f"{type(error).__name__}: {error}"[:REASON_LIMIT]
                await message.reply(
                    f"{self.bot.persona.line('error')}\n`{detail}`",
                    mention_author=False,
                )
                return

        history.append({"role": "assistant", "content": reply})
        await message.reply(
            self.bot.persona.decorate(reply)[:DISCORD_LIMIT], mention_author=False
        )

    async def ask(self, messages: list[dict]) -> str:
        persona = self.bot.persona
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            # 매 요청 동일한 앞부분이라 캐시된다. 마지막 안정 블록에 표시를 건다.
            system=[
                {"type": "text", "text": persona.system_prompt},
                {
                    "type": "text",
                    "text": OUTPUT_RULES,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            # 소넷 5에는 budget_tokens가 없다. 깊이는 effort로 조절한다.
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            messages=messages,
        )
        reply = "".join(b.text for b in response.content if b.type == "text").strip()
        # 발언을 '이름: 내용'으로 넘기다 보니 모델이 그 형식을 따라 할 때가 있다.
        # 하지 말라고 일러도 새므로 여기서 떼어낸다.
        return reply.removeprefix(f"{persona.name}:").lstrip()


async def setup(bot: commands.Bot):
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY가 없어 대화 기능을 건너뜁니다.")
        return
    cog = Chat(bot)
    await bot.add_cog(cog)
    logger.info("대화 기능: %s (effort=%s)", cog.model, cog.effort)
