# Codeflow Prompt Examples

이 폴더는 Codeflow의 기본 오케스트레이션에 요청과 원하는 Git 결과를
명시할 때 쓰는 portable 프롬프트 예시입니다. 구현, 리뷰, 재리뷰, 검증,
병렬화, 최종 합성은 Skill의 기본 동작이므로 매번 반복해서 적을 필요가
없습니다.

Codeflow는 DMG/EXE를 자동 설치하지 않습니다. 먼저 데스크탑 앱을 설치하고, Codex 또는 Claude Code에서 plugin/Skill이 로드된 상태에서 사용하세요.

## Files

- [`codeflow-review-loop.md`](codeflow-review-loop.md): commit/push 없이 구현, 리뷰, 리뷰 반영, 검증만 기록하는 기본 예시입니다.
- [`claude-code-codex-review.md`](claude-code-codex-review.md): Claude Code가 구현하고 Codex built-in reviewer를 우선 사용하되 Claude reviewer로 폴백하는 예시입니다.
- [`markdown-branch-commit.md`](markdown-branch-commit.md): Markdown 요구사항 폴더를 읽고 문서별 로컬 커밋까지 수행하는 예시입니다.
- [`markdown-branch-push.md`](markdown-branch-push.md): Markdown 요구사항 폴더를 읽고 push/merge까지 수행하는 예시입니다.

## Invocation Notes

Codex와 Claude Code는 요청의 의미로 Codeflow를 자동 선택할 수 있습니다.
자동 Skill 라우팅은 모든 임의 프롬프트에서 보장되지 않으므로 확실히
활성화하려면 Codex에서 `$codeflow`, Claude Code에서
`/codeflow:codeflow`를 사용하세요.

```text
codeflow로 이번 변경을 구현하고 Codeflow에 기록해줘.
```

작업 중 commit/push를 원하지 않으면 프롬프트에 명시하세요.

```text
검증까지 기록하고 commit/push는 하지 마.
```
