"""Provedores de LLM para o realizador ``llm`` (variante B).

Interface mínima: ``complete(system, user, schema) -> str`` devolve o texto
JSON da resposta. Os SDKs são dependências **opcionais**, importadas só
quando o provedor é usado (o resto do pacote segue só com a biblioteca
padrão):

- ``anthropic``: ``pip install anthropic`` (credenciais: ``ANTHROPIC_API_KEY``
  ou perfil do ``ant auth login``).
- ``openai``: ``pip install openai``; serve para OpenAI e qualquer API
  compatível (Ollama, vLLM, Groq...) via ``base_url``. Chave em
  ``OPENAI_API_KEY`` (Ollama aceita qualquer valor).
- ``dry``: não chama nada; conta requisições e estima tokens para orçar a
  geração antes de gastar.
"""


class LLMUnavailable(Exception):
    """A chamada não produziu texto utilizável (recusa, erro, dry-run)."""


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model="claude-opus-5-5", effort="low", max_tokens=16000, max_retries=4):
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - depende do ambiente
            raise SystemExit("O provedor 'anthropic' precisa do SDK: pip install anthropic") from e
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=max_retries)  # o SDK já repete 408/409/429/5xx
        self.model, self.effort, self.max_tokens = model, effort, max_tokens

    def params(self):
        return {"provider": self.name, "model": self.model, "effort": self.effort}

    def complete(self, system, user, schema):
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",  # recusa de classificador é refeita em outro modelo, no servidor
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except self._anthropic.APIStatusError as e:
            raise LLMUnavailable(f"HTTP {e.status_code}: {e.message}") from e
        except self._anthropic.APIConnectionError as e:
            raise LLMUnavailable(f"conexão: {e}") from e
        if resp.stop_reason == "refusal":
            raise LLMUnavailable("recusa do modelo")
        if resp.stop_reason == "max_tokens":
            raise LLMUnavailable("resposta truncada (max_tokens)")
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if not text:
            raise LLMUnavailable("resposta sem texto")
        return text


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(self, model, base_url=None, max_retries=4):
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover - depende do ambiente
            raise SystemExit("O provedor 'openai' precisa do SDK: pip install openai") from e
        self.client = OpenAI(base_url=base_url, max_retries=max_retries) if base_url else OpenAI(max_retries=max_retries)
        self.model, self.base_url = model, base_url

    def params(self):
        return {"provider": self.name, "model": self.model, "base_url": self.base_url}

    def complete(self, system, user, schema):
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user + "\n\nReply with a single JSON object only."}],
                response_format={"type": "json_object"},
            )
        except Exception as e:  # erros tipados variam entre servidores compatíveis
            raise LLMUnavailable(str(e)) from e
        text = resp.choices[0].message.content if resp.choices else None
        if not text:
            raise LLMUnavailable("resposta sem texto")
        return text


class DryRunProvider:
    """Não chama LLM: acumula a contagem de requisições e uma estimativa de
    tokens (≈ 4 caracteres por token) e força o fallback para as regras."""

    name = "dry"

    def __init__(self, model="claude-opus-5-5", **_):
        self.model = model
        self.requests = 0
        self.input_chars = 0
        self.expected_output_chars = 0

    def params(self):
        return {"provider": self.name, "model": self.model}

    def complete(self, system, user, schema):
        self.requests += 1
        self.input_chars += len(system) + len(user)
        self.expected_output_chars += int(len(user) * 0.6)  # a resposta reescreve ~os mesmos turnos, sem metadados
        raise LLMUnavailable("dry-run")

    def estimate(self):
        return {"requests": self.requests, "input_tokens": self.input_chars // 4, "output_tokens": self.expected_output_chars // 4}


def make_provider(name, model=None, effort="low", base_url=None):
    if name == "anthropic":
        return AnthropicProvider(model=model or "claude-opus-5-5", effort=effort)
    if name == "openai":
        if not model:
            raise SystemExit("--llm-model é obrigatório com --llm-provider openai")
        return OpenAICompatibleProvider(model=model, base_url=base_url)
    if name == "dry":
        return DryRunProvider(model=model or "claude-opus-5-5")
    raise SystemExit(f"provedor desconhecido: {name} (opções: anthropic, openai, dry)")
