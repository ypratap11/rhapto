# Rhapto Stage 1: Engine and CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Rhapto tailoring engine (extract, select, compose, validate, repair, render) as a pure Python library plus a `rhapto tailor` CLI that turns a job description and a YAML profile into a guardrail-checked resume package.

**Architecture:** One uv project at `apps/api` containing the `rhapto` package. `rhapto.engine` is a pure pipeline that only depends on generated Pydantic models and on provider interfaces (LLM, embeddings) passed in as arguments, so every engine test runs with fakes and no network. `rhapto.profile` loads YAML into the engine's `Profile` type. `rhapto.cli` wires real providers (Anthropic, fastembed) and writes the output folder. JSON Schemas in `packages/schemas` are the source of truth and Pydantic models are generated from them.

**Tech Stack:** Python 3.12, uv, Pydantic v2, pydantic-settings, anthropic SDK, fastembed, python-docx, LibreOffice (PDF), PyYAML, Typer, rapidfuzz, pytest, pytest-asyncio, ruff, mypy strict, datamodel-code-generator, import-linter.

**Spec:** `docs/superpowers/specs/2026-09-09-rhapto-architecture-design.md` (sections 2, 3, 4, 5, 11, and stage 1 of section 12).

## Global Constraints

- Python `>=3.12`; dependencies managed with `uv`; run all Python commands from `apps/api` as `uv run ...`.
- `rhapto.engine` must never import `rhapto.profile`, `rhapto.db`, `rhapto.api`, `rhapto.worker`, or `rhapto.cli` (import-linter contract, Task 17).
- Maximum 3 LLM calls per tailoring run, enforced by `CallBudget` in `rhapto/engine/pipeline.py`.
- Every bullet and entry in a `ResumeDocument` carries a `source_block_id`; the renderer raises `OrphanBulletError` on any id not in the block library.
- Every number in output must trace to a block with `verified: true` (`no-unverified-metrics` rule).
- Never copy content from `profile/` into code, tests, fixtures, or docs. Tests use `profile.example/` only.
- Generated models live in `apps/api/src/rhapto/models/` and are never hand-edited; fix the JSON Schema and regenerate.
- ruff (`E,F,I,UP,B`, line length 100) and `mypy --strict` must pass before every commit.
- Default LLM model id: `claude-sonnet-5`. Default embedding model: `BAAI/bge-small-en-v1.5` (384 dimensions).
- License: AGPL-3.0-only.
- Commit messages end with the two attribution lines given in the session (Co-Authored-By and Claude-Session).

## File Structure

```
rhapto-starter/                               (repo root)
├── LICENSE                                   AGPL-3.0 text
├── .gitignore                                extended
├── .env.example                              documented env keys
├── scripts/
│   ├── codegen.sh                            JSON Schema -> Pydantic
│   └── check-no-personal-data.py             fails if real profile org names leak into tracked files
├── packages/schemas/
│   ├── profile/{blocks,tracks,bases,guardrails,answers,watchlist}.json
│   ├── jd_extract.json
│   ├── resume_document.json
│   ├── guardrail_report.json
│   └── package.json
├── profile.example/
│   ├── answers.yaml                          add name/email/phone (fictional)
│   └── blocks.yaml                           mark acme-data-pm verified
└── apps/api/
    ├── pyproject.toml
    ├── uv.lock
    ├── Dockerfile                            targets base, cli
    ├── .importlinter
    ├── src/rhapto/
    │   ├── __init__.py
    │   ├── config.py                         Settings (pydantic-settings)
    │   ├── models/                           GENERATED (Task 2)
    │   ├── engine/
    │   │   ├── __init__.py
    │   │   ├── types.py                      Profile, TailorRequest, TailorResult, errors
    │   │   ├── providers/
    │   │   │   ├── __init__.py
    │   │   │   ├── llm.py                    SystemBlock, Message, TokenUsage, StructuredResult, LLMProvider
    │   │   │   ├── embeddings.py             EmbeddingProvider, FastEmbedProvider
    │   │   │   ├── anthropic.py              AnthropicProvider
    │   │   │   └── fake.py                   FakeLLMProvider, FakeEmbeddingProvider
    │   │   ├── extract.py                    extract()
    │   │   ├── select.py                     select_blocks(), Selection, SelectionConfig
    │   │   ├── compose.py                    ComposeOutput, compose(), assemble_resume(), build_header()
    │   │   ├── repair.py                     repair()
    │   │   ├── guardrails/
    │   │   │   ├── __init__.py
    │   │   │   ├── base.py                   GuardrailContext, iter_bullets, iter_entries, make_violation
    │   │   │   ├── provenance.py
    │   │   │   ├── metrics.py
    │   │   │   ├── entities.py
    │   │   │   ├── dates.py
    │   │   │   ├── attribution.py
    │   │   │   ├── visibility.py
    │   │   │   └── registry.py               RULES, run_guardrails()
    │   │   ├── render/
    │   │   │   ├── __init__.py
    │   │   │   ├── docx.py                   render_docx(), OrphanBulletError
    │   │   │   └── pdf.py                    soffice_available(), convert_docx_to_pdf()
    │   │   └── pipeline.py                   CallBudget, LLMBudgetExceeded, tailor()
    │   ├── profile/
    │   │   ├── __init__.py
    │   │   └── loader.py                     load_profile(), dump_profile(), ProfileError
    │   └── cli/
    │       ├── __init__.py
    │       └── main.py                       Typer app: tailor, profile validate
    └── tests/
        ├── conftest.py
        ├── helpers.py                        demo_resume(), bullet()
        ├── unit/
        ├── guardrails/
        └── golden/
            ├── test_golden.py
            └── cases/<case>/{jd.txt,extract.json,compose.json,[repair.json],expected.json}
```

---
### Task 1: Repository scaffold and Python project

**Files:**
- Create: `LICENSE`, `.env.example`, `scripts/check-no-personal-data.py`
- Modify: `.gitignore`, `profile.example/answers.yaml`, `profile.example/blocks.yaml`
- Create: `apps/api/pyproject.toml`, `apps/api/src/rhapto/__init__.py`, `apps/api/src/rhapto/config.py`, `apps/api/tests/conftest.py`, `apps/api/tests/unit/test_config.py`

**Interfaces:**
- Produces: `rhapto.config.Settings` with fields `anthropic_api_key: str`, `rhapto_llm_model: str`, `rhapto_embedding_model: str`, `rhapto_soffice_binary: str`; `get_settings() -> Settings`.

- [ ] **Step 1: Add license, env example, gitignore, and demo profile edits**

```bash
curl -fsSL https://www.gnu.org/licenses/agpl-3.0.txt -o LICENSE
```

Write `.env.example`:

```
# Copy to .env (gitignored). Rhapto never sends personal data anywhere except the LLM API.
ANTHROPIC_API_KEY=
RHAPTO_LLM_MODEL=claude-sonnet-5
RHAPTO_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RHAPTO_SOFFICE_BINARY=soffice
```

Replace `.gitignore` with:

```
# personal data (never commit)
profile/
.env
.env.*
!.env.example

# outputs
out/
dist/

# python
__pycache__/
*.pyc
.venv/
.mypy_cache/
.ruff_cache/
.pytest_cache/
*.egg-info/

# node
node_modules/
.next/
```

Replace `profile.example/answers.yaml` with (fictional data):

```yaml
answers:
  name: "Maya Chen"
  email: "maya.chen@example.com"
  phone: "+1 555 0100"
  location: "Denver, CO"
  links: "github.com/mayachen-example"
  work_authorization: "US citizen"
  onsite_preference: "Remote or hybrid"
  salary_range: "$160k-$190k base"
  notice_period: "2 weeks"
```

In `profile.example/blocks.yaml`, add `verified: true` to the `acme-data-pm` block (after the `period` line) so its "4 teams" figure is a verified metric.

- [ ] **Step 2: Write the personal-data leak check**

`scripts/check-no-personal-data.py`:

```python
"""Fail if any organisation name from the real profile appears in git-tracked files.

Runs as a no-op when profile/ is absent (for example in CI).
Usage: uv run --project apps/api python scripts/check-no-personal-data.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIN_LEN = 4


def main() -> int:
    blocks_path = ROOT / "profile" / "blocks.yaml"
    if not blocks_path.exists():
        print("profile/blocks.yaml absent; nothing to check")
        return 0
    data = yaml.safe_load(blocks_path.read_text(encoding="utf-8")) or {}
    needles = {
        str(b["org"]).strip()
        for b in data.get("blocks", [])
        if b.get("org") and len(str(b["org"]).strip()) >= MIN_LEN
    }
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    hits: list[tuple[str, str]] = []
    for rel in filter(None, tracked):
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        hits.extend((rel, n) for n in needles if n.lower() in text)
    for rel, needle in hits:
        print(f"LEAK: {rel} contains org name from profile/: {needle!r}", file=sys.stderr)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Create the uv project**

`apps/api/pyproject.toml`:

```toml
[project]
name = "rhapto"
version = "0.1.0"
description = "Human-in-the-loop AI job application copilot"
license = "AGPL-3.0-only"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.9",
    "pydantic-settings>=2.5",
    "anthropic>=0.50",
    "fastembed>=0.4",
    "numpy>=1.26",
    "python-docx>=1.1",
    "pyyaml>=6.0",
    "typer>=0.12",
    "rapidfuzz>=3.9",
]

[project.scripts]
rhapto = "rhapto.cli.main:app"

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.24",
    "ruff>=0.6",
    "mypy>=1.11",
    "datamodel-code-generator>=0.26",
    "import-linter>=2.0",
    "types-PyYAML",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/rhapto"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
extend-exclude = ["src/rhapto/models"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]  # line length is handled by ruff format; long string literals are allowed

[tool.ruff.lint.flake8-bugbear]
extend-immutable-calls = ["typer.Option", "typer.Argument"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
mypy_path = "src"
packages = ["rhapto"]

[[tool.mypy.overrides]]
module = ["fastembed.*", "docx.*", "rapidfuzz.*"]
ignore_missing_imports = true
```

`apps/api/src/rhapto/__init__.py`:

```python
"""Rhapto: human-in-the-loop AI job application copilot."""

__version__ = "0.1.0"
```

`apps/api/src/rhapto/config.py`:

```python
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration read from environment variables and a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    rhapto_llm_model: str = "claude-sonnet-5"
    rhapto_embedding_model: str = "BAAI/bge-small-en-v1.5"
    rhapto_soffice_binary: str = "soffice"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Write the failing config test**

`apps/api/tests/conftest.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_PROFILE = REPO_ROOT / "profile.example"


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def demo_profile_dir() -> Path:
    return DEMO_PROFILE
```

`apps/api/tests/unit/test_config.py`:

```python
from rhapto.config import Settings


def test_defaults_when_env_missing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("RHAPTO_LLM_MODEL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.rhapto_llm_model == "claude-sonnet-5"
    assert settings.rhapto_embedding_model == "BAAI/bge-small-en-v1.5"


def test_env_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("RHAPTO_LLM_MODEL", "claude-opus-5")
    assert Settings(_env_file=None).rhapto_llm_model == "claude-opus-5"
```

- [ ] **Step 5: Install and run**

```bash
cd apps/api && uv sync && uv run pytest -v
```
Expected: 2 passed.

```bash
cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy
```
Expected: no errors (run `uv run ruff format .` first if formatting differs).

- [ ] **Step 6: Commit**

```bash
git add LICENSE .env.example .gitignore scripts profile.example apps/api
git commit -m "chore: scaffold Python project, license, env example, leak check"
```

---
### Task 2: JSON Schemas and generated Pydantic models

**Files:**
- Create: `packages/schemas/profile/blocks.json`, `tracks.json`, `bases.json`, `guardrails.json`, `answers.json`, `watchlist.json`
- Create: `packages/schemas/jd_extract.json`, `resume_document.json`, `guardrail_report.json`, `package.json`
- Create: `scripts/codegen.sh`
- Generate: `apps/api/src/rhapto/models/**` (committed)
- Test: `apps/api/tests/unit/test_models.py`

**Interfaces:**
- Produces these classes (module path in parentheses). Later tasks import exactly these names:
  - `rhapto.models.profile.blocks`: `BlocksFile(blocks: list[Block])`, `Block(id, type: Literal['achievement','role','project','skill','credential'], org: str|None, role: str|None, period: str|None, verified: bool=False, metric: str|None, content: str, tags: list[str]=[], attribution: str|None, concurrent: bool=False, visibility: Visibility|None)`, `Visibility(exclude_when: list[str]=[])`
  - `rhapto.models.profile.tracks`: `TracksFile(tracks: list[Track])`, `Track(id, name, description: str|None, keywords: list[str]=[], resume_base: str, min_fit: int=50)`
  - `rhapto.models.profile.bases`: `BasesFile(bases: list[ResumeBase])`, `ResumeBase(id, name, block_ids: list[str], section_order: list[str], style: dict[str, Any]={})`
  - `rhapto.models.profile.guardrails`: `GuardrailsFile(guardrails: list[GuardrailRule])`, `GuardrailRule(rule: str, active: bool=True, config: dict[str, Any]={})`
  - `rhapto.models.profile.answers`: `AnswersFile(answers: dict[str, str])`
  - `rhapto.models.profile.watchlist`: `WatchlistFile(watchlist: list[WatchlistEntry])`, `WatchlistEntry(company, source, board)`
  - `rhapto.models.jd_extract`: `JDExtract(company, title, location_policy, seniority, must_have: list[str], nice_to_have: list[str], keywords: list[str], likely_knockouts: list[str], context_tags: list[str])`
  - `rhapto.models.resume_document`: `ResumeDocument(header: ResumeHeader, summary: list[ResumeBullet], sections: list[ResumeSection])`, `ResumeHeader(name, email, phone, location, links: list[str])`, `ResumeSection(title, kind: Literal['experience','projects','skills','credentials'], entries: list[ResumeEntry])`, `ResumeEntry(source_block_id, org, role, period, title, bullets: list[ResumeBullet])`, `ResumeBullet(text, source_block_id)`
  - `rhapto.models.guardrail_report`: `GuardrailReport(passed: bool, rules_run: list[str], violations: list[Violation])`, `Violation(rule, severity: Literal['error','warning'], message, path, block_id: str|None)`
  - `rhapto.models.package`: `ApplicationPackage(job: JobSnapshot, track_id, jd_extract, resume, cover_note, change_log, answers: dict[str,str], guardrail_report, version: int, status: Literal['draft','blocked'], llm_calls: int, created_at: datetime)`, `JobSnapshot(company, title, location, url, jd_text)`

- [ ] **Step 1: Write the profile schemas**

`packages/schemas/profile/blocks.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rhapto.dev/schemas/profile/blocks.json",
  "title": "BlocksFile",
  "description": "blocks.yaml: the user's provenance-checked resume block library.",
  "type": "object",
  "additionalProperties": false,
  "required": ["blocks"],
  "properties": {
    "blocks": { "type": "array", "items": { "$ref": "#/$defs/Block" } }
  },
  "$defs": {
    "Visibility": {
      "title": "Visibility",
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "exclude_when": {
          "description": "Context tags that hard-exclude this block from a tailoring run.",
          "type": "array", "items": { "type": "string" }, "default": []
        }
      }
    },
    "Block": {
      "title": "Block",
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "type", "content"],
      "properties": {
        "id": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$" },
        "type": { "type": "string", "enum": ["achievement", "role", "project", "skill", "credential"] },
        "org": { "type": "string" },
        "role": { "type": "string" },
        "period": { "type": "string", "description": "YYYY, YYYY-YYYY, or YYYY-Present" },
        "verified": { "type": "boolean", "default": false, "description": "Only verified blocks may carry metrics." },
        "metric": { "type": "string" },
        "content": { "type": "string" },
        "tags": { "type": "array", "items": { "type": "string" }, "default": [] },
        "attribution": { "type": "string", "description": "Required attribution phrase for named projects." },
        "concurrent": { "type": "boolean", "default": false, "description": "May overlap in time with other roles." },
        "visibility": { "$ref": "#/$defs/Visibility" }
      }
    }
  }
}
```

`packages/schemas/profile/tracks.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rhapto.dev/schemas/profile/tracks.json",
  "title": "TracksFile",
  "type": "object",
  "additionalProperties": false,
  "required": ["tracks"],
  "properties": {
    "tracks": { "type": "array", "items": { "$ref": "#/$defs/Track" } }
  },
  "$defs": {
    "Track": {
      "title": "Track",
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "name", "resume_base"],
      "properties": {
        "id": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$" },
        "name": { "type": "string" },
        "description": { "type": "string" },
        "keywords": { "type": "array", "items": { "type": "string" }, "default": [] },
        "resume_base": { "type": "string" },
        "min_fit": { "type": "integer", "minimum": 0, "maximum": 100, "default": 50 }
      }
    }
  }
}
```

`packages/schemas/profile/bases.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rhapto.dev/schemas/profile/bases.json",
  "title": "BasesFile",
  "type": "object",
  "additionalProperties": false,
  "required": ["bases"],
  "properties": {
    "bases": { "type": "array", "items": { "$ref": "#/$defs/ResumeBase" } }
  },
  "$defs": {
    "ResumeBase": {
      "title": "ResumeBase",
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "name", "block_ids"],
      "properties": {
        "id": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$" },
        "name": { "type": "string" },
        "block_ids": { "type": "array", "items": { "type": "string" } },
        "section_order": {
          "type": "array", "items": { "type": "string" },
          "default": ["summary", "experience", "projects", "skills", "credentials"]
        },
        "style": { "type": "object", "additionalProperties": true, "default": {} }
      }
    }
  }
}
```

`packages/schemas/profile/guardrails.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rhapto.dev/schemas/profile/guardrails.json",
  "title": "GuardrailsFile",
  "type": "object",
  "additionalProperties": false,
  "required": ["guardrails"],
  "properties": {
    "guardrails": { "type": "array", "items": { "$ref": "#/$defs/GuardrailRule" } }
  },
  "$defs": {
    "GuardrailRule": {
      "title": "GuardrailRule",
      "type": "object",
      "additionalProperties": false,
      "required": ["rule"],
      "properties": {
        "rule": { "type": "string" },
        "active": { "type": "boolean", "default": true },
        "config": { "type": "object", "additionalProperties": true, "default": {} }
      }
    }
  }
}
```

`packages/schemas/profile/answers.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rhapto.dev/schemas/profile/answers.json",
  "title": "AnswersFile",
  "description": "answers.yaml: standard application answers plus header fields name, email, phone, location, links.",
  "type": "object",
  "additionalProperties": false,
  "required": ["answers"],
  "properties": {
    "answers": { "type": "object", "additionalProperties": { "type": "string" } }
  }
}
```

`packages/schemas/profile/watchlist.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rhapto.dev/schemas/profile/watchlist.json",
  "title": "WatchlistFile",
  "type": "object",
  "additionalProperties": false,
  "required": ["watchlist"],
  "properties": {
    "watchlist": { "type": "array", "items": { "$ref": "#/$defs/WatchlistEntry" } }
  },
  "$defs": {
    "WatchlistEntry": {
      "title": "WatchlistEntry",
      "type": "object",
      "additionalProperties": false,
      "required": ["company", "source", "board"],
      "properties": {
        "company": { "type": "string" },
        "source": { "type": "string", "enum": ["greenhouse", "lever", "ashby", "smartrecruiters", "workable"] },
        "board": { "type": "string" }
      }
    }
  }
}
```

- [ ] **Step 2: Write the document schemas**

`packages/schemas/jd_extract.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rhapto.dev/schemas/jd_extract.json",
  "title": "JDExtract",
  "description": "Structured requirements extracted from a job description.",
  "type": "object",
  "additionalProperties": false,
  "required": ["company", "title"],
  "properties": {
    "company": { "type": "string" },
    "title": { "type": "string" },
    "location_policy": { "type": "string", "default": "unspecified", "description": "remote, hybrid, onsite, or unspecified" },
    "seniority": { "type": "string", "default": "unspecified" },
    "must_have": { "type": "array", "items": { "type": "string" }, "default": [] },
    "nice_to_have": { "type": "array", "items": { "type": "string" }, "default": [] },
    "keywords": { "type": "array", "items": { "type": "string" }, "default": [] },
    "likely_knockouts": { "type": "array", "items": { "type": "string" }, "default": [] },
    "context_tags": { "type": "array", "items": { "type": "string" }, "default": [], "description": "Tags matched against block visibility.exclude_when" }
  }
}
```

`packages/schemas/resume_document.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rhapto.dev/schemas/resume_document.json",
  "title": "ResumeDocument",
  "description": "A tailored resume. Every bullet and entry cites the block it came from.",
  "type": "object",
  "additionalProperties": false,
  "required": ["header", "sections"],
  "properties": {
    "header": { "$ref": "#/$defs/ResumeHeader" },
    "summary": { "type": "array", "items": { "$ref": "#/$defs/ResumeBullet" }, "default": [] },
    "sections": { "type": "array", "items": { "$ref": "#/$defs/ResumeSection" } }
  },
  "$defs": {
    "ResumeHeader": {
      "title": "ResumeHeader",
      "type": "object",
      "additionalProperties": false,
      "required": ["name"],
      "properties": {
        "name": { "type": "string" },
        "email": { "type": "string" },
        "phone": { "type": "string" },
        "location": { "type": "string" },
        "links": { "type": "array", "items": { "type": "string" }, "default": [] }
      }
    },
    "ResumeBullet": {
      "title": "ResumeBullet",
      "type": "object",
      "additionalProperties": false,
      "required": ["text", "source_block_id"],
      "properties": {
        "text": { "type": "string" },
        "source_block_id": { "type": "string" }
      }
    },
    "ResumeEntry": {
      "title": "ResumeEntry",
      "type": "object",
      "additionalProperties": false,
      "required": ["source_block_id"],
      "properties": {
        "source_block_id": { "type": "string" },
        "org": { "type": "string" },
        "role": { "type": "string" },
        "period": { "type": "string" },
        "title": { "type": "string" },
        "bullets": { "type": "array", "items": { "$ref": "#/$defs/ResumeBullet" }, "default": [] }
      }
    },
    "ResumeSection": {
      "title": "ResumeSection",
      "type": "object",
      "additionalProperties": false,
      "required": ["title", "kind", "entries"],
      "properties": {
        "title": { "type": "string" },
        "kind": { "type": "string", "enum": ["experience", "projects", "skills", "credentials"] },
        "entries": { "type": "array", "items": { "$ref": "#/$defs/ResumeEntry" } }
      }
    }
  }
}
```

`packages/schemas/guardrail_report.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rhapto.dev/schemas/guardrail_report.json",
  "title": "GuardrailReport",
  "type": "object",
  "additionalProperties": false,
  "required": ["passed", "rules_run", "violations"],
  "properties": {
    "passed": { "type": "boolean" },
    "rules_run": { "type": "array", "items": { "type": "string" } },
    "violations": { "type": "array", "items": { "$ref": "#/$defs/Violation" } }
  },
  "$defs": {
    "Violation": {
      "title": "Violation",
      "type": "object",
      "additionalProperties": false,
      "required": ["rule", "severity", "message", "path"],
      "properties": {
        "rule": { "type": "string" },
        "severity": { "type": "string", "enum": ["error", "warning"] },
        "message": { "type": "string" },
        "path": { "type": "string", "description": "e.g. sections[0].entries[1].bullets[2]" },
        "block_id": { "type": "string" }
      }
    }
  }
}
```

`packages/schemas/package.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rhapto.dev/schemas/package.json",
  "title": "ApplicationPackage",
  "description": "Everything produced for one application, versioned.",
  "type": "object",
  "additionalProperties": false,
  "required": ["job", "track_id", "jd_extract", "resume", "cover_note", "change_log", "answers", "guardrail_report", "version", "status", "llm_calls", "created_at"],
  "properties": {
    "job": { "$ref": "#/$defs/JobSnapshot" },
    "track_id": { "type": "string" },
    "jd_extract": { "$ref": "jd_extract.json" },
    "resume": { "$ref": "resume_document.json" },
    "cover_note": { "type": "string" },
    "change_log": { "type": "string" },
    "answers": { "type": "object", "additionalProperties": { "type": "string" } },
    "guardrail_report": { "$ref": "guardrail_report.json" },
    "version": { "type": "integer", "minimum": 1 },
    "status": { "type": "string", "enum": ["draft", "blocked"] },
    "llm_calls": { "type": "integer", "minimum": 0 },
    "created_at": { "type": "string", "format": "date-time" }
  },
  "$defs": {
    "JobSnapshot": {
      "title": "JobSnapshot",
      "type": "object",
      "additionalProperties": false,
      "required": ["company", "title", "jd_text"],
      "properties": {
        "company": { "type": "string" },
        "title": { "type": "string" },
        "location": { "type": "string" },
        "url": { "type": "string" },
        "jd_text": { "type": "string" }
      }
    }
  }
}
```

- [ ] **Step 3: Write the codegen script**

`scripts/codegen.sh`:

```bash
#!/usr/bin/env bash
# Regenerate Pydantic models from packages/schemas. Run from the repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/apps/api/src/rhapto/models"
rm -rf "$OUT"
(cd "$ROOT/apps/api" && uv run datamodel-codegen \
  --input "$ROOT/packages/schemas" \
  --input-file-type jsonschema \
  --output "$OUT" \
  --output-model-type pydantic_v2.BaseModel \
  --use-title-as-name \
  --strict-nullable \
  --use-annotated \
  --field-constraints \
  --enum-field-as-literal all \
  --use-standard-collections \
  --use-union-operator \
  --collapse-root-models \
  --use-schema-description \
  --use-field-description \
  --target-python-version 3.12 \
  --disable-timestamp)
touch "$OUT/__init__.py" "$OUT/profile/__init__.py"
echo "models regenerated in $OUT"
```

- [ ] **Step 4: Write the failing model test**

`apps/api/tests/unit/test_models.py`:

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from rhapto.models.guardrail_report import GuardrailReport, Violation
from rhapto.models.jd_extract import JDExtract
from rhapto.models.package import ApplicationPackage, JobSnapshot
from rhapto.models.profile.answers import AnswersFile
from rhapto.models.profile.bases import ResumeBase
from rhapto.models.profile.blocks import Block, BlocksFile, Visibility
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import WatchlistEntry
from rhapto.models.resume_document import (
    ResumeBullet,
    ResumeDocument,
    ResumeEntry,
    ResumeHeader,
    ResumeSection,
)


def test_block_defaults() -> None:
    block = Block(id="x-1", type="achievement", content="Did a thing.")
    assert block.verified is False
    assert block.tags == []
    assert block.visibility is None
    assert block.concurrent is False


def test_block_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        Block.model_validate({"id": "x", "type": "role", "content": "c", "bogus": 1})


def test_block_rejects_bad_type() -> None:
    with pytest.raises(ValidationError):
        Block.model_validate({"id": "x", "type": "hobby", "content": "c"})


def test_blocks_file_round_trip() -> None:
    data = {"blocks": [{"id": "a", "type": "role", "content": "c", "visibility": {"exclude_when": ["t"]}}]}
    parsed = BlocksFile.model_validate(data)
    assert parsed.blocks[0].visibility == Visibility(exclude_when=["t"])


def test_track_and_base_defaults() -> None:
    track = Track(id="t", name="T", resume_base="b")
    assert track.min_fit == 50 and track.keywords == []
    base = ResumeBase(id="b", name="B", block_ids=["a"])
    assert base.section_order[0] == "summary" and base.style == {}


def test_guardrail_rule_defaults() -> None:
    rule = GuardrailRule(rule="no-unverified-metrics")
    assert rule.active is True and rule.config == {}


def test_answers_and_watchlist() -> None:
    assert AnswersFile(answers={"name": "Maya Chen"}).answers["name"] == "Maya Chen"
    assert WatchlistEntry(company="ExampleCo", source="greenhouse", board="exampleco").board == "exampleco"


def test_jd_extract_defaults() -> None:
    extract = JDExtract(company="ExampleCo", title="PM")
    assert extract.must_have == [] and extract.context_tags == []
    assert extract.location_policy == "unspecified"


def test_resume_document_and_package() -> None:
    resume = ResumeDocument(
        header=ResumeHeader(name="Maya Chen"),
        summary=[ResumeBullet(text="Summary.", source_block_id="acme-data-pm")],
        sections=[
            ResumeSection(
                title="Experience",
                kind="experience",
                entries=[
                    ResumeEntry(
                        source_block_id="acme-data-pm",
                        org="Acme Analytics",
                        bullets=[ResumeBullet(text="Led it.", source_block_id="acme-data-pm")],
                    )
                ],
            )
        ],
    )
    package = ApplicationPackage(
        job=JobSnapshot(company="ExampleCo", title="PM", jd_text="..."),
        track_id="data-pm",
        jd_extract=JDExtract(company="ExampleCo", title="PM"),
        resume=resume,
        cover_note="Hi.",
        change_log="Emphasised data.",
        answers={},
        guardrail_report=GuardrailReport(
            passed=False,
            rules_run=["provenance"],
            violations=[Violation(rule="provenance", severity="error", message="m", path="summary[0]")],
        ),
        version=1,
        status="blocked",
        llm_calls=2,
        created_at=datetime.now(UTC),
    )
    dumped = package.model_dump(mode="json")
    assert ApplicationPackage.model_validate(dumped).resume.sections[0].kind == "experience"
```

- [ ] **Step 5: Generate and verify**

```bash
bash scripts/codegen.sh
cd apps/api && uv run python -c "import rhapto.models.package, rhapto.models.profile.blocks; print('ok')" && uv run pytest tests/unit/test_models.py -v
```
Expected: `ok` and 9 passed. If datamodel-codegen produced different class names or module paths, fix the schema `title`s or the codegen flags and regenerate. Never edit generated files. If the `$ref` to a sibling file did not resolve, confirm the referenced file names match exactly (`jd_extract.json`, `resume_document.json`, `guardrail_report.json`).

```bash
cd apps/api && uv run ruff check . && uv run mypy
```
Expected: clean. If mypy reports errors inside `src/rhapto/models`, add `[[tool.mypy.overrides]] module = ["rhapto.models.*"] disable_error_code = ["misc"]` to pyproject rather than editing generated code.

- [ ] **Step 6: Commit**

```bash
git add packages/schemas scripts/codegen.sh apps/api
git commit -m "feat(schemas): add JSON Schemas and generated Pydantic models"
```

---
### Task 3: Engine types and YAML profile loader

**Files:**
- Create: `apps/api/src/rhapto/engine/__init__.py`, `apps/api/src/rhapto/engine/types.py`
- Create: `apps/api/src/rhapto/profile/__init__.py`, `apps/api/src/rhapto/profile/loader.py`
- Test: `apps/api/tests/unit/test_profile_loader.py`

**Interfaces:**
- Consumes: generated models from Task 2.
- Produces:
  - `rhapto.engine.types.Profile(blocks, tracks, bases, guardrails, answers, watchlist)` with `block_map() -> dict[str, Block]`, `get_track(track_id: str | None) -> Track`, `base_for(track: Track) -> ResumeBase`.
  - `rhapto.engine.types.EngineError(Exception)`, `ProfileError(EngineError)`.
  - `rhapto.engine.types.TailorRequest(jd_text, track_id: str|None=None, feedback: str|None=None, previous_package: ApplicationPackage|None=None)`.
  - `rhapto.engine.types.TailorResult(package: ApplicationPackage, docx: bytes, selection: Selection)` is defined in Task 14 once `Selection` exists; Task 3 defines everything else.
  - `rhapto.profile.loader.load_profile(path: Path) -> Profile`, `dump_profile(profile: Profile, path: Path) -> None`, `default_guardrails() -> list[GuardrailRule]`, `synthesize_bases(tracks, blocks) -> list[ResumeBase]`.

- [ ] **Step 1: Write the failing loader tests**

`apps/api/tests/unit/test_profile_loader.py`:

```python
from pathlib import Path

import pytest
import yaml

from rhapto.engine.types import ProfileError
from rhapto.profile.loader import dump_profile, load_profile


def test_loads_demo_profile(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    assert {b.id for b in profile.blocks} == {"acme-data-pm", "acme-migration", "side-llm-tool", "cred-pmp"}
    assert [t.id for t in profile.tracks] == ["data-pm", "ai-pm"]
    assert profile.answers["name"] == "Maya Chen"
    assert profile.watchlist[0].company == "ExampleCo"
    assert {g.rule for g in profile.guardrails} == {
        "no-unverified-metrics",
        "no-invented-entities",
        "date-consistency",
    }


def test_synthesizes_bases_when_missing(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    assert {b.id for b in profile.bases} == {"data-pm", "ai-pm"}
    base = profile.base_for(profile.get_track("ai-pm"))
    assert set(base.block_ids) == {b.id for b in profile.blocks}


def test_get_track_defaults_to_first(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    assert profile.get_track(None).id == "data-pm"
    with pytest.raises(ProfileError, match="unknown track"):
        profile.get_track("nope")


def test_missing_blocks_file(tmp_path: Path) -> None:
    (tmp_path / "tracks.yaml").write_text("tracks: []\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="blocks.yaml"):
        load_profile(tmp_path)


def test_duplicate_block_id(tmp_path: Path) -> None:
    (tmp_path / "blocks.yaml").write_text(
        yaml.safe_dump(
            {
                "blocks": [
                    {"id": "a", "type": "role", "content": "x"},
                    {"id": "a", "type": "role", "content": "y"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "tracks.yaml").write_text(
        yaml.safe_dump({"tracks": [{"id": "t", "name": "T", "resume_base": "t"}]}), encoding="utf-8"
    )
    with pytest.raises(ProfileError, match="duplicate block id"):
        load_profile(tmp_path)


def test_base_referencing_unknown_block(tmp_path: Path) -> None:
    (tmp_path / "blocks.yaml").write_text(
        yaml.safe_dump({"blocks": [{"id": "a", "type": "role", "content": "x"}]}), encoding="utf-8"
    )
    (tmp_path / "tracks.yaml").write_text(
        yaml.safe_dump({"tracks": [{"id": "t", "name": "T", "resume_base": "b"}]}), encoding="utf-8"
    )
    (tmp_path / "bases.yaml").write_text(
        yaml.safe_dump({"bases": [{"id": "b", "name": "B", "block_ids": ["a", "ghost"]}]}),
        encoding="utf-8",
    )
    with pytest.raises(ProfileError, match="ghost"):
        load_profile(tmp_path)


def test_invalid_yaml_shape_names_file(tmp_path: Path) -> None:
    (tmp_path / "blocks.yaml").write_text("blocks: [{id: a, type: hobby, content: x}]\n", encoding="utf-8")
    (tmp_path / "tracks.yaml").write_text("tracks: []\n", encoding="utf-8")
    with pytest.raises(ProfileError, match="blocks.yaml"):
        load_profile(tmp_path)


def test_default_guardrails_when_file_missing(tmp_path: Path) -> None:
    (tmp_path / "blocks.yaml").write_text(
        yaml.safe_dump({"blocks": [{"id": "a", "type": "role", "content": "x"}]}), encoding="utf-8"
    )
    (tmp_path / "tracks.yaml").write_text(
        yaml.safe_dump({"tracks": [{"id": "t", "name": "T", "resume_base": "t"}]}), encoding="utf-8"
    )
    profile = load_profile(tmp_path)
    assert {g.rule for g in profile.guardrails} == {
        "no-unverified-metrics",
        "no-invented-entities",
        "date-consistency",
        "attribution",
        "visibility-context",
    }


def test_dump_round_trip(demo_profile_dir: Path, tmp_path: Path) -> None:
    profile = load_profile(demo_profile_dir)
    dump_profile(profile, tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {
        "blocks.yaml", "tracks.yaml", "bases.yaml", "guardrails.yaml", "answers.yaml", "watchlist.yaml",
    }
    assert load_profile(tmp_path) == profile
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/unit/test_profile_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.engine`.

- [ ] **Step 3: Implement engine types**

`apps/api/src/rhapto/engine/__init__.py`:

```python
"""Pure tailoring pipeline. Must not import rhapto.profile, db, api, worker, or cli."""
```

`apps/api/src/rhapto/engine/types.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from rhapto.models.package import ApplicationPackage
from rhapto.models.profile.bases import ResumeBase
from rhapto.models.profile.blocks import Block
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import WatchlistEntry


class EngineError(Exception):
    """Base class for engine failures."""


class ProfileError(EngineError):
    """The profile is missing, malformed, or internally inconsistent."""


class Profile(BaseModel):
    """In-memory profile. Loaded from YAML (CLI) or Postgres (worker); the engine does not care."""

    blocks: list[Block]
    tracks: list[Track]
    bases: list[ResumeBase]
    guardrails: list[GuardrailRule]
    answers: dict[str, str] = Field(default_factory=dict)
    watchlist: list[WatchlistEntry] = Field(default_factory=list)

    def block_map(self) -> dict[str, Block]:
        return {b.id: b for b in self.blocks}

    def get_track(self, track_id: str | None) -> Track:
        if not self.tracks:
            raise ProfileError("profile has no tracks")
        if track_id is None:
            return self.tracks[0]
        for track in self.tracks:
            if track.id == track_id:
                return track
        raise ProfileError(f"unknown track: {track_id}")

    def base_for(self, track: Track) -> ResumeBase:
        for base in self.bases:
            if base.id == track.resume_base:
                return base
        raise ProfileError(f"track {track.id} references unknown resume base {track.resume_base}")


class TailorRequest(BaseModel):
    jd_text: str
    track_id: str | None = None
    feedback: str | None = None
    previous_package: ApplicationPackage | None = None
```

- [ ] **Step 4: Implement the loader**

`apps/api/src/rhapto/profile/__init__.py`:

```python
"""YAML profile loading and dumping."""

from rhapto.profile.loader import dump_profile, load_profile

__all__ = ["dump_profile", "load_profile"]
```

`apps/api/src/rhapto/profile/loader.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from rhapto.engine.types import Profile, ProfileError
from rhapto.models.profile.answers import AnswersFile
from rhapto.models.profile.bases import BasesFile, ResumeBase
from rhapto.models.profile.blocks import Block, BlocksFile
from rhapto.models.profile.guardrails import GuardrailRule, GuardrailsFile
from rhapto.models.profile.tracks import Track, TracksFile
from rhapto.models.profile.watchlist import WatchlistFile

M = TypeVar("M", bound=BaseModel)

DEFAULT_RULES = [
    "no-unverified-metrics",
    "no-invented-entities",
    "date-consistency",
    "attribution",
    "visibility-context",
]


def _read(path: Path, model: type[M]) -> M | None:
    if not path.exists():
        return None
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return model.model_validate(raw)
    except (yaml.YAMLError, ValidationError) as exc:
        raise ProfileError(f"{path.name}: {exc}") from exc


def _require(path: Path, model: type[M]) -> M:
    loaded = _read(path, model)
    if loaded is None:
        raise ProfileError(f"{path.name} not found in {path.parent}")
    return loaded


def default_guardrails() -> list[GuardrailRule]:
    return [GuardrailRule(rule=rule) for rule in DEFAULT_RULES]


def synthesize_bases(tracks: list[Track], blocks: list[Block]) -> list[ResumeBase]:
    """One base per distinct track.resume_base containing every block, in library order."""
    seen: dict[str, ResumeBase] = {}
    for track in tracks:
        if track.resume_base not in seen:
            seen[track.resume_base] = ResumeBase(
                id=track.resume_base,
                name=f"{track.name} (all blocks)",
                block_ids=[b.id for b in blocks],
            )
    return list(seen.values())


def load_profile(path: Path) -> Profile:
    path = Path(path)
    blocks = _require(path / "blocks.yaml", BlocksFile).blocks
    tracks = _require(path / "tracks.yaml", TracksFile).tracks
    ids = [b.id for b in blocks]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ProfileError(f"blocks.yaml: duplicate block id(s): {', '.join(dupes)}")

    bases_file = _read(path / "bases.yaml", BasesFile)
    bases = bases_file.bases if bases_file else synthesize_bases(tracks, blocks)
    known = set(ids)
    for base in bases:
        missing = [bid for bid in base.block_ids if bid not in known]
        if missing:
            raise ProfileError(f"bases.yaml: base {base.id} references unknown block(s): {', '.join(missing)}")
    base_ids = {b.id for b in bases}
    for track in tracks:
        if track.resume_base not in base_ids:
            raise ProfileError(f"tracks.yaml: track {track.id} references unknown base {track.resume_base}")

    guardrails_file = _read(path / "guardrails.yaml", GuardrailsFile)
    answers_file = _read(path / "answers.yaml", AnswersFile)
    watchlist_file = _read(path / "watchlist.yaml", WatchlistFile)
    return Profile(
        blocks=blocks,
        tracks=tracks,
        bases=bases,
        guardrails=guardrails_file.guardrails if guardrails_file else default_guardrails(),
        answers=answers_file.answers if answers_file else {},
        watchlist=watchlist_file.watchlist if watchlist_file else [],
    )


def _write(path: Path, payload: BaseModel) -> None:
    path.write_text(
        yaml.safe_dump(payload.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def dump_profile(profile: Profile, path: Path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    _write(path / "blocks.yaml", BlocksFile(blocks=profile.blocks))
    _write(path / "tracks.yaml", TracksFile(tracks=profile.tracks))
    _write(path / "bases.yaml", BasesFile(bases=profile.bases))
    _write(path / "guardrails.yaml", GuardrailsFile(guardrails=profile.guardrails))
    _write(path / "answers.yaml", AnswersFile(answers=profile.answers))
    _write(path / "watchlist.yaml", WatchlistFile(watchlist=profile.watchlist))
```

- [ ] **Step 5: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/unit/test_profile_loader.py -v && uv run ruff check . && uv run mypy`
Expected: 9 passed, no lint or type errors.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/rhapto/engine apps/api/src/rhapto/profile apps/api/tests/unit/test_profile_loader.py
git commit -m "feat(profile): engine Profile type and YAML loader with validation"
```

---
### Task 4: Provider interfaces, fakes, Anthropic, and fastembed

**Files:**
- Create: `apps/api/src/rhapto/engine/providers/__init__.py`, `llm.py`, `embeddings.py`, `anthropic.py`, `fake.py`
- Test: `apps/api/tests/unit/test_providers.py`

**Interfaces:**
- Produces (`rhapto.engine.providers.llm`): `SystemBlock(text: str, cache: bool=False)`, `Message(role: Literal['user','assistant'], content: str)`, `TokenUsage(input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens)` with `__add__`, `StructuredResult[T](value: T, usage: TokenUsage)`, `LLMProvider` Protocol with `async complete_structured(*, system: list[SystemBlock], messages: list[Message], output_schema: type[T], max_tokens: int = 4096) -> StructuredResult[T]`.
- Produces (`rhapto.engine.providers.embeddings`): `EmbeddingProvider` Protocol with `dimensions: int` and `async embed(texts: list[str]) -> list[list[float]]`; `FastEmbedProvider(model_name: str)`.
- Produces (`rhapto.engine.providers.anthropic`): `AnthropicProvider(model: str, api_key: str | None = None, client: Any | None = None)`.
- Produces (`rhapto.engine.providers.fake`): `FakeLLMProvider(responses: Sequence[BaseModel | dict])` with `.calls: list[FakeCall]`; `FakeCall(system, messages, output_schema)`; `FakeEmbeddingProvider(dimensions: int = 64)`.

- [ ] **Step 1: Write the failing provider tests**

`apps/api/tests/unit/test_providers.py`:

```python
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from rhapto.engine.providers.anthropic import AnthropicProvider
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.engine.providers.llm import Message, SystemBlock, TokenUsage


class Answer(BaseModel):
    text: str
    score: int


async def test_fake_llm_returns_scripted_responses_in_order() -> None:
    llm = FakeLLMProvider([{"text": "a", "score": 1}, Answer(text="b", score=2)])
    first = await llm.complete_structured(
        system=[SystemBlock(text="sys")], messages=[Message(role="user", content="hi")], output_schema=Answer
    )
    second = await llm.complete_structured(system=[], messages=[], output_schema=Answer)
    assert (first.value.text, second.value.text) == ("a", "b")
    assert llm.calls[0].messages[0].content == "hi"
    assert llm.calls[0].output_schema is Answer


async def test_fake_llm_raises_when_exhausted() -> None:
    llm = FakeLLMProvider([])
    with pytest.raises(AssertionError, match="no scripted response"):
        await llm.complete_structured(system=[], messages=[], output_schema=Answer)


async def test_fake_embedder_is_deterministic_and_similarity_aware() -> None:
    embedder = FakeEmbeddingProvider()
    a, b, c = await embedder.embed(["snowflake migration", "snowflake migration program", "pmp certification"])
    assert a == (await embedder.embed(["snowflake migration"]))[0]
    assert len(a) == embedder.dimensions

    def dot(x: list[float], y: list[float]) -> float:
        return sum(i * j for i, j in zip(x, y, strict=True))

    assert dot(a, b) > dot(a, c)


def test_token_usage_adds() -> None:
    total = TokenUsage(input_tokens=1, output_tokens=2) + TokenUsage(input_tokens=3, cache_read_input_tokens=4)
    assert (total.input_tokens, total.output_tokens, total.cache_read_input_tokens) == (4, 2, 4)


class _FakeMessages:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="tool_use", input={"text": "ok", "score": 9})],
            usage=SimpleNamespace(
                input_tokens=100, output_tokens=20, cache_read_input_tokens=80, cache_creation_input_tokens=0
            ),
        )


async def test_anthropic_provider_builds_forced_tool_call_with_cache_control() -> None:
    messages = _FakeMessages()
    client = SimpleNamespace(messages=messages)
    provider = AnthropicProvider(model="claude-sonnet-5", client=client)
    result = await provider.complete_structured(
        system=[SystemBlock(text="static", cache=True), SystemBlock(text="dynamic")],
        messages=[Message(role="user", content="go")],
        output_schema=Answer,
        max_tokens=123,
    )
    assert result.value == Answer(text="ok", score=9)
    assert result.usage.cache_read_input_tokens == 80
    kw = messages.kwargs
    assert kw["model"] == "claude-sonnet-5" and kw["max_tokens"] == 123
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in kw["system"][1]
    assert kw["tool_choice"] == {"type": "tool", "name": "emit"}
    assert kw["tools"][0]["input_schema"]["properties"]["score"]["type"] == "integer"
    assert kw["messages"] == [{"role": "user", "content": "go"}]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/unit/test_providers.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.engine.providers`.

- [ ] **Step 3: Implement interfaces and fakes**

`apps/api/src/rhapto/engine/providers/__init__.py`:

```python
"""Pluggable LLM and embedding providers. The engine only depends on the Protocols in llm.py and embeddings.py."""
```

`apps/api/src/rhapto/engine/providers/llm.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class SystemBlock(BaseModel):
    """A system prompt segment. cache=True marks it for provider-side prompt caching."""

    text: str
    cache: bool = False


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens + other.cache_read_input_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens + other.cache_creation_input_tokens,
        )


@dataclass(frozen=True)
class StructuredResult(Generic[T]):
    value: T
    usage: TokenUsage


class LLMProvider(Protocol):
    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]: ...
```

`apps/api/src/rhapto/engine/providers/embeddings.py`:

```python
from __future__ import annotations

import asyncio
from typing import Any, Protocol


class EmbeddingProvider(Protocol):
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedProvider:
    """Local ONNX embeddings via fastembed. The model is loaded lazily on first use."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", dimensions: int = 384) -> None:
        self.model_name = model_name
        self.dimensions = dimensions
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding  # imported lazily: heavy dependency

            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = await asyncio.to_thread(self._load)
        vectors = await asyncio.to_thread(lambda: list(model.embed(texts)))
        return [[float(x) for x in vec] for vec in vectors]
```

`apps/api/src/rhapto/engine/providers/fake.py`:

```python
from __future__ import annotations

import math
import re
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from rhapto.engine.providers.llm import Message, StructuredResult, SystemBlock, T, TokenUsage


@dataclass
class FakeCall:
    system: list[SystemBlock]
    messages: list[Message]
    output_schema: type[BaseModel]


@dataclass
class FakeLLMProvider:
    """Returns scripted responses in order and records every call."""

    responses: Sequence[BaseModel | dict[str, Any]]
    calls: list[FakeCall] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._queue = list(self.responses)

    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        if not self._queue:
            raise AssertionError("FakeLLMProvider: no scripted response left")
        raw = self._queue.pop(0)
        payload = raw if isinstance(raw, dict) else raw.model_dump(mode="json")
        value = output_schema.model_validate(payload)
        self.calls.append(FakeCall(system=list(system), messages=list(messages), output_schema=output_schema))
        return StructuredResult(value=value, usage=TokenUsage(input_tokens=10, output_tokens=5))


class FakeEmbeddingProvider:
    """Deterministic hashed bag-of-words vectors: similar texts get similar vectors."""

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dimensions
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                vec[zlib.crc32(word.encode()) % self.dimensions] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out
```

- [ ] **Step 4: Implement the Anthropic provider**

`apps/api/src/rhapto/engine/providers/anthropic.py`:

```python
from __future__ import annotations

from typing import Any

from rhapto.engine.providers.llm import Message, StructuredResult, SystemBlock, T, TokenUsage

TOOL_NAME = "emit"


class AnthropicProvider:
    """Structured output via a single forced tool call; static system blocks are prompt-cached."""

    def __init__(self, model: str, api_key: str | None = None, client: Any | None = None) -> None:
        self.model = model
        if client is None:
            import anthropic  # imported lazily so tests never need the SDK configured

            client = anthropic.AsyncAnthropic(api_key=api_key or None)
        self._client = client

    @staticmethod
    def _system_payload(system: list[SystemBlock]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for block in system:
            item: dict[str, Any] = {"type": "text", "text": block.text}
            if block.cache:
                item["cache_control"] = {"type": "ephemeral"}
            payload.append(item)
        return payload

    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        tool = {
            "name": TOOL_NAME,
            "description": f"Return the {output_schema.__name__} exactly as specified by the schema.",
            "input_schema": output_schema.model_json_schema(),
        }
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=self._system_payload(system),
            messages=[{"role": m.role, "content": m.content} for m in messages],
            tools=[tool],
            tool_choice={"type": "tool", "name": TOOL_NAME},
        )
        tool_use = next((b for b in response.content if getattr(b, "type", None) == "tool_use"), None)
        if tool_use is None:
            raise RuntimeError("Anthropic response contained no tool_use block")
        usage = response.usage
        return StructuredResult(
            value=output_schema.model_validate(tool_use.input),
            usage=TokenUsage(
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            ),
        )
```

- [ ] **Step 5: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/unit/test_providers.py -v && uv run ruff check . && uv run mypy`
Expected: 5 passed, clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/rhapto/engine/providers apps/api/tests/unit/test_providers.py
git commit -m "feat(engine): LLM and embedding provider interfaces with Anthropic, fastembed, and fakes"
```

---
### Task 5: Extract step

**Files:**
- Create: `apps/api/src/rhapto/engine/prompts/__init__.py`, `apps/api/src/rhapto/engine/prompts/extract.py`, `apps/api/src/rhapto/engine/extract.py`
- Test: `apps/api/tests/unit/test_extract.py`

**Interfaces:**
- Consumes: `LLMProvider`, `SystemBlock`, `Message`, `TokenUsage` (Task 4); `JDExtract` (Task 2).
- Produces: `rhapto.engine.extract.extract(jd_text: str, llm: LLMProvider) -> tuple[JDExtract, TokenUsage]`; `rhapto.engine.prompts.extract.EXTRACT_SYSTEM: str`.

- [ ] **Step 1: Write the failing test**

`apps/api/tests/unit/test_extract.py`:

```python
import pytest

from rhapto.engine.extract import extract
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.models.jd_extract import JDExtract

JD = "ExampleCo is hiring a Data Platform Program Manager. Must have Snowflake migration experience."


async def test_extract_returns_structured_requirements() -> None:
    llm = FakeLLMProvider(
        [
            {
                "company": "ExampleCo",
                "title": "Data Platform Program Manager",
                "must_have": ["Snowflake migration"],
                "keywords": ["Snowflake", "data platform"],
            }
        ]
    )
    result, usage = await extract(JD, llm)
    assert isinstance(result, JDExtract)
    assert result.must_have == ["Snowflake migration"]
    assert usage.input_tokens == 10
    call = llm.calls[0]
    assert call.output_schema is JDExtract
    assert call.system[0].cache is True
    assert JD in call.messages[0].content


async def test_extract_rejects_empty_jd() -> None:
    with pytest.raises(ValueError, match="empty"):
        await extract("   ", FakeLLMProvider([]))
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/unit/test_extract.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.engine.extract`.

- [ ] **Step 3: Implement**

`apps/api/src/rhapto/engine/prompts/__init__.py`:

```python
"""Prompt text for the tailoring pipeline. Static prompts are marked for caching by their callers."""
```

`apps/api/src/rhapto/engine/prompts/extract.py`:

```python
EXTRACT_SYSTEM = """You are a meticulous recruiter's analyst. Read the job description and return a structured
extract. Rules:
- company and title: copy from the posting. If the company is not named, use "Unknown".
- must_have: hard requirements (skills, years, certifications) as short phrases.
- nice_to_have: preferred or bonus items as short phrases.
- keywords: 8-15 ATS-relevant terms that appear in the posting (tools, methods, domains, titles).
- location_policy: one of remote, hybrid, onsite, unspecified.
- seniority: junior, mid, senior, staff, director, executive, or unspecified.
- likely_knockouts: screening questions this posting will probably ask (authorization, relocation, clearance).
- context_tags: short lowercase tags describing the hiring context (for example: agency, consulting,
  startup, enterprise, government, internal-transfer). Empty if unclear.
Never invent requirements that are not in the text."""
```

`apps/api/src/rhapto/engine/extract.py`:

```python
from __future__ import annotations

from rhapto.engine.prompts.extract import EXTRACT_SYSTEM
from rhapto.engine.providers.llm import LLMProvider, Message, SystemBlock, TokenUsage
from rhapto.models.jd_extract import JDExtract


async def extract(jd_text: str, llm: LLMProvider) -> tuple[JDExtract, TokenUsage]:
    """LLM call 1: job description text to structured requirements."""
    if not jd_text.strip():
        raise ValueError("job description is empty")
    result = await llm.complete_structured(
        system=[SystemBlock(text=EXTRACT_SYSTEM, cache=True)],
        messages=[Message(role="user", content=f"<job_description>\n{jd_text.strip()}\n</job_description>")],
        output_schema=JDExtract,
        max_tokens=2048,
    )
    return result.value, result.usage
```

- [ ] **Step 4: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/unit/test_extract.py -v && uv run ruff check . && uv run mypy`
Expected: 2 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/engine/prompts apps/api/src/rhapto/engine/extract.py apps/api/tests/unit/test_extract.py
git commit -m "feat(engine): extract step (LLM call 1)"
```

---

### Task 6: Select step (deterministic block ranking)

**Files:**
- Create: `apps/api/src/rhapto/engine/select.py`
- Test: `apps/api/tests/unit/test_select.py`

**Interfaces:**
- Consumes: `Profile` (Task 3), `EmbeddingProvider` (Task 4), `JDExtract`, `Block`, `Track` (Task 2).
- Produces: `rhapto.engine.select.Selection(block_ids: list[str], scores: dict[str, float], excluded_block_ids: list[str], requirements_text: str)`; `SelectionConfig(top_k: dict[str,int], w_embedding=0.6, w_keywords=0.3, w_tags=0.1)`; `select_blocks(extract, profile, track, embedder, config=None) -> Selection`; `block_text(block: Block) -> str`; `cosine(a, b) -> float`; `TYPE_ORDER`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/unit/test_select.py`:

```python
from pathlib import Path

import pytest

from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.engine.select import Selection, SelectionConfig, block_text, cosine, select_blocks
from rhapto.engine.types import Profile
from rhapto.models.jd_extract import JDExtract
from rhapto.models.profile.blocks import Block, Visibility
from rhapto.models.profile.tracks import Track
from rhapto.profile.loader import load_profile


@pytest.fixture
def profile(demo_profile_dir: Path) -> Profile:
    return load_profile(demo_profile_dir)


@pytest.fixture
def extract() -> JDExtract:
    return JDExtract(
        company="ExampleCo",
        title="Data Platform Program Manager",
        must_have=["Snowflake migration", "program management across teams"],
        nice_to_have=["warehouse cost optimisation"],
        keywords=["Snowflake", "migration", "data platform", "program manager", "warehouse"],
    )


def test_cosine_basics() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_block_text_joins_fields() -> None:
    block = Block(id="b", type="achievement", org="Acme", content="Did X.", metric="12 things", tags=["a", "b"])
    assert block_text(block) == "Acme Did X. 12 things a b"


async def test_ranks_relevant_blocks_higher(profile: Profile, extract: JDExtract) -> None:
    selection = await select_blocks(extract, profile, profile.get_track("data-pm"), FakeEmbeddingProvider())
    assert isinstance(selection, Selection)
    assert selection.scores["acme-migration"] > selection.scores["cred-pmp"]
    assert "acme-migration" in selection.block_ids
    assert selection.requirements_text.startswith("Snowflake migration")


async def test_orders_by_type_then_score(profile: Profile, extract: JDExtract) -> None:
    selection = await select_blocks(extract, profile, profile.get_track("data-pm"), FakeEmbeddingProvider())
    types = [profile.block_map()[bid].type for bid in selection.block_ids]
    assert types == sorted(types, key=["role", "achievement", "project", "skill", "credential"].index)


async def test_top_k_limits_per_type(profile: Profile, extract: JDExtract) -> None:
    config = SelectionConfig(top_k={"role": 1, "achievement": 0, "project": 0, "skill": 0, "credential": 0})
    selection = await select_blocks(extract, profile, profile.get_track("data-pm"), FakeEmbeddingProvider(), config)
    assert selection.block_ids == ["acme-data-pm"]


async def test_visibility_hard_excludes_before_ranking(extract: JDExtract) -> None:
    hidden = Block(
        id="agency-secret",
        type="achievement",
        content="Snowflake migration for a client",
        visibility=Visibility(exclude_when=["agency"]),
    )
    visible = Block(id="open", type="achievement", content="Snowflake migration")
    track = Track(id="t", name="T", resume_base="all")
    profile = Profile(
        blocks=[hidden, visible],
        tracks=[track],
        bases=[{"id": "all", "name": "All", "block_ids": ["agency-secret", "open"]}],  # type: ignore[list-item]
        guardrails=[],
    )
    tagged = extract.model_copy(update={"context_tags": ["agency"]})
    selection = await select_blocks(tagged, profile, track, FakeEmbeddingProvider())
    assert selection.excluded_block_ids == ["agency-secret"]
    assert "agency-secret" not in selection.block_ids and "agency-secret" not in selection.scores
    assert selection.block_ids == ["open"]


async def test_restricts_to_track_base(profile: Profile, extract: JDExtract) -> None:
    narrow = profile.model_copy(
        update={"bases": [{"id": "data-pm", "name": "N", "block_ids": ["cred-pmp"]}, profile.bases[1]]}
    )
    narrow = Profile.model_validate(narrow.model_dump())
    selection = await select_blocks(extract, narrow, narrow.get_track("data-pm"), FakeEmbeddingProvider())
    assert selection.block_ids == ["cred-pmp"]


async def test_empty_candidates(extract: JDExtract) -> None:
    track = Track(id="t", name="T", resume_base="empty")
    profile = Profile(blocks=[], tracks=[track], bases=[{"id": "empty", "name": "E", "block_ids": []}], guardrails=[])  # type: ignore[list-item]
    selection = await select_blocks(extract, profile, track, FakeEmbeddingProvider())
    assert selection.block_ids == [] and selection.scores == {}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/unit/test_select.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.engine.select`.

- [ ] **Step 3: Implement**

`apps/api/src/rhapto/engine/select.py`:

```python
from __future__ import annotations

import math

from pydantic import BaseModel, Field

from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.engine.types import Profile
from rhapto.models.jd_extract import JDExtract
from rhapto.models.profile.blocks import Block
from rhapto.models.profile.tracks import Track

TYPE_ORDER = ["role", "achievement", "project", "skill", "credential"]
DEFAULT_TOP_K = {"role": 4, "achievement": 8, "project": 3, "skill": 1, "credential": 3}


class SelectionConfig(BaseModel):
    top_k: dict[str, int] = Field(default_factory=lambda: dict(DEFAULT_TOP_K))
    w_embedding: float = 0.6
    w_keywords: float = 0.3
    w_tags: float = 0.1


class Selection(BaseModel):
    """Blocks chosen for composition, in TYPE_ORDER then descending score."""

    block_ids: list[str]
    scores: dict[str, float]
    excluded_block_ids: list[str]
    requirements_text: str


def block_text(block: Block) -> str:
    parts = [block.role, block.org, block.content, block.metric, " ".join(block.tags)]
    return " ".join(p for p in parts if p)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


async def select_blocks(
    extract: JDExtract,
    profile: Profile,
    track: Track,
    embedder: EmbeddingProvider,
    config: SelectionConfig | None = None,
) -> Selection:
    """Deterministic ranking: embeddings + keyword hits + tag overlap, top-K per block type."""
    config = config or SelectionConfig()
    block_map = profile.block_map()
    base = profile.base_for(track)
    candidates = [block_map[bid] for bid in base.block_ids if bid in block_map]

    context = set(extract.context_tags)
    excluded = [
        b.id for b in candidates if b.visibility is not None and context & set(b.visibility.exclude_when)
    ]
    candidates = [b for b in candidates if b.id not in excluded]

    requirements_text = " ".join(extract.must_have + extract.nice_to_have + extract.keywords)
    if not candidates:
        return Selection(block_ids=[], scores={}, excluded_block_ids=excluded, requirements_text=requirements_text)

    keywords = {k.lower() for k in extract.keywords + track.keywords if k.strip()}
    vectors = await embedder.embed([requirements_text] + [block_text(b) for b in candidates])
    requirements_vec, block_vecs = vectors[0], vectors[1:]

    scores: dict[str, float] = {}
    for block, vec in zip(candidates, block_vecs, strict=True):
        text = block_text(block).lower()
        keyword_ratio = sum(1 for k in keywords if k in text) / len(keywords) if keywords else 0.0
        tags = {t.lower() for t in block.tags}
        tag_overlap = len(tags & keywords) / len(tags) if tags else 0.0
        scores[block.id] = (
            config.w_embedding * cosine(requirements_vec, vec)
            + config.w_keywords * keyword_ratio
            + config.w_tags * tag_overlap
        )

    chosen: list[str] = []
    for block_type in TYPE_ORDER:
        typed = sorted(
            (b for b in candidates if b.type == block_type), key=lambda b: (-scores[b.id], b.id)
        )
        chosen.extend(b.id for b in typed[: config.top_k.get(block_type, 0)])
    return Selection(
        block_ids=chosen, scores=scores, excluded_block_ids=excluded, requirements_text=requirements_text
    )
```

- [ ] **Step 4: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/unit/test_select.py -v && uv run ruff check . && uv run mypy`
Expected: 8 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/engine/select.py apps/api/tests/unit/test_select.py
git commit -m "feat(engine): deterministic block selection with embeddings, keywords, and visibility exclusion"
```

---
### Task 7: Guardrail framework, provenance rule, registry, and test helpers

**Files:**
- Create: `apps/api/tests/helpers.py`
- Create: `apps/api/src/rhapto/engine/guardrails/__init__.py`, `base.py`, `provenance.py`, `registry.py`
- Test: `apps/api/tests/guardrails/test_provenance.py`, `apps/api/tests/guardrails/test_registry.py`

**Interfaces:**
- Consumes: `ResumeDocument`, `ResumeEntry`, `ResumeBullet`, `Block`, `JDExtract`, `Violation`, `GuardrailReport` (Task 2); `Profile`, `EngineError` (Task 3).
- Produces (`rhapto.engine.guardrails.base`): `GuardrailContext(resume, blocks: Mapping[str, Block], selection_ids: frozenset[str], extract: JDExtract, config: Mapping[str, Any])` with `with_config(config) -> GuardrailContext`; `Rule = Callable[[GuardrailContext], list[Violation]]`; `iter_entries(resume) -> Iterator[tuple[str, ResumeEntry]]`; `iter_bullets(resume) -> Iterator[tuple[str, ResumeBullet]]` (summary bullets have paths `summary[i]`); `violation(rule, message, path, block_id=None, severity='error') -> Violation`.
- Produces (`rhapto.engine.guardrails.provenance`): `check_provenance(ctx) -> list[Violation]`, `RULE_NAME = "provenance"`.
- Produces (`rhapto.engine.guardrails.registry`): `RULES: dict[str, Rule]` (configurable rules only; later tasks add entries), `UnknownGuardrailError(EngineError)`, `run_guardrails(resume, profile, selection_ids: Iterable[str], extract) -> GuardrailReport`.
- Produces (`tests/helpers.py`): `bullet(text, source_block_id) -> ResumeBullet`, `demo_resume() -> ResumeDocument` (valid against `profile.example`), `demo_extract() -> JDExtract`.

- [ ] **Step 1: Write the test helpers**

`apps/api/tests/helpers.py`:

```python
"""Builders for a resume that is valid against profile.example. Uses fictional demo data only."""

from __future__ import annotations

from rhapto.models.jd_extract import JDExtract
from rhapto.models.resume_document import (
    ResumeBullet,
    ResumeDocument,
    ResumeEntry,
    ResumeHeader,
    ResumeSection,
)


def bullet(text: str, source_block_id: str) -> ResumeBullet:
    return ResumeBullet(text=text, source_block_id=source_block_id)


def demo_extract() -> JDExtract:
    return JDExtract(
        company="ExampleCo",
        title="Data Platform Program Manager",
        location_policy="remote",
        seniority="senior",
        must_have=["Snowflake migration", "program management across teams"],
        nice_to_have=["warehouse cost optimisation"],
        keywords=["Snowflake", "migration", "data platform", "program manager", "warehouse"],
        likely_knockouts=["work authorization"],
        context_tags=[],
    )


def demo_resume() -> ResumeDocument:
    return ResumeDocument(
        header=ResumeHeader(name="Maya Chen", email="maya.chen@example.com", location="Denver, CO"),
        summary=[
            bullet("Senior data program manager who has led cross-functional platform delivery.", "acme-data-pm")
        ],
        sections=[
            ResumeSection(
                title="Experience",
                kind="experience",
                entries=[
                    ResumeEntry(
                        source_block_id="acme-data-pm",
                        org="Acme Analytics",
                        role="Senior Data Program Manager",
                        period="2019-2025",
                        bullets=[
                            bullet("Led cross-functional delivery of the customer data platform across 4 teams.", "acme-data-pm"),
                            bullet(
                                "Owned the Snowflake migration end to end, migrating 12 pipelines with zero "
                                "downtime and cutting warehouse cost 18%.",
                                "acme-migration",
                            ),
                        ],
                    )
                ],
            ),
            ResumeSection(
                title="Projects",
                kind="projects",
                entries=[
                    ResumeEntry(
                        source_block_id="side-llm-tool",
                        org="Independent",
                        title="Open-source LLM eval harness",
                        bullets=[bullet("Built an open-source LLM eval harness.", "side-llm-tool")],
                    )
                ],
            ),
            ResumeSection(
                title="Credentials",
                kind="credentials",
                entries=[ResumeEntry(source_block_id="cred-pmp", bullets=[bullet("PMP certification.", "cred-pmp")])],
            ),
        ],
    )
```

- [ ] **Step 2: Write the failing tests**

`apps/api/tests/guardrails/test_provenance.py`:

```python
from pathlib import Path

from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.base import GuardrailContext, iter_bullets, iter_entries
from rhapto.engine.guardrails.provenance import check_provenance
from rhapto.profile.loader import load_profile


def make_ctx(demo_profile_dir: Path, resume=None, selection=None):  # type: ignore[no-untyped-def]
    profile = load_profile(demo_profile_dir)
    resume = resume or demo_resume()
    ids = frozenset(selection if selection is not None else profile.block_map())
    return GuardrailContext(resume=resume, blocks=profile.block_map(), selection_ids=ids, extract=demo_extract())


def test_iterators_yield_paths() -> None:
    resume = demo_resume()
    assert [p for p, _ in iter_entries(resume)] == [
        "sections[0].entries[0]", "sections[1].entries[0]", "sections[2].entries[0]",
    ]
    paths = [p for p, _ in iter_bullets(resume)]
    assert paths[0] == "summary[0]" and "sections[0].entries[0].bullets[1]" in paths


def test_passes_for_valid_resume(demo_profile_dir: Path) -> None:
    assert check_provenance(make_ctx(demo_profile_dir)) == []


def test_flags_bullet_with_unknown_block(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].bullets.append(bullet("Invented thing.", "ghost-block"))
    violations = check_provenance(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1
    assert violations[0].path == "sections[0].entries[0].bullets[2]"
    assert violations[0].block_id == "ghost-block" and violations[0].severity == "error"


def test_flags_entry_with_unknown_block(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].source_block_id = "ghost"
    violations = check_provenance(make_ctx(demo_profile_dir, resume))
    assert [v.path for v in violations] == ["sections[0].entries[0]"]


def test_flags_block_outside_selection(demo_profile_dir: Path) -> None:
    violations = check_provenance(make_ctx(demo_profile_dir, selection={"acme-data-pm", "acme-migration"}))
    assert {v.block_id for v in violations} == {"side-llm-tool", "cred-pmp"}
    assert all("not in the selection" in v.message for v in violations)
```

`apps/api/tests/guardrails/test_registry.py`:

```python
from pathlib import Path

import pytest
from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.registry import RULES, UnknownGuardrailError, run_guardrails
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.profile.loader import load_profile


def test_provenance_always_runs_even_with_no_configured_rules(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir).model_copy(update={"guardrails": []})
    resume = demo_resume()
    resume.summary.append(bullet("Made up.", "ghost"))
    report = run_guardrails(resume, profile, profile.block_map(), demo_extract())
    assert report.rules_run == ["provenance"]
    assert report.passed is False and report.violations[0].rule == "provenance"


def test_inactive_rules_are_skipped(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    inactive = [GuardrailRule(rule=r.rule, active=False) for r in profile.guardrails]
    profile = profile.model_copy(update={"guardrails": inactive})
    report = run_guardrails(demo_resume(), profile, profile.block_map(), demo_extract())
    assert report.rules_run == ["provenance"] and report.passed is True


def test_unknown_rule_raises(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir).model_copy(update={"guardrails": [GuardrailRule(rule="bogus")]})
    with pytest.raises(UnknownGuardrailError, match="bogus"):
        run_guardrails(demo_resume(), profile, profile.block_map(), demo_extract())


def test_registry_has_no_provenance_entry() -> None:
    assert "provenance" not in RULES
```

- [ ] **Step 3: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/guardrails -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.engine.guardrails`.

- [ ] **Step 4: Implement**

`apps/api/src/rhapto/engine/guardrails/__init__.py`:

```python
"""Deterministic guardrail rules. Each rule is a pure function GuardrailContext -> list[Violation]."""
```

`apps/api/src/rhapto/engine/guardrails/base.py`:

```python
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from rhapto.models.guardrail_report import Violation
from rhapto.models.jd_extract import JDExtract
from rhapto.models.profile.blocks import Block
from rhapto.models.resume_document import ResumeBullet, ResumeDocument, ResumeEntry


@dataclass(frozen=True)
class GuardrailContext:
    resume: ResumeDocument
    blocks: Mapping[str, Block]
    selection_ids: frozenset[str]
    extract: JDExtract
    config: Mapping[str, Any] = field(default_factory=dict)

    def with_config(self, config: Mapping[str, Any]) -> GuardrailContext:
        return replace(self, config=config)


Rule = Callable[[GuardrailContext], list[Violation]]


def iter_entries(resume: ResumeDocument) -> Iterator[tuple[str, ResumeEntry]]:
    for s, section in enumerate(resume.sections):
        for e, entry in enumerate(section.entries):
            yield f"sections[{s}].entries[{e}]", entry


def iter_bullets(resume: ResumeDocument) -> Iterator[tuple[str, ResumeBullet]]:
    for i, b in enumerate(resume.summary):
        yield f"summary[{i}]", b
    for entry_path, entry in iter_entries(resume):
        for i, b in enumerate(entry.bullets):
            yield f"{entry_path}.bullets[{i}]", b


def violation(
    rule: str,
    message: str,
    path: str,
    block_id: str | None = None,
    severity: Literal["error", "warning"] = "error",
) -> Violation:
    return Violation(rule=rule, severity=severity, message=message, path=path, block_id=block_id)
```

`apps/api/src/rhapto/engine/guardrails/provenance.py`:

```python
from __future__ import annotations

from rhapto.engine.guardrails.base import GuardrailContext, iter_bullets, iter_entries, violation
from rhapto.models.guardrail_report import Violation

RULE_NAME = "provenance"


def check_provenance(ctx: GuardrailContext) -> list[Violation]:
    """Every entry and bullet must cite a block that exists and was selected for this run."""
    out: list[Violation] = []
    cited = [(p, e.source_block_id) for p, e in iter_entries(ctx.resume)]
    cited += [(p, b.source_block_id) for p, b in iter_bullets(ctx.resume)]
    for path, block_id in cited:
        if block_id not in ctx.blocks:
            out.append(violation(RULE_NAME, f"source block {block_id!r} does not exist", path, block_id))
        elif block_id not in ctx.selection_ids:
            out.append(violation(RULE_NAME, f"source block {block_id!r} was not in the selection", path, block_id))
    return out
```

`apps/api/src/rhapto/engine/guardrails/registry.py`:

```python
from __future__ import annotations

from collections.abc import Iterable

from rhapto.engine.guardrails.base import GuardrailContext, Rule
from rhapto.engine.guardrails.provenance import RULE_NAME as PROVENANCE
from rhapto.engine.guardrails.provenance import check_provenance
from rhapto.engine.types import EngineError, Profile
from rhapto.models.guardrail_report import GuardrailReport, Violation
from rhapto.models.jd_extract import JDExtract
from rhapto.models.resume_document import ResumeDocument

# Configurable rules, keyed by the name used in guardrails.yaml. Later tasks add entries.
RULES: dict[str, Rule] = {}


class UnknownGuardrailError(EngineError):
    """guardrails.yaml names a rule this build does not ship."""


def run_guardrails(
    resume: ResumeDocument,
    profile: Profile,
    selection_ids: Iterable[str],
    extract: JDExtract,
) -> GuardrailReport:
    ctx = GuardrailContext(
        resume=resume,
        blocks=profile.block_map(),
        selection_ids=frozenset(selection_ids),
        extract=extract,
    )
    rules_run = [PROVENANCE]
    violations: list[Violation] = check_provenance(ctx)
    for rule in profile.guardrails:
        if not rule.active:
            continue
        check = RULES.get(rule.rule)
        if check is None:
            raise UnknownGuardrailError(f"unknown guardrail rule: {rule.rule}")
        violations.extend(check(ctx.with_config(rule.config)))
        rules_run.append(rule.rule)
    passed = not any(v.severity == "error" for v in violations)
    return GuardrailReport(passed=passed, rules_run=rules_run, violations=violations)
```

- [ ] **Step 5: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/guardrails -v && uv run ruff check . && uv run mypy`
Expected: 9 passed (inactive rules are skipped before the registry lookup, so the demo profile's not-yet-registered rules do not matter here). Lint and mypy clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/tests/helpers.py apps/api/tests/guardrails apps/api/src/rhapto/engine/guardrails
git commit -m "feat(guardrails): context, provenance rule (always on), and registry"
```

---
### Task 8: Guardrail rule `no-unverified-metrics`

**Files:**
- Create: `apps/api/src/rhapto/engine/guardrails/metrics.py`
- Modify: `apps/api/src/rhapto/engine/guardrails/registry.py` (add to `RULES`)
- Test: `apps/api/tests/guardrails/test_metrics.py`

**Interfaces:**
- Consumes: `GuardrailContext`, `iter_bullets`, `violation` (Task 7).
- Produces: `check_metrics(ctx) -> list[Violation]`, `RULE_NAME = "no-unverified-metrics"`, `find_numeric_tokens(text) -> list[str]`, `find_spelled_quantities(text) -> list[str]`, `normalize_number(token) -> str`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/guardrails/test_metrics.py`:

```python
from pathlib import Path

from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.base import GuardrailContext
from rhapto.engine.guardrails.metrics import (
    check_metrics,
    find_numeric_tokens,
    find_spelled_quantities,
    normalize_number,
)
from rhapto.engine.guardrails.registry import RULES
from rhapto.profile.loader import load_profile


def make_ctx(demo_profile_dir: Path, resume=None):  # type: ignore[no-untyped-def]
    profile = load_profile(demo_profile_dir)
    return GuardrailContext(
        resume=resume or demo_resume(),
        blocks=profile.block_map(),
        selection_ids=frozenset(profile.block_map()),
        extract=demo_extract(),
    )


def test_registered() -> None:
    assert RULES["no-unverified-metrics"] is check_metrics


def test_tokenizers() -> None:
    assert find_numeric_tokens("cut cost 18% and saved $2.5M across 12 pipelines, 3x faster") == [
        "18%", "$2.5M", "12", "3x",
    ]
    assert find_numeric_tokens("v2 API and iso-8601") == []
    assert [normalize_number(t) for t in ["18%", "$2.5M", "1,200", "3x"]] == ["18", "2.5", "1200", "3"]
    assert find_spelled_quantities("shrank the backlog by nearly a fifth and doubled throughput") == [
        "a fifth", "doubled",
    ]


def test_passes_when_numbers_trace_to_verified_blocks(demo_profile_dir: Path) -> None:
    assert check_metrics(make_ctx(demo_profile_dir)) == []


def test_flags_number_absent_from_source(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].bullets[1] = bullet("Cut warehouse cost 25% via Snowflake migration.", "acme-migration")
    violations = check_metrics(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1
    assert violations[0].path == "sections[0].entries[0].bullets[1]"
    assert "25%" in violations[0].message and violations[0].block_id == "acme-migration"


def test_flags_number_from_unverified_block_even_if_present_in_source(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[1].entries[0].bullets[0] = bullet("Built an LLM eval harness with 1.2k GitHub stars.", "side-llm-tool")
    violations = check_metrics(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and "not verified" in violations[0].message


def test_adversarial_spelled_out_fraction(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].bullets[1] = bullet(
        "Cut warehouse cost by nearly a fifth through the Snowflake migration.", "acme-migration"
    )
    violations = check_metrics(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and "a fifth" in violations[0].message


def test_adversarial_multiplier_and_currency(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.summary = [bullet("Delivered $2M in savings, 3x faster than plan.", "acme-migration")]
    messages = " ".join(v.message for v in check_metrics(make_ctx(demo_profile_dir, resume)))
    assert "$2M" in messages and "3x" in messages


def test_years_in_block_period_are_exempt(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.summary = [bullet("Since 2019 has led data platform programs at Acme Analytics.", "acme-data-pm")]
    assert check_metrics(make_ctx(demo_profile_dir, resume)) == []


def test_years_outside_block_period_are_not_exempt(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.summary = [bullet("Since 2015 has led data platform programs.", "acme-data-pm")]
    assert len(check_metrics(make_ctx(demo_profile_dir, resume))) == 1


def test_unknown_block_is_skipped_here(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.summary = [bullet("Saved 99%.", "ghost")]
    assert check_metrics(make_ctx(demo_profile_dir, resume)) == []  # provenance rule reports it
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/guardrails/test_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.engine.guardrails.metrics`.

- [ ] **Step 3: Implement**

`apps/api/src/rhapto/engine/guardrails/metrics.py`:

```python
from __future__ import annotations

import re

from rhapto.engine.guardrails.base import GuardrailContext, iter_bullets, violation
from rhapto.models.guardrail_report import Violation
from rhapto.models.profile.blocks import Block

RULE_NAME = "no-unverified-metrics"

# A number optionally prefixed by currency and suffixed by %, percent, k/m/b, or x. Not part of a word.
NUMERIC_RE = re.compile(
    r"(?<![\w.\-])[$€£]?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|percent|k|m|bn|b|x))?(?![\w\-])",
    re.IGNORECASE,
)
SPELLED_RE = re.compile(
    r"\b(?:half|a third|a quarter|a fifth|one[- ]third|doubl(?:e|ed|ing)|tripl(?:e|ed|ing)|quadrupled"
    r"|dozens?|hundreds?|thousands?|millions?|billions?|twice|thrice"
    r"|(?:two|three|four|five|six|seven|eight|nine|ten|hundred)fold)\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")


def find_numeric_tokens(text: str) -> list[str]:
    return [m.group(0).strip() for m in NUMERIC_RE.finditer(text)]


def find_spelled_quantities(text: str) -> list[str]:
    return [m.group(0) for m in SPELLED_RE.finditer(text)]


def normalize_number(token: str) -> str:
    return re.sub(r"[^\d.]", "", token)


def _source_text(block: Block) -> str:
    return f"{block.metric or ''} {block.content}"


def _is_exempt_year(normalized: str, block: Block) -> bool:
    return bool(YEAR_RE.match(normalized)) and block.period is not None and normalized in block.period


def check_metrics(ctx: GuardrailContext) -> list[Violation]:
    """Every number or spelled-out quantity must appear in a verified source block."""
    out: list[Violation] = []
    for path, bullet in iter_bullets(ctx.resume):
        block = ctx.blocks.get(bullet.source_block_id)
        if block is None:
            continue
        source = _source_text(block)
        source_numbers = {normalize_number(t) for t in find_numeric_tokens(source)}
        source_lower = source.casefold()
        offending: list[str] = []
        for token in find_numeric_tokens(bullet.text):
            normalized = normalize_number(token)
            if _is_exempt_year(normalized, block):
                continue
            if not block.verified or normalized not in source_numbers:
                offending.append(token)
        for phrase in find_spelled_quantities(bullet.text):
            if not block.verified or phrase.casefold() not in source_lower:
                offending.append(phrase)
        if not offending:
            continue
        if not block.verified:
            message = f"block {block.id!r} is not verified but the bullet contains metric(s): {', '.join(offending)}"
        else:
            message = f"metric(s) not found in verified block {block.id!r}: {', '.join(offending)}"
        out.append(violation(RULE_NAME, message, path, block.id))
    return out
```

Register it in `apps/api/src/rhapto/engine/guardrails/registry.py`:

```python
from rhapto.engine.guardrails.metrics import RULE_NAME as METRICS
from rhapto.engine.guardrails.metrics import check_metrics

RULES: dict[str, Rule] = {METRICS: check_metrics}
```

- [ ] **Step 4: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/guardrails -v && uv run ruff check . && uv run mypy`
Expected: all guardrail tests pass (11 new), clean. If `test_tokenizers` fails on a boundary case, adjust `NUMERIC_RE` lookarounds, never the test expectations.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/engine/guardrails apps/api/tests/guardrails/test_metrics.py
git commit -m "feat(guardrails): no-unverified-metrics rule with adversarial cases"
```

---
### Task 9: Guardrail rule `no-invented-entities`

**Files:**
- Create: `apps/api/src/rhapto/engine/guardrails/entities.py`
- Modify: `apps/api/src/rhapto/engine/guardrails/registry.py` (add to `RULES`)
- Test: `apps/api/tests/guardrails/test_entities.py`

**Interfaces:**
- Consumes: `GuardrailContext`, `iter_entries`, `violation` (Task 7).
- Produces: `check_entities(ctx) -> list[Violation]`, `RULE_NAME = "no-invented-entities"`, `normalize_entity(text) -> str`. Config key: `fuzzy_threshold` (int, default 90).

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/guardrails/test_entities.py`:

```python
from pathlib import Path

from helpers import demo_extract, demo_resume

from rhapto.engine.guardrails.base import GuardrailContext
from rhapto.engine.guardrails.entities import check_entities, normalize_entity
from rhapto.engine.guardrails.registry import RULES
from rhapto.profile.loader import load_profile


def make_ctx(demo_profile_dir: Path, resume=None, config=None):  # type: ignore[no-untyped-def]
    profile = load_profile(demo_profile_dir)
    return GuardrailContext(
        resume=resume or demo_resume(),
        blocks=profile.block_map(),
        selection_ids=frozenset(profile.block_map()),
        extract=demo_extract(),
        config=config or {},
    )


def test_registered() -> None:
    assert RULES["no-invented-entities"] is check_entities


def test_normalize_handles_dashes_case_and_spaces() -> None:
    assert normalize_entity("  Acme   Analytics ") == "acme analytics"
    assert normalize_entity("2019–2025") == "2019-2025"


def test_passes_for_matching_entities(demo_profile_dir: Path) -> None:
    assert check_entities(make_ctx(demo_profile_dir)) == []


def test_en_dash_period_matches(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].period = "2019–2025"
    assert check_entities(make_ctx(demo_profile_dir, resume)) == []


def test_flags_inflated_title(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].role = "Director of Data Programs"
    violations = check_entities(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1
    assert violations[0].path == "sections[0].entries[0]" and "role" in violations[0].message


def test_flags_org_suffix_below_threshold_but_allows_with_lower_threshold(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].org = "Acme Analytics Inc"
    assert len(check_entities(make_ctx(demo_profile_dir, resume))) == 1
    assert check_entities(make_ctx(demo_profile_dir, resume, {"fuzzy_threshold": 80})) == []


def test_flags_changed_period(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].period = "2018-2025"
    violations = check_entities(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and "period" in violations[0].message


def test_flags_entity_the_block_does_not_have(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[2].entries[0].org = "Project Management Institute"  # cred-pmp has no org
    violations = check_entities(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and violations[0].block_id == "cred-pmp"


def test_unknown_block_is_skipped_here(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].source_block_id = "ghost"
    assert check_entities(make_ctx(demo_profile_dir, resume)) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/guardrails/test_entities.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.engine.guardrails.entities`.

- [ ] **Step 3: Implement**

`apps/api/src/rhapto/engine/guardrails/entities.py`:

```python
from __future__ import annotations

import re

from rapidfuzz import fuzz

from rhapto.engine.guardrails.base import GuardrailContext, iter_entries, violation
from rhapto.models.guardrail_report import Violation

RULE_NAME = "no-invented-entities"
DEFAULT_THRESHOLD = 90
DASHES = re.compile(r"[‒–—−]")


def normalize_entity(text: str) -> str:
    return re.sub(r"\s+", " ", DASHES.sub("-", text)).strip().casefold()


def _fuzzy_match(candidate: str, source: str, threshold: int) -> bool:
    a, b = normalize_entity(candidate), normalize_entity(source)
    return a == b or fuzz.ratio(a, b) >= threshold


def check_entities(ctx: GuardrailContext) -> list[Violation]:
    """Entry org, role, and period must match the entry's source block (fuzzy for org/role, exact for period)."""
    threshold = int(ctx.config.get("fuzzy_threshold", DEFAULT_THRESHOLD))
    out: list[Violation] = []
    for path, entry in iter_entries(ctx.resume):
        block = ctx.blocks.get(entry.source_block_id)
        if block is None:
            continue
        for field_name in ("org", "role"):
            value = getattr(entry, field_name)
            if value is None:
                continue
            source = getattr(block, field_name)
            if source is None or not _fuzzy_match(value, source, threshold):
                out.append(
                    violation(
                        RULE_NAME,
                        f"{field_name} {value!r} does not match block {block.id!r} ({source!r})",
                        path,
                        block.id,
                    )
                )
        if entry.period is not None and (
            block.period is None or normalize_entity(entry.period) != normalize_entity(block.period)
        ):
            out.append(
                violation(
                    RULE_NAME,
                    f"period {entry.period!r} does not match block {block.id!r} ({block.period!r})",
                    path,
                    block.id,
                )
            )
    return out
```

Register it in `registry.py`:

```python
from rhapto.engine.guardrails.entities import RULE_NAME as ENTITIES
from rhapto.engine.guardrails.entities import check_entities

RULES: dict[str, Rule] = {METRICS: check_metrics, ENTITIES: check_entities}
```

- [ ] **Step 4: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/guardrails -v && uv run ruff check . && uv run mypy`
Expected: all pass (10 new), clean.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/engine/guardrails apps/api/tests/guardrails/test_entities.py
git commit -m "feat(guardrails): no-invented-entities rule with fuzzy org/role and exact period checks"
```

---
### Task 10: Guardrail rule `date-consistency`

**Files:**
- Create: `apps/api/src/rhapto/engine/guardrails/dates.py`
- Modify: `apps/api/src/rhapto/engine/guardrails/registry.py` (add to `RULES`)
- Test: `apps/api/tests/guardrails/test_dates.py`

**Interfaces:**
- Consumes: `GuardrailContext`, `violation` (Task 7).
- Produces: `check_dates(ctx) -> list[Violation]`, `RULE_NAME = "date-consistency"`, `parse_period(text: str) -> tuple[int, int] | None` (end is `PRESENT = 9999` for open ranges).

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/guardrails/test_dates.py`:

```python
from pathlib import Path

from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.base import GuardrailContext
from rhapto.engine.guardrails.dates import PRESENT, check_dates, parse_period
from rhapto.engine.guardrails.registry import RULES
from rhapto.models.profile.blocks import Block
from rhapto.models.resume_document import ResumeEntry
from rhapto.profile.loader import load_profile


def make_ctx(demo_profile_dir: Path, resume=None, extra_blocks=()):  # type: ignore[no-untyped-def]
    profile = load_profile(demo_profile_dir)
    blocks = profile.block_map() | {b.id: b for b in extra_blocks}
    return GuardrailContext(
        resume=resume or demo_resume(),
        blocks=blocks,
        selection_ids=frozenset(blocks),
        extract=demo_extract(),
    )


def _second_role(concurrent: bool = False, period: str = "2022-2024") -> tuple[Block, ResumeEntry]:
    block = Block(
        id="beta-role", type="role", org="Beta Labs", role="Advisor", period=period, content="Advised.", concurrent=concurrent
    )
    entry = ResumeEntry(
        source_block_id="beta-role", org="Beta Labs", role="Advisor", period=period, bullets=[bullet("Advised.", "beta-role")]
    )
    return block, entry


def test_registered() -> None:
    assert RULES["date-consistency"] is check_dates


def test_parse_period_formats() -> None:
    assert parse_period("2019-2025") == (2019, 2025)
    assert parse_period("2019 – 2025") == (2019, 2025)
    assert parse_period("2019 to 2025") == (2019, 2025)
    assert parse_period("2021-Present") == (2021, PRESENT)
    assert parse_period("2023") == (2023, 2023)
    assert parse_period("Spring 2020") is None
    assert parse_period("") is None


def test_passes_for_demo(demo_profile_dir: Path) -> None:
    assert check_dates(make_ctx(demo_profile_dir)) == []


def test_flags_unparseable_period(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].period = "Spring 2020"
    violations = check_dates(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and "unparseable" in violations[0].message


def test_flags_reversed_range(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].period = "2025-2019"
    violations = check_dates(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and "ends before it starts" in violations[0].message


def test_flags_overlapping_roles(demo_profile_dir: Path) -> None:
    block, entry = _second_role()
    resume = demo_resume()
    resume.sections[0].entries.append(entry)
    violations = check_dates(make_ctx(demo_profile_dir, resume, [block]))
    assert len(violations) == 1 and "overlaps" in violations[0].message
    assert violations[0].path == "sections[0].entries[1]"


def test_allows_overlap_when_a_block_is_concurrent(demo_profile_dir: Path) -> None:
    block, entry = _second_role(concurrent=True)
    resume = demo_resume()
    resume.sections[0].entries.append(entry)
    assert check_dates(make_ctx(demo_profile_dir, resume, [block])) == []


def test_adjacent_years_do_not_overlap(demo_profile_dir: Path) -> None:
    block, entry = _second_role(period="2025-Present")
    resume = demo_resume()
    resume.sections[0].entries.append(entry)
    assert check_dates(make_ctx(demo_profile_dir, resume, [block])) == []


def test_projects_section_is_not_checked_for_overlap(demo_profile_dir: Path) -> None:
    block, entry = _second_role()
    resume = demo_resume()
    resume.sections[1].entries.append(entry)  # projects section
    assert check_dates(make_ctx(demo_profile_dir, resume, [block])) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/guardrails/test_dates.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.engine.guardrails.dates`.

- [ ] **Step 3: Implement**

`apps/api/src/rhapto/engine/guardrails/dates.py`:

```python
from __future__ import annotations

import re

from rhapto.engine.guardrails.base import GuardrailContext, iter_entries, violation
from rhapto.models.guardrail_report import Violation

RULE_NAME = "date-consistency"
PRESENT = 9999
PERIOD_RE = re.compile(
    r"^\s*(\d{4})\s*(?:(?:[-‒–—−]|to)\s*(\d{4}|present|current|now))?\s*$", re.IGNORECASE
)


def parse_period(text: str) -> tuple[int, int] | None:
    match = PERIOD_RE.match(text or "")
    if not match:
        return None
    start = int(match.group(1))
    end_raw = match.group(2)
    if end_raw is None:
        return start, start
    end = PRESENT if not end_raw.isdigit() else int(end_raw)
    return start, end


def check_dates(ctx: GuardrailContext) -> list[Violation]:
    """Periods parse and are ordered; experience entries do not overlap unless a block is concurrent."""
    out: list[Violation] = []
    experience: list[tuple[str, str, int, int, bool]] = []  # path, block_id, start, end, concurrent
    for path, entry in iter_entries(ctx.resume):
        if entry.period is None:
            continue
        parsed = parse_period(entry.period)
        if parsed is None:
            out.append(violation(RULE_NAME, f"unparseable period {entry.period!r}", path, entry.source_block_id))
            continue
        start, end = parsed
        if end < start:
            out.append(
                violation(RULE_NAME, f"period {entry.period!r} ends before it starts", path, entry.source_block_id)
            )
            continue
        section_index = int(path.split("[")[1].split("]")[0])
        if ctx.resume.sections[section_index].kind == "experience":
            block = ctx.blocks.get(entry.source_block_id)
            concurrent = bool(block and block.concurrent)
            experience.append((path, entry.source_block_id, start, end, concurrent))

    for i, (path_a, id_a, start_a, end_a, conc_a) in enumerate(experience):
        for path_b, id_b, start_b, end_b, conc_b in experience[i + 1 :]:
            if conc_a or conc_b:
                continue
            if start_a < end_b and start_b < end_a:
                out.append(
                    violation(RULE_NAME, f"period of {id_b!r} overlaps {id_a!r} ({path_a})", path_b, id_b)
                )
    return out
```

Register it in `registry.py`:

```python
from rhapto.engine.guardrails.dates import RULE_NAME as DATES
from rhapto.engine.guardrails.dates import check_dates

RULES: dict[str, Rule] = {METRICS: check_metrics, ENTITIES: check_entities, DATES: check_dates}
```

- [ ] **Step 4: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/guardrails -v && uv run ruff check . && uv run mypy`
Expected: all pass (9 new), clean.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/engine/guardrails apps/api/tests/guardrails/test_dates.py
git commit -m "feat(guardrails): date-consistency rule"
```

---
### Task 11: Guardrail rules `attribution` and `visibility-context`

**Files:**
- Create: `apps/api/src/rhapto/engine/guardrails/attribution.py`, `apps/api/src/rhapto/engine/guardrails/visibility.py`
- Modify: `apps/api/src/rhapto/engine/guardrails/registry.py` (add both to `RULES`)
- Test: `apps/api/tests/guardrails/test_attribution.py`, `apps/api/tests/guardrails/test_visibility.py`

**Interfaces:**
- Consumes: `GuardrailContext`, `iter_entries`, `iter_bullets`, `violation` (Task 7).
- Produces: `check_attribution(ctx)`, `RULE_NAME = "attribution"`; `check_visibility(ctx)`, `RULE_NAME = "visibility-context"`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/guardrails/test_attribution.py`:

```python
from pathlib import Path

from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.attribution import check_attribution
from rhapto.engine.guardrails.base import GuardrailContext
from rhapto.engine.guardrails.registry import RULES
from rhapto.models.profile.blocks import Block
from rhapto.models.resume_document import ResumeEntry
from rhapto.profile.loader import load_profile

STUDIO = Block(
    id="studio-app",
    type="project",
    org="Example Studio",
    content="Shipped a scheduling app for a retail client.",
    attribution="built at Example Studio",
)


def make_ctx(demo_profile_dir: Path, resume):  # type: ignore[no-untyped-def]
    profile = load_profile(demo_profile_dir)
    blocks = profile.block_map() | {STUDIO.id: STUDIO}
    return GuardrailContext(resume=resume, blocks=blocks, selection_ids=frozenset(blocks), extract=demo_extract())


def _project_entry(text: str) -> ResumeEntry:
    return ResumeEntry(source_block_id="studio-app", org="Example Studio", title="Scheduling app", bullets=[bullet(text, "studio-app")])


def test_registered() -> None:
    assert RULES["attribution"] is check_attribution


def test_passes_when_no_block_has_attribution(demo_profile_dir: Path) -> None:
    assert check_attribution(make_ctx(demo_profile_dir, demo_resume())) == []


def test_passes_when_entry_carries_attribution(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[1].entries.append(_project_entry("Shipped a scheduling app, built at Example Studio."))
    assert check_attribution(make_ctx(demo_profile_dir, resume)) == []


def test_flags_entry_missing_attribution(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[1].entries.append(_project_entry("Shipped a scheduling app deployed at a retail client."))
    violations = check_attribution(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and violations[0].path == "sections[1].entries[1]"
    assert "built at Example Studio" in violations[0].message


def test_flags_leaked_bullet_under_another_entry(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].bullets.append(bullet("Shipped a scheduling app for a retail client.", "studio-app"))
    violations = check_attribution(make_ctx(demo_profile_dir, resume))
    assert [v.path for v in violations] == ["sections[0].entries[0].bullets[2]"]


def test_flags_summary_bullet_without_attribution(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.summary.append(bullet("Shipped a retail scheduling app.", "studio-app"))
    assert [v.path for v in check_attribution(make_ctx(demo_profile_dir, resume))] == ["summary[1]"]


def test_attribution_match_is_case_insensitive(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.summary.append(bullet("Shipped a retail scheduling app, Built At Example Studio.", "studio-app"))
    assert check_attribution(make_ctx(demo_profile_dir, resume)) == []
```

`apps/api/tests/guardrails/test_visibility.py`:

```python
from pathlib import Path

from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.base import GuardrailContext
from rhapto.engine.guardrails.registry import RULES
from rhapto.engine.guardrails.visibility import check_visibility
from rhapto.models.profile.blocks import Block, Visibility
from rhapto.models.resume_document import ResumeEntry
from rhapto.profile.loader import load_profile

SECRET = Block(
    id="agency-secret",
    type="achievement",
    org="Acme Analytics",
    content="Delivered a client migration.",
    visibility=Visibility(exclude_when=["agency", "internal-transfer"]),
)


def make_ctx(demo_profile_dir: Path, resume, context_tags):  # type: ignore[no-untyped-def]
    profile = load_profile(demo_profile_dir)
    blocks = profile.block_map() | {SECRET.id: SECRET}
    extract = demo_extract().model_copy(update={"context_tags": context_tags})
    return GuardrailContext(resume=resume, blocks=blocks, selection_ids=frozenset(blocks), extract=extract)


def test_registered() -> None:
    assert RULES["visibility-context"] is check_visibility


def test_passes_when_context_does_not_match(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].bullets.append(bullet("Delivered a client migration.", "agency-secret"))
    assert check_visibility(make_ctx(demo_profile_dir, resume, ["startup"])) == []


def test_flags_bullet_when_context_matches(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].bullets.append(bullet("Delivered a client migration.", "agency-secret"))
    violations = check_visibility(make_ctx(demo_profile_dir, resume, ["agency"]))
    assert len(violations) == 1
    assert violations[0].path == "sections[0].entries[0].bullets[2]" and "agency" in violations[0].message


def test_flags_entry_when_context_matches(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries.append(ResumeEntry(source_block_id="agency-secret", org="Acme Analytics"))
    violations = check_visibility(make_ctx(demo_profile_dir, resume, ["internal-transfer"]))
    assert [v.path for v in violations] == ["sections[0].entries[1]"]


def test_passes_for_demo_without_visibility(demo_profile_dir: Path) -> None:
    assert check_visibility(make_ctx(demo_profile_dir, demo_resume(), ["agency"])) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/guardrails/test_attribution.py tests/guardrails/test_visibility.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`apps/api/src/rhapto/engine/guardrails/attribution.py`:

```python
from __future__ import annotations

from rhapto.engine.guardrails.base import GuardrailContext, iter_entries, violation
from rhapto.models.guardrail_report import Violation

RULE_NAME = "attribution"


def _missing(attribution: str, text: str) -> bool:
    return attribution.casefold() not in text.casefold()


def check_attribution(ctx: GuardrailContext) -> list[Violation]:
    """Blocks with an attribution phrase must keep it wherever they appear."""
    out: list[Violation] = []
    for i, bullet in enumerate(ctx.resume.summary):
        block = ctx.blocks.get(bullet.source_block_id)
        if block and block.attribution and _missing(block.attribution, bullet.text):
            out.append(_violation(block.attribution, f"summary[{i}]", block.id))
    for path, entry in iter_entries(ctx.resume):
        entry_block = ctx.blocks.get(entry.source_block_id)
        if entry_block and entry_block.attribution:
            text = " ".join(filter(None, [entry.title, entry.org, entry.role, *(b.text for b in entry.bullets)]))
            if _missing(entry_block.attribution, text):
                out.append(_violation(entry_block.attribution, path, entry_block.id))
        for i, bullet in enumerate(entry.bullets):
            if bullet.source_block_id == entry.source_block_id:
                continue  # covered by the entry-level check
            block = ctx.blocks.get(bullet.source_block_id)
            if block and block.attribution and _missing(block.attribution, bullet.text):
                out.append(_violation(block.attribution, f"{path}.bullets[{i}]", block.id))
    return out


def _violation(attribution: str, path: str, block_id: str) -> Violation:
    return violation(RULE_NAME, f"required attribution {attribution!r} is missing", path, block_id)
```

`apps/api/src/rhapto/engine/guardrails/visibility.py`:

```python
from __future__ import annotations

from rhapto.engine.guardrails.base import GuardrailContext, iter_bullets, iter_entries, violation
from rhapto.models.guardrail_report import Violation

RULE_NAME = "visibility-context"


def check_visibility(ctx: GuardrailContext) -> list[Violation]:
    """No entry or bullet may derive from a block excluded by the JD's context tags."""
    context = set(ctx.extract.context_tags)
    if not context:
        return []
    out: list[Violation] = []
    cited = [(p, e.source_block_id) for p, e in iter_entries(ctx.resume)]
    cited += [(p, b.source_block_id) for p, b in iter_bullets(ctx.resume)]
    for path, block_id in cited:
        block = ctx.blocks.get(block_id)
        if block is None or block.visibility is None:
            continue
        hits = sorted(context & set(block.visibility.exclude_when))
        if hits:
            out.append(
                violation(RULE_NAME, f"block {block_id!r} is excluded for context {', '.join(hits)}", path, block_id)
            )
    return out
```

Final `registry.py` `RULES` (with imports for each):

```python
from rhapto.engine.guardrails.attribution import RULE_NAME as ATTRIBUTION
from rhapto.engine.guardrails.attribution import check_attribution
from rhapto.engine.guardrails.visibility import RULE_NAME as VISIBILITY
from rhapto.engine.guardrails.visibility import check_visibility

RULES: dict[str, Rule] = {
    METRICS: check_metrics,
    ENTITIES: check_entities,
    DATES: check_dates,
    ATTRIBUTION: check_attribution,
    VISIBILITY: check_visibility,
}
```

- [ ] **Step 4: Run all tests, lint, and type-check**

Run: `cd apps/api && uv run pytest -v && uv run ruff check . && uv run mypy`
Expected: all pass, clean.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/engine/guardrails apps/api/tests/guardrails
git commit -m "feat(guardrails): attribution and visibility-context rules; registry complete"
```

---
### Task 12: Compose and repair steps (LLM calls 2 and 3)

**Files:**
- Create: `apps/api/src/rhapto/engine/prompts/compose.py`, `apps/api/src/rhapto/engine/compose.py`, `apps/api/src/rhapto/engine/repair.py`
- Test: `apps/api/tests/unit/test_compose.py`, `apps/api/tests/unit/test_repair.py`

**Interfaces:**
- Consumes: `Profile` (Task 3); `LLMProvider`, `SystemBlock`, `Message`, `TokenUsage` (Task 4); `Selection` (Task 6); `ResumeDocument`, `ResumeBullet`, `ResumeSection`, `ResumeHeader`, `GuardrailReport`, `ApplicationPackage`, `Track` (Task 2).
- Produces (`rhapto.engine.compose`): `HEADER_KEYS`, `ComposeOutput(summary: list[ResumeBullet], sections: list[ResumeSection], cover_note: str, change_log: str, answers: dict[str, str])`, `build_header(answers: dict[str, str]) -> ResumeHeader`, `application_answers(answers) -> dict[str, str]` (answers minus header keys), `build_system_blocks(profile, track) -> list[SystemBlock]`, `build_user_message(extract, selection, answers, feedback=None, previous=None) -> str`, `compose(extract, profile, track, selection, llm, feedback=None, previous=None) -> tuple[ComposeOutput, TokenUsage]`, `assemble_resume(output, profile) -> ResumeDocument`.
- Produces (`rhapto.engine.repair`): `repair(previous: ComposeOutput, report: GuardrailReport, system: list[SystemBlock], llm) -> tuple[ComposeOutput, TokenUsage]`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/unit/test_compose.py`:

```python
import json
from pathlib import Path

from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.compose import (
    ComposeOutput,
    application_answers,
    assemble_resume,
    build_header,
    build_system_blocks,
    build_user_message,
    compose,
)
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.engine.select import Selection
from rhapto.profile.loader import load_profile


def _selection() -> Selection:
    return Selection(
        block_ids=["acme-data-pm", "acme-migration", "side-llm-tool", "cred-pmp"],
        scores={}, excluded_block_ids=[], requirements_text="Snowflake",
    )


def _output() -> ComposeOutput:
    resume = demo_resume()
    return ComposeOutput(
        summary=resume.summary, sections=resume.sections, cover_note="Dear team, ...",
        change_log="Emphasised Snowflake migration.", answers={"why_this_company": "Because data."},
    )


def test_build_header_from_answers() -> None:
    header = build_header({"name": "Maya Chen", "email": "m@example.com", "links": "a.example, b.example"})
    assert header.name == "Maya Chen" and header.email == "m@example.com"
    assert header.links == ["a.example", "b.example"] and header.phone is None
    assert build_header({}).name == "Candidate"


def test_application_answers_excludes_header_keys() -> None:
    answers = application_answers({"name": "x", "email": "e", "notice_period": "2 weeks"})
    assert answers == {"notice_period": "2 weeks"}


def test_system_blocks_cache_rules_and_base_blocks(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    blocks = build_system_blocks(profile, profile.get_track("data-pm"))
    assert blocks[0].cache is True and "source_block_id" in blocks[0].text
    assert '"id": "acme-migration"' in blocks[0].text
    assert "Data Program Management" in blocks[1].text and blocks[1].cache is False


def test_user_message_contains_job_selection_answers_feedback_previous() -> None:
    message = build_user_message(
        demo_extract(), _selection(), {"notice_period": "2 weeks"},
        feedback="lean harder on migration", previous=demo_resume(),
    )
    assert "Data Platform Program Manager" in message
    assert json.dumps(_selection().block_ids) in message
    assert "notice_period" in message and "lean harder on migration" in message
    assert "<previous_resume>" in message and "Acme Analytics" in message
    assert "<feedback>" not in build_user_message(demo_extract(), _selection(), {})


async def test_compose_calls_llm_with_schema_and_returns_output(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    llm = FakeLLMProvider([_output()])
    output, usage = await compose(demo_extract(), profile, profile.get_track("data-pm"), _selection(), llm)
    assert output.cover_note.startswith("Dear") and usage.output_tokens == 5
    call = llm.calls[0]
    assert call.output_schema is ComposeOutput and call.system[0].cache is True
    assert call.messages[0].role == "user"


def test_assemble_resume_adds_header(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    resume = assemble_resume(_output(), profile)
    assert resume.header.name == "Maya Chen" and resume.header.email == "maya.chen@example.com"
    assert resume.sections[0].entries[0].bullets[0] == bullet(
        "Led cross-functional delivery of the customer data platform across 4 teams.", "acme-data-pm"
    )
```

`apps/api/tests/unit/test_repair.py`:

```python
from helpers import demo_resume

from rhapto.engine.compose import ComposeOutput
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.engine.providers.llm import SystemBlock
from rhapto.engine.repair import repair
from rhapto.models.guardrail_report import GuardrailReport, Violation


async def test_repair_sends_violations_and_previous_output() -> None:
    resume = demo_resume()
    previous = ComposeOutput(summary=resume.summary, sections=resume.sections, cover_note="c", change_log="l", answers={})
    fixed = previous.model_copy(update={"cover_note": "fixed"})
    report = GuardrailReport(
        passed=False,
        rules_run=["provenance", "no-unverified-metrics"],
        violations=[
            Violation(
                rule="no-unverified-metrics", severity="error", path="sections[0].entries[0].bullets[1]",
                message="metric(s) not found in verified block 'acme-migration': 25%", block_id="acme-migration",
            )
        ],
    )
    llm = FakeLLMProvider([fixed])
    system = [SystemBlock(text="rules", cache=True)]
    output, usage = await repair(previous, report, system, llm)
    assert output.cover_note == "fixed" and usage.input_tokens == 10
    call = llm.calls[0]
    assert call.system == system and call.output_schema is ComposeOutput
    body = call.messages[0].content
    assert "sections[0].entries[0].bullets[1]" in body and "25%" in body and "<previous_output>" in body
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/unit/test_compose.py tests/unit/test_repair.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.engine.compose`.

- [ ] **Step 3: Implement the prompt**

`apps/api/src/rhapto/engine/prompts/compose.py`:

```python
COMPOSE_RULES = """You are Rhapto's resume composer. You tailor a resume for one job using ONLY the resume
blocks listed in <blocks>. The user message names which of those blocks were selected for this job.

Hard rules (a validator enforces every one of them and will reject your output):
1. Every bullet and every entry cites, in source_block_id, the id of the block it came from. Cite only ids
   listed in <selected_block_ids>. Never cite anything else.
2. Never introduce a number, percentage, currency amount, multiplier, or spelled-out quantity (half, a
   third, doubled, dozens) that does not appear verbatim in the cited block's metric or content. Blocks with
   verified=false must yield bullets with no numbers at all.
3. Copy organisation names, role titles, and periods exactly from the block. Never inflate a title.
4. If a block has an attribution phrase, every bullet from it must contain that phrase verbatim.
5. Rephrase and reorder freely to match the job's requirements and keywords. Do not invent experience.

Structure:
- summary: 1-3 bullets, each citing a block.
- sections, in this order when non-empty, with these exact titles and kinds:
  Experience (kind "experience"): one entry per role block with org, role, period copied from the block;
    achievement bullets grouped under the role entry with the same org.
  Projects (kind "projects"): one entry per project block with title and org.
  Skills (kind "skills"): one entry per skill block with a single bullet.
  Credentials (kind "credentials"): one entry per credential block with a single bullet.
- cover_note: 120-180 words, first person, specific to this job, obeying rule 2.
- change_log: 3-6 short lines on what you emphasised and why.
- answers: a short drafted answer for every key given in <answers>, plus "why_this_company".
When <feedback> is present, apply it to <previous_resume> rather than starting over."""
```

- [ ] **Step 4: Implement compose**

`apps/api/src/rhapto/engine/compose.py`:

```python
from __future__ import annotations

import json

from pydantic import BaseModel, Field

from rhapto.engine.prompts.compose import COMPOSE_RULES
from rhapto.engine.providers.llm import LLMProvider, Message, SystemBlock, TokenUsage
from rhapto.engine.select import Selection
from rhapto.engine.types import Profile
from rhapto.models.jd_extract import JDExtract
from rhapto.models.profile.tracks import Track
from rhapto.models.resume_document import ResumeBullet, ResumeDocument, ResumeHeader, ResumeSection

HEADER_KEYS = frozenset({"name", "email", "phone", "location", "links"})


class ComposeOutput(BaseModel):
    """Exactly what the LLM returns. The header is added deterministically by assemble_resume."""

    summary: list[ResumeBullet] = Field(default_factory=list)
    sections: list[ResumeSection]
    cover_note: str
    change_log: str
    answers: dict[str, str] = Field(default_factory=dict)


def build_header(answers: dict[str, str]) -> ResumeHeader:
    links = [s.strip() for s in answers.get("links", "").split(",") if s.strip()]
    return ResumeHeader(
        name=answers.get("name") or "Candidate",
        email=answers.get("email"),
        phone=answers.get("phone"),
        location=answers.get("location"),
        links=links,
    )


def application_answers(answers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in answers.items() if k not in HEADER_KEYS}


def build_system_blocks(profile: Profile, track: Track) -> list[SystemBlock]:
    """Cached block = rules + every block in the track's base (stable per track, so cache hits across JDs)."""
    block_map = profile.block_map()
    base = profile.base_for(track)
    blocks_json = json.dumps(
        [block_map[bid].model_dump(mode="json", exclude_none=True) for bid in base.block_ids if bid in block_map],
        indent=1,
    )
    static = f"{COMPOSE_RULES}\n\n<blocks>\n{blocks_json}\n</blocks>"
    dynamic = f"Track: {track.name}. {track.description or ''}".strip()
    return [SystemBlock(text=static, cache=True), SystemBlock(text=dynamic)]


def build_user_message(
    extract: JDExtract,
    selection: Selection,
    answers: dict[str, str],
    feedback: str | None = None,
    previous: ResumeDocument | None = None,
) -> str:
    parts = [
        f"<job>\n{extract.model_dump_json(indent=1)}\n</job>",
        f"<selected_block_ids>\n{json.dumps(selection.block_ids)}\n</selected_block_ids>",
        f"<answers>\n{json.dumps(application_answers(answers), indent=1)}\n</answers>",
    ]
    if previous is not None:
        parts.append(f"<previous_resume>\n{previous.model_dump_json(indent=1, exclude_none=True)}\n</previous_resume>")
    if feedback:
        parts.append(f"<feedback>\n{feedback.strip()}\n</feedback>")
    return "\n\n".join(parts)


async def compose(
    extract: JDExtract,
    profile: Profile,
    track: Track,
    selection: Selection,
    llm: LLMProvider,
    feedback: str | None = None,
    previous: ResumeDocument | None = None,
) -> tuple[ComposeOutput, TokenUsage]:
    """LLM call 2: selected blocks + JD extract to resume sections, cover note, change log, answers."""
    result = await llm.complete_structured(
        system=build_system_blocks(profile, track),
        messages=[Message(role="user", content=build_user_message(extract, selection, profile.answers, feedback, previous))],
        output_schema=ComposeOutput,
        max_tokens=8192,
    )
    return result.value, result.usage


def assemble_resume(output: ComposeOutput, profile: Profile) -> ResumeDocument:
    return ResumeDocument(header=build_header(profile.answers), summary=output.summary, sections=output.sections)
```

- [ ] **Step 5: Implement repair**

`apps/api/src/rhapto/engine/repair.py`:

```python
from __future__ import annotations

from rhapto.engine.compose import ComposeOutput
from rhapto.engine.providers.llm import LLMProvider, Message, SystemBlock, TokenUsage
from rhapto.models.guardrail_report import GuardrailReport

REPAIR_INSTRUCTIONS = """Your previous output violated the guardrails listed in <violations>. Return the complete
corrected output. Fix every violation: remove any number you cannot source verbatim from the cited block, restore
exact organisation names, titles, and periods, add missing attribution phrases, and drop bullets whose block is
not allowed. Do not introduce new block ids."""


async def repair(
    previous: ComposeOutput,
    report: GuardrailReport,
    system: list[SystemBlock],
    llm: LLMProvider,
) -> tuple[ComposeOutput, TokenUsage]:
    """LLM call 3: one retry with the violations spelled out. Uses the same cached system blocks as compose."""
    violations = "\n".join(f"- {v.path} [{v.rule}]: {v.message}" for v in report.violations)
    content = (
        f"{REPAIR_INSTRUCTIONS}\n\n<previous_output>\n{previous.model_dump_json(indent=1)}\n</previous_output>"
        f"\n\n<violations>\n{violations}\n</violations>"
    )
    result = await llm.complete_structured(
        system=system, messages=[Message(role="user", content=content)], output_schema=ComposeOutput, max_tokens=8192
    )
    return result.value, result.usage
```

- [ ] **Step 6: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/unit/test_compose.py tests/unit/test_repair.py -v && uv run ruff check . && uv run mypy`
Expected: 7 passed, clean.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/rhapto/engine/prompts/compose.py apps/api/src/rhapto/engine/compose.py apps/api/src/rhapto/engine/repair.py apps/api/tests/unit/test_compose.py apps/api/tests/unit/test_repair.py
git commit -m "feat(engine): compose and repair steps with cached system blocks"
```

---
### Task 13: Renderer (DOCX via python-docx, PDF via LibreOffice)

**Files:**
- Create: `apps/api/src/rhapto/engine/render/__init__.py`, `apps/api/src/rhapto/engine/render/docx.py`, `apps/api/src/rhapto/engine/render/pdf.py`
- Test: `apps/api/tests/unit/test_render_docx.py`, `apps/api/tests/unit/test_render_pdf.py`

**Interfaces:**
- Consumes: `ResumeDocument`, `Block` (Task 2); `EngineError` (Task 3); `iter_entries`, `iter_bullets` (Task 7).
- Produces (`rhapto.engine.render.docx`): `OrphanBulletError(EngineError)` with `.path` and `.block_id`; `render_docx(resume: ResumeDocument, blocks: Mapping[str, Block]) -> bytes`.
- Produces (`rhapto.engine.render.pdf`): `PdfRenderError(EngineError)`; `soffice_available(binary: str = "soffice") -> bool`; `convert_docx_to_pdf(docx_path: Path, out_dir: Path, binary: str = "soffice", timeout: int = 180) -> Path`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/unit/test_render_docx.py`:

```python
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from helpers import bullet, demo_resume

from rhapto.engine.render.docx import OrphanBulletError, render_docx
from rhapto.profile.loader import load_profile


def test_renders_single_column_ats_safe_docx(demo_profile_dir: Path) -> None:
    blocks = load_profile(demo_profile_dir).block_map()
    data = render_docx(demo_resume(), blocks)
    doc = Document(BytesIO(data))
    texts = [p.text for p in doc.paragraphs]
    assert texts[0] == "Maya Chen"
    assert "maya.chen@example.com | Denver, CO" in texts
    assert "SUMMARY" in texts and "EXPERIENCE" in texts and "PROJECTS" in texts and "CREDENTIALS" in texts
    assert "Senior Data Program Manager | Acme Analytics | 2019-2025" in texts
    assert any("cutting warehouse cost 18%" in t for t in texts)
    assert doc.tables == [] and not doc.inline_shapes
    bullet_styles = {p.style.name for p in doc.paragraphs if p.text.startswith("Led cross-functional")}
    assert bullet_styles == {"List Bullet"}
    assert doc.styles["Normal"].font.name == "Calibri"


def test_orphan_bullet_raises(demo_profile_dir: Path) -> None:
    blocks = load_profile(demo_profile_dir).block_map()
    resume = demo_resume()
    resume.sections[0].entries[0].bullets.append(bullet("Made up.", "ghost"))
    with pytest.raises(OrphanBulletError) as exc:
        render_docx(resume, blocks)
    assert exc.value.block_id == "ghost" and exc.value.path == "sections[0].entries[0].bullets[2]"


def test_orphan_entry_raises(demo_profile_dir: Path) -> None:
    blocks = load_profile(demo_profile_dir).block_map()
    resume = demo_resume()
    resume.sections[1].entries[0].source_block_id = "ghost"
    with pytest.raises(OrphanBulletError):
        render_docx(resume, blocks)
```

`apps/api/tests/unit/test_render_pdf.py`:

```python
import subprocess
from pathlib import Path
from typing import Any

import pytest

from rhapto.engine.render import pdf


def test_soffice_available_uses_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pdf.shutil, "which", lambda name: "/usr/bin/soffice" if name == "soffice" else None)
    assert pdf.soffice_available() is True
    assert pdf.soffice_available("nope") is False


def test_convert_runs_headless_and_returns_pdf_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    seen: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        seen["cmd"] = cmd
        (out_dir / "resume.pdf").write_bytes(b"%PDF")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(pdf.subprocess, "run", fake_run)
    result = pdf.convert_docx_to_pdf(docx_path, out_dir, binary="soffice")
    assert result == out_dir / "resume.pdf"
    assert seen["cmd"][:4] == ["soffice", "--headless", "--convert-to", "pdf"]
    assert str(docx_path) in seen["cmd"] and "--outdir" in seen["cmd"]


def test_convert_raises_when_no_pdf_produced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"fake")
    monkeypatch.setattr(pdf.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, b"", b""))
    with pytest.raises(pdf.PdfRenderError, match="did not produce"):
        pdf.convert_docx_to_pdf(docx_path, tmp_path)


def test_convert_raises_when_binary_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(cmd: list[str], **kw: Any) -> None:
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(pdf.subprocess, "run", missing)
    with pytest.raises(pdf.PdfRenderError, match="not found"):
        pdf.convert_docx_to_pdf(tmp_path / "x.docx", tmp_path, binary="nope")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/unit/test_render_docx.py tests/unit/test_render_pdf.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.engine.render`.

- [ ] **Step 3: Implement DOCX rendering**

`apps/api/src/rhapto/engine/render/__init__.py`:

```python
"""Deterministic rendering: ResumeDocument to DOCX, DOCX to PDF."""
```

`apps/api/src/rhapto/engine/render/docx.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from typing import Any

from docx import Document
from docx.shared import Inches, Pt

from rhapto.engine.guardrails.base import iter_bullets, iter_entries
from rhapto.engine.types import EngineError
from rhapto.models.profile.blocks import Block
from rhapto.models.resume_document import ResumeDocument

FONT_NAME = "Calibri"
FONT_SIZE = Pt(11)


class OrphanBulletError(EngineError):
    """A bullet or entry cites a block that is not in the library. The renderer refuses to continue."""

    def __init__(self, path: str, block_id: str) -> None:
        super().__init__(f"{path} cites unknown block {block_id!r}")
        self.path = path
        self.block_id = block_id


def _check_provenance(resume: ResumeDocument, blocks: Mapping[str, Block]) -> None:
    for path, entry in iter_entries(resume):
        if entry.source_block_id not in blocks:
            raise OrphanBulletError(path, entry.source_block_id)
    for path, bullet in iter_bullets(resume):
        if bullet.source_block_id not in blocks:
            raise OrphanBulletError(path, bullet.source_block_id)


def _heading(doc: Any, text: str) -> None:
    paragraph = doc.add_paragraph()
    run = paragraph.add_run(text.upper())
    run.bold = True
    run.font.size = Pt(12)
    paragraph.paragraph_format.space_before = Pt(10)
    paragraph.paragraph_format.space_after = Pt(2)


def render_docx(resume: ResumeDocument, blocks: Mapping[str, Block]) -> bytes:
    """Single column, standard headings, bullets via the built-in List Bullet style. No tables or images."""
    _check_provenance(resume, blocks)
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = FONT_NAME
    normal.font.size = FONT_SIZE
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Inches(0.7)
        section.left_margin = section.right_margin = Inches(0.8)

    name = doc.add_paragraph()
    name_run = name.add_run(resume.header.name)
    name_run.bold = True
    name_run.font.size = Pt(16)
    header = resume.header
    contact = " | ".join(filter(None, [header.email, header.phone, header.location, *header.links]))
    if contact:
        doc.add_paragraph(contact)

    if resume.summary:
        _heading(doc, "Summary")
        doc.add_paragraph(" ".join(b.text for b in resume.summary))

    for section in resume.sections:
        _heading(doc, section.title)
        for entry in section.entries:
            head = " | ".join(filter(None, [entry.role or entry.title, entry.org, entry.period]))
            if head:
                paragraph = doc.add_paragraph()
                paragraph.add_run(head).bold = True
            for bullet in entry.bullets:
                doc.add_paragraph(bullet.text, style="List Bullet")

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
```

- [ ] **Step 4: Implement PDF conversion**

`apps/api/src/rhapto/engine/render/pdf.py`:

```python
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from rhapto.engine.types import EngineError


class PdfRenderError(EngineError):
    """LibreOffice is missing or did not produce a PDF."""


def soffice_available(binary: str = "soffice") -> bool:
    return shutil.which(binary) is not None


def convert_docx_to_pdf(docx_path: Path, out_dir: Path, binary: str = "soffice", timeout: int = 180) -> Path:
    """Convert the rendered DOCX with headless LibreOffice so DOCX and PDF never drift."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [binary, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise PdfRenderError(f"LibreOffice binary {binary!r} not found") from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise PdfRenderError(f"LibreOffice failed: {exc}") from exc
    pdf_path = out_dir / f"{docx_path.stem}.pdf"
    if not pdf_path.exists():
        raise PdfRenderError(f"LibreOffice did not produce {pdf_path}")
    return pdf_path
```

- [ ] **Step 5: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/unit/test_render_docx.py tests/unit/test_render_pdf.py -v && uv run ruff check . && uv run mypy`
Expected: 7 passed, clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/rhapto/engine/render apps/api/tests/unit/test_render_docx.py apps/api/tests/unit/test_render_pdf.py
git commit -m "feat(render): ATS-safe DOCX renderer with orphan check and LibreOffice PDF conversion"
```

---
### Task 14: Pipeline orchestrator with call budget

**Files:**
- Create: `apps/api/src/rhapto/engine/pipeline.py`
- Test: `apps/api/tests/unit/test_pipeline.py`

**Interfaces:**
- Consumes: `extract` (Task 5), `select_blocks`, `Selection`, `SelectionConfig` (Task 6), `run_guardrails` (Task 7), `compose`, `assemble_resume`, `build_system_blocks`, `ComposeOutput` (Task 12), `repair` (Task 12), `render_docx`, `OrphanBulletError` (Task 13), `Profile`, `TailorRequest`, `EngineError` (Task 3), `TokenUsage` (Task 4).
- Produces: `LLMBudgetExceeded(EngineError)`; `CallBudget(max_calls: int = 3)` with `.calls`, `.usage`, `before_call()`, `after_call(usage)`; `ProgressCallback = Callable[[str], Awaitable[None]]`; `STEPS = ("extract", "select", "compose", "validate", "repair", "render")`; `TailorResult(package: ApplicationPackage, docx: bytes, selection: Selection)`; `tailor(request, profile, llm, embedder, *, selection_config=None, budget=None, on_step=None) -> TailorResult`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/unit/test_pipeline.py`:

```python
from pathlib import Path
from typing import Any

import pytest
from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.compose import ComposeOutput
from rhapto.engine.pipeline import CallBudget, LLMBudgetExceeded, TailorResult, tailor
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.engine.providers.llm import TokenUsage
from rhapto.engine.types import Profile, ProfileError, TailorRequest
from rhapto.profile.loader import load_profile

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration."


@pytest.fixture
def profile(demo_profile_dir: Path) -> Profile:
    return load_profile(demo_profile_dir)


def good_output() -> dict[str, Any]:
    resume = demo_resume()
    return ComposeOutput(
        summary=resume.summary, sections=resume.sections, cover_note="Dear ExampleCo team, " + "word " * 120,
        change_log="Emphasised migration.", answers={"why_this_company": "Data."},
    ).model_dump(mode="json")


def bad_output() -> dict[str, Any]:
    output = good_output()
    output["sections"][0]["entries"][0]["bullets"][1] = bullet("Cut warehouse cost 25%.", "acme-migration").model_dump()
    return output


def test_call_budget() -> None:
    budget = CallBudget(max_calls=2)
    budget.before_call()
    budget.after_call(TokenUsage(input_tokens=3))
    budget.before_call()
    budget.after_call(TokenUsage(input_tokens=4))
    assert budget.calls == 2 and budget.usage.input_tokens == 7
    with pytest.raises(LLMBudgetExceeded):
        budget.before_call()


async def test_happy_path_uses_two_calls(profile: Profile) -> None:
    llm = FakeLLMProvider([demo_extract(), good_output()])
    steps: list[str] = []

    async def on_step(name: str) -> None:
        steps.append(name)

    result = await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider(), on_step=on_step)
    assert isinstance(result, TailorResult)
    package = result.package
    assert package.status == "draft" and package.guardrail_report.passed and package.llm_calls == 2
    assert package.version == 1 and package.track_id == "data-pm"
    assert package.job.company == "ExampleCo" and package.job.jd_text == JD
    assert package.resume.header.name == "Maya Chen"
    assert "acme-migration" in result.selection.block_ids
    assert result.docx[:2] == b"PK"
    assert steps == ["extract", "select", "compose", "validate", "render"]


async def test_repair_path_uses_three_calls_and_passes(profile: Profile) -> None:
    llm = FakeLLMProvider([demo_extract(), bad_output(), good_output()])
    result = await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider())
    assert result.package.status == "draft" and result.package.llm_calls == 3
    repair_call = llm.calls[2]
    assert "25%" in repair_call.messages[0].content and repair_call.output_schema is ComposeOutput
    assert repair_call.system == llm.calls[1].system  # same cached system blocks as compose


async def test_unrepairable_output_is_blocked(profile: Profile) -> None:
    llm = FakeLLMProvider([demo_extract(), bad_output(), bad_output()])
    result = await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider())
    assert result.package.status == "blocked" and result.package.llm_calls == 3
    assert {v.rule for v in result.package.guardrail_report.violations} == {"no-unverified-metrics"}
    assert result.docx[:2] == b"PK"  # still rendered for review; the orphan check is the only hard stop


async def test_budget_exceeded_raises_before_fourth_call(profile: Profile) -> None:
    llm = FakeLLMProvider([demo_extract(), bad_output(), bad_output()])
    with pytest.raises(LLMBudgetExceeded):
        await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider(), budget=CallBudget(max_calls=2))
    assert len(llm.calls) == 2


async def test_orphan_bullet_blocks_without_docx(profile: Profile) -> None:
    output = good_output()
    output["summary"] = [bullet("Made up.", "ghost").model_dump()]
    llm = FakeLLMProvider([demo_extract(), output, output])
    result = await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider())
    assert result.package.status == "blocked" and result.docx == b""
    assert any(v.rule == "provenance" for v in result.package.guardrail_report.violations)


async def test_regeneration_increments_version_and_passes_feedback(profile: Profile) -> None:
    first = await tailor(
        TailorRequest(jd_text=JD), profile, FakeLLMProvider([demo_extract(), good_output()]), FakeEmbeddingProvider()
    )
    llm = FakeLLMProvider([demo_extract(), good_output()])
    second = await tailor(
        TailorRequest(jd_text=JD, feedback="lean harder on migration", previous_package=first.package),
        profile, llm, FakeEmbeddingProvider(),
    )
    assert second.package.version == 2
    assert "lean harder on migration" in llm.calls[1].messages[0].content
    assert "<previous_resume>" in llm.calls[1].messages[0].content


async def test_unknown_track_raises(profile: Profile) -> None:
    with pytest.raises(ProfileError):
        await tailor(TailorRequest(jd_text=JD, track_id="nope"), profile, FakeLLMProvider([]), FakeEmbeddingProvider())
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/unit/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.engine.pipeline`.

- [ ] **Step 3: Implement**

`apps/api/src/rhapto/engine/pipeline.py`:

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from pydantic import BaseModel

from rhapto.engine.compose import assemble_resume, build_system_blocks, compose
from rhapto.engine.extract import extract
from rhapto.engine.guardrails.registry import run_guardrails
from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.engine.providers.llm import LLMProvider, TokenUsage
from rhapto.engine.render.docx import OrphanBulletError, render_docx
from rhapto.engine.repair import repair
from rhapto.engine.select import Selection, SelectionConfig, select_blocks
from rhapto.engine.types import EngineError, Profile, TailorRequest
from rhapto.models.package import ApplicationPackage, JobSnapshot

STEPS = ("extract", "select", "compose", "validate", "repair", "render")
ProgressCallback = Callable[[str], Awaitable[None]]


class LLMBudgetExceeded(EngineError):
    """The pipeline would exceed the per-run LLM call budget."""


class CallBudget:
    def __init__(self, max_calls: int = 3) -> None:
        self.max_calls = max_calls
        self.calls = 0
        self.usage = TokenUsage()

    def before_call(self) -> None:
        if self.calls >= self.max_calls:
            raise LLMBudgetExceeded(f"LLM call budget of {self.max_calls} exhausted")

    def after_call(self, usage: TokenUsage) -> None:
        self.calls += 1
        self.usage = self.usage + usage


class TailorResult(BaseModel):
    package: ApplicationPackage
    docx: bytes
    selection: Selection


async def _notify(on_step: ProgressCallback | None, step: str) -> None:
    if on_step is not None:
        await on_step(step)


async def tailor(
    request: TailorRequest,
    profile: Profile,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
    *,
    selection_config: SelectionConfig | None = None,
    budget: CallBudget | None = None,
    on_step: ProgressCallback | None = None,
) -> TailorResult:
    """extract -> select -> compose -> validate -> (repair -> validate) -> render. At most 3 LLM calls."""
    budget = budget or CallBudget()
    track = profile.get_track(request.track_id)

    await _notify(on_step, "extract")
    budget.before_call()
    jd_extract, usage = await extract(request.jd_text, llm)
    budget.after_call(usage)

    await _notify(on_step, "select")
    selection = await select_blocks(jd_extract, profile, track, embedder, selection_config)

    await _notify(on_step, "compose")
    previous = request.previous_package.resume if request.previous_package else None
    budget.before_call()
    output, usage = await compose(jd_extract, profile, track, selection, llm, request.feedback, previous)
    budget.after_call(usage)

    await _notify(on_step, "validate")
    resume = assemble_resume(output, profile)
    report = run_guardrails(resume, profile, selection.block_ids, jd_extract)

    if not report.passed:
        await _notify(on_step, "repair")
        budget.before_call()
        output, usage = await repair(output, report, build_system_blocks(profile, track), llm)
        budget.after_call(usage)
        resume = assemble_resume(output, profile)
        report = run_guardrails(resume, profile, selection.block_ids, jd_extract)

    await _notify(on_step, "render")
    try:
        docx = render_docx(resume, profile.block_map())
    except OrphanBulletError:
        docx = b""  # provenance violation is already in the report; nothing safe to render

    package = ApplicationPackage(
        job=JobSnapshot(company=jd_extract.company, title=jd_extract.title, jd_text=request.jd_text),
        track_id=track.id,
        jd_extract=jd_extract,
        resume=resume,
        cover_note=output.cover_note,
        change_log=output.change_log,
        answers=output.answers,
        guardrail_report=report,
        version=(request.previous_package.version + 1) if request.previous_package else 1,
        status="draft" if report.passed else "blocked",
        llm_calls=budget.calls,
        created_at=datetime.now(UTC),
    )
    return TailorResult(package=package, docx=docx, selection=selection)
```

- [ ] **Step 4: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/unit/test_pipeline.py -v && uv run ruff check . && uv run mypy`
Expected: 8 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/engine/pipeline.py apps/api/tests/unit/test_pipeline.py
git commit -m "feat(engine): tailor() orchestrator with 3-call budget, repair, and render"
```

---
### Task 15: CLI (`rhapto tailor`, `rhapto profile validate`)

**Files:**
- Create: `apps/api/src/rhapto/cli/__init__.py`, `apps/api/src/rhapto/cli/main.py`
- Test: `apps/api/tests/unit/test_cli.py`

**Interfaces:**
- Consumes: `Settings`, `get_settings` (Task 1); `load_profile`, `ProfileError` (Task 3); `AnthropicProvider`, `FastEmbedProvider`, `LLMProvider`, `EmbeddingProvider` (Task 4); `tailor`, `TailorRequest`, `LLMBudgetExceeded` (Task 14); `soffice_available`, `convert_docx_to_pdf`, `PdfRenderError` (Task 13).
- Produces: `rhapto.cli.main.app` (Typer), `Providers(llm, embedder)` dataclass, `build_providers(settings: Settings) -> Providers` (tests monkeypatch this), `slugify(text: str) -> str`, `write_package(result: TailorResult, target: Path) -> None`. Exit codes: 0 draft, 1 error, 2 usage error, 3 blocked.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/unit/test_cli.py`:

```python
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from helpers import bullet, demo_extract, demo_resume
from typer.testing import CliRunner

from rhapto.cli import main as cli
from rhapto.engine.compose import ComposeOutput
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider

runner = CliRunner()
JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration."


def _good() -> dict[str, Any]:
    resume = demo_resume()
    return ComposeOutput(
        summary=resume.summary, sections=resume.sections, cover_note="Dear team.", change_log="Emphasised migration.",
        answers={"why_this_company": "Data."},
    ).model_dump(mode="json")


def _bad() -> dict[str, Any]:
    output = _good()
    output["sections"][0]["entries"][0]["bullets"][1] = bullet("Cut warehouse cost 25%.", "acme-migration").model_dump()
    return output


@pytest.fixture
def workspace(tmp_path: Path, demo_profile_dir: Path) -> Path:
    shutil.copytree(demo_profile_dir, tmp_path / "profile")
    (tmp_path / "jd.txt").write_text(JD, encoding="utf-8")
    return tmp_path


def _patch_providers(monkeypatch: pytest.MonkeyPatch, responses: list[Any]) -> FakeLLMProvider:
    llm = FakeLLMProvider(responses)
    monkeypatch.setattr(cli, "build_providers", lambda settings: cli.Providers(llm=llm, embedder=FakeEmbeddingProvider()))
    return llm


def test_slugify() -> None:
    assert cli.slugify("ExampleCo, Inc.") == "exampleco-inc"
    assert cli.slugify("Data Platform  Program Manager") == "data-platform-program-manager"
    assert cli.slugify("") == "untitled"


def test_tailor_writes_package(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_providers(monkeypatch, [demo_extract(), _good()])
    result = runner.invoke(
        cli.app,
        ["tailor", "--jd", str(workspace / "jd.txt"), "--profile", str(workspace / "profile"), "--out", str(workspace / "out"), "--no-pdf"],
    )
    assert result.exit_code == 0, result.output
    target = workspace / "out" / "exampleco-data-platform-program-manager"
    assert {p.name for p in target.iterdir()} == {"resume.docx", "cover-note.md", "package.json"}
    package = json.loads((target / "package.json").read_text(encoding="utf-8"))
    assert package["status"] == "draft" and package["llm_calls"] == 2
    assert (target / "cover-note.md").read_text(encoding="utf-8").strip() == "Dear team."
    assert "guardrails: passed" in result.output and "extract" in result.output


def test_tailor_blocked_exits_2(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_providers(monkeypatch, [demo_extract(), _bad(), _bad()])
    result = runner.invoke(
        cli.app,
        ["tailor", "--jd", str(workspace / "jd.txt"), "--profile", str(workspace / "profile"), "--out", str(workspace / "out"), "--no-pdf"],
    )
    assert result.exit_code == 2, result.output
    assert "no-unverified-metrics" in result.output and "25%" in result.output
    assert (workspace / "out" / "exampleco-data-platform-program-manager" / "package.json").exists()


def test_tailor_with_track_and_feedback(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    llm = _patch_providers(monkeypatch, [demo_extract(), _good()])
    result = runner.invoke(
        cli.app,
        ["tailor", "--jd", str(workspace / "jd.txt"), "--profile", str(workspace / "profile"), "--out", str(workspace / "out"),
         "--no-pdf", "--track", "ai-pm", "--feedback", "lean on AI"],
    )
    assert result.exit_code == 0, result.output
    package = json.loads((workspace / "out" / "exampleco-data-platform-program-manager" / "package.json").read_text(encoding="utf-8"))
    assert package["track_id"] == "ai-pm"
    assert "lean on AI" in llm.calls[1].messages[0].content


def test_tailor_bad_profile_exits_1(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_providers(monkeypatch, [])
    (workspace / "profile" / "blocks.yaml").write_text("blocks: [{id: a, type: hobby, content: x}]\n", encoding="utf-8")
    result = runner.invoke(cli.app, ["tailor", "--jd", str(workspace / "jd.txt"), "--profile", str(workspace / "profile"), "--no-pdf"])
    assert result.exit_code == 1 and "blocks.yaml" in result.output


def test_tailor_skips_pdf_when_soffice_missing(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_providers(monkeypatch, [demo_extract(), _good()])
    monkeypatch.setattr(cli, "soffice_available", lambda binary: False)
    result = runner.invoke(
        cli.app, ["tailor", "--jd", str(workspace / "jd.txt"), "--profile", str(workspace / "profile"), "--out", str(workspace / "out")]
    )
    assert result.exit_code == 0 and "PDF skipped" in result.output


def test_tailor_renders_pdf_when_available(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_providers(monkeypatch, [demo_extract(), _good()])
    monkeypatch.setattr(cli, "soffice_available", lambda binary: True)

    def fake_convert(docx_path: Path, out_dir: Path, binary: str = "soffice", timeout: int = 180) -> Path:
        pdf = out_dir / "resume.pdf"
        pdf.write_bytes(b"%PDF")
        return pdf

    monkeypatch.setattr(cli, "convert_docx_to_pdf", fake_convert)
    result = runner.invoke(
        cli.app, ["tailor", "--jd", str(workspace / "jd.txt"), "--profile", str(workspace / "profile"), "--out", str(workspace / "out")]
    )
    assert result.exit_code == 0, result.output
    assert (workspace / "out" / "exampleco-data-platform-program-manager" / "resume.pdf").exists()


def test_build_providers_requires_api_key() -> None:
    from rhapto.config import Settings

    with pytest.raises(cli.typer.BadParameter, match="ANTHROPIC_API_KEY"):
        cli.build_providers(Settings(_env_file=None, anthropic_api_key=""))


def test_profile_validate(workspace: Path, demo_profile_dir: Path) -> None:
    ok = runner.invoke(cli.app, ["profile", "validate", str(demo_profile_dir)])
    assert ok.exit_code == 0 and "4 blocks" in ok.output and "2 tracks" in ok.output
    bad = runner.invoke(cli.app, ["profile", "validate", str(workspace / "nothing")])
    assert bad.exit_code == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/unit/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.cli`.

- [ ] **Step 3: Implement**

`apps/api/src/rhapto/cli/__init__.py`:

```python
"""Command-line interface."""
```

`apps/api/src/rhapto/cli/main.py`:

```python
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import typer

from rhapto.config import Settings, get_settings
from rhapto.engine.pipeline import LLMBudgetExceeded, TailorResult, tailor
from rhapto.engine.providers.anthropic import AnthropicProvider
from rhapto.engine.providers.embeddings import EmbeddingProvider, FastEmbedProvider
from rhapto.engine.providers.llm import LLMProvider
from rhapto.engine.render.pdf import PdfRenderError, convert_docx_to_pdf, soffice_available
from rhapto.engine.types import ProfileError, TailorRequest
from rhapto.profile.loader import load_profile

app = typer.Typer(no_args_is_help=True, help="Rhapto: human-in-the-loop AI job application copilot.")
profile_app = typer.Typer(no_args_is_help=True, help="Inspect and validate a profile directory.")
app.add_typer(profile_app, name="profile")

EXIT_BLOCKED = 2


@dataclass
class Providers:
    llm: LLMProvider
    embedder: EmbeddingProvider


def build_providers(settings: Settings) -> Providers:
    if not settings.anthropic_api_key:
        raise typer.BadParameter("ANTHROPIC_API_KEY is not set; put it in .env or the environment")
    return Providers(
        llm=AnthropicProvider(model=settings.rhapto_llm_model, api_key=settings.anthropic_api_key),
        embedder=FastEmbedProvider(settings.rhapto_embedding_model),
    )


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "untitled"


def write_package(result: TailorResult, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if result.docx:
        (target / "resume.docx").write_bytes(result.docx)
    (target / "cover-note.md").write_text(result.package.cover_note + "\n", encoding="utf-8")
    (target / "package.json").write_text(result.package.model_dump_json(indent=2), encoding="utf-8")


@app.command(name="tailor")
def tailor_cmd(
    jd: Path = typer.Option(..., "--jd", exists=True, dir_okay=False, readable=True, help="Job description text file"),
    profile: Path = typer.Option(Path("./profile"), "--profile", help="Profile directory"),
    track: str | None = typer.Option(None, "--track", help="Track id (default: first track)"),
    out: Path = typer.Option(Path("out"), "--out", help="Output root; a <company>-<role> folder is created"),
    no_pdf: bool = typer.Option(False, "--no-pdf", help="Skip PDF conversion"),
    feedback: str | None = typer.Option(None, "--feedback", help="Regeneration feedback"),
) -> None:
    """Tailor a resume package for one job description."""
    settings = get_settings()
    try:
        loaded = load_profile(profile)
    except ProfileError as exc:
        typer.echo(f"profile error: {exc}", err=True)
        raise typer.Exit(1) from exc
    providers = build_providers(settings)
    jd_text = jd.read_text(encoding="utf-8")

    async def on_step(step: str) -> None:
        typer.echo(f"  {step}...")

    try:
        result = asyncio.run(
            tailor(
                TailorRequest(jd_text=jd_text, track_id=track, feedback=feedback),
                loaded, providers.llm, providers.embedder, on_step=on_step,
            )
        )
    except LLMBudgetExceeded as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc

    package = result.package
    target = out / f"{slugify(package.job.company)}-{slugify(package.job.title)}"
    write_package(result, target)

    if no_pdf or not result.docx:
        typer.echo("PDF skipped")
    elif not soffice_available(settings.rhapto_soffice_binary):
        typer.echo(f"PDF skipped: LibreOffice ({settings.rhapto_soffice_binary}) not found")
    else:
        try:
            convert_docx_to_pdf(target / "resume.docx", target, binary=settings.rhapto_soffice_binary)
        except PdfRenderError as exc:
            typer.echo(f"PDF skipped: {exc}")

    report = package.guardrail_report
    typer.echo(f"wrote {target}")
    typer.echo(f"llm calls: {package.llm_calls}  guardrails: {'passed' if report.passed else 'BLOCKED'}")
    for v in report.violations:
        typer.echo(f"  [{v.severity}] {v.rule} at {v.path}: {v.message}")
    if not report.passed:
        raise typer.Exit(EXIT_BLOCKED)


@profile_app.command("validate")
def profile_validate(path: Path = typer.Argument(Path("./profile"), help="Profile directory")) -> None:
    """Validate a profile directory against the schemas."""
    try:
        loaded = load_profile(path)
    except ProfileError as exc:
        typer.echo(f"invalid: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"ok: {len(loaded.blocks)} blocks, {len(loaded.tracks)} tracks, {len(loaded.bases)} bases, "
        f"{len(loaded.guardrails)} guardrail rules, {len(loaded.answers)} answers"
    )
```

Note: the function is named `tailor_cmd` to avoid shadowing the imported `tailor` and is registered under the command name `tailor` via the decorator argument.

- [ ] **Step 4: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/unit/test_cli.py -v && uv run ruff check . && uv run mypy`
Expected: 9 passed, clean. Then smoke the entrypoint: `cd apps/api && uv run rhapto --help` shows `tailor` and `profile`.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/cli apps/api/tests/unit/test_cli.py
git commit -m "feat(cli): rhapto tailor and rhapto profile validate"
```

---
### Task 16: Golden tests

**Files:**
- Create: `apps/api/tests/golden/test_golden.py`
- Create: `apps/api/tests/golden/cases/acme-data-pm-clean/{jd.txt,extract.json,compose.json,expected.json}`
- Create: `apps/api/tests/golden/cases/invented-metric-repaired/{jd.txt,extract.json,compose.json,repair.json,expected.json}`
- Create: `apps/api/tests/golden/cases/invented-metric-unrepairable/{jd.txt,extract.json,compose.json,repair.json,expected.json}`

**Interfaces:**
- Consumes: `tailor`, `TailorRequest` (Task 14), `FakeLLMProvider`, `FakeEmbeddingProvider` (Task 4), `load_profile` (Task 3).
- Produces: a parametrised test that runs every case directory. `expected.json` keys: `status`, `passed`, `llm_calls`, `violation_rules` (sorted unique rule names in the final report), `selected_block_ids_include` (list).

- [ ] **Step 1: Write the test runner**

`apps/api/tests/golden/test_golden.py`:

```python
"""Golden cases: fictional JDs + scripted LLM responses + expected pipeline outcome. Demo profile only."""

import json
from pathlib import Path
from typing import Any

import pytest

from rhapto.engine.pipeline import tailor
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.engine.types import TailorRequest
from rhapto.profile.loader import load_profile

CASES_DIR = Path(__file__).parent / "cases"
CASES = sorted(p for p in CASES_DIR.iterdir() if p.is_dir())


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
async def test_golden_case(case: Path, demo_profile_dir: Path) -> None:
    responses = [_load(case / "extract.json"), _load(case / "compose.json")]
    if (case / "repair.json").exists():
        responses.append(_load(case / "repair.json"))
    expected = _load(case / "expected.json")
    llm = FakeLLMProvider(responses)

    result = await tailor(
        TailorRequest(jd_text=(case / "jd.txt").read_text(encoding="utf-8")),
        load_profile(demo_profile_dir), llm, FakeEmbeddingProvider(),
    )
    package = result.package
    assert package.status == expected["status"]
    assert package.guardrail_report.passed is expected["passed"]
    assert package.llm_calls == expected["llm_calls"]
    assert sorted({v.rule for v in package.guardrail_report.violations}) == expected["violation_rules"]
    for block_id in expected["selected_block_ids_include"]:
        assert block_id in result.selection.block_ids, block_id
    assert len(llm.calls) == expected["llm_calls"]


def test_every_case_has_required_files() -> None:
    for case in CASES:
        for name in ("jd.txt", "extract.json", "compose.json", "expected.json"):
            assert (case / name).exists(), f"{case.name} is missing {name}"
```

- [ ] **Step 2: Write case `acme-data-pm-clean`**

`jd.txt`:

```
ExampleCo is hiring a Data Platform Program Manager (Remote, US).

You will lead our Snowflake migration and coordinate ETL modernisation across product, data engineering,
and analytics teams. Must have: 5+ years of program management on data platforms, hands-on experience
running a warehouse migration, strong cross-functional leadership. Nice to have: cost optimisation
experience, PMP. We will ask about US work authorization.
```

`extract.json`:

```json
{
  "company": "ExampleCo",
  "title": "Data Platform Program Manager",
  "location_policy": "remote",
  "seniority": "senior",
  "must_have": ["5+ years program management on data platforms", "warehouse migration experience", "cross-functional leadership"],
  "nice_to_have": ["cost optimisation", "PMP"],
  "keywords": ["Snowflake", "migration", "ETL", "data platform", "program management", "cross-functional", "warehouse", "PMP"],
  "likely_knockouts": ["US work authorization"],
  "context_tags": []
}
```

`compose.json`:

```json
{
  "summary": [
    {"text": "Senior data program manager who has led cross-functional platform delivery and a full warehouse migration.", "source_block_id": "acme-data-pm"}
  ],
  "sections": [
    {
      "title": "Experience",
      "kind": "experience",
      "entries": [
        {
          "source_block_id": "acme-data-pm",
          "org": "Acme Analytics",
          "role": "Senior Data Program Manager",
          "period": "2019-2025",
          "bullets": [
            {"text": "Led cross-functional delivery of the customer data platform across 4 teams spanning product, data engineering, and analytics.", "source_block_id": "acme-data-pm"},
            {"text": "Owned the Snowflake migration program end to end, migrating 12 pipelines with zero downtime and cutting warehouse cost 18%.", "source_block_id": "acme-migration"}
          ]
        }
      ]
    },
    {
      "title": "Projects",
      "kind": "projects",
      "entries": [
        {"source_block_id": "side-llm-tool", "org": "Independent", "title": "Open-source LLM eval harness", "bullets": [{"text": "Built and maintain an open-source LLM eval harness.", "source_block_id": "side-llm-tool"}]}
      ]
    },
    {
      "title": "Credentials",
      "kind": "credentials",
      "entries": [
        {"source_block_id": "cred-pmp", "bullets": [{"text": "PMP certification.", "source_block_id": "cred-pmp"}]}
      ]
    }
  ],
  "cover_note": "I am applying for the Data Platform Program Manager role at ExampleCo because the Snowflake migration you describe is exactly the program I have run. At Acme Analytics I owned a warehouse migration end to end, coordinating product, data engineering, and analytics teams while keeping the platform live for customers. I bring the cross-functional leadership your posting asks for, a habit of measuring outcomes rather than activity, and a PMP-backed approach to planning that still leaves room for engineering judgement. I would welcome the chance to talk about how I could help ExampleCo modernise its ETL estate without disrupting the teams that depend on it. Thank you for your consideration.",
  "change_log": "Led with the Snowflake migration because it is the posting's core must-have.\nKept the verified cost and downtime metrics from the migration block.\nSurfaced PMP as a nice-to-have match.\nDropped GitHub star counts from the side project because that block is unverified.",
  "answers": {
    "work_authorization": "US citizen; no sponsorship required.",
    "onsite_preference": "Remote preferred; open to hybrid.",
    "salary_range": "$160k-$190k base",
    "notice_period": "2 weeks",
    "why_this_company": "ExampleCo is modernising its data platform, which is the work I do best."
  }
}
```

`expected.json`:

```json
{
  "status": "draft",
  "passed": true,
  "llm_calls": 2,
  "violation_rules": [],
  "selected_block_ids_include": ["acme-data-pm", "acme-migration", "cred-pmp"]
}
```

- [ ] **Step 3: Write case `invented-metric-repaired`**

Copy `jd.txt` and `extract.json` from the clean case unchanged. `compose.json` is the clean `compose.json` with the second Experience bullet replaced by:

```json
{"text": "Owned the Snowflake migration program end to end, cutting warehouse cost 25% and migrating 12 pipelines.", "source_block_id": "acme-migration"}
```

`repair.json` is the clean `compose.json` verbatim (the model corrected 25% back to 18%).

`expected.json`:

```json
{
  "status": "draft",
  "passed": true,
  "llm_calls": 3,
  "violation_rules": [],
  "selected_block_ids_include": ["acme-migration"]
}
```

- [ ] **Step 4: Write case `invented-metric-unrepairable`**

Copy `jd.txt`, `extract.json`, and `compose.json` from `invented-metric-repaired`. `repair.json` is the same as that case's `compose.json` (the model failed to fix it), except the summary bullet also becomes:

```json
{"text": "Senior data program manager who doubled platform throughput.", "source_block_id": "acme-data-pm"}
```

`expected.json`:

```json
{
  "status": "blocked",
  "passed": false,
  "llm_calls": 3,
  "violation_rules": ["no-unverified-metrics"],
  "selected_block_ids_include": ["acme-migration"]
}
```

- [ ] **Step 5: Run the golden suite, then the full suite**

Run: `cd apps/api && uv run pytest tests/golden -v`
Expected: 4 passed (3 cases + file check).

Run: `cd apps/api && uv run pytest -q && uv run ruff check . && uv run mypy`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add apps/api/tests/golden
git commit -m "test: golden cases for clean, repaired, and unrepairable tailoring runs"
```

---
### Task 17: Import-linter contract, Dockerfile, and README quick start

**Files:**
- Create: `apps/api/.importlinter`, `apps/api/Dockerfile`, `.dockerignore` (repo root)
- Modify: `README.md` (append a Quick start section)

**Interfaces:**
- Produces: the `engine-is-pure` contract that CI (stage 4) will run; a `cli` Docker target that includes LibreOffice and the pre-downloaded embedding model.

- [ ] **Step 1: Add the import-linter contract and run it**

`apps/api/.importlinter`:

```ini
[importlinter]
root_package = rhapto

[importlinter:contract:engine-is-pure]
name = engine must not import application layers
type = forbidden
source_modules =
    rhapto.engine
forbidden_modules =
    rhapto.profile
    rhapto.cli
```

Run: `cd apps/api && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.` If it reports a broken contract, the offending import is a bug in an earlier task; fix the import, not the contract.

- [ ] **Step 2: Write the Dockerfile**

`.dockerignore` (repo root):

```
# never ship personal data or secrets into an image build context
profile/
.env
.env.*
!.env.example

# scratch and outputs
out/
.superpowers/
docs/
.git/

# python
**/.venv/
**/__pycache__/
**/*.pyc
**/.pytest_cache/
**/.mypy_cache/
**/.ruff_cache/
apps/api/tests/

# node (future web app)
**/node_modules/
**/.next/
```

`apps/api/Dockerfile` (build context is the repo root):

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/api/src ./src
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

# CLI image: LibreOffice for PDF conversion and the embedding model baked in.
FROM base AS cli
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
ENV FASTEMBED_CACHE_PATH=/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"
WORKDIR /work
ENTRYPOINT ["rhapto"]
CMD ["--help"]
```

- [ ] **Step 3: Build and smoke the image**

Run from the repo root:

```bash
docker build -f apps/api/Dockerfile --target cli -t rhapto-cli .
docker run --rm -v "$PWD:/work" rhapto-cli profile validate profile.example
```
Expected: the build succeeds and the second command prints `ok: 4 blocks, 2 tracks, 2 bases, 3 guardrail rules, 9 answers`.

- [ ] **Step 4: Append the quick start to README.md**

Add at the end of `README.md`:

````markdown
## Quick start (CLI, phase 0.1)

```bash
cp .env.example .env            # add your ANTHROPIC_API_KEY
cp -r profile.example profile   # then replace the fictional data with yours (profile/ is gitignored)
cd apps/api && uv sync
uv run rhapto profile validate ../../profile
uv run rhapto tailor --jd path/to/jd.txt --profile ../../profile --out ../../out
```

`tailor` writes `out/<company>-<role>/resume.docx`, `resume.pdf` (when LibreOffice is installed, otherwise skipped),
`cover-note.md`, and `package.json` with the guardrail report and change log. Exit code 2 means the guardrails
blocked the draft; the files are still written so you can see why.

Without LibreOffice locally, use the container:

```bash
docker build -f apps/api/Dockerfile --target cli -t rhapto-cli .
docker run --rm --env-file .env -v "$PWD:/work" rhapto-cli tailor --jd jd.txt --profile profile --out out
```

Development: `uv run pytest`, `uv run ruff check .`, `uv run mypy`, `uv run lint-imports` from `apps/api`;
`bash scripts/codegen.sh` after editing `packages/schemas`.
````

- [ ] **Step 5: Full verification**

```bash
cd apps/api && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports
cd ../.. && bash scripts/codegen.sh && git diff --exit-code apps/api/src/rhapto/models
uv run --project apps/api python scripts/check-no-personal-data.py
```
Expected: all tests pass, no lint, format, type, or contract errors, generated models unchanged, and the leak check reports no hits (it scans against the real `profile/` present on this machine).

- [ ] **Step 6: Commit**

```bash
git add apps/api/.importlinter apps/api/Dockerfile .dockerignore README.md
git commit -m "build: import-linter contract, CLI Docker image, README quick start"
```

---

## Self-review notes

- Spec coverage: section 4.1 providers (Task 4), 4.2 pipeline steps (Tasks 5, 6, 12, 14), 4.3 all six rules (Tasks 7 to 11), 4.4 renderer (Task 13), section 5 loader and CLI (Tasks 3, 15; `profile import/export` and `db upgrade` belong to stage 2), section 11 unit, guardrail, and golden tests (every task, Task 16), stage 1 Dockerfile targets (Task 17), leak check (Task 1).
- Deviation from spec section 2 layering: `rhapto.profile` imports `rhapto.engine.types` for the `Profile` class. The contract in Task 17 enforces the direction that matters (engine never imports profile or cli).
- The three-call budget is enforced in `CallBudget`; the repair path is the only conditional call.
