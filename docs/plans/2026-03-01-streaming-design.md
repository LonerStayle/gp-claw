# 토큰 스트리밍 설계

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** LLM 응답을 토큰 단위로 실시간 스트리밍하여 ChatGPT 같은 UX 제공.

**Approach:** LangGraph `astream_events` + `<tool_call>` 태그 버퍼링.

---

## 설계

### 흐름

```
agent.astream_events()
  → on_chat_model_stream 이벤트 (토큰 청크)
    → 일반 텍스트 → WebSocket assistant_chunk 즉시 전송
    → "<tool_call" 감지 → 버퍼링 시작, 전송 중단
  → agent 노드 완료
    → tool_calls 있으면 → approval/safe 라우팅 (기존 로직)
    → tool_calls 없으면 → assistant_done 전송
```

### 프로토콜 확장

```json
// 새로 추가
{"type": "assistant_chunk", "content": "안녕"}
{"type": "assistant_done"}
```

기존 `assistant_message`는 제거하고 `assistant_chunk` + `assistant_done`으로 대체.

### 버퍼링 로직

토큰 스트리밍 중 `<tool_call` 문자열이 감지되면:
1. 해당 시점부터 스트리밍 중단 (프론트엔드로 전송 안 함)
2. 나머지 토큰은 내부 버퍼에 축적
3. 전체 응답 완료 후 `_parse_tool_calls()`로 도구 파싱
4. 도구 호출이 있으면 approval/safe 라우팅

---

## 구현 계획

### Task 1: 백엔드 — server.py 스트리밍 전환

**Files:**
- Modify: `src/gp_claw/server.py`

**Step 1: `ainvoke` → `astream_events` 전환 + 버퍼링**

`websocket_endpoint`의 `user_message` 핸들러를 스트리밍으로 변경:

```python
# 기존: result = await session_agent.ainvoke(...)
# 변경: async for event in session_agent.astream_events(...):

buffer = ""
tool_call_detected = False

async for event in session_agent.astream_events(
    {"messages": [HumanMessage(content=content)]},
    config,
    version="v2",
):
    if event["event"] == "on_chat_model_stream":
        chunk = event["data"]["chunk"]
        if hasattr(chunk, "content") and chunk.content:
            token = chunk.content
            buffer += token
            if not tool_call_detected:
                if "<tool_call" in buffer:
                    tool_call_detected = True
                else:
                    await websocket.send_json({
                        "type": "assistant_chunk",
                        "content": token,
                    })
```

**Step 2: 스트리밍 완료 후 처리**

이벤트 루프 종료 후:
- interrupt 상태 확인 → approval_request 전송 (기존 로직 유지)
- tool_calls 없으면 → `assistant_done` 전송

**Step 3: Commit**

```bash
git add src/gp_claw/server.py
git commit -m "feat: LLM 응답 토큰 스트리밍 (astream_events)"
```

---

### Task 2: 프론트엔드 — 타입 + useWebSocket 스트리밍 처리

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/hooks/useWebSocket.ts`

**Step 1: 타입 확장**

```typescript
// WsReceive에 추가
| { type: "assistant_chunk"; content: string }
| { type: "assistant_done" }
```

**Step 2: useWebSocket 스트리밍 메시지 처리**

- `assistant_chunk`: 현재 assistant 메시지에 텍스트 누적 (없으면 새 메시지 생성)
- `assistant_done`: 스트리밍 완료, isWaitingResponse 해제
- 기존 `assistant_message`는 fallback으로 유지 (호환성)

```typescript
case "assistant_chunk":
  setMessages(prev => {
    const last = prev[prev.length - 1]
    if (last?.type === "assistant") {
      return [...prev.slice(0, -1), { ...last, content: last.content + data.content }]
    }
    return [...prev, { id: crypto.randomUUID(), type: "assistant", content: data.content }]
  })
  break

case "assistant_done":
  setIsWaitingResponse(false)
  setIsWaitingApproval(false)
  break
```

**Step 3: Commit**

```bash
git add frontend/src/types.ts frontend/src/hooks/useWebSocket.ts
git commit -m "feat: 프론트엔드 토큰 스트리밍 수신 처리"
```

---

### Task 3: 빌드 검증 + 수동 테스트

**Step 1: Backend 테스트**

```bash
python -m pytest tests/ -q
```

**Step 2: Frontend 빌드**

```bash
cd frontend && npm run build
```

**Step 3: Commit**

최종 검증 후 필요시 수정사항 커밋.
