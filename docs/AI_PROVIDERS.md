# AI translation provider feasibility

Evaluated on 2026-11-06. This is a feasibility assessment; version 2026.11.06.1 continues to use DeepL and does not send text to an AI agent.

| Route | Assessment |
| --- | --- |
| Existing Home Assistant AI Task entity | Recommended optional adapter: reuse the configured provider, explicitly choose its entity and request structured results through `ai_task.generate_data`. |
| Conversation agent | Possible, but a poor default for JSON translation: conversation history, free-form replies and potentially enabled home-control tools complicate a text-only task. |
| Direct cloud or local model API | Possible through another provider adapter, but requires credentials, model selection, retry handling and provider-specific usage reporting. A local backend also needs sufficient hardware. |

[AI Task](https://www.home-assistant.io/integrations/ai_task/) supports structured generation and selecting an entity. [Anthropic's Home Assistant integration](https://www.home-assistant.io/integrations/anthropic/) documents AI Task entities and structured outputs. These capabilities make an optional adapter feasible; they do not establish translation accuracy for a particular model. Availability must be detected at runtime so the current Core 2023.7 baseline remains usable with DeepL.

The proposed adapter would send selected phrases with stable IDs, source/target languages and protected markers. Source phrases must be treated as data, never as instructions to execute. The response must contain exactly the expected IDs, string values and unchanged marker multiplicities before any file is written. Show an editable preview before committing AI output. Recovery and original-file protection remain provider-independent. Generated-key metadata needs a provider identity instead of assuming every generated value is DeepL.

Reuse an explicitly selected text-generation task with no home-control tools or entity context. Batch sizes should follow the selected model's context limit. Do not fall back silently to another paid service after failure. AI billing needs provider-specific input/output token accounting; DeepL character quota must never be reused as an AI token or price estimate. If a provider exposes no account balance, display unknown.

A follow-up implementation should test malformed/missing/duplicate IDs, altered placeholders, prompt-like source phrases, interrupted requests, unsupported Core versions and both local and hosted providers using mocked responses before any optional paid quality evaluation.
