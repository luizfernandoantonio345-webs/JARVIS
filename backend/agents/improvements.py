"""
Advanced agent capabilities for faster, smarter responses
B6: Memory context injection
B7: Quick response detection
B8-B10: Specialized endpoints
"""

QUICK_RESPONSES = {
    # Time queries
    "what time is it": lambda: __import__('datetime').datetime.now().strftime("It's %H:%M, Sir"),
    "que horas são": lambda: __import__('datetime').datetime.now().strftime("São %H:%M, Senhor"),
    "what's the date": lambda: __import__('datetime').datetime.now().strftime("Today is %B %d, %Y, Sir"),
    
    # Status queries  
    "are you online": lambda: "All systems operational, Sir",
    "status": lambda: "All systems operational, Sir",
    "jarvis status": lambda: "All systems operational, Sir",
    "tudo bem": lambda: "Todos os sistemas operacionais, Senhor",
    
    # Greeting
    "hello jarvis": lambda: "Good day, Sir. How may I assist?",
    "oi jarvis": lambda: "Boa tarde, Senhor. Como posso ajudar?",
    "good morning": lambda: "Good morning, Sir. What do you need?",
    "bom dia": lambda: "Bom dia, Senhor. Como posso ajudar?",
}

async def check_quick_response(message: str) -> str | None:
    """Check if message matches a quick response pattern"""
    msg_lower = message.strip().lower()
    
    for pattern, fn in QUICK_RESPONSES.items():
        if pattern in msg_lower:
            try:
                response = fn()
                return response
            except Exception:
                return None
    
    return None

async def inject_memory_context(session_id: str) -> str:
    """Inject relevant memory context before LLM call"""
    try:
        from memory.persistent_memory import get_persistent_memory
        mem = get_persistent_memory()
        
        parts = []
        
        # User profile
        profile = mem.get_profile()
        if profile:
            profile_str = "; ".join(f"{k}={v}" for k, v in profile.items())
            parts.append(f"[Profile] {profile_str}")
        
        # Recent facts
        facts = mem.get_facts(5)
        if facts:
            facts_str = "; ".join(facts[:3])
            parts.append(f"[Facts] {facts_str}")
        
        # Recent conversation
        recent = mem.get_recent(session_id, 3)
        if recent:
            recent_str = "; ".join([f"User: {r.get('user', '')}" for r in recent])
            parts.append(f"[Recent] {recent_str}")
        
        return "\n".join(parts) if parts else ""
    except Exception:
        return ""

async def detect_language(text: str) -> str:
    """Auto-detect language (en or pt)"""
    pt_words = ["como", "é", "você", "por", "que", "bem", "quer", "fazer", "pode", "já"]
    en_words = ["how", "is", "you", "why", "what", "well", "want", "make", "can", "already"]
    
    text_lower = text.lower().split()
    
    pt_count = sum(1 for w in text_lower if any(pw in w for pw in pt_words))
    en_count = sum(1 for w in text_lower if any(ew in w for ew in en_words))
    
    return "pt" if pt_count > en_count else "en"
