"""Bind every AI syscall into a host registry."""

from __future__ import annotations

from typing import Any


from .llm_api import (
    ai_llm_create,
    ai_llm_dataset,
    ai_llm_eval,
    ai_llm_generate,
    ai_llm_info,
    ai_llm_load,
    ai_llm_save,
    ai_llm_tokenize,
    ai_llm_train,
)
from .llm_service import (
    ai_llm_backends,
    ai_llm_chat,
    ai_llm_complete,
    ai_llm_device_plan,
    ai_llm_models,
    ai_llm_tensor,
    ai_llm_tensor_batch,
)
from .models import (
    ai_chat,
    ai_embed,
    ai_loss_history,
    ai_model_create,
    ai_model_info,
    ai_model_load,
    ai_model_save,
    ai_models_list,
    ai_predict,
    ai_train,
)
from .providers import ai_api_complete, ai_api_configure, ai_api_embed, ai_api_providers
from .sessions import (
    ai_prompt_template,
    ai_rag_answer,
    ai_runtime_boot,
    ai_runtime_info,
    ai_session_history,
    ai_session_message,
    ai_session_open,
    ai_vector_search,
)


def register_ai_functions(registry: Any) -> None:
    """Register all AI host functions into a HostRegistry."""
    from ..host.runtime import HostFunction

    def _api_complete(args: Any) -> Any:
        return ai_api_complete(args, runtime_config=registry.runtime_config)

    funcs = [
        HostFunction("std.ai.model_create",  ai_model_create,  cost=5,  min_args=1, max_args=3),
        HostFunction("std.ai.train",         ai_train,          cost=50, min_args=3, max_args=5),
        HostFunction("std.ai.predict",       ai_predict,        cost=5,  min_args=2, max_args=2),
        HostFunction("std.ai.model_save",    ai_model_save,     cost=10, min_args=2, max_args=2),
        HostFunction("std.ai.model_load",    ai_model_load,     cost=10, min_args=1, max_args=1),
        HostFunction("std.ai.embed",         ai_embed,          cost=5,  min_args=1, max_args=1),
        HostFunction("std.ai.chat",          ai_chat,           cost=10, min_args=1, max_args=3),
        HostFunction("std.ai.runtime_boot",  ai_runtime_boot,   cost=2,  min_args=0, max_args=1),
        HostFunction("std.ai.runtime_info",  ai_runtime_info,   cost=1,  min_args=0, max_args=0),
        HostFunction("std.ai.session_open",  ai_session_open,   cost=2,  min_args=0, max_args=2),
        HostFunction("std.ai.session_message", ai_session_message, cost=5, min_args=2, max_args=2),
        HostFunction("std.ai.session_history", ai_session_history, cost=1, min_args=1, max_args=1),
        HostFunction("std.ai.prompt_template", ai_prompt_template, cost=1, min_args=2, max_args=2),
        HostFunction("std.ai.vector_search", ai_vector_search,  cost=3,  min_args=2, max_args=3),
        HostFunction("std.ai.rag_answer",    ai_rag_answer,     cost=5,  min_args=2, max_args=3),
        HostFunction("std.ai.loss_history",  ai_loss_history,   cost=1,  min_args=1, max_args=1),
        HostFunction("std.ai.model_info",    ai_model_info,     cost=1,  min_args=1, max_args=1),
        HostFunction("std.ai.models_list",   ai_models_list,    cost=1,  min_args=0, max_args=0),
        HostFunction("std.ai.api_providers", ai_api_providers,  cost=1,  min_args=0, max_args=0),
        HostFunction("std.ai.api_configure", ai_api_configure,  cost=1,  min_args=1, max_args=2),
        HostFunction("std.ai.api_complete",  _api_complete,     cost=2,  min_args=1, max_args=3),
        HostFunction("std.ai.api_embed",     ai_api_embed,      cost=1,  min_args=1, max_args=2),
        HostFunction("std.ai.llm_create",    ai_llm_create,     cost=5,  min_args=1, max_args=2),
        HostFunction("std.ai.llm_train",     ai_llm_train,      cost=80, min_args=2, max_args=3),
        HostFunction("std.ai.llm_generate",  ai_llm_generate,   cost=20, min_args=1, max_args=3),
        HostFunction("std.ai.llm_tokenize",  ai_llm_tokenize,   cost=2,  min_args=1, max_args=1),
        HostFunction("std.ai.llm_info",      ai_llm_info,       cost=1,  min_args=0, max_args=1),
        HostFunction("std.ai.llm_dataset",   ai_llm_dataset,    cost=5,  min_args=1, max_args=2),
        HostFunction("std.ai.llm_eval",      ai_llm_eval,       cost=10, min_args=2, max_args=2),
        HostFunction("std.ai.llm_complete",  ai_llm_complete,   cost=20, min_args=2, max_args=3),
        HostFunction("std.ai.llm_chat",      ai_llm_chat,       cost=20, min_args=2, max_args=3),
        HostFunction("std.ai.llm_models",    ai_llm_models,     cost=1,  min_args=0, max_args=0),
        HostFunction("std.ai.llm_backends",  ai_llm_backends,   cost=1,  min_args=0, max_args=0),
        HostFunction("std.ai.llm_device_plan", ai_llm_device_plan, cost=1, min_args=0, max_args=1),
        HostFunction("std.ai.llm_tensor",    ai_llm_tensor,     cost=10, min_args=1, max_args=6),
        HostFunction("std.ai.llm_tensor_batch", ai_llm_tensor_batch, cost=20, min_args=1, max_args=1),
        HostFunction("std.ai.llm_save",      ai_llm_save,       cost=10, min_args=2, max_args=2),
        HostFunction("std.ai.llm_load",      ai_llm_load,       cost=10, min_args=1, max_args=1),
    ]
    for fn in funcs:
        registry.register(fn)
