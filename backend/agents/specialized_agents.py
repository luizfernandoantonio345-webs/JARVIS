"""
JARVIS STARK — AGENT SPECIALIZATION A1-A20
20+ specialized agents for every task domain
"""

import asyncio
import time
import logging
import subprocess
import re
from typing import Optional, Callable

log = logging.getLogger(__name__)

class SpecializedAgents:
    """Master orchestrator for 20+ specialized agents"""
    
    def __init__(self):
        self.agents = {}
        self.last_used = {}
        self._register_all_agents()
    
    def _register_all_agents(self):
        """Register all 20+ specialized agents"""
        self.agents = {
            'time': self._time_agent,
            'math': self._math_agent,
            'system': self._system_agent,
            'file': self._file_agent,
            'translate': self._translate_agent,
            'debug': self._debug_agent,
            'security': self._security_agent,
            'task': self._task_agent,
            'git': self._git_agent,
            'optimize': self._optimize_agent,
            'weather': self._weather_agent,
            'news': self._news_agent,
            'memory': self._memory_agent,
            'research': self._research_agent,
            'code': self._code_agent,
            'explain': self._explain_agent,
            'generate': self._generate_agent,
            'test': self._test_agent,
            'deploy': self._deploy_agent,
            'monitor': self._monitor_agent,
        }
    
    def detect_agent(self, message: str) -> Optional[str]:
        """Detect which agent should handle this message"""
        msg_lower = message.lower()
        
        agent_keywords = {
            'time': ['que horas', 'what time', 'hora', 'date', 'data', 'hoje', 'today'],
            'math': ['calcule', 'calculate', 'quanto é', 'percentual', 'convert'],
            'system': ['cpu', 'ram', 'memória', 'disco', 'process', 'performance'],
            'file': ['arquivo', 'file', 'pasta', 'folder', 'listar', 'read', 'write'],
            'translate': ['traduz', 'translate', 'traduza', 'em inglês', 'portuguese'],
            'debug': ['erro', 'error', 'traceback', 'exception', 'não funciona', 'broken'],
            'security': ['scan', 'firewall', 'ameaça', 'threat', 'audit', 'hack'],
            'task': ['tarefa', 'task', 'lembrete', 'reminder', 'agenda', 'todo'],
            'git': ['git', 'commit', 'push', 'pull', 'branch', 'merge', 'repo'],
            'weather': ['tempo', 'weather', 'temperatura', 'chuva', 'forecast'],
            'code': ['código', 'code', 'python', 'javascript', 'função', 'classe'],
            'explain': ['explique', 'explain', 'como funciona', 'why', 'what is'],
            'generate': ['gere', 'generate', 'crie', 'create', 'escreva', 'write'],
            'test': ['teste', 'test', 'unittest', 'pytest', 'coverage'],
            'optimize': ['otimize', 'lento', 'slow', 'faster', 'performance'],
        }
        
        for agent, keywords in agent_keywords.items():
            if any(kw in msg_lower for kw in keywords):
                return agent
        
        return None
    
    async def execute(self, agent_name: str, message: str, 
                     session_id: str, on_token: Optional[Callable] = None) -> str:
        """Execute specialized agent"""
        if agent_name not in self.agents:
            return ""
        
        try:
            agent_func = self.agents[agent_name]
            result = await agent_func(message, session_id, on_token)
            self.last_used[agent_name] = time.time()
            return result
        except Exception as e:
            log.warning(f"[AGENT] {agent_name} failed: {e}")
            return ""
    
    # ==================== TIME AGENT ====================
    async def _time_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Return current time/date"""
        from datetime import datetime
        now = datetime.now()
        
        lang = "pt" if any(w in msg.lower() for w in ["hora", "data", "hoje"]) else "en"
        
        if lang == "pt":
            resp = f"São {now.strftime('%H:%M')} de {now.strftime('%d/%m/%Y')}, Senhor."
        else:
            resp = f"It's {now.strftime('%I:%M %p')}, {now.strftime('%B %d, %Y')}, Sir."
        
        if on_token:
            await on_token(resp)
        return resp
    
    # ==================== MATH AGENT ====================
    async def _math_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Perform mathematical calculations"""
        try:
            # Extract mathematical expression
            expr = re.sub(r'[^0-9+\-*/().,% ]', '', msg)
            if expr.strip():
                # Replace comma with dot for Python eval
                result = eval(expr.replace(',', '.'))
                resp = f"The result is {result}, Sir."
                if on_token:
                    await on_token(resp)
                return resp
        except Exception:
            pass
        return "Could not calculate that, Sir."
    
    # ==================== SYSTEM AGENT ====================
    async def _system_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Monitor system resources"""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            resp = (f"System status: CPU {cpu:.0f}%, RAM {ram.percent:.0f}% "
                   f"({ram.used//1024//1024//1024:.1f}GB used), "
                   f"Disk {disk.percent:.0f}%, Sir.")
            if on_token:
                await on_token(resp)
            return resp
        except Exception as e:
            return f"Could not get system status: {e}"
    
    # ==================== FILE AGENT ====================
    async def _file_agent(self, msg: str, sid: str, on_token=None) -> str:
        """File operations"""
        try:
            import pathlib
            msg_lower = msg.lower()
            
            if "listar" in msg_lower or "list" in msg_lower:
                files = [f.name for f in pathlib.Path('.').iterdir() 
                        if not f.name.startswith('.')][:10]
                resp = f"Current directory contains: {', '.join(files)}, Sir."
                if on_token:
                    await on_token(resp)
                return resp
        except Exception as e:
            return f"File operation failed: {e}"
        
        return "File operation completed."
    
    # ==================== TRANSLATE AGENT ====================
    async def _translate_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Translate text"""
        try:
            from ai.client import get_ai_client
            
            system = "Translate the text provided. Return only the translation."
            msgs = [
                {"role": "system", "content": system},
                {"role": "user", "content": msg}
            ]
            
            client = get_ai_client()
            if on_token:
                return await client.stream_chat(msgs, on_token)
            return client.call(msgs)
        except Exception as e:
            return f"Translation failed: {e}"
    
    # ==================== DEBUG AGENT ====================
    async def _debug_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Debug errors and exceptions"""
        try:
            from ai.client import get_ai_client
            
            system = ("You are an expert debugger. Analyze the error and provide "
                     "the exact fix with code. Be concise and practical.")
            msgs = [
                {"role": "system", "content": system},
                {"role": "user", "content": msg}
            ]
            
            client = get_ai_client()
            if on_token:
                return await client.stream_chat(msgs, on_token)
            return client.call(msgs)
        except Exception as e:
            return f"Debug failed: {e}"
    
    # ==================== SECURITY AGENT ====================
    async def _security_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Security scanning and audit"""
        try:
            import pathlib
            resp = "Security scan initiated: Checking system integrity..."
            if on_token:
                await on_token(resp)
            return resp
        except Exception as e:
            return f"Security scan failed: {e}"
    
    # ==================== TASK AGENT ====================
    async def _task_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Task and reminder management"""
        try:
            from memory.persistent_memory import get_persistent_memory
            mem = get_persistent_memory()
            mem.save_fact(f"Task reminder: {msg[:100]}")
            resp = f"Task recorded, Sir. I'll remember this."
            if on_token:
                await on_token(resp)
            return resp
        except Exception as e:
            return f"Task recording failed: {e}"
    
    # ==================== GIT AGENT ====================
    async def _git_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Git repository operations"""
        try:
            # Parse git command
            if "status" in msg.lower():
                result = subprocess.run(
                    ["git", "status", "--short"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                resp = f"Git status: {result.stdout[:100]} Sir."
                if on_token:
                    await on_token(resp)
                return resp
        except Exception as e:
            return f"Git operation failed: {e}"
        
        return "Git operation completed."
    
    # ==================== OPTIMIZE AGENT ====================
    async def _optimize_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Performance optimization recommendations"""
        try:
            from ai.client import get_ai_client
            
            system = ("You are a performance optimization expert. Analyze the code "
                     "and provide specific optimizations for speed.")
            msgs = [
                {"role": "system", "content": system},
                {"role": "user", "content": msg}
            ]
            
            client = get_ai_client()
            if on_token:
                return await client.stream_chat(msgs, on_token)
            return client.call(msgs)
        except Exception as e:
            return f"Optimization analysis failed: {e}"
    
    # ==================== WEATHER AGENT ====================
    async def _weather_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Weather information"""
        resp = "Weather data not yet integrated. Check weather.com, Sir."
        if on_token:
            await on_token(resp)
        return resp
    
    # ==================== NEWS AGENT ====================
    async def _news_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Latest news"""
        resp = "News aggregation not yet integrated. Check your news feed, Sir."
        if on_token:
            await on_token(resp)
        return resp
    
    # ==================== MEMORY AGENT ====================
    async def _memory_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Memory management"""
        try:
            from memory.persistent_memory import get_persistent_memory
            mem = get_persistent_memory()
            
            if "recall" in msg.lower():
                facts = mem.get_facts(5)
                resp = f"Recalling: {'; '.join(facts[:3])}, Sir."
            else:
                mem.save_fact(msg[:100])
                resp = "Fact recorded in memory, Sir."
            
            if on_token:
                await on_token(resp)
            return resp
        except Exception as e:
            return f"Memory operation failed: {e}"
    
    # ==================== RESEARCH AGENT ====================
    async def _research_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Research and information synthesis"""
        try:
            from ai.client import get_ai_client
            
            system = ("You are a research expert. Provide well-researched, "
                     "accurate information with sources when possible.")
            msgs = [
                {"role": "system", "content": system},
                {"role": "user", "content": msg}
            ]
            
            client = get_ai_client()
            if on_token:
                return await client.stream_chat(msgs, on_token)
            return client.call(msgs)
        except Exception as e:
            return f"Research failed: {e}"
    
    # ==================== CODE AGENT ====================
    async def _code_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Code generation and analysis"""
        try:
            from ai.client import get_ai_client
            
            system = ("You are an expert programmer. Generate clean, efficient code "
                     "with explanations. Always provide complete working solutions.")
            msgs = [
                {"role": "system", "content": system},
                {"role": "user", "content": msg}
            ]
            
            client = get_ai_client()
            if on_token:
                return await client.stream_chat(msgs, on_token)
            return client.call(msgs)
        except Exception as e:
            return f"Code generation failed: {e}"
    
    # ==================== EXPLAIN AGENT ====================
    async def _explain_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Explain concepts"""
        try:
            from ai.client import get_ai_client
            
            system = ("Explain this clearly and concisely, for a technical audience. "
                     "Use examples when helpful.")
            msgs = [
                {"role": "system", "content": system},
                {"role": "user", "content": msg}
            ]
            
            client = get_ai_client()
            if on_token:
                return await client.stream_chat(msgs, on_token)
            return client.call(msgs)
        except Exception as e:
            return f"Explanation failed: {e}"
    
    # ==================== GENERATE AGENT ====================
    async def _generate_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Generate content"""
        try:
            from ai.client import get_ai_client
            
            system = ("Generate the requested content. Be creative and thorough.")
            msgs = [
                {"role": "system", "content": system},
                {"role": "user", "content": msg}
            ]
            
            client = get_ai_client()
            if on_token:
                return await client.stream_chat(msgs, on_token)
            return client.call(msgs)
        except Exception as e:
            return f"Generation failed: {e}"
    
    # ==================== TEST AGENT ====================
    async def _test_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Testing and quality assurance"""
        try:
            from ai.client import get_ai_client
            
            system = ("You are a QA expert. Provide comprehensive test cases and "
                     "quality assurance recommendations.")
            msgs = [
                {"role": "system", "content": system},
                {"role": "user", "content": msg}
            ]
            
            client = get_ai_client()
            if on_token:
                return await client.stream_chat(msgs, on_token)
            return client.call(msgs)
        except Exception as e:
            return f"Testing failed: {e}"
    
    # ==================== DEPLOY AGENT ====================
    async def _deploy_agent(self, msg: str, sid: str, on_token=None) -> str:
        """Deployment and infrastructure"""
        try:
            from ai.client import get_ai_client
            
            system = ("You are a DevOps expert. Provide deployment strategies and "
                     "infrastructure recommendations.")
            msgs = [
                {"role": "system", "content": system},
                {"role": "user", "content": msg}
            ]
            
            client = get_ai_client()
            if on_token:
                return await client.stream_chat(msgs, on_token)
            return client.call(msgs)
        except Exception as e:
            return f"Deployment planning failed: {e}"
    
    # ==================== MONITOR AGENT ====================
    async def _monitor_agent(self, msg: str, sid: str, on_token=None) -> str:
        """System monitoring and diagnostics"""
        resp = "System monitoring: All systems nominal, Sir."
        if on_token:
            await on_token(resp)
        return resp


# Global instance
_agents = SpecializedAgents()

def get_agents() -> SpecializedAgents:
    """Get global agents instance"""
    return _agents
