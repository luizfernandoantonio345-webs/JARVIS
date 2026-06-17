"""
System Architect Route — JARVIS v7.0
Gera planos arquiteturais completos: tech stack, telas, módulos, banco, monetização
"""
from __future__ import annotations

import json
import re
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ArchitectRequest(BaseModel):
    description: str
    type: str = "auto"      # web, mobile, api, fullstack, desktop, auto
    budget: str = "startup"  # startup, medium, enterprise
    language: str = ""       # preferred language (optional)


_TYPE_HINTS = {
    "academia": "fullstack", "gym": "fullstack", "saas": "web",
    "e-commerce": "fullstack", "ecommerce": "fullstack", "loja": "fullstack",
    "app": "mobile", "mobile": "mobile", "delivery": "fullstack",
    "api": "api", "rest": "api", "microservices": "api",
    "desktop": "desktop", "dashboard": "web", "landing": "web",
    "blog": "web", "portfólio": "web", "portfolio": "web",
    "chat": "fullstack", "streaming": "fullstack",
}

_TECH_DEFAULTS = {
    "fullstack": {
        "frontend": "React + TypeScript + Tailwind CSS",
        "backend": "FastAPI (Python 3.11)",
        "database": "PostgreSQL + Redis (cache)",
        "mobile": "React Native (iOS + Android)",
        "auth": "JWT + bcrypt + refresh tokens",
        "storage": "AWS S3 / Cloudflare R2",
        "deploy": "Docker + VPS (Hetzner/DigitalOcean)",
        "ci_cd": "GitHub Actions",
    },
    "web": {
        "frontend": "Next.js 14 + TypeScript + Tailwind",
        "backend": "FastAPI (Python 3.11)",
        "database": "PostgreSQL",
        "auth": "NextAuth.js + JWT",
        "deploy": "Vercel (frontend) + Railway (backend)",
    },
    "mobile": {
        "frontend": "Flutter (iOS + Android)",
        "backend": "FastAPI (Python 3.11)",
        "database": "PostgreSQL + SQLite (local)",
        "auth": "JWT + biometria",
        "deploy": "App Store + Google Play + Railway (API)",
    },
    "api": {
        "backend": "FastAPI (Python 3.11) + Pydantic v2",
        "database": "PostgreSQL + Redis",
        "auth": "OAuth 2.0 + API Keys",
        "docs": "OpenAPI 3.1 (Swagger + ReDoc)",
        "deploy": "Docker + Kubernetes (ou Railway)",
    },
    "desktop": {
        "frontend": "Electron + React + TypeScript",
        "backend": "FastAPI local (Python)",
        "database": "SQLite",
        "deploy": "Electron Builder (Windows/Mac/Linux)",
    },
}


def _detect_type(description: str) -> str:
    d = description.lower()
    for keyword, t in _TYPE_HINTS.items():
        if keyword in d:
            return t
    if any(w in d for w in ['web', 'site', 'portal', 'plataforma']):
        return 'web'
    if any(w in d for w in ['app', 'aplicativo', 'mobile']):
        return 'mobile'
    return 'fullstack'


def _parse_llm_json(raw: str) -> dict:
    raw = re.sub(r'```(?:json)?\s*', '', raw).replace('```', '')
    m = re.search(r'\{[\s\S]+\}', raw)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return {}


@router.post("")
async def generate_architecture(req: ArchitectRequest):
    from ai.client import get_ai_client
    from core.jarvis_persona import _build_identity

    sys_type = req.type if req.type != "auto" else _detect_type(req.description)
    default_stack = _TECH_DEFAULTS.get(sys_type, _TECH_DEFAULTS["fullstack"])
    stack_hint = json.dumps(default_stack, ensure_ascii=False)
    lang_hint = f"Linguagem/framework preferido pelo Senhor: {req.language}. " if req.language else ""

    system = f"""{_build_identity()}

MODO ARQUITETO DE SISTEMAS SÊNIOR — 15+ anos em sistemas enterprise:
{lang_hint}
Gere um plano arquitetural COMPLETO e PROFISSIONAL.
Stack padrão sugerido (adapte ao nicho): {stack_hint}
Budget: {req.budget}

Retorne EXATAMENTE este JSON (válido, sem markdown, sem texto extra):
{{
  "title": "<nome profissional do sistema>",
  "tagline": "<slogan curto>",
  "niche": "<nicho de mercado>",
  "description": "<descrição do sistema em 2 frases>",
  "complexity": "simple|medium|complex|enterprise",
  "type": "{sys_type}",
  "tech_stack": {{
    "frontend": "<tech>",
    "backend": "<tech>",
    "database": "<tech>",
    "mobile": "<tech ou null>",
    "auth": "<tech>",
    "cache": "<tech ou null>",
    "storage": "<tech ou null>",
    "deploy": "<tech>",
    "ci_cd": "<tech>",
    "monitoring": "<tech>",
    "extras": ["<extra 1>", "<extra 2>"]
  }},
  "screens": [
    {{"name": "<nome da tela>", "description": "<função>", "priority": <1-5>, "complexity": "low|medium|high"}}
  ],
  "modules": [
    {{"name": "<módulo>", "description": "<função>", "estimated_hours": <horas>}}
  ],
  "database_tables": [
    {{"name": "<tabela>", "main_fields": ["<campo1>", "<campo2>", "<campo3>"]}}
  ],
  "api_endpoints": [
    {{"method": "GET|POST|PUT|DELETE", "path": "/api/<path>", "description": "<função>"}}
  ],
  "security_features": ["<feature 1>", "<feature 2>"],
  "estimated_hours": <total horas>,
  "estimated_sprints": <número de sprints de 2 semanas>,
  "team_size": "<ex: 1 dev solo | 2-3 devs>",
  "mvp_features": ["<feature MVP 1>", "<feature MVP 2>", "<feature MVP 3>", "<feature MVP 4>"],
  "monetization": [
    {{"model": "<modelo>", "price": "<valor em R$>", "description": "<como funciona>"}}
  ],
  "risks": [
    {{"risk": "<risco>", "mitigation": "<mitigação>"}}
  ],
  "next_steps": ["<passo 1>", "<passo 2>", "<passo 3>", "<passo 4>", "<passo 5>"]
}}

Regras:
- Seja ESPECÍFICO ao nicho descrito — não genérico
- Screens: mínimo 6, máximo 15 telas relevantes
- Modules: mínimo 5 módulos técnicos com horas estimadas
- Database: mínimo 5 tabelas com campos reais
- API endpoints: mínimo 8 endpoints reais
- Monetização: 2-4 modelos realistas para o nicho
- estimated_hours: realista para a complexidade (solo dev)
"""

    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Gere o plano completo para: {req.description}"},
    ]

    try:
        raw = get_ai_client().call(msgs)
        plan = _parse_llm_json(raw)
    except Exception as e:
        plan = {}

    # Fallback if LLM fails or returns invalid JSON
    if not plan or "title" not in plan:
        plan = {
            "title": req.description.title()[:60],
            "tagline": "Sistema desenvolvido com JARVIS",
            "niche": "geral",
            "description": f"Sistema completo para {req.description}.",
            "complexity": "medium",
            "type": sys_type,
            "tech_stack": default_stack,
            "screens": [
                {"name": "Dashboard", "description": "Visão geral", "priority": 1, "complexity": "medium"},
                {"name": "Cadastro", "description": "Formulário de cadastro", "priority": 1, "complexity": "low"},
                {"name": "Login", "description": "Autenticação", "priority": 1, "complexity": "low"},
                {"name": "Configurações", "description": "Perfil e config", "priority": 3, "complexity": "low"},
                {"name": "Relatórios", "description": "Análises e gráficos", "priority": 2, "complexity": "high"},
                {"name": "Listagem", "description": "Lista com filtros", "priority": 2, "complexity": "medium"},
            ],
            "modules": [
                {"name": "Autenticação JWT", "description": "Login/logout/refresh", "estimated_hours": 16},
                {"name": "CRUD Principal", "description": "Operações básicas", "estimated_hours": 40},
                {"name": "API REST", "description": "Endpoints documentados", "estimated_hours": 32},
                {"name": "Frontend Base", "description": "UI/UX responsivo", "estimated_hours": 60},
                {"name": "Deploy & CI/CD", "description": "Infraestrutura", "estimated_hours": 16},
            ],
            "database_tables": [
                {"name": "users", "main_fields": ["id", "email", "password_hash", "role", "created_at"]},
                {"name": "sessions", "main_fields": ["id", "user_id", "token", "expires_at"]},
                {"name": "settings", "main_fields": ["id", "key", "value", "updated_at"]},
                {"name": "audit_logs", "main_fields": ["id", "user_id", "action", "created_at"]},
                {"name": "notifications", "main_fields": ["id", "user_id", "message", "read", "created_at"]},
            ],
            "api_endpoints": [
                {"method": "POST", "path": "/api/auth/login", "description": "Autenticação"},
                {"method": "POST", "path": "/api/auth/register", "description": "Cadastro"},
                {"method": "GET", "path": "/api/users/me", "description": "Perfil atual"},
                {"method": "GET", "path": "/api/dashboard", "description": "Dados do dashboard"},
                {"method": "GET", "path": "/api/items", "description": "Listar itens"},
                {"method": "POST", "path": "/api/items", "description": "Criar item"},
                {"method": "PUT", "path": "/api/items/{id}", "description": "Atualizar item"},
                {"method": "DELETE", "path": "/api/items/{id}", "description": "Remover item"},
            ],
            "security_features": ["JWT + refresh tokens", "Rate limiting", "Input validation", "HTTPS"],
            "estimated_hours": 200,
            "estimated_sprints": 10,
            "team_size": "1 dev solo",
            "mvp_features": ["Autenticação", "CRUD principal", "Dashboard básico", "API documentada"],
            "monetization": [
                {"model": "SaaS mensal", "price": "R$97-297/mês", "description": "Assinatura por empresa"},
                {"model": "Setup fee", "price": "R$500-2000", "description": "Configuração inicial"},
            ],
            "risks": [
                {"risk": "Escopo não definido", "mitigation": "Documento de requisitos detalhado"},
                {"risk": "Prazo apertado", "mitigation": "MVP primeiro, features depois"},
            ],
            "next_steps": [
                "Validar requisitos com o Senhor",
                "Configurar ambiente de desenvolvimento",
                "Criar estrutura de pastas e repositório",
                "Implementar autenticação (base de tudo)",
                "Desenvolver MVP com 4 features principais",
            ],
        }

    screens = plan.get("screens", [])
    modules = plan.get("modules", [])
    tech = plan.get("tech_stack", {})
    hours = plan.get("estimated_hours", 0)
    sprints = plan.get("estimated_sprints", 0)

    voice = (
        f"Plano arquitetural gerado para '{plan.get('title', req.description)}', Senhor. "
        f"Sistema {plan.get('complexity', '')} — {len(screens)} telas, {len(modules)} módulos. "
        f"Stack: {tech.get('frontend', '?')} + {tech.get('backend', '?')}. "
        f"Estimativa: {hours} horas ({sprints} sprints). "
        f"Aguardando confirmação para iniciar o desenvolvimento."
    )

    return {
        "voice_response": voice,
        "display_type": "architect_plan",
        "data": plan,
    }
