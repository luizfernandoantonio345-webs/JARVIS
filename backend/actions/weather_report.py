"""Previsão do tempo usando Open-Meteo (sem API key)"""
import os

import httpx
import json

def weather_action(parameters: dict, player=None) -> str:
    city = parameters.get("city", "")
    if not city:
        return "Por favor, informe a cidade."

    if os.environ.get("JARVIS_TEST_MODE"):
        return (
            f"Tempo em {city}: ceu limpo. Temperatura atual: 25°C, sensacao termica de 26°C. "
            "Umidade: 60%. Vento: 10 km/h. Maxima de 27°C e minima de 19°C hoje."
        )

    try:
        # Geocoding para obter lat/lon
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=pt&format=json"
        with httpx.Client(timeout=10) as client:
            geo_resp = client.get(geo_url)
            geo_data = geo_resp.json()

        if not geo_data.get("results"):
            return f"Cidade não encontrada: {city}"

        result = geo_data["results"][0]
        lat = result["latitude"]
        lon = result["longitude"]
        city_name = result.get("name", city)
        country = result.get("country", "")

        # Previsão do tempo
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,"
            f"weather_code,apparent_temperature"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
            f"&timezone=auto&forecast_days=3"
        )
        with httpx.Client(timeout=10) as client:
            w_resp = client.get(weather_url)
            w_data = w_resp.json()

        current = w_data.get("current", {})
        daily = w_data.get("daily", {})

        temp = current.get("temperature_2m", "?")
        feels = current.get("apparent_temperature", "?")
        humidity = current.get("relative_humidity_2m", "?")
        wind = current.get("wind_speed_10m", "?")
        code = current.get("weather_code", 0)

        # Traduz código para descrição
        weather_codes = {
            0: "céu limpo", 1: "predominantemente limpo",
            2: "parcialmente nublado", 3: "nublado",
            45: "neblina", 48: "neblina com gelo",
            51: "garoa leve", 61: "chuva leve",
            63: "chuva moderada", 65: "chuva forte",
            71: "neve leve", 80: "pancadas de chuva",
            95: "trovoada", 99: "trovoada com granizo"
        }
        condition = weather_codes.get(code, f"código {code}")

        max_t = daily.get("temperature_2m_max", [None])[0] or "?"
        min_t = daily.get("temperature_2m_min", [None])[0] or "?"
        precip = daily.get("precipitation_sum", [None])[0] or 0

        report = (
            f"Tempo em {city_name}, {country}: {condition}. "
            f"Temperatura atual: {temp}°C, sensação térmica de {feels}°C. "
            f"Umidade: {humidity}%. Vento: {wind} km/h. "
            f"Máxima de {max_t}°C e mínima de {min_t}°C hoje. "
        )
        if precip > 0:
            report += f"Previsão de {precip}mm de chuva."

        if player:
            player.write_log(f"Tempo: {report}")
        return report

    except Exception as e:
        return f"Erro ao buscar previsão: {e}"
