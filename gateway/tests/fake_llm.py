"""A fake OpenAI-compatible chat server for testing the agent. Usage: python tests/fake_llm.py <port>

It is scripted by keywords in the user's message, and it records what it was sent so the
test can check that no credentials ever reach the language model.
  "echo"  -> asks for alpha__echo, then summarises the tool result
  "bad"   -> asks for a tool that does not exist
  "args"  -> asks for a tool with invalid JSON arguments
  "loop"  -> asks for a tool every time (never finishes)
  other   -> plain answer, no tool
"""
import json
import sys

import uvicorn
from fastapi import FastAPI, Header, Request

app = FastAPI()
seen: list[dict] = []


def tool_call(name: str, arguments: str) -> dict:
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": name, "arguments": arguments}}]}


@app.post("/v1/chat/completions")
async def completions(request: Request, authorization: str = Header(default="")):
    body = await request.json()
    seen.append({"auth": authorization, "raw": json.dumps(body), "tools": [t["function"]["name"] for t in body.get("tools", [])]})
    messages = body["messages"]
    last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
    tool_results = [m for m in messages if m["role"] == "tool"]
    if "loop" in last_user:
        reply = tool_call("alpha__echo", json.dumps({"text": "again"}))
    elif tool_results:
        reply = {"role": "assistant", "content": "Tool said: " + tool_results[-1]["content"]}
    elif "echo" in last_user:
        reply = tool_call("alpha__echo", json.dumps({"text": "hello"}))
    elif "bad" in last_user:
        reply = tool_call("nope__missing", "{}")
    elif "args" in last_user:
        reply = tool_call("alpha__echo", "this is not json")
    else:
        reply = {"role": "assistant", "content": "Plain answer."}
    return {"choices": [{"index": 0, "message": reply}]}


@app.get("/_seen")
async def get_seen():
    return seen


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")