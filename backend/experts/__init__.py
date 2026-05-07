from .software_engineer import SoftwareEngineerExpert
from .cybersecurity import CybersecurityExpert
from .quality_engineer import QualityEngineerExpert

CORE_EXPERTS = {
    SoftwareEngineerExpert.DOMAIN: SoftwareEngineerExpert(),
    CybersecurityExpert.DOMAIN: CybersecurityExpert(),
    QualityEngineerExpert.DOMAIN: QualityEngineerExpert(),
}

CORE_EXPERT_ALIASES = {}
for _domain, _expert in CORE_EXPERTS.items():
    for _alias in _expert.ALIASES:
        CORE_EXPERT_ALIASES[_alias] = _domain

