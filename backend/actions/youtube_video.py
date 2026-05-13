"""Controla YouTube: play, resumo, trending, info"""
import webbrowser
import urllib.parse
import subprocess


def youtube_video(parameters: dict, response=None, player=None) -> str:
    action = parameters.get("action", "play")
    query = parameters.get("query", "")
    url = parameters.get("url", "")
    region = parameters.get("region", "BR")
    save = parameters.get("save", False)

    try:
        if action == "play":
            if not query:
                return "Informe o que deseja tocar."
            encoded = urllib.parse.quote(query)
            search_url = f"https://www.youtube.com/results?search_query={encoded}"
            webbrowser.open(search_url)
            if player:
                player.write_log(f"YouTube: buscando '{query}'")
            return f"Abrindo YouTube com '{query}'. Selecione o vídeo desejado."

        elif action == "play_direct":
            if not query:
                return "Informe o que deseja tocar."
            try:
                result = subprocess.run(
                    ["yt-dlp", f"ytsearch1:{query}", "--get-url", "-f", "best"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.stdout.strip():
                    video_url = result.stdout.strip().split("\n")[0]
                    webbrowser.open(video_url)
                    return f"Tocando: {query}"
            except Exception:
                pass

            encoded = urllib.parse.quote(query)
            webbrowser.open(f"https://www.youtube.com/results?search_query={encoded}")
            return f"Abrindo YouTube: {query}"

        elif action == "summarize":
            if not url and not query:
                return "Informe a URL ou título do vídeo."
            target = url or f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            try:
                subprocess.run(
                    [
                        "yt-dlp",
                        target,
                        "--write-auto-subs",
                        "--skip-download",
                        "--sub-lang",
                        "pt,en",
                        "-o",
                        "temp_subs",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return f"Legendas extraídas de {target}. Resumo disponível nos arquivos gerados."
            except Exception as e:
                return f"Não foi possível extrair legendas: {e}"

        elif action == "trending":
            trend_url = f"https://www.youtube.com/feed/trending?gl={region}"
            webbrowser.open(trend_url)
            return f"Abrindo trending do YouTube para região {region}."

        elif action == "get_info":
            if not url:
                return "Informe a URL do vídeo."
            try:
                result = subprocess.run(
                    ["yt-dlp", url, "--dump-json", "--skip-download"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                if result.stdout:
                    import json
                    data = json.loads(result.stdout)
                    title = data.get("title", "?")
                    channel = data.get("uploader", "?")
                    duration = data.get("duration", 0)
                    views = data.get("view_count", 0)
                    mins = duration // 60
                    secs = duration % 60
                    return (
                        f"Vídeo: {title}. Canal: {channel}. "
                        f"Duração: {mins}m{secs}s. Visualizações: {views:,}"
                    )
            except Exception as e:
                return f"Erro ao obter info: {e}"

        else:
            return f"Ação desconhecida: {action}. Use play, trending, get_info ou summarize."

    except Exception as e:
        return f"Erro youtube_video/{action}: {e}"
