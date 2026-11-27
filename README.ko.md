[English](README.md) | **한국어**

# t3-lead

T3 Code에서 쓰는 계층형 오케스트레이션입니다. 사용자와 이야기하는 **리드** 세션이 요청을 **업무 확인 세션(verifier)** 에 맡기고, verifier가 일을 병렬 **레인(lane)** 으로 나눠 돌린 뒤 결과를 검증해 보고합니다.

```
사용자 ─ 리드              (사용자와 대화하는 스레드; Claude 하네스)
           └─ verifier     (요청 1건당 1개; Claude 하네스)
                 └─ 레인 × N   (병렬; Codex 또는 Claude 하네스)
```

역할별 행동 규칙은 브리프에 적지 않습니다. `UserPromptSubmit` 훅이 T3 메타데이터로 스레드의 역할을 판별해 해당 규칙을 넣어 주므로, 리드는 브리프에 규칙이나 신원을 쓸 필요가 없습니다.

## 빠른 시작: 에이전트에게 설치 맡기기

설치할 컴퓨터의 T3 Code 스레드(셸을 쓸 수 있는 Claude 또는 Codex 세션)에 아래를 그대로 붙여 넣으세요.

```text
이 컴퓨터에 t3-lead를 설치해줘. https://github.com/justice-hwan/t3-lead/blob/main/docs/agent-install.md 를 순서대로 따라 하고, 확인 단계 출력을 보여줘. 이 스레드를 리드로 등록하지는 마.
```

설치가 끝나면 에이전트가 알려 준 리드용 인스턴스와 모델로 **새 스레드**를 열고 이렇게 말하세요.

```text
t3lead init 하고 리드 모드로 일해
```

그다음부터는 그 스레드에 일을 맡기면 됩니다. 직접 설정하려면 [설정](#설정)과 [설치](#설치)를 보세요.

## 구성

```
install.sh                 여러 번 실행해도 안전한 설치/재적용 스크립트 (--dry-run 지원)
config.example.json        config.json 템플릿 (이 컴퓨터 전용 값; config.json은 추적 안 함)
lib/t3lead_config.py       install.sh, bin/t3lead, hooks/role.py가 함께 쓰는 설정 로더
bin/t3lead                 상태 CLI (요청 장부, 교훈, 리드 등록)
hooks/role.py              역할 판별 훅 (UserPromptSubmit)
rules/verifier.md          verifier 세션에 넣는 규칙 ({{자리표시자}}는 설정 값으로 채움)
rules/lane.md              레인에 넣는 규칙
skill/SKILL.md             리드용 스킬 (<skill_dir>/t3-lead로 링크)
docs/agent-install.md      에이전트가 따라 하는 단계별 설치 안내
skill/references/          브리프 형식(briefs.md), 모델과 인스턴스(models.md)
state/                     실행 중 데이터(추적 안 함): tasks/, roles/, lessons.jsonl, hook.log
```

## 역할 판별 훅이 동작하는 방식

`hooks/role.py`는 프롬프트마다 stdin으로 훅 이벤트를 받아 스레드의 역할을 정합니다.

- **스레드 ID**는 환경변수 `T3CODE_THREAD_ID`에서 읽습니다(Claude 하네스).
- **부모**는 다른 에이전트가 보낸 메시지 맨 앞에 T3가 붙이는 머리말에서 읽습니다: `[T3 Code: the agent in T3 thread "<부모>" sent this message, not the user.]`
- **역할**은 부모의 역할로 정합니다. 리드는 `t3lead init`으로 직접 등록하고, 리드의 자식은 `verifier`, verifier의 자식은 `lane`, lane의 자식도 `lane`입니다. 부모가 등록되어 있지 않으면 `unmanaged`로 보고, 훅은 아무것도 출력하지 않고 exit 0으로 끝납니다.
- 역할은 스레드의 첫 프롬프트에서 한 번 정해 `state/roles/`에 저장하고, 이후 프롬프트에도 같은 규칙을 넣습니다. 판정은 `state/hook.log`에 한 줄씩 남습니다.
- `verifier`와 `lane`에는 `rules/verifier.md` / `rules/lane.md`를 `additionalContext`로 출력합니다.

**Codex 하네스.** Codex app-server는 여러 스레드를 한 프로세스에서 돌리므로 `T3CODE_THREAD_ID`를 쓸 수 없습니다. 이 경우 훅은 기록 없이, 매 프롬프트의 머리말(보낸 스레드)만으로 판정합니다. 레인에는 이것으로 충분합니다. Codex 세션은 verifier를 맡지 않습니다(스레드 ID 없이는 자식이 부모를 찾을 수 없음). 그래서 역할이 `verifier`로 나오는 Codex 세션에는 아무것도 넣지 않습니다.

## 설정

이 컴퓨터 전용 값(경로, T3 provider 인스턴스 이름, 모델 이름)은 추적되지 않는 파일 하나, `config.json`에 둡니다. 템플릿을 복사해 고치세요.

```bash
cp config.example.json config.json
$EDITOR config.json
./install.sh --dry-run     # 무엇이 바뀔지만 출력, 아무것도 쓰지 않음
./install.sh
```

모든 키는 선택입니다. 경로 맨 앞의 `~`는 `$HOME`이 아니라 passwd에서 읽은 **실제** 홈을 뜻합니다(자체 `HOME`을 지정하는 래핑 세션에서는 `$HOME`이 다를 수 있음). `config.json`은 코드 옆에서 찾으며, 다른 파일을 쓰려면 `T3_LEAD_CONFIG`를 지정하세요.

| 키 | 기본값 | 뜻 |
|---|---|---|
| `real_home` | 현재 사용자의 passwd 홈 | 실제 홈. `~`와 아래 기본값의 기준 |
| `home` | `~/.t3-lead` | 저장소를 clone한 곳이자 `state/`가 있는 곳(`T3_LEAD_HOME`이 우선) |
| `claude_settings` | `["~/.claude/settings.json"]` | 훅을 넣을 Claude `settings.json`들 |
| `claude_wrapper` | 없음 | 수정할 Claude 래퍼 스크립트(선택, 설치 절 참고) |
| `codex_homes` | `["~/.codex"]` | 훅을 넣을 Codex 홈들(`CODEX_HOME`) |
| `codex_bin` | `~/.local/bin`과 `PATH`에서 찾은 `codex` | 훅 신뢰 해시를 읽는 데 쓰는 Codex 실행 파일 |
| `skill_dirs` | `["~/.claude/skills"]` | 스킬 폴더들. 각각에 `t3-lead`를 링크 |
| `cli_link` | `~/.local/bin/t3lead` | CLI 심볼릭 링크 위치 |
| `models` | 아래 참고 | 역할별 provider 인스턴스와 모델 |

`models`에는 `lead`, `verifier`, `claude_lane`, `light_lane`, `gpt_lane_refusal_prone`마다 `{"instance": "...", "model": "..."}`를 넣고, `gpt_lanes`에는 그런 쌍을 순서대로 나열합니다(첫 번째가 기본 GPT 레인). 키가 없을 때의 기본값은 `config.example.json`의 값, 곧 `claudeAgent`·`codex` 인스턴스와 그 파일에 적힌 모델 이름입니다. 인스턴스 이름은 쓰는 T3 환경에서 Claude·Codex provider 인스턴스를 부르는 이름으로 바꾸세요.

값이 쓰이는 방식: `rules/verifier.md`에는 `{{자리표시자}}`(`{{gpt_lanes}}`, `{{claude_lane}}`, `{{light_lane}}`)가 있고, `hooks/role.py`가 규칙을 넣을 때마다 설정 값으로 채웁니다. 그래서 설정을 바꾸면 다시 설치하지 않아도 다음 프롬프트부터 적용됩니다. 리드 스킬도 이름을 박아 두지 않고, 리드가 `t3lead models`를 실행해 보게 합니다.

## 설치

```bash
./install.sh
```

여러 번 실행해도 안전합니다. Claude·Codex 설정을 다시 쓰는 작업을 한 뒤에도 다시 실행하세요. 대상은 모두 `config.json`에서 읽습니다(설정 절 참고). `T3_LEAD_CODEX_BIN`은 더 이상 읽지 않으니 `codex_bin`을 쓰세요.

- `./install.sh --dry-run`은 각 단계가 무엇을 할지만 출력하고 아무것도 쓰지 않습니다.
- `T3_LEAD_HOME`을 설정된 `home`과 다른 값(예: 시험 실행용 임시 폴더)으로 주면, 스크립트는 사용자 전역 파일(Claude/Codex 훅, 스킬 링크, CLI 링크)을 **건드리지 않고** 그 폴더 아래에 `state/`만 만듭니다. 그래도 전역 변경을 적용하려면 `--allow-custom-home`을 붙이세요. 시험 실행 때문에 실제 링크가 나중에 지워질 폴더를 가리키게 되는 사고를 막기 위한 것입니다.

바꾸는 것(각 단계는 이미 적용되어 있으면 "already ..." 계열로 출력하고 아무것도 하지 않습니다):

1. **Claude 훅**: `claude_settings`의 각 파일에 `UserPromptSubmit` 명령 훅(timeout 10초)을 추가합니다.
2. **Claude 래퍼**(`claude_wrapper`를 지정했을 때만. 예: 제한된 환경으로 Claude를 띄우는 래퍼 스크립트): 환경변수 허용 목록에 `T3CODE_THREAD_ID`를 넣고, `--setting-sources`를 `''`에서 `user`로 바꿔 사용자 수준 훅이 로드되게 합니다.
3. **Codex 훅**: `codex_homes`의 폴더마다 `hooks.json`에 훅을 추가하고, `config.toml`에 `[features] hooks = true`를 설정하고, 훅의 신뢰 해시(`codex app-server`의 `hooks/list`로 읽음)를 `config.toml`에 등록합니다.
4. **링크와 폴더**: `skill_dirs`의 각 폴더에 `<skill_dir>/t3-lead` → `skill/`, `cli_link` → `bin/t3lead`를 만들고, `state/roles/`와 `state/tasks/`를 만듭니다.

**백업.** `settings.json`, `hooks.json`, `config.toml`을 처음 고치기 전에 `<파일>.bak-t3lead-YYYYMMDD`로 복사합니다(파일마다 하루에 한 번, 이미 있는 백업은 덮어쓰지 않음). `claude-wrapper` 수정은 백업 없이 그 자리에서 씁니다.

## `t3lead` CLI

```
t3lead init                                 이 스레드(T3CODE_THREAD_ID)를 리드로 등록
t3lead task add "<요청>" [--source S]       요청 기록, ID(t-xxxx) 출력
t3lead task move <id> <상태> [--note N] [--verifier THREAD]
        상태: open working waiting-owner delivered done dropped
t3lead task list [--all]                    끝나지 않은 요청(기본) / 전체
t3lead task show <id>                       요청 하나의 전체 JSON
t3lead learn "<한 줄 교훈>" [--kind K]      교훈 추가 (기본 kind: general)
t3lead lessons [--kind K]                   교훈 목록 (kind를 주면 general도 포함)
t3lead status                               재시작 때 읽는 짧은 요약
t3lead models                               설정 기준 역할별 provider 인스턴스와 모델
```

`open`, `working`, `waiting-owner`, `delivered`는 끝나지 않은 상태입니다. 사용자가 알게 되어야 끝난 것이므로 `delivered` → `done` 순서로 옮깁니다. 요청은 `state/tasks/<id>.json`, 교훈은 `state/lessons.jsonl`의 한 줄로 저장됩니다.

리드의 일반적인 흐름: `t3lead init`(처음 한 번) → `task add` → verifier에 맡김 → `task move <id> working --verifier <thread>` → 보고를 확인한 뒤 `task move <id> delivered` → 사용자에게 알림 → `task move <id> done`.

## 모델과 인스턴스

역할별 provider 인스턴스와 모델은 `config.json`의 `models`에서 오며(설정 절 참고), `t3lead models`가 실제 적용 값을 출력합니다. 역할은 리드, verifier(Claude 하네스여야 함), GPT 레인(기본 레인이 먼저, 그다음 대체 순서), Claude 레인, 가벼운 레인입니다. `config.example.json`의 기본값은 리드에 Claude Opus, verifier와 Claude 레인에 Claude Sonnet을 씁니다. 리드 브리프가 인스턴스와 모델을 따로 정하면 그것을 따릅니다. 역할별 용도, 이 선택의 근거가 된 측정(훅으로 규칙을 넣을 때와 브리프에 넣을 때의 비교), effort 지침은 `skill/references/models.md`에 있습니다.

## 알려진 제약

- **체크아웃 하나에 설정 하나.** `home`은 Claude/Codex 설정에 등록되는 훅 명령이 가리키는 경로이기도 합니다. 체크아웃을 옮기면 `home`을 바꾸고 `install.sh`를 다시 실행하세요. 옛 경로의 훅 항목은 "command differs from config"로 알려 주며 직접 고쳐야 합니다(명령이 바뀌면 Codex 신뢰 해시도 다시 등록해야 합니다).
- **Claude 래퍼 수정은 문자열 기반입니다.** 작성 당시의 정확한 코드 조각만 알아봅니다. 래퍼 모양이 다르면 스크립트가 알려 주며, 두 가지 변경을 직접 적용해야 합니다.
- **인스턴스·모델 이름은 검증하지 않습니다.** `config.json`의 이름이 틀리면 레인을 만들 때에야 드러납니다.
- **Codex 세션은 verifier를 맡지 않습니다.** 자기 스레드를 식별할 수 없어 레인으로만 동작합니다.
- **유실된 완료 알림은 재전달되지 않습니다.** 리드는 완료 알림으로 깨어납니다. 알림이 유실되면 다시 보내 주는 장치가 없습니다. 재시작 뒤에는 `t3lead status`로 아직 `working`인 요청을 찾아야 합니다.
