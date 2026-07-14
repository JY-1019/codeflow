# Markdown Branch Commit + Codeflow Light Prompt

Markdown 요구사항 문서를 하나씩 구현하고 로컬 커밋까지만 수행할 때 사용합니다. 원격 push와 main 통합은 수행하지 않습니다.

```text
markdown-branch-commit과 codeflow-light를 함께 사용해서 아래 폴더의 요구사항 문서를 하나씩 독립 구현 단위로 처리해줘.

요구사항 문서 폴더:
<REQUIREMENTS_FOLDER_PATH>

진행 방식:
- 각 요구사항 문서를 읽고 구현 범위와 제외 범위를 보수적으로 해석해줘.
- 요구사항 문서별로 독립 브랜치를 생성해줘.
- 관련 코드를 먼저 탐색한 뒤 최소 범위로 구현해줘.
- 요구사항 해석, 구현, 리뷰, 리뷰 반영, 검증, 커밋 단계를 Codeflow Light에 기록해줘.
- 구현 후 Codex review를 품질 게이트로 수행해줘.
- 리뷰 지적사항이 있으면 반영하고 재리뷰해줘.
- 필요한 경우 focused test 또는 저비용 검증만 실행해줘.
- 요구사항 문서별 변경 파일만 커밋해줘.
- push와 main 통합은 수행하지 마.
```

리뷰 프롬프트:

```text
Review correctness, edge cases, public API compatibility, maintainability, cohesion, naming, abstraction boundaries, unnecessary coupling, and whether the code design is easy to evolve.
```
