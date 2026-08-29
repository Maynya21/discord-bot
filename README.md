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

## 대화 기능

`ANTHROPIC_API_KEY`가 있으면 페르소나로 대화합니다. 키가 없으면 이 기능만 조용히
꺼지고 슬래시 명령어는 그대로 동작합니다.

말을 거는 방법은 세 가지입니다. 멘션(`@차라`), 이름으로 시작하는 메시지
(`차라 오늘 힘들었어`), 봇 메시지에 답장. 그 외 대화에는 끼어들지 않습니다 —
페르소나 문서의 "먼저 말 걸지 않는다"를 그대로 옮긴 것입니다.

```
ANTHROPIC_API_KEY=sk-ant-...
PERSONA_MODEL=claude-sonnet-5
PERSONA_EFFORT=low
```

`PERSONA_EFFORT`는 생각의 깊이입니다 (`low`|`medium`|`high`|`xhigh`|`max`).
대화는 낮은 쪽이 어울리고 저렴합니다. 코딩이나 장기 에이전트 작업과 달리 대화는
높은 effort가 값을 하지 않습니다. `budget_tokens`(생각 토큰 예산)는 이 모델들에서
제거됐으므로 깊이는 `effort`로만 조절합니다.

채널마다 최근 대화 12개를 기억하고, 봇을 껐다 켜면 잊습니다.

### 시스템 프롬프트

`personas/<key>.md` 전문이 그대로 넘어갑니다. 디스코드에서 필요한 출력 규칙
(길이, 마크다운 자제 등)은 문서를 고치지 않고 `cogs/chat.py`의 `OUTPUT_RULES`에서
덧붙입니다. 페르소나 문서는 캐릭터 설정만 담고, 매체 규칙은 코드가 담당합니다.
시스템 프롬프트는 매 요청 동일해서 캐시됩니다.

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

### 서술자 목소리 표시 방식

대사에서 `* `로 시작하는 줄은 서술자 목소리입니다. 원문에는 표기를 그대로 두고,
디스코드로 보낼 때 `narrator_style`에 따라 변환됩니다. 이 변환이 없으면 `* `가
디스코드 마크다운의 글머리 기호로 해석되어 목록처럼 보입니다.

```python
PERSONA = Persona(
    ...,
    narrator_style="italic",   # "italic" | "ansi" | "plain"
    narrator_color="red",      # narrator_style="ansi"일 때만 사용
)
```

| 값 | 결과 | PC | 모바일 |
|---|---|---|---|
| `italic` | `*기울임*` — 본문 흐름 유지 | ✅ | ✅ |
| `ansi` | ANSI 코드블록으로 색 지정 | ✅ | ⚠️ 색 없이 코드블록으로만 |
| `plain` | 표기만 제거 | ✅ | ✅ |

디스코드는 일반 메시지에서 글자 색을 지원하지 않습니다. `ansi`는 코드블록 안에서만
색이 나오는 우회 방법이라 고정폭 글꼴과 테두리가 따라붙고, 코드블록 안에서는 다른
마크다운이 동작하지 않습니다. 색과 기울임은 동시에 쓸 수 없습니다.

`ansi`는 손으로 확인할 수 없다는 점도 알아두세요. 색을 켜는 것은 `\x1b`(ESC)라는
보이지 않는 제어 문자인데, 이 문자는 타이핑도 복사·붙여넣기도 되지 않습니다.
어딘가에서 복사한 ANSI 블록을 디스코드에 붙여넣으면 ESC가 빠져 색이 나오지 않습니다.
봇이 직접 보낼 때만 제대로 동작하므로, 확인하려면 봇을 실행해야 합니다.

### 색상

모든 응답은 임베드로 나갑니다. 임베드 왼쪽 색 띠가 디스코드에서 기기를 가리지 않고
색을 넣을 수 있는 유일한 자리이기 때문입니다. ESC 문자도, 코드블록도 필요 없고
모바일에서도 그대로 보입니다.

색은 두 개입니다.

```python
PERSONA = Persona(
    ...,
    color=0xBFBFBF,          # 평상시
    accent_color=0x9E1B1B,   # 무거운 대사. None이면 색을 나누지 않음
    accent_keys=frozenset(), # 내용과 무관하게 항상 강조색을 쓸 대사 키
)
```

**서술자 목소리(`* `)가 섞인 대사만 강조색으로 나갑니다.** 서술자 줄은 원래 아껴 쓰는
장치라, 색을 따로 관리하지 않아도 강조 빈도가 자동으로 따라옵니다. 빨강이 너무 자주
보이면 해당 대사 키에 서술자 없는 변형을 더 넣으면 되고, 반대로 특정 명령어를 항상
강조하고 싶으면 `accent_keys`에 키를 넣으면 됩니다.

차라의 색 배분은 원작을 따랐습니다. 언더테일 기본 텍스트는 흰색이고 빨강은 드물게
쓰이는 강조였습니다. 흔히 떠올리는 빨강은 빨간 SOUL에서 온 팬덤 관습에 가깝습니다.

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
  chara.md          # 차라 - 설정 문서 (대화 기능의 시스템 프롬프트)
cogs/
  utility.py        # 유틸리티 슬래시 명령어
  chat.py           # 페르소나 대화 (ANTHROPIC_API_KEY 필요)
```

`cogs/` 아래에 파일을 추가하면 자동으로 로드됩니다.
