from __future__ import annotations

import json
import logging
import os

from behavior.profile_manager import get_profile_manager

logger = logging.getLogger("Jarvis.Behavior")

_DEFAULT_PROFILE = {
    "name": "Luiz",
    "title": "Chefe",
    "risk_tolerance": "medium",
    "dev_preferences": {
        "ide": "vscode",
        "language": "python",
        "tabs_vs_spaces": "spaces",
    },
}


def load_behavior_profile(filepath: str) -> dict:
    """Carrega o perfil de comportamento, tratando erros de leitura."""
    if not os.path.exists(filepath):
        logger.warning("Perfil não encontrado em %s. Usando perfil padrão.", filepath)
        return dict(_DEFAULT_PROFILE)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            profile_data = json.load(f)
        logger.info("Perfil de comportamento carregado com sucesso.")
        return profile_data
    except json.JSONDecodeError as e:
        broken_path = f"{filepath}.broken"
        logger.error(
            "❌ Erro crítico: JSON corrompido em %s. Detalhes: %s", filepath, e
        )
        try:
            os.rename(filepath, broken_path)
            logger.warning(
                "Arquivo quebrado renomeado para %s. Usando perfil padrão.", broken_path
            )
        except OSError as rename_err:
            logger.error("Não foi possível renomear o arquivo quebrado: %s", rename_err)
        return dict(_DEFAULT_PROFILE)
    except Exception as e:
        logger.error("Erro genérico ao ler perfil: %s", e)
        return dict(_DEFAULT_PROFILE)


def learn_preferences(interactions: list) -> dict:
    profile = get_profile_manager().get()
    text = " ".join(str(i.get("text", i)) for i in interactions if i).lower()
    if any(term in text for term in ("resuma", "curto", "conciso", "short")):
        profile.verbosity = "minimal"
    elif any(term in text for term in ("detalhe", "passo a passo", "detailed")):
        profile.verbosity = "detailed"
    profile.update_count += 1
    get_profile_manager().save(profile)
    return profile.model_dump()

