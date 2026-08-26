# Discord 유틸리티 봇

discord.py 기반의 기본 유틸리티 디스코드 봇입니다.

## 기능

- `/ping` - 봇 응답 속도 확인
- `/userinfo [member]` - 유저 정보 확인
- `/serverinfo` - 서버 정보 확인
- `/avatar [member]` - 유저 아바타 확인
- `/clear <amount>` - 메시지 일괄 삭제 (메시지 관리 권한 필요)

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

   ```
   DISCORD_TOKEN=여기에_봇_토큰_입력
   ```

5. 봇을 실행합니다.

   ```bash
   python bot.py
   ```

## 구조

```
bot.py            # 봇 진입점, cogs 자동 로드
cogs/
  utility.py      # 유틸리티 슬래시 명령어
.env.example      # 환경 변수 템플릿
requirements.txt  # 의존성 목록
```

새 기능은 `cogs/` 아래에 새 파일을 추가하면 자동으로 로드됩니다.
