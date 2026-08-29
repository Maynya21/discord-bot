# Discord 페르소나 봇

discord.py 기반 디스코드 봇. 캐릭터 페르소나를 갈아끼울 수 있는 구조입니다.

## 기능

- `/ping` - 봇 응답 속도 확인
- `/userinfo [member]` - 유저 정보 확인
- `/serverinfo` - 서버 정보 확인
- `/avatar [member]` - 유저 아바타 확인
- `/clear [amount]` - 이 채널에 내가 남긴 메시지 삭제 (기본 50개 범위)

`/clear`는 자기가 쓴 메시지만 지웁니다. `amount`는 지울 개수가 아니라 거슬러
올라가며 훑어볼 범위이고, 그중 실행한 사람이 쓴 것만 삭제됩니다. 쓰는 사람에게
권한은 필요 없지만, 봇에게는 `메시지 관리` 권한이 있어야 합니다.

모든 응답 문구는 페르소나에서 나옵니다. 사실 정보(멤버 수, 날짜 등)는 임베드 필드에
그대로 두고, 페르소나는 그 위에 얹히는 말투만 담당합니다.

## 설치 및 실행

1. 파이썬 3.10 이상을 준비합니다.
2. 의존성을 설치합니다.

   ```bash
   pip install -r requirements.txt
   ```

3. [Discord Developer Portal](https://discord.com/developers/applications)에서 애플리케이션과 봇을 생성하고 토큰을 발급받습니다.
   - Bot 탭에서 `MESSAGE CONTENT INTENT`와 `SERVER MEMBERS INTENT`를 활성화하세요.
   - OAuth2 > URL Generator에서 `bot`, `applications.commands` 스코프와 필요한 권한을 선택해 초대 링크를 생성합니다.

4. `.env.example`을 `.env`로 복사하고 토큰을 입력합니다.

   ```bash
   cp .env.example .env
   ```

5. 봇을 실행합니다.

   ```bash
   python bot.py
   ```

## 페르소나

`.env`의 `PERSONA=` 한 줄로 봇 전체 말투가 바뀝니다.

```
PERSONA=chara
```

명령어 코드는 어떤 캐릭터인지 전혀 모릅니다. `persona.line("ping", latency=89)`처럼
키만 넘기고 문구는 페르소나가 결정합니다.

### 페르소나 한 개의 구성

| 파일 | 내용 |
|---|---|
| `personas/<key>.py` | 고정 대사 (`LINES`)와 `PERSONA` 인스턴스. API 키 불필요. |
| `personas/<key>.md` | 캐릭터 설정 문서. AI 대화 기능의 시스템 프롬프트로 쓰입니다. |

`LINES`의 각 키는 후보 목록을 가지고, 호출할 때마다 그중 하나가 무작위로 선택됩니다.
같은 명령어를 반복해도 문구가 조금씩 달라집니다.

### 새 페르소나 추가하기

1. `personas/newkey.py`에 `LINES`와 `PERSONA`를 정의합니다 (`personas/chara.py` 참고).
2. 설정 문서가 필요하면 `personas/newkey.md`를 만들고 `prompt_file="newkey.md"`로 연결합니다.
3. `.env`에서 `PERSONA=newkey`로 바꿉니다.

기존 페르소나가 가진 대사 키를 모두 채워야 합니다. 빠진 키는 호출 시 `KeyError`로
바로 드러납니다.

### 톤 조정

말투가 어긋날 때는 규칙 문장을 고치기보다 `personas/<key>.md`의 `## 예시 모음`에
원하는 톤의 대화를 한두 개 추가하는 쪽이 잘 먹힙니다.

## 구조

```
bot.py              # 진입점. 페르소나를 읽어 bot.persona에 붙이고 cogs를 로드
personas/
  __init__.py       # load_persona()
  base.py           # Persona 자료구조
  chara.py          # 차라 - 고정 대사
  chara.md          # 차라 - 설정 문서 (AI 대화용 시스템 프롬프트)
cogs/
  utility.py        # 유틸리티 슬래시 명령어
```

`cogs/` 아래에 파일을 추가하면 자동으로 로드됩니다.
