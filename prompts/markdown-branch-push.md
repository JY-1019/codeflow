# Markdown Branch Push + Codeflow Prompt

Markdown 요구사항 문서를 하나씩 구현하고 브랜치 push, main 통합, main push까지 수행할 때 사용합니다.

```text
markdown-branch-push와 codeflow를 함께 사용해서 아래 폴더의 요구사항 문서를 하나씩 독립 구현 단위로 처리하고, 각 구현을 main까지 반영해줘.

요구사항 문서 폴더:
<REQUIREMENTS_FOLDER_PATH>

진행 방식:
- 각 요구사항 문서를 읽고 구현 범위와 제외 범위를 보수적으로 해석해줘.
- 요구사항 문서별로 독립 브랜치와 worktree를 생성해줘.
- 겹치지 않는 요구사항은 worktree별로 병렬 구현해줘.
- 관련 코드를 먼저 탐색한 뒤 최소 범위로 구현해줘.
- 요구사항 해석, 구현, 리뷰, 리뷰 반영, 검증, 커밋, push, merge 단계를 Codeflow에 기록해줘.
- 구현 전 해당 단위의 수정 예정 파일을 스냅샷하고, Claude Code 자동 루프에서는
  결과 unit patch로 범위를 제한한 `codex review --uncommitted`로 Codex built-in reviewer를
  사용하고 사용자가 직접 시작할 때만 `/codex:review --wait`를 사용해줘.
  없으면 별도 Claude reviewer로 폴백해줘. Codex에서는 native `/review`의
  dedicated reviewer를 사용해줘. 다른 worktree나 기존 변경은 범위에서 제외해줘.
- 리뷰 지적사항이 있으면 반영하고 재리뷰해줘.
- 필요한 경우 focused test 또는 저비용 검증만 실행해줘.
- 요구사항 문서별 변경 파일만 커밋해줘.
- 브랜치를 push하고, main 통합과 main push까지 수행해줘.
- main 통합은 직렬화해서 충돌과 원격 변경을 안전하게 처리해줘.
- 충돌 해결, hook, 원격 변경 대응으로 파일이 바뀌면 새 integration 단위로
  구현 기록, 리뷰, 검증을 다시 수행한 뒤 push해줘.
- 모든 worktree 결과를 하나의 최종 보고서로 합성해줘.
```
