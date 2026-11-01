"""mini-swe-agent's model client, extended from one tool (`bash`) to our tool set.

Everything else is reused unchanged: the API call, retries and cost tracking. So the baseline
and our agent talk to the model in exactly the same way.
"""

import json

from jinja2 import StrictUndefined, Template
from minisweagent.exceptions import FormatError
from minisweagent.models.litellm_model import LitellmModel, LitellmModelConfig

from gated_agent.tools import TOOL_NAMES, TOOL_SCHEMAS

FORMAT_ERROR = (
    "Tool call error: {{error}}\n"
    "Every reply must call at least one tool, with JSON arguments. Available tools: {{tools}}."
)


class GatedModelConfig(LitellmModelConfig):
    format_error_template: str = FORMAT_ERROR
    observation_template: str = "{{ output.output }}"


class GatedModel(LitellmModel):
    def __init__(self, *, allowed_tools: set[str] | None = None, **kwargs):
        super().__init__(config_class=GatedModelConfig, **kwargs)
        self.allowed = allowed_tools or TOOL_NAMES
        self.schemas = [t for t in TOOL_SCHEMAS if t["function"]["name"] in self.allowed]

    def _query(self, messages, **kwargs):
        import litellm

        return litellm.completion(
            model=self.config.model_name, messages=messages, tools=self.schemas, **(self.config.model_kwargs | kwargs)
        )

    def _error(self, error: str, has_tool_calls: bool) -> FormatError:
        content = Template(self.config.format_error_template, undefined=StrictUndefined).render(
            error=error, tools=", ".join(sorted(self.allowed))
        )
        return FormatError({"role": "user", "content": content, "extra": {"interrupt_type": "FormatError"}})

    def _parse_actions(self, response) -> list[dict]:
        tool_calls = response.choices[0].message.tool_calls or []
        if not tool_calls:
            raise self._error("no tool call found in your reply.", False)
        actions = []
        for call in tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError as e:
                raise self._error(f"arguments for `{name}` are not valid JSON ({e}).", True) from e
            if name not in self.allowed:
                raise self._error(f"unknown tool `{name}`.", True)
            if not isinstance(args, dict):
                raise self._error(f"arguments for `{name}` must be a JSON object.", True)
            actions.append({"tool": name, "args": args, "tool_call_id": call.id, "command": f"{name} {json.dumps(args)[:2000]}"})
        return actions
