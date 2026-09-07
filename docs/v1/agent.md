# Agent

An `Agent` is a configured `harness` with a model running in a `Runtime`. It can be configured with an `AgentConfig`. An agent is given a `Task` and produces a `Trace`.

```python
async with vf.make_agent(vf.AgentConfig(model="z-ai/glm-5.2")) as solver:
    trace = await solver.run(vf.Task(vf.TaskData(prompt="What is 2+2?")))
```

`agent.interaction(task)` holds a rollout open turn by turn. The caller acts as the
user, and each `turn()` runs one harness segment (i.e., a message, tool call, tool result etc.). A `Segment` therefore contains messages, tool calls etc.

```python
async with agent.interaction(task) as interaction:
    segment = await interaction.turn("hello")
    if not segment.terminated:
        segment = await interaction.turn(f"you said: {segment.last_reply}")

trace = interaction.trace
```

## AgentENV runtime

Install the `agentenv` extra and set `E2B_API_KEY` for the AgentENV API. Configure `AgentEnvConfig(api_url="http://127.0.0.1:8000", snapshot="<immutable-snapshot-id>")` as the agent runtime. A task's `image` selects its snapshot, so world identity is included in task identity.

The framework clones the snapshot, runs the harness and colocated tool servers inside it, and kills the sandbox on success, failure, or cancellation. The runtime supports commands, detached processes, and file reads/writes. The snapshot must support the harness's Python/uv dependencies. Sandbox expiration is a crash backstop, not the episode lifecycle.

AgentENV is a remote runtime: configure the existing interception tunnel with an endpoint reachable from inside the VM. Colocated tools use guest loopback. No host-local URL is silently translated into a reachable address.

Remote tool installation accepts a Verifiers source checkout or a Git-pinned installation. Source checkouts are uploaded as source distributions; a Git installation installs that exact recorded commit in the sandbox. The environment tool-server package is uploaded from its local source tree.
