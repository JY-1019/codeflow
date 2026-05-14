---
name: codeflow-light
description: |
  방금 LLM(나 자신 또는 Codex)이 코드를 수정한 직후, 그 수정에 대한 *내 응답
  텍스트* + *실제 git diff* 를 백엔드에 보내 노드·엣지 그래프로 시각화합니다.
  백엔드는 LLM을 호출하지 않으며, 응답 단락을 변경된 파일/심볼 노드에 매핑할
  뿐입니다. 결과는 http://localhost:5174 의 라이트 웹 앱에서 표시됩니다.

  TRIGGER:
  - 사용자가 "방금 한 변경 보여줘", "변경 그래프", "수정 시각화", "/codeflow-light"
    이라고 말할 때
  - 코드를 수정한 응답을 막 마쳤고 그 변경을 그래프로 보여주는 게 자연스러울 때
---

# Codeflow Light

`/api/changes`는 두 가지 입력으로 그래프를 만듭니다:

1. `project_root` — git 저장소 경로 (`$PWD` 또는 사용자가 지정한 경로)
2. `assistant_response` — *나(LLM)*가 방금 사용자에게 보낸 변경 설명 텍스트

백엔드는 LLM 키나 외부 API 호출이 필요 없습니다.

## 호출 절차

### 1. 백엔드 헬스 체크

```bash
curl -sf http://127.0.0.1:8019/api/health > /dev/null && echo ok || echo down
```

`down`이면 백그라운드로 띄웁니다.

```bash
cd ~/workspace/codeflow-light/backend && \
  (./venv/bin/python main.py > /tmp/codeflow-light-backend.log 2>&1 &)
```

### 2. 프론트엔드 헬스 체크

```bash
curl -sf http://127.0.0.1:5174 > /dev/null && echo ok || echo down
```

`down`이면:

```bash
cd ~/workspace/codeflow-light/frontend && \
  (npm run dev > /tmp/codeflow-light-frontend.log 2>&1 &)
```

### 3. `/api/changes` 호출

내가 직전에 사용자에게 보낸 변경 설명 텍스트를 `assistant_response`에 그대로
담아 보냅니다. (코드 펜스, 인라인 코드, 단락 구조 그대로 — response_mapper가
파일명·심볼명을 거기서 추출합니다.)

```bash
RESPONSE=$(cat <<'EOF'
<여기에 사용자에게 보낸 변경 설명 본문을 그대로 붙여넣기>
EOF
)

curl -s -X POST http://127.0.0.1:8019/api/changes \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg root "$PWD" --arg resp "$RESPONSE" '{project_root: $root, source: "working", assistant_response: $resp}')"
```

`jq`가 없다면 Python 한 줄로 안전하게 JSON 인코딩하세요.

### 4. 사용자에게 안내

응답을 분석한 뒤 이런 형식으로 안내합니다.

```
변경 그래프: http://localhost:5174
project_root: <위 경로> · 변경된 파일: N개 · 엣지: M개
(브라우저에서 같은 경로 입력 + 같은 응답 붙여넣기 + 분석 클릭으로도 동일 결과)
```

## 응답 텍스트 작성 팁 (매핑 품질 향상)

response_mapper는 단순 토큰 매칭으로 동작하므로 다음을 지키면 매핑이 정확해집니다.

- 파일은 인라인 코드로: `` `backend/app/routers/changes.py` ``
- 심볼은 인라인 코드로: `` `hello()` `` 또는 `` `ChangePage` ``
- 단락(빈 줄)으로 주제를 분리: 한 단락 = 한 노드 / 관계 설명
- 코드 펜스(``` ``` ```)는 그래프 매핑에서 제외되고 원본 응답 영역에만 표시됩니다.

## 주의

- `project_root`는 반드시 git 저장소 안.
- 백엔드는 127.0.0.1만 바인딩 (외부 노출 금지).
- 사용자에게 보내지 *않은* 내용을 `assistant_response`에 넣지 마세요. 매핑된 단락이
  실제 변경과 어긋나면 시각화가 거짓이 됩니다.
