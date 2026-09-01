# Codeflow Review Loop Prompt

commit/push 없이 현재 작업의 구현, 리뷰, 리뷰 반영, 검증 단계만 Codeflow에 기록하고 싶을 때 사용합니다.

```text
codeflow로 이번 구현과 리뷰 루틴을 Codeflow에 기록해줘.

요청:
<여기에 구현 요청을 적습니다>

진행 방식:
- 독립적인 읽기 전용 탐색은 먼저 병렬화하고, Git 작업을 요청하지 않았으므로 구현 쓰기는 직렬화해줘.
- 관련 코드를 탐색하고 최소 범위로 구현해줘.
- 구현 단계가 끝나면 implementation 이벤트를 기록해줘.
- 구현 전 해당 단위의 수정 예정 파일을 스냅샷하고, Claude Code 자동 루프에서는
  결과 unit patch로 범위를 제한한 `codex review --uncommitted`로 Codex built-in reviewer를
  사용하고, 사용자가 직접 시작할 때만 `/codex:review --wait`를 사용해줘.
  없으면 별도 Claude reviewer를 사용해줘. Codex에서는 native `/review`로
  dedicated reviewer를 사용해줘. 일반 Codex 호출이나 구현
  agent의 자기검토로 대체하지 마. 기존 working tree 변경은 finding이나
  수정 대상으로 삼지 마.
- 리뷰 결과는 finding이 없어도 review 이벤트로 기록해줘.
- 리뷰 지적사항이 있으면 반영하고 review_fix 이벤트를 기록한 뒤 재리뷰해줘.
- 필요한 focused test, typecheck, 또는 build만 실행하고 verification 이벤트로 기록해줘.
- 모든 단위의 결과를 하나의 최종 보고서로 합성해줘.
- commit/push는 하지 마.
```
