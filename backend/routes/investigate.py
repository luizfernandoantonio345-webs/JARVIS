"""
OSINT Investigation Route — JARVIS v7.0
Investigação de informações públicas: telefone, IP, email, domínio
"""
from __future__ import annotations

import re
import socket
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class InvestigateRequest(BaseModel):
    target: str
    query: str = ""
    type: str = "auto"  # phone, ip, email, domain, auto


def _detect_type(target: str) -> str:
    t = target.strip()
    if re.match(r'^\+?[\d\s\-().]{7,20}$', t):
        return "phone"
    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', t):
        return "ip"
    if re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', t):
        return "email"
    if re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$', t):
        return "domain"
    return "text"


# ── Brazilian DDD → city mapping ───────────────────────────────────────────────
_BR_DDD: dict[str, str] = {
    '11': 'São Paulo', '12': 'São José dos Campos', '13': 'Santos',
    '14': 'Bauru', '15': 'Sorocaba', '16': 'Ribeirão Preto',
    '17': 'São José do Rio Preto', '18': 'Presidente Prudente',
    '19': 'Campinas', '21': 'Rio de Janeiro', '22': 'Campos dos Goytacazes',
    '24': 'Volta Redonda', '27': 'Vitória', '28': 'Cachoeiro de Itapemirim',
    '31': 'Belo Horizonte', '32': 'Juiz de Fora', '33': 'Governador Valadares',
    '34': 'Uberlândia', '35': 'Poços de Caldas', '37': 'Divinópolis',
    '38': 'Montes Claros', '41': 'Curitiba', '42': 'Ponta Grossa',
    '43': 'Londrina', '44': 'Maringá', '45': 'Cascavel', '46': 'Pato Branco',
    '47': 'Joinville', '48': 'Florianópolis', '49': 'Chapecó',
    '51': 'Porto Alegre', '53': 'Pelotas', '54': 'Caxias do Sul', '55': 'Santa Maria',
    '61': 'Brasília', '62': 'Goiânia', '63': 'Palmas', '64': 'Rio Verde',
    '65': 'Cuiabá', '66': 'Rondonópolis', '67': 'Campo Grande', '68': 'Rio Branco',
    '69': 'Porto Velho', '71': 'Salvador', '73': 'Ilhéus', '74': 'Juazeiro',
    '75': 'Feira de Santana', '77': 'Vitória da Conquista', '79': 'Aracaju',
    '81': 'Recife', '82': 'Maceió', '83': 'João Pessoa', '84': 'Natal',
    '85': 'Fortaleza', '86': 'Teresina', '87': 'Petrolina', '88': 'Juazeiro do Norte',
    '89': 'Picos', '91': 'Belém', '92': 'Manaus', '93': 'Santarém',
    '94': 'Marabá', '95': 'Boa Vista', '96': 'Macapá', '97': 'Coari',
    '98': 'São Luís', '99': 'Imperatriz',
}


def _investigate_phone(target: str) -> dict:
    result: dict = {
        "target": target, "type": "phone", "valid": False,
        "country": "—", "region": "—", "carrier": "—",
        "timezone": [], "format": {"international": target, "national": target},
        "findings": [],
    }

    # Try phonenumbers library first
    try:
        import phonenumbers
        from phonenumbers import geocoder, carrier as carr, timezone as tz_mod

        parsed = phonenumbers.parse(target, None)
        result["valid"] = phonenumbers.is_valid_number(parsed)
        result["country"] = geocoder.country_name_for_number(parsed, "pt") or "—"
        result["region"] = geocoder.description_for_number(parsed, "pt") or "—"
        result["carrier"] = carr.name_for_number(parsed, "pt") or "—"
        result["timezone"] = list(tz_mod.time_zones_for_number(parsed))
        result["format"]["international"] = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
        )
        result["format"]["national"] = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.NATIONAL
        )
        result["format"]["e164"] = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        )
        num_type = phonenumbers.number_type(parsed)
        type_names = {
            0: "Fixo", 1: "Móvel", 2: "Fixo ou Móvel", 3: "Pago",
            4: "Premium", 5: "Compartilhado", 6: "VoIP", 7: "Pessoal",
            8: "Emergência", 9: "Voicemail", 10: "Short code", 27: "UAN",
        }
        result["number_type"] = type_names.get(num_type, f"Tipo {num_type}")

    except ImportError:
        # Fallback: regex-based Brazilian number analysis
        clean = re.sub(r'[\s\-().+]', '', target)

        if clean.startswith('55') and len(clean) in (12, 13):
            result["valid"] = True
            result["country"] = "Brasil"
            ddd = clean[2:4]
            rest = clean[4:]
            result["region"] = _BR_DDD.get(ddd, f"DDD {ddd}")
            is_mobile = len(rest) == 9 and rest[0] in '6789'
            result["carrier"] = "Operadora desconhecida"
            result["number_type"] = "Móvel" if is_mobile else "Fixo"
            result["timezone"] = ["America/Sao_Paulo"]
            formatted = f"+55 {ddd} {rest[:5]}-{rest[5:]}" if is_mobile else f"+55 {ddd} {rest[:4]}-{rest[4:]}"
            result["format"]["international"] = formatted
            result["format"]["national"] = f"({ddd}) {rest[:5]}-{rest[5:]}"

        elif re.match(r'^\+?[\d\s\-().]{7,20}$', target):
            result["valid"] = True
            result["country"] = "Internacional"
            result["region"] = "Região desconhecida"

    except Exception:
        pass

    # Findings list
    result["findings"] = [
        f"Número {'VÁLIDO' if result['valid'] else 'INVÁLIDO ou suspeito'}",
        f"País: {result['country']}",
        f"Região / DDD: {result['region']}" if result['region'] != '—' else None,
        f"Operadora: {result['carrier']}" if result['carrier'] not in ('—', 'Operadora desconhecida') else None,
        f"Tipo: {result.get('number_type', '—')}",
        f"Fuso horário: {result['timezone'][0]}" if result['timezone'] else None,
        f"Internacional: {result['format']['international']}",
        f"Nacional: {result['format']['national']}",
    ]
    result["findings"] = [f for f in result["findings"] if f]

    # Public OSINT links (do NOT create direct lookup links — user opens manually)
    clean_e164 = re.sub(r'[^\d+]', '', target)
    result["links"] = {
        "truecaller": f"https://www.truecaller.com/search/br/{clean_e164.lstrip('+')}",
        "numverify": "https://numverify.com",
        "phoneinfoga": "https://github.com/sundowndev/phoneinfoga",
    }

    voice = (
        f"Investigação do número concluída, Senhor. "
        f"{'Número válido' if result['valid'] else 'Número suspeito ou inválido'} — "
        f"{result['country']}, {result['region']}. "
        f"{'Operadora: ' + result['carrier'] + '.' if result['carrier'] not in ('—', 'Operadora desconhecida') else ''}"
    )
    return {"voice_response": voice, "display_type": "osint_result", "data": result}


def _investigate_ip(target: str) -> dict:
    result: dict = {
        "target": target, "type": "ip", "valid": False,
        "country": "—", "region": "—", "city": "—",
        "org": "—", "timezone": "—", "hostname": "—",
        "findings": [],
    }

    # Validate
    try:
        socket.inet_aton(target)
        result["valid"] = True
    except socket.error:
        pass

    if not result["valid"]:
        return {"voice_response": f"IP inválido: {target}", "display_type": "osint_result", "data": result}

    # Reverse DNS
    try:
        result["hostname"] = socket.gethostbyaddr(target)[0]
    except Exception:
        pass

    # ipinfo.io — free public API, no key needed
    try:
        import urllib.request
        import json as _json
        req = urllib.request.Request(
            f"https://ipinfo.io/{target}/json",
            headers={"Accept": "application/json", "User-Agent": "JARVIS-OSINT/7.0"},
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            info = _json.loads(resp.read())
        result["country"] = info.get("country", "—")
        result["region"] = info.get("region", "—")
        result["city"] = info.get("city", "—")
        result["org"] = info.get("org", "—")
        result["timezone"] = info.get("timezone", "—")
        if "loc" in info:
            lat, lon = info["loc"].split(",")
            result["lat"] = float(lat)
            result["lon"] = float(lon)
        result["postal"] = info.get("postal", "—")
    except Exception:
        pass

    result["findings"] = [
        f"IP: {target}",
        f"País: {result['country']}",
        f"Região: {result['region']}, {result['city']}",
        f"Organização / ASN: {result['org']}",
        f"Fuso: {result['timezone']}",
        f"Hostname: {result['hostname']}" if result['hostname'] != '—' else None,
        f"CEP: {result.get('postal', '—')}" if result.get('postal', '—') != '—' else None,
    ]
    result["findings"] = [f for f in result["findings"] if f]
    result["links"] = {
        "shodan": f"https://www.shodan.io/host/{target}",
        "ipinfo": f"https://ipinfo.io/{target}",
        "abuseipdb": f"https://www.abuseipdb.com/check/{target}",
    }

    voice = (
        f"IP {target} investigado, Senhor. "
        f"{result['country']}, {result['city']}. "
        f"Organização: {result['org']}."
    )
    return {"voice_response": voice, "display_type": "osint_result", "data": result}


def _investigate_email(target: str) -> dict:
    domain = target.split("@")[-1] if "@" in target else "—"
    username = target.split("@")[0] if "@" in target else target
    valid = bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', target))

    result: dict = {
        "target": target, "type": "email", "valid": valid,
        "domain": domain, "username": username,
        "mx_records": [], "deliverable": None,
        "findings": [],
    }

    if valid:
        try:
            import dns.resolver
            mx = dns.resolver.resolve(domain, "MX")
            result["mx_records"] = sorted(
                [str(r.exchange).rstrip('.') for r in mx],
                key=lambda x: x
            )[:3]
            result["deliverable"] = bool(result["mx_records"])
        except Exception:
            result["deliverable"] = None

    result["findings"] = [
        f"Email: {target}",
        f"Formato: {'VÁLIDO' if valid else 'INVÁLIDO'}",
        f"Domínio: {domain}",
        f"Username: {username}",
        f"MX records: {', '.join(result['mx_records'][:2])}" if result["mx_records"] else "MX: não verificado",
        f"Entregável: {'SIM' if result.get('deliverable') else 'INCERTO'}",
    ]
    result["links"] = {
        "haveibeenpwned": f"https://haveibeenpwned.com/account/{target}",
        "hunter_io": f"https://hunter.io/email-verifier/{target}",
    }

    voice = (
        f"Email {target} analisado, Senhor. "
        f"Domínio: {domain}. "
        f"{'MX records encontrados — entregável.' if result.get('mx_records') else 'Domínio não verificado.'}"
    )
    return {"voice_response": voice, "display_type": "osint_result", "data": result}


def _investigate_domain(target: str) -> dict:
    result: dict = {
        "target": target, "type": "domain",
        "ip": "—", "hosting": "—", "registrar": "—",
        "created": "—", "expires": "—",
        "findings": [],
    }

    # Resolve IP
    try:
        result["ip"] = socket.gethostbyname(target)
    except Exception:
        pass

    # WHOIS
    try:
        import whois
        w = whois.whois(target)
        result["registrar"] = str(w.registrar or "—")
        result["created"] = str(w.creation_date[0] if isinstance(w.creation_date, list) else w.creation_date or "—")[:10]
        result["expires"] = str(w.expiration_date[0] if isinstance(w.expiration_date, list) else w.expiration_date or "—")[:10]
        result["org"] = str(w.org or "—")
        result["country"] = str(w.country or "—")
    except Exception:
        pass

    result["findings"] = [
        f"Domínio: {target}",
        f"IP: {result['ip']}",
        f"Registrar: {result['registrar']}",
        f"Criado: {result['created']}",
        f"Expira: {result['expires']}",
    ]
    result["links"] = {
        "whois": f"https://whois.domaintools.com/{target}",
        "shodan": f"https://www.shodan.io/search?query={target}",
        "builtwith": f"https://builtwith.com/{target}",
        "wayback": f"https://web.archive.org/web/*/{target}",
    }

    voice = f"Domínio {target} investigado. IP: {result['ip']}. Registrar: {result['registrar']}."
    return {"voice_response": voice, "display_type": "osint_result", "data": result}


def _extract_target_from_query(query: str) -> str:
    """Extract phone/IP/email/domain from natural language."""
    # Phone: +55... or (XX) numbers
    m = re.search(r'\+?\d[\d\s\-().]{8,18}\d', query)
    if m:
        return m.group().strip()
    # IP
    m = re.search(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', query)
    if m:
        return m.group()
    # Email
    m = re.search(r'[^\s<>"]+@[^\s<>"]+\.[^\s<>"]+', query)
    if m:
        return m.group()
    # Domain
    m = re.search(r'[a-zA-Z0-9][a-zA-Z0-9\-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}', query)
    if m:
        return m.group()
    return ""


@router.post("")
async def investigate(req: InvestigateRequest):
    target = req.target.strip()

    # If no explicit target, try to extract from query
    if not target and req.query:
        target = _extract_target_from_query(req.query)

    if not target:
        # Generic LLM OSINT analysis
        from ai.client import get_ai_client
        from core.jarvis_persona import _build_main_prompt
        msgs = [
            {"role": "system", "content": _build_main_prompt()},
            {"role": "user", "content": f"[MODO OSINT] {req.query}"},
        ]
        text = get_ai_client().call(msgs)
        return {"voice_response": text, "display_type": "text_result", "data": {"analysis": text}}

    inv_type = req.type if req.type != "auto" else _detect_type(target)

    if inv_type == "phone":
        return _investigate_phone(target)
    elif inv_type == "ip":
        return _investigate_ip(target)
    elif inv_type == "email":
        return _investigate_email(target)
    elif inv_type == "domain":
        return _investigate_domain(target)
    else:
        # LLM-assisted investigation
        from ai.client import get_ai_client
        from core.jarvis_persona import _build_main_prompt
        msgs = [
            {"role": "system", "content": _build_main_prompt()},
            {"role": "user", "content": f"[MODO OSINT] Investiga o alvo '{target}'. Consulta: {req.query}"},
        ]
        text = get_ai_client().call(msgs)
        return {
            "voice_response": text,
            "display_type": "text_result",
            "data": {"target": target, "analysis": text},
        }
