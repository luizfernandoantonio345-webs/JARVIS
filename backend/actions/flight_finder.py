"""Busca voos no Google Flights via browser."""
from __future__ import annotations

import os
import urllib.parse
import webbrowser
from datetime import datetime

from backend.utils.env import env_flag


def flight_finder(parameters: dict, player=None) -> str:
    origin = parameters.get("origin", "")
    destination = parameters.get("destination", "")
    date = parameters.get("date", "")
    return_date = parameters.get("return_date", "")
    passengers = parameters.get("passengers", 1)
    cabin = parameters.get("cabin", "economy")

    if not origin or not destination or not date:
        return "Origem, destino e data sao obrigatorios."

    try:
        date_formats = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]
        parsed_date = None
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(date, fmt)
                break
            except ValueError:
                continue

        if not parsed_date:
            return f"Formato de data invalido: {date}"

        cabin_map = {"economy": "1", "premium": "2", "business": "3", "first": "4"}
        _ = cabin_map.get(cabin.lower(), "1")

        base_url = "https://www.google.com/travel/flights"
        params = (
            f"?q=Voos+{urllib.parse.quote(origin)}+para+{urllib.parse.quote(destination)}"
            "&hl=pt-BR"
        )

        if not env_flag("JARVIS_TEST_MODE"):
            webbrowser.open(base_url + params)

        result = (
            f"Buscando voos de {origin} para {destination} em {parsed_date.strftime('%d/%m/%Y')}. "
            f"Passageiros: {passengers}. Classe: {cabin}. "
            f"{'Google Flights aberto no browser.' if not env_flag('JARVIS_TEST_MODE') else 'Consulta simulada em modo de teste.'}"
        )

        if return_date:
            result += f" Volta: {return_date}."

        if player:
            player.write_log(f"FlightFinder: {result}")

        return result

    except Exception as e:
        return f"Erro flight_finder: {e}"
