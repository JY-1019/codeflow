# Markdown Branch Commit + Codeflow Prompt

Markdown 요구사항 문서를 하나씩 구현하고 로컬 커밋까지만 수행할 때 사용합니다. 원격 push와 main 통합은 수행하지 않습니다.

```text
markdown-branch-commit과 codeflow를 함께 사용해서 아래 폴더의 요구사항 문서를 하나씩 독립 구현 단위로 처리해줘.

요구사항 문서 폴더:
<REQUIREMENTS_FOLDER_PATH>

진행 방식:
- 각 요구사항 문서를 읽고 구현 범위와 제외 범위를 보수적으로 해석해줘.
- 요구사항 문서별로 독립 브랜치와 worktree를 생성해줘.
- 겹치지 않는 요구사항은 worktree별로 병렬 구현해줘.
- 관련 코드를 먼저 탐색한 뒤 최소 범위로 구현해줘.
- 요구사항 해석, 구현, 리뷰, 리뷰 반영, 검증, 커밋 단계를 Codeflow에 기록해줘.
- 구현 전 해당 단위의 수정 예정 파일을 스냅샷하고, Claude Code 자동 루프에서는
  결과 unit patch로 범위를 제한한 `codex review --uncommitted`로 Codex built-in reviewer를
  사용하고 사용자가 직접 시작할 때만 `/codex:review --wait`를 사용해줘.
  없으면 별도 Claude reviewer로 폴백해줘. Codex에서는 native `/review`의
  dedicated reviewer를 사용해줘. 다른 worktree나 기존 변경은 범위에서 제외해줘.
- 리뷰 지적사항이 있으면 반영하고 재리뷰해줘.
- 필요한 경우 focused test 또는 저비용 검증만 실행해줘.
- 요구사항 문서별 변경 파일만 커밋해줘.
- commit hook이 파일을 바꾸면 새 integration 단위로 리뷰와 검증을 반복해줘.
- 모든 worktree 결과를 하나의 최종 보고서로 합성해줘.
- push와 main 통합은 수행하지 마.
```
