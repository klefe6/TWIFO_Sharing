# Article Prompts

Single source of truth for article summarization prompts.

## Exports

- `PROMPT_VERSION` - string constant
- `SYSTEM_PROMPT` - system instructions
- `USER_PROMPT` - user prompt template (uses `<<<PLACEHOLDER>>>` for document text)
- `prompt_sha256()` - SHA256 hex of canonical prompt
- `prompt_source_file()` - path to this module

## Verify imports

From repo root (`TWIFO_Sharing`):

```bash
python -c "
from twifo_prompts.prompts.article_prompts import PROMPT_VERSION, SYSTEM_PROMPT, USER_PROMPT, prompt_sha256, prompt_source_file
assert PROMPT_VERSION == '1.0'
assert '<<<PLACEHOLDER>>>' in USER_PROMPT
h = prompt_sha256()
assert len(h) == 64 and all(c in '0123456789abcdef' for c in h)
print('OK: article_prompts imports verified')
"
```
