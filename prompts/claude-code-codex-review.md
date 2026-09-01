# Claude Code Implementation + Codex Review Prompt

Claude Code에서 구현하고 Codex review를 우선 사용하되, 사용할 수 없으면
Claude 내부 reviewer로 폴백하는 흐름을 Codeflow에 기록할 때 사용합니다.

```text
codeflow로 이번 변경을 구현하고 Codeflow에 기록해줘.

요청:
<여기에 구현 요청을 적습니다>

진행 방식:
- 구현 단계는 Claude Code가 수행한 것으로 기록해줘. implementation event에는 agent를 claude-code로 남겨줘.
- 구현 전 해당 단위의 수정 예정 파일을 스냅샷하고, 자동 루프에서는 결과 unit patch로
  범위를 제한한 `codex review --uncommitted`로 Codex의 dedicated reviewer를
  실행해줘. `/codex:review --wait`는 사용자가 직접 리뷰를 시작할 때만
  사용해줘. 일반 Codex 프롬프트나 `codex exec`로 대체하지 마. 사용할 수
  없으면 별도 Claude reviewer context로 폴백해줘. 기존 working tree 변경은
  finding이나 수정 대상으로 삼지 마.
- review event에는 실제 reviewer에 따라 agent를 codex 또는 claude-code로 남겨줘.
- 리뷰 finding이 없더라도 review event를 남겨줘.
- 리뷰 지적사항이 있으면 Claude Code가 반영하고 review_fix event에는 agent를 claude-code로 남겨줘.
- 반영 후 같은 reviewer 경로로 재리뷰해줘.
- 필요한 focused test, typecheck, 또는 build만 실행하고 verification event를 기록해줘.
- 독립적인 읽기 전용 탐색만 먼저 병렬화하고 구현 쓰기는 직렬화해줘.
  마지막 응답은 하나로 합성해줘.
- commit/push는 하지 마.
```
