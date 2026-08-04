# Codeflow Review Loop Prompt

commit/push 없이 현재 작업의 구현, 리뷰, 리뷰 반영, 검증 단계만 Codeflow에 기록하고 싶을 때 사용합니다.

```text
codeflow로 이번 구현과 리뷰 루틴을 Codeflow에 기록해줘.

요청:
<여기에 구현 요청을 적습니다>

진행 방식:
- 관련 코드를 먼저 탐색하고 최소 범위로 구현해줘.
- 구현 단계가 끝나면 implementation 이벤트를 기록해줘.
- 구현 후 Codex review를 품질 게이트로 실행해줘.
- 리뷰 결과는 finding이 없어도 review 이벤트로 기록해줘.
- 리뷰 지적사항이 있으면 반영하고 review_fix 이벤트를 기록한 뒤 재리뷰해줘.
- 필요한 focused test, typecheck, 또는 build만 실행하고 verification 이벤트로 기록해줘.
- commit/push는 하지 마.
```

리뷰 프롬프트로는 다음 기준을 사용할 수 있습니다.

```text
Review correctness, edge cases, public API compatibility, maintainability, cohesion, naming, abstraction boundaries, unnecessary coupling, and whether the code design is easy to evolve.
```
