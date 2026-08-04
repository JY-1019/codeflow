# Codeflow Prompt Examples

이 폴더는 Codeflow를 작업 요청에 함께 호출할 때 쓰는 portable 프롬프트 예시입니다. 예시는 로컬 절대경로를 포함하지 않으므로 Codex, Claude Code, 플러그인 설치 환경에 맞게 그대로 복사해 조정할 수 있습니다.

Codeflow는 DMG/EXE를 자동 설치하지 않습니다. 먼저 데스크탑 앱을 설치하고, Codex 또는 Claude Code에서 plugin/Skill이 로드된 상태에서 사용하세요.

## Files

- [`codeflow-review-loop.md`](codeflow-review-loop.md): commit/push 없이 구현, 리뷰, 리뷰 반영, 검증만 기록하는 기본 예시입니다.
- [`claude-code-codex-review.md`](claude-code-codex-review.md): Claude Code가 구현하고 Claude Code 안의 Codex review plugin이 리뷰하는 cross-tool 예시입니다.
- [`markdown-branch-commit.md`](markdown-branch-commit.md): Markdown 요구사항 폴더를 읽고 문서별 로컬 커밋까지 수행하는 예시입니다.
- [`markdown-branch-push.md`](markdown-branch-push.md): Markdown 요구사항 폴더를 읽고 push/merge까지 수행하는 예시입니다.

## Invocation Notes

Codex에서는 자연어로 `codeflow`를 명시하거나 설치된 skill/plugin 호출 방식을 사용하세요.

Claude Code 플러그인으로 로드된 경우 작업 요청에 `codeflow`를 명시하세요.

```text
codeflow로 이번 변경을 구현하고 Codeflow에 기록해줘.
```

작업 중 commit/push를 원하지 않으면 프롬프트에 명시하세요.

```text
검증까지 기록하고 commit/push는 하지 마.
```
