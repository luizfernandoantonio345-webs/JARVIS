import sqlite3, json, time, pathlib, logging, os
log = logging.getLogger("jarvis.experience")

def _get_db_path() -> pathlib.Path:
    try:
        from backend.config import get_config
        d = pathlib.Path(get_config().data_dir)
    except Exception:
        d = pathlib.Path("data")
    d.mkdir(exist_ok=True)
    return d / "experience.db"

class ExperienceEngine:
    def __init__(self):
        self._db = _get_db_path()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self._db) as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                problem TEXT DEFAULT '',
                solution TEXT DEFAULT '',
                outcome TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                confidence REAL DEFAULT 1.0,
                times_used INTEGER DEFAULT 0,
                created_at REAL DEFAULT (unixepoch()),
                updated_at REAL DEFAULT (unixepoch())
            );
            CREATE TABLE IF NOT EXISTS reflections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                what_worked TEXT,
                what_failed TEXT,
                pattern TEXT,
                improvement TEXT,
                created_at REAL DEFAULT (unixepoch())
            );
            CREATE INDEX IF NOT EXISTS idx_exp_cat ON experiences(category);
            CREATE INDEX IF NOT EXISTS idx_exp_title ON experiences(title);
            """)

    def save(self, category: str, title: str, problem: str = "",
             solution: str = "", outcome: str = "",
             tags: list = None, confidence: float = 1.0) -> int:
        with sqlite3.connect(self._db) as c:
            cur = c.execute(
                "INSERT INTO experiences (category,title,problem,solution,outcome,tags,confidence) VALUES(?,?,?,?,?,?,?)",
                (category, title[:200], problem[:3000], solution[:8000], outcome[:1000], json.dumps(tags or []), confidence)
            )
            return cur.lastrowid

    def find(self, query: str, category: str = None, limit: int = 5) -> list:
        if not query:
            with sqlite3.connect(self._db) as c:
                rows = c.execute("SELECT * FROM experiences ORDER BY times_used DESC, created_at DESC LIMIT ?", (limit,)).fetchall()
        else:
            q = f"%{query[:60]}%"
            with sqlite3.connect(self._db) as c:
                if category:
                    rows = c.execute("SELECT * FROM experiences WHERE category=? AND (title LIKE ? OR problem LIKE ? OR solution LIKE ?) ORDER BY times_used DESC, confidence DESC LIMIT ?", (category, q, q, q, limit)).fetchall()
                else:
                    rows = c.execute("SELECT * FROM experiences WHERE title LIKE ? OR problem LIKE ? OR solution LIKE ? ORDER BY times_used DESC, confidence DESC LIMIT ?", (q, q, q, limit)).fetchall()
        cols = ["id","category","title","problem","solution","outcome","tags","confidence","times_used","created_at","updated_at"]
        return [dict(zip(cols, r)) for r in rows]

    def use(self, exp_id: int):
        with sqlite3.connect(self._db) as c:
            c.execute("UPDATE experiences SET times_used=times_used+1, updated_at=unixepoch() WHERE id=?", (exp_id,))

    def reflect(self, session_id: str, worked: str, failed: str, pattern: str = "", improvement: str = ""):
        with sqlite3.connect(self._db) as c:
            c.execute("INSERT INTO reflections (session_id,what_worked,what_failed,pattern,improvement) VALUES(?,?,?,?,?)", (session_id, worked[:1000], failed[:1000], pattern[:500], improvement[:500]))

    def stats(self) -> dict:
        with sqlite3.connect(self._db) as c:
            total = c.execute("SELECT COUNT(*) FROM experiences").fetchone()[0]
            cats = c.execute("SELECT category, COUNT(*) FROM experiences GROUP BY category").fetchall()
            refs = c.execute("SELECT COUNT(*) FROM reflections").fetchone()[0]
        return {"total": total, "categories": dict(cats), "reflections": refs}

_exp = None
def get_experience() -> ExperienceEngine:
    global _exp
    if _exp is None:
        _exp = ExperienceEngine()
    return _exp
