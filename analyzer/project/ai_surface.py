"""AI surface detection (P10-5): what in this codebase talks to, routes, or IS AI.

A codebase's AI surface is a thing owners increasingly need enumerated the same
way they need a dependency inventory: which model providers it calls, whether
calls go direct or through a gateway/router, what runs locally, which agent
frameworks and MCP servers are wired in, where model identifiers are hardcoded,
and which files configure AI-assisted development of the codebase itself.

Everything here is deterministic. Four evidence classes, none of which involves
a model call or a network request:

  dependencies  the supply-chain section the SBOM collector already parsed:
                package names matched against a curated catalog, with the
                manifest file and line as evidence
  imports       per-file import strings the extraction tier already recorded,
                matched against the same catalog's module names
  content       bounded regex scan of file content already in the store (never
                a source re-read): provider API hosts, OpenAI-compatible
                endpoint paths, model identifier strings, AI credential
                env-var names
  paths         filenames that are themselves the artifact: MCP configs,
                assistant-instruction files (CLAUDE.md, .cursorrules, ...),
                model weight files (.gguf, .safetensors)
  hidden roots  a short fixed list of well-known artifacts that live inside
                hidden directories (.github/copilot-instructions.md, a .claude/
                or .cursor/ directory). The extraction ledger deliberately
                skips hidden directories, and assistant tooling lives in them
                BY convention, so this class would otherwise be structurally
                invisible. Read from the scan root at projection tier, the
                same license the CRA emitter uses for .github/dependabot.yml.

The catalog is curated and deliberately visible at the top of this module:
adding a provider, gateway, or framework is one line, and what the detector can
and cannot see should be readable without reading the code. OpenAI-compatible
endpoints get their own kind because "openai" in a URL long ago stopped meaning
the company: it is the de-facto wire protocol most gateways, routers, and local
runtimes speak, so a /v1/chat/completions path is evidence of AI plumbing even
when no OpenAI package appears anywhere.

Emission is deterministic (invariant I4): items are aggregated per
(kind, name, component), id-sorted, ids content-derived, evidence sorted and
capped at a declared limit with the true instance count kept alongside, so a
cap never reads as completeness.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

__all__ = ["emit_ai_surface", "AI_KINDS"]

# The kinds this detector emits, in the order a reader should meet them.
AI_KINDS = (
    "provider_sdk",       # a vendor's own SDK or cloud client
    "gateway",            # routers/proxies in front of providers (OpenRouter, LiteLLM, ...)
    "llm_observability",  # tracing/eval layers that sit on the call path
    "mcp",                # Model Context Protocol: SDKs and server configs
    "agent_framework",    # orchestration frameworks (LangChain, CrewAI, ...)
    "local_inference",    # on-box runtimes (Ollama, llama.cpp, vLLM, transformers)
    "model_hub",          # Hugging Face hub tooling
    "vector_store",       # embedding stores commonly paired with retrieval
    "provider_endpoint",  # a provider API host literal in code
    "openai_compat",      # the OpenAI wire protocol used as a standard
    "model_id",           # a model identifier literal in code
    "ai_env",             # an AI credential/config env var named in code
    "assistant_config",   # files steering AI-assisted development of THIS repo
    "model_artifact",     # model weight files committed or referenced
)

# --------------------------------------------------------------------------
# The catalog: package names (per ecosystem conventions) and the import-module
# spellings that map back to them. `confidence` is "certain" unless the name is
# generic enough to collide with non-AI packages, in which case the match is
# recorded as "inferred" rather than dropped: a maybe that is visible can be
# judged, a maybe that was filtered cannot.
# --------------------------------------------------------------------------

_PKG = [
    # kind, canonical name, package-name matchers, import-module matchers, confidence
    ("provider_sdk", "openai", ["openai"], ["openai"], "certain"),
    ("provider_sdk", "anthropic", ["anthropic", "@anthropic-ai/sdk", "@anthropic-ai/bedrock-sdk", "@anthropic-ai/vertex-sdk", "@anthropic-ai/foundry-sdk"], ["anthropic", "@anthropic-ai/"], "certain"),
    ("provider_sdk", "google-genai", ["@google/generative-ai", "@google/genai", "google-generativeai", "google-genai"], ["@google/generative-ai", "@google/genai", "google.generativeai", "google.genai"], "certain"),
    ("provider_sdk", "azure-openai", ["@azure/openai", "azure-openai"], ["@azure/openai"], "certain"),
    ("provider_sdk", "aws-bedrock", ["@aws-sdk/client-bedrock-runtime", "@aws-sdk/client-bedrock", "aws-bedrock"], ["@aws-sdk/client-bedrock"], "certain"),
    ("provider_sdk", "cohere", ["cohere", "cohere-ai", "cohere-aws"], ["cohere"], "certain"),
    ("provider_sdk", "mistral", ["mistralai", "@mistralai/mistralai"], ["mistralai", "@mistralai/"], "certain"),
    ("provider_sdk", "groq", ["groq", "groq-sdk"], ["groq"], "certain"),
    ("provider_sdk", "together", ["together", "together-ai"], ["together"], "inferred"),
    ("provider_sdk", "replicate", ["replicate"], ["replicate"], "certain"),
    ("provider_sdk", "fireworks", ["fireworks-ai"], ["fireworks"], "certain"),
    ("provider_sdk", "xai", ["xai-sdk", "@ai-sdk/xai"], ["xai_sdk"], "certain"),
    ("provider_sdk", "deepseek", ["deepseek", "@ai-sdk/deepseek"], [], "certain"),

    ("gateway", "openrouter", ["openrouter", "@openrouter/ai-sdk-provider"], ["openrouter"], "certain"),
    ("gateway", "litellm", ["litellm"], ["litellm"], "certain"),
    ("gateway", "portkey", ["portkey-ai", "@portkey-ai/gateway"], ["portkey"], "certain"),
    ("gateway", "unify", ["unifyai"], ["unify"], "inferred"),

    ("llm_observability", "helicone", ["helicone", "@helicone/helicone"], ["helicone"], "certain"),
    ("llm_observability", "langfuse", ["langfuse", "langfuse-node"], ["langfuse"], "certain"),
    ("llm_observability", "langsmith", ["langsmith"], ["langsmith"], "certain"),
    ("llm_observability", "braintrust", ["braintrust", "autoevals"], ["braintrust"], "certain"),
    ("llm_observability", "arize-phoenix", ["arize-phoenix"], ["phoenix.trace"], "certain"),
    ("llm_observability", "openllmetry", ["traceloop-sdk", "@traceloop/node-server-sdk"], ["traceloop"], "certain"),

    ("mcp", "mcp-sdk", ["@modelcontextprotocol/sdk", "mcp", "fastmcp"], ["@modelcontextprotocol/", "mcp.server", "mcp.client", "fastmcp"], "certain"),

    ("agent_framework", "langchain", ["langchain", "langchain-core", "langchain-community", "@langchain/core", "@langchain/community"], ["langchain", "@langchain/"], "certain"),
    ("agent_framework", "langgraph", ["langgraph", "@langchain/langgraph"], ["langgraph"], "certain"),
    ("agent_framework", "llamaindex", ["llama-index", "llama-index-core", "llamaindex"], ["llama_index", "llamaindex"], "certain"),
    ("agent_framework", "crewai", ["crewai"], ["crewai"], "certain"),
    ("agent_framework", "autogen", ["pyautogen", "autogen-agentchat", "ag2"], ["autogen"], "certain"),
    ("agent_framework", "semantic-kernel", ["semantic-kernel", "microsoft.semantickernel"], ["semantic_kernel"], "certain"),
    ("agent_framework", "haystack", ["haystack-ai", "farm-haystack"], ["haystack"], "inferred"),
    ("agent_framework", "dspy", ["dspy", "dspy-ai"], ["dspy"], "certain"),
    ("agent_framework", "pydantic-ai", ["pydantic-ai", "pydantic-ai-slim"], ["pydantic_ai"], "certain"),
    ("agent_framework", "mastra", ["mastra", "@mastra/core"], ["@mastra/"], "certain"),
    ("agent_framework", "vercel-ai-sdk", ["ai", "@ai-sdk/openai", "@ai-sdk/anthropic", "@ai-sdk/google", "@ai-sdk/react"], ["@ai-sdk/"], "inferred"),
    ("agent_framework", "openai-agents", ["openai-agents", "@openai/agents"], ["agents"], "inferred"),
    ("agent_framework", "claude-agent-sdk", ["claude-agent-sdk", "@anthropic-ai/claude-agent-sdk", "@anthropic-ai/claude-code"], ["claude_agent_sdk"], "certain"),

    ("local_inference", "ollama", ["ollama", "ollama-js"], ["ollama"], "certain"),
    ("local_inference", "llama-cpp", ["llama-cpp-python", "node-llama-cpp"], ["llama_cpp"], "certain"),
    ("local_inference", "vllm", ["vllm"], ["vllm"], "certain"),
    ("local_inference", "mlx", ["mlx", "mlx-lm"], ["mlx_lm"], "inferred"),
    ("local_inference", "transformers", ["transformers", "sentence-transformers", "@huggingface/transformers", "@xenova/transformers"], ["transformers", "sentence_transformers"], "certain"),
    ("local_inference", "gpt4all", ["gpt4all"], ["gpt4all"], "certain"),
    ("local_inference", "onnxruntime", ["onnxruntime", "onnxruntime-node", "onnxruntime-web"], ["onnxruntime"], "inferred"),

    ("model_hub", "huggingface", ["huggingface_hub", "huggingface-hub", "@huggingface/hub", "@huggingface/inference", "tokenizers", "safetensors", "datasets"], ["huggingface_hub", "@huggingface/"], "certain"),

    ("vector_store", "pinecone", ["pinecone", "pinecone-client", "@pinecone-database/pinecone"], ["pinecone"], "certain"),
    ("vector_store", "weaviate", ["weaviate-client", "weaviate-ts-client"], ["weaviate"], "certain"),
    ("vector_store", "qdrant", ["qdrant-client", "@qdrant/js-client-rest"], ["qdrant_client"], "certain"),
    ("vector_store", "chroma", ["chromadb"], ["chromadb"], "certain"),
    ("vector_store", "faiss", ["faiss", "faiss-cpu", "faiss-gpu"], ["faiss"], "certain"),
    ("vector_store", "milvus", ["pymilvus", "@zilliz/milvus2-sdk-node"], ["pymilvus"], "certain"),
    ("vector_store", "pgvector", ["pgvector"], ["pgvector"], "certain"),
    ("vector_store", "lancedb", ["lancedb", "vectordb"], ["lancedb"], "inferred"),
]

# Generic package names that collide with non-AI software. Matched only when the
# manifest or import also shows a second, unambiguous AI signal is NOT how this
# works today; instead they are emitted with confidence "inferred" (set above)
# so a human or the enrichment tier can judge. "ai" (the Vercel SDK), "agents",
# "datasets", "together" are the honest examples.

# --------------------------------------------------------------------------
# Content patterns. Compiled once; scanned only over code/config content the
# store already holds. Every pattern here is a literal-ish signature: a host
# name, a wire path, a credential key, a model id shape.
# --------------------------------------------------------------------------

_HOSTS = [
    ("api.openai.com", "openai"),
    ("api.anthropic.com", "anthropic"),
    ("openrouter.ai", "openrouter"),
    ("generativelanguage.googleapis.com", "google-genai"),
    ("aiplatform.googleapis.com", "vertex-ai"),
    ("api.groq.com", "groq"),
    ("api.mistral.ai", "mistral"),
    ("api.together.xyz", "together"),
    ("api.together.ai", "together"),
    ("api.cohere.com", "cohere"),
    ("api.cohere.ai", "cohere"),
    ("api.x.ai", "xai"),
    ("api.deepseek.com", "deepseek"),
    ("api.replicate.com", "replicate"),
    ("api.fireworks.ai", "fireworks"),
    ("openai.azure.com", "azure-openai"),
    ("models.inference.ai.azure.com", "github-models"),
    ("api.githubcopilot.com", "github-copilot"),
    ("huggingface.co", "huggingface"),
    ("bedrock-runtime", "aws-bedrock"),
]
_HOST_RE = re.compile("|".join(re.escape(h) for h, _ in _HOSTS))
_HOST_TO_NAME = dict(_HOSTS)

_COMPAT_RE = re.compile(
    r"/v1/chat/completions|/v1/completions\b|/v1/embeddings\b|"
    r"(?:localhost|127\.0\.0\.1|0\.0\.0\.0):11434"
)

_MODEL_ID_RE = re.compile(
    r"\b(?:"
    r"claude-(?:opus|sonnet|haiku|fable|mythos|instant|\d)[\w.\-]*"
    r"|gpt-(?:3\.5|4|5)[\w.\-]*"
    r"|o1-mini|o1-preview|o3-mini"
    r"|gemini-\d[\w.\-]*"
    r"|text-embedding-[\w.\-]+"
    r"|dall-e-\d"
    r"|whisper-1"
    r"|llama-?\d[\w.\-]*"
    r"|mistral-(?:large|medium|small|tiny|7b|8x7b)[\w.\-]*"
    r"|deepseek-(?:chat|coder|reasoner|r1)[\w.\-]*"
    r")\b"
)

_ENV_RE = re.compile(
    r"\b(OPENAI_API_KEY|AZURE_OPENAI_API_KEY|ANTHROPIC_API_KEY|CLAUDE_API_KEY|"
    r"OPENROUTER_API_KEY|GEMINI_API_KEY|GROQ_API_KEY|MISTRAL_API_KEY|"
    r"COHERE_API_KEY|TOGETHER_API_KEY|REPLICATE_API_TOKEN|FIREWORKS_API_KEY|"
    r"HF_TOKEN|HUGGING_FACE_HUB_TOKEN|HUGGINGFACEHUB_API_TOKEN|"
    r"DEEPSEEK_API_KEY|XAI_API_KEY|OLLAMA_HOST)\b"
)

# Files whose NAME is the evidence.
_PATH_RULES = [
    # basename or suffix, kind, canonical name, confidence
    (".mcp.json", "mcp", "mcp-config", "certain"),
    ("mcp.json", "mcp", "mcp-config", "inferred"),
    ("claude_desktop_config.json", "mcp", "mcp-config", "certain"),
    ("CLAUDE.md", "assistant_config", "claude-instructions", "certain"),
    ("AGENTS.md", "assistant_config", "agents-instructions", "certain"),
    ("GEMINI.md", "assistant_config", "gemini-instructions", "certain"),
    (".cursorrules", "assistant_config", "cursor-rules", "certain"),
    (".windsurfrules", "assistant_config", "windsurf-rules", "certain"),
    (".clinerules", "assistant_config", "cline-rules", "certain"),
    ("copilot-instructions.md", "assistant_config", "copilot-instructions", "certain"),
    (".aider.conf.yml", "assistant_config", "aider-config", "certain"),
    ("Modelfile", "local_inference", "ollama-modelfile", "inferred"),
    (".gguf", "model_artifact", "gguf-weights", "certain"),
    (".safetensors", "model_artifact", "safetensors-weights", "certain"),
    (".prompty", "assistant_config", "prompty-template", "certain"),
]

# Content is scanned only for these languages plus common config formats: the
# signatures above are code-and-config signatures, and scanning prose invites
# every blog-post mention of gpt-4 into the inventory.
_SCAN_LANGUAGES = {
    "typescript", "javascript", "python", "rust", "go", "java", "ruby",
    "csharp", "cpp", "swift", "json", "yaml", "toml", "shell",
}
_MAX_SCAN_BYTES = 1_000_000  # minified bundles say nothing a manifest does not

_EVIDENCE_CAP = 5  # per item; instance_count keeps the honest total

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", (text or "").lower()).strip("-") or "root"


def _line_of(content: str, pos: int) -> int:
    return content.count("\n", 0, pos) + 1


class _Collector:
    """Aggregates raw hits into per-(kind, name, component) items."""

    def __init__(self, file_to_component) -> None:
        self._file_to_component = file_to_component
        self._items: dict[tuple, dict] = {}

    def hit(self, kind: str, name: str, file: str, line: Optional[int],
            confidence: str, detail: Optional[dict] = None) -> None:
        component = self._file_to_component(file)
        key = (kind, name, component)
        item = self._items.get(key)
        if item is None:
            item = self._items[key] = {
                "id": f"ai:{kind}:{_slug(name)}:{_slug(component)}",
                "kind": kind,
                "name": name,
                "component_id": component,
                "confidence": confidence,
                "instance_count": 0,
                "evidence": [],
                "detail": detail or {},
            }
        item["instance_count"] += 1
        # A single certain sighting outranks any number of inferred ones.
        if confidence == "certain":
            item["confidence"] = "certain"
        if len(item["evidence"]) < _EVIDENCE_CAP:
            ev = {"file": file}
            if line is not None:
                ev["line"] = line
            if ev not in item["evidence"]:
                item["evidence"].append(ev)
        if detail:
            item["detail"].update(
                {k: v for k, v in detail.items() if k not in item["detail"]}
            )

    def items(self) -> list[dict]:
        out = list(self._items.values())
        for item in out:
            item["evidence"].sort(key=lambda e: (e.get("file", ""), e.get("line", 0)))
        out.sort(key=lambda i: i["id"])
        return out


def _flatten_component_files(arch: dict) -> dict[str, str]:
    """path -> owning component id, deepest owner winning."""
    mapping: dict[str, str] = {}

    def walk(comp: dict) -> None:
        cid = comp.get("id") or ""
        for f in comp.get("files") or []:
            path = f.get("path") if isinstance(f, dict) else f
            if isinstance(path, str):
                mapping[path] = cid
        for child in comp.get("children") or []:
            if isinstance(child, dict):
                walk(child)

    for comp in arch.get("components") or []:
        if isinstance(comp, dict):
            walk(comp)
    return mapping


def _match_catalog_package(name: str) -> Optional[tuple]:
    lowered = (name or "").lower()
    for kind, canonical, pkgs, _mods, conf in _PKG:
        for pkg in pkgs:
            if lowered == pkg:
                return kind, canonical, conf
    return None


def _match_catalog_import(module: str) -> Optional[tuple]:
    lowered = (module or "").lower()
    for kind, canonical, _pkgs, mods, conf in _PKG:
        for mod in mods:
            if not mod:
                continue
            if mod.endswith("/") or mod.endswith("."):
                if lowered.startswith(mod):
                    return kind, canonical, conf
            elif lowered == mod or lowered.startswith(mod + ".") or lowered.startswith(mod + "/"):
                return kind, canonical, conf
    return None


# Hidden-directory artifacts checked directly against the scan root. Fixed and
# short on purpose: this is not a filesystem walk, it is a list of conventions.
_HIDDEN_ROOT_FILES = [
    (".github/copilot-instructions.md", "assistant_config", "copilot-instructions"),
    (".claude/settings.json", "assistant_config", "claude-config"),
]
_HIDDEN_ROOT_DIRS = [
    (".claude", "assistant_config", "claude-config"),
    (".cursor", "assistant_config", "cursor-config"),
    (".windsurf", "assistant_config", "windsurf-config"),
    (".gemini", "assistant_config", "gemini-config"),
    (".codex", "assistant_config", "codex-config"),
]


def emit_ai_surface(
    arch: dict,
    store: Any,
    *,
    supply_chain: Optional[dict] = None,
    root: Optional[str] = None,
) -> Optional[list]:
    """Detect the AI surface and return the ``ai_surface`` items array.

    ``supply_chain`` is the section ``emit_sbom`` returned, whose parsed
    dependency rows carry name, version, and manifest evidence: the highest-
    confidence class, reused rather than re-derived. The store supplies imports,
    file content, and the path inventory the extraction tier already recorded,
    so nothing here reads source from disk.

    Returns None only when there is nothing to scan at all (no store), so an
    unaffected projection stays byte-identical. An empty list is a real answer:
    "we looked, and this codebase has no detectable AI surface" is exactly the
    claim an owner wants to be able to make.
    """
    if store is None:
        return None
    from ..derive.storeview import StoreView

    view = StoreView.load(store)
    file_map = _flatten_component_files(arch)
    # The fallback owner is the root COMPONENT, whose id is not the empty
    # string: an item must always resolve to a component the ref band can find.
    root_id = ""
    for comp in arch.get("components") or []:
        if isinstance(comp, dict) and comp.get("id"):
            root_id = comp["id"]
            break

    def owner(path: str) -> str:
        if path in file_map:
            return file_map[path]
        # walk up: a config file may not be associated with a component's files
        parts = path.split("/")
        for cut in range(len(parts) - 1, 0, -1):
            candidate = "/".join(parts[:cut])
            for fpath, cid in file_map.items():
                if fpath.startswith(candidate + "/"):
                    return cid
        return root_id

    collector = _Collector(owner)

    # -- 1. dependencies -----------------------------------------------------
    for dep in (supply_chain or {}).get("dependencies") or []:
        matched = _match_catalog_package(dep.get("name", ""))
        if not matched:
            continue
        kind, canonical, conf = matched
        ev = dep.get("evidence") or {}
        collector.hit(
            kind, canonical, ev.get("file", ""), ev.get("line"), conf,
            detail={
                "package": dep.get("name"),
                "version": dep.get("version") or dep.get("declared"),
                "ecosystem": dep.get("ecosystem"),
                "scope": dep.get("scope"),
            },
        )

    # -- 2. imports ----------------------------------------------------------
    for path, modules in view.imports_by_path.items():
        for module in modules:
            matched = _match_catalog_import(module)
            if not matched:
                continue
            kind, canonical, conf = matched
            collector.hit(kind, canonical, path, None, conf,
                          detail={"import": module})

    # -- 3. content ----------------------------------------------------------
    lang_by_path = {f["path"]: (f.get("language") or "") for f in view.files}
    for path, content in view.content_by_path.items():
        if not content or len(content) > _MAX_SCAN_BYTES:
            continue
        if lang_by_path.get(path, "") not in _SCAN_LANGUAGES:
            continue
        for m in _HOST_RE.finditer(content):
            host = m.group(0)
            collector.hit("provider_endpoint", _HOST_TO_NAME.get(host, host),
                          path, _line_of(content, m.start()), "certain",
                          detail={"host": host})
        for m in _COMPAT_RE.finditer(content):
            collector.hit("openai_compat", "openai-wire-protocol",
                          path, _line_of(content, m.start()), "certain",
                          detail={"signature": m.group(0)})
        for m in _MODEL_ID_RE.finditer(content):
            collector.hit("model_id", m.group(0).lower(),
                          path, _line_of(content, m.start()), "certain")
        for m in _ENV_RE.finditer(content):
            collector.hit("ai_env", m.group(1),
                          path, _line_of(content, m.start()), "certain")

    # -- 4. paths ------------------------------------------------------------
    for path in view.all_paths:
        base = path.rsplit("/", 1)[-1]
        for pattern, kind, canonical, conf in _PATH_RULES:
            if pattern.startswith("."):
                hit = base == pattern or base.endswith(pattern)
            else:
                hit = base == pattern
            if hit:
                collector.hit(kind, canonical, path, None, conf,
                              detail={"artifact": base})
                break

    # -- 5. hidden-directory conventions, from the scan root -----------------
    if root:
        base = Path(root)
        for rel, kind, canonical in _HIDDEN_ROOT_FILES:
            if (base / rel).is_file():
                collector.hit(kind, canonical, rel, None, "certain",
                              detail={"artifact": rel})
        for rel, kind, canonical in _HIDDEN_ROOT_DIRS:
            d = base / rel
            if d.is_dir() and any(d.iterdir()):
                collector.hit(kind, canonical, rel + "/", None, "certain",
                              detail={"artifact": rel + "/"})

    return collector.items()
