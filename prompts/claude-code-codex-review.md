# Claude Code Implementation + Codex Review Prompt

Claude Code에서 구현하고, Claude Code 안의 Codex review plugin이 리뷰하는 흐름을 Codeflow에 기록할 때 사용합니다.

```text
codeflow로 이번 변경을 구현하고 Codeflow에 기록해줘.

요청:
<여기에 구현 요청을 적습니다>

진행 방식:
- 구현 단계는 Claude Code가 수행한 것으로 기록해줘. implementation event에는 agent를 claude-code로 남겨줘.
- 구현 후 Claude Code 안의 Codex review plugin으로 리뷰를 실행해줘.
- 리뷰 단계는 Codex가 수행한 것으로 기록해줘. review event에는 agent를 codex로 남겨줘.
- 리뷰 finding이 없더라도 review event를 남겨줘.
- 리뷰 지적사항이 있으면 Claude Code가 반영하고 review_fix event에는 agent를 claude-code로 남겨줘.
- 반영 후 다시 Codex review plugin으로 재리뷰하고 review event에는 agent를 codex로 남겨줘.
- 필요한 focused test, typecheck, 또는 build만 실행하고 verification event를 기록해줘.
- commit/push는 하지 마.
```
