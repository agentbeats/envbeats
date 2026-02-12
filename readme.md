# EnvBeats

This is an example repo demonstrating integration between OpenEnv and AgentBeats.

## How to run

1. Start MCP-X (at 9000 by default):

```bash
cd mcp-x
uv run python mcp_x.py
```

2. Start the assessor agent (at 9999 by default):

```bash
cd eb_assessor
uv run python main.py
```

3. Start the assessee agent (at 9990 by default):

```bash
# remember to config the `.env` file first to include the key
cd eb_assessee_pure_mcp/a2a-mcp-without-framework
uv run --env-file ../.env python -m src.no_llm_framework.server.__main__ --port 9990
```
or

```bash
# remember to run `npx @modelcontextprotocol/inspector` first to install the inspector for MCP debugging
cd eb_assessee_human
uv run python main.py
```

4. Kickoff the evaluation

```bash
cd eb_kickoff
uv run python main.py
```

## Workflow

- Env init message (from `reset()`) is passed to the assessee in the task instruction message.
- Assessee agent is provided with OpenEnv interfaces as MCPs (`state()`, `step()`).

## Future work

This could be generic for any OpenEnv environment (without Python type enforcement).
