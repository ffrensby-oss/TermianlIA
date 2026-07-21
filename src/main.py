import os
import sys
import subprocess
from google import genai
from google.genai import types
from rich import print
from rich.panel import Panel
from rich.live import Live
from rich.markdown import Markdown

# Obtención del contexto más ligera
def obtener_contexto_sistema() -> str:
    cmd = r"""
    OS=$(grep -oP '(?<=^PRETTY_NAME=)"?\K[^"]+' /etc/os-release 2>/dev/null || uname -sr)
    KERNEL=$(uname -r)
    CPU=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)
    CORES=$(nproc)
    RAM=$(free -m | awk 'NR==2{printf "%.1fGB / %.1fGB (%.0f%%)", $3/1024, $2/1024, $3*100/$2}')
    DISCO=$(df -h / | awk 'NR==2{printf "%s / %s (%s)", $3, $2, $5}')

    echo "Host: $USER@$HOSTNAME | SO: $OS ($KERNEL) | CPU: $CPU ($CORES núcleos) | RAM: $RAM | Disco /: $DISCO"
    """
    try:
        return subprocess.check_output(cmd, shell=True, text=True, executable='/bin/bash').strip()
    except Exception:
        return "Info del sistema no disponible"

def generate():
    if len(sys.argv) < 2:
        print("[bold red]Error:[/bold red] Debes ingresar un texto al ejecutar el script.")
        print("Ejemplo: python script.py dame un comando para ver archivos")
        return

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    prompt_usuario = " ".join(sys.argv[1:])

    model = "gemma-4-26b-a4b-it"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=prompt_usuario),
            ],
        ),
    ]
    tools = [
        types.Tool(googleSearch=types.GoogleSearch()),
    ]
    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_level="MINIMAL",
        ),
        tools=tools,
        system_instruction = f"""
        [OBJETIVO Y ENTORNO]
        El objetivo principal de esta herramienta es servir como un asistente de terminal avanzado para un sistema Linux.
        Información detallada de la máquina detectada:
        {obtener_contexto_sistema()}

        [PERSONALIDAD Y TONO]
        - TONO PRINCIPAL: Confianza absoluta, seguridad, ironía y sarcasmo.
        - HUMOR: Humor negro y ácido. CERO chistes malos, bromas bobas o clichés.
        - ACTITUD: Directo, mordaz y sin rodeos. Nada de formalidades, disculpas ni discursos vacíos.

        [REGLAS DE COMANDOS Y REGIMEN DE BREVEDAD]
        - COMPATIBILIDAD LINUX ESTRICTA: Todos los comandos, binarios y sintaxis DEBEN ser 100% compatibles con la distribución, versión del Kernel y arquitectura especificadas en [OBJETIVO Y ENTORNO] (usa los gestores de paquetes como apt, pacman, dnf, etc., correspondientes).
        - BREVEDAD POR DEFECTO: Mantén la respuesta ultra corta y al grano. Muestra el comando exacto y una breve nota concisa. NO te extiendas bajo ninguna circunstancia a menos que se desbloquee la brevedad o la respuesta sea codigo o coamndos si es codigo o comandos puedes extenderte sin ninguna limitacion. Tampoco te intersa responder nada que no tenga que ver con linux con la brevedad activada y custa un poco que hables de algo que no sea de linux cuando la tienes desactivada. Debes ser conciente de que no puedes mantener una conversacion que que el chat no tiene memoria

        [CONTROL DE EXPANSION]
        - Si la orden incluye '/etc': Reactiva la regla de brevedad estricta. Solo en este modo estás autorizado a extenderte y dar explicaciones detalladas o profundas.
        """
        )

    texto_acumulado = ""
    
    # Live con refresh adecuado para renderizar cada chunk conforme llega
    with Live(Panel("", title="Respuesta"), refresh_per_second=15, auto_refresh=True) as live:
        # Usamos generate_content_stream en lugar de generate_content
        response_stream = client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=generate_content_config,
        )

        for chunk in response_stream:
            if chunk.text:
                texto_acumulado += chunk.text
                panel_actualizado = Panel(
                    Markdown(texto_acumulado, style="#9fa5d9"),
                    title="[#858ab6]Response[/#858ab6]",
                    border_style="#858ab6",
                    style="on #0f0f14",
                )
                live.update(panel_actualizado)

if __name__ == "__main__":
    generate()