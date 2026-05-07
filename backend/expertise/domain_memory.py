from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from pydantic import BaseModel, Field

from config import get_config
from .knowledge_researcher import ResearchResult


class DomainKnowledge(BaseModel):
    domain: str
    role: str
    research: ResearchResult
    usage_count: int = 0
    last_used: float = Field(default_factory=time.time)
    quality_score: float = 0.0


class DomainMemory:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_config().memory_db_path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), check_same_thread=False)

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS domain_knowledge (
                    domain TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    research_json TEXT NOT NULL,
                    usage_count INTEGER DEFAULT 0,
                    last_used REAL NOT NULL,
                    quality_score REAL DEFAULT 0.0
                )
                """
            )
            conn.commit()

    async def save(self, knowledge: DomainKnowledge | ResearchResult) -> DomainKnowledge:
        if isinstance(knowledge, ResearchResult):
            item = DomainKnowledge(domain=knowledge.domain, role=knowledge.role, research=knowledge)
        else:
            item = knowledge
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO domain_knowledge(domain, role, research_json, usage_count, last_used, quality_score)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    role=excluded.role,
                    research_json=excluded.research_json,
                    last_used=excluded.last_used
                """,
                (
                    item.domain,
                    item.role,
                    item.research.model_dump_json(),
                    item.usage_count,
                    item.last_used,
                    item.quality_score,
                ),
            )
            conn.commit()
        try:
            from services.memory_service import set_project_context
            set_project_context("default", f"domain:{item.domain}", item.research.knowledge_base)
        except Exception:
            pass
        return item

    async def load(self, domain: str) -> ResearchResult | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT research_json, usage_count FROM domain_knowledge WHERE lower(domain)=lower(?)",
                (domain,),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE domain_knowledge SET usage_count=?, last_used=? WHERE lower(domain)=lower(?)",
                ((row[1] or 0) + 1, time.time(), domain),
            )
            conn.commit()
        return ResearchResult.model_validate(json.loads(row[0]))

    async def delete(self, domain: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM domain_knowledge WHERE lower(domain)=lower(?)", (domain,))
            conn.commit()
            return cur.rowcount > 0

    async def update_quality(self, domain: str, score: float) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE domain_knowledge SET quality_score=? WHERE lower(domain)=lower(?)", (score, domain))
            conn.commit()

    async def list_known_domains(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT domain, role, usage_count, last_used, quality_score FROM domain_knowledge ORDER BY usage_count DESC, last_used DESC"
            ).fetchall()
        return [
            {"domain": r[0], "role": r[1], "usage_count": r[2], "last_used": r[3], "quality_score": r[4]}
            for r in rows
        ]

    async def get_stats(self) -> dict:
        domains = await self.list_known_domains()
        avg = sum(d["quality_score"] or 0 for d in domains) / len(domains) if domains else 0.0
        return {"known_domains": len(domains), "average_quality_score": avg, "most_used": domains[:5]}

    async def get_relevant_knowledge(self, query: str) -> str:
        domains = await self.list_known_domains()
        q = query.lower()
        for d in domains:
            if d["domain"].lower() in q or any(part in q for part in d["domain"].lower().split()):
                loaded = await self.load(d["domain"])
                return loaded.knowledge_base if loaded else ""
        return ""

