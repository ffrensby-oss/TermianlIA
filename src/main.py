#!/usr/bin/env python3
import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

from google import genai
from google.genai import types
from rich import print
from rich.panel import Panel
from rich.live import Live
from rich.markdown import Markdown

from tools_registry import TOOLS
from tools_registry import FUNCTIONS

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
MEMORY_FILE = Path(os.environ.get("ASSISTANT_MEMORY_FILE", Path.home() / ".terminal_assistant_memory.json"))
MAX_MEMORY_TURNS = 12          # nº de intercambios (usuario+modelo) que se conservan
MAX_TOOL_ITERATIONS = 6        # evita loops infinitos de function-calling
MODEL = os.environ.get("GEMINI_MODEL", "gemma-4-31b-it")  # ajusta según los modelos disponibles en tu API key


# ---------------------------------------------------------------------------
# Contexto del sistema
# ---------------------------------------------------------------------------
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
        return subprocess.check_output(
            cmd, shell=True, text=True, executable="/bin/bash", timeout=5
        ).strip()
    except Exception as e:
        return f"Info del sistema no disponible ({e})"


# ---------------------------------------------------------------------------
# Memoria persistente (JSON externo, ya que el script no mantiene bucle)
# ---------------------------------------------------------------------------
def cargar_memoria() -> list[dict]:
    if not MEMORY_FILE.exists():
        return []
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []


def guardar_memoria(turnos: list[dict]) -> None:
    # Nos quedamos solo con los últimos N intercambios para no inflar el contexto
    recortado = turnos[-MAX_MEMORY_TURNS * 2:]
    try:
        MEMORY_FILE.write_text(
            json.dumps(recortado, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        print(f"[red]No se pudo guardar la memoria:[/red] {e}")


def memoria_a_contents(turnos: list[dict]) -> list[types.Content]:
    contents = []
    for turno in turnos:
        rol = turno.get("role")
        texto = turno.get("content", "")
        if not texto or rol not in ("user", "model"):
            continue
        contents.append(
            types.Content(role=rol, parts=[types.Part.from_text(text=texto)])
        )
    return contents


def limpiar_memoria():
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()
    print("[green]Memoria borrada.[/green]")


# ---------------------------------------------------------------------------
# Ejecución de herramientas (con soporte a múltiples rondas)
# ---------------------------------------------------------------------------
def ejecutar_function_calls(candidate) -> list[types.Part]:
    partes_respuesta = []
    for part in candidate.content.parts:
        if not getattr(part, "function_call", None):
            continue

        nombre = part.function_call.name
        args = dict(part.function_call.args or {})

        print(f"[yellow]Ejecutando:[/yellow] {nombre} {args}")

        try:
            funcion = FUNCTIONS[nombre]
            resultado = funcion(**args)
        except KeyError:
            resultado = f"Error: herramienta '{nombre}' no está registrada."
        except Exception as e:
            resultado = f"Error ejecutando '{nombre}': {e}"

        print(f"[green]Resultado:[/green]\n{resultado}")

        partes_respuesta.append(
            types.Part.from_function_response(name=nombre, response={"result": resultado})
        )
    return partes_respuesta


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Asistente de terminal con memoria persistente."
    )
    parser.add_argument("prompt", nargs="*", help="Consulta para el asistente")
    parser.add_argument("--clear-memory", action="store_true", help="Borra la memoria guardada y sale")
    parser.add_argument("--no-memory", action="store_true", help="Ignora la memoria en esta ejecución")
    return parser.parse_args()


def generate():
    args = parse_args()

    if args.clear_memory:
        limpiar_memoria()
        return

    if not args.prompt:
        print("[bold red]Error:[/bold red] Debes ingresar un texto al ejecutar el script.")
        print("Ejemplo: python terminal_assistant.py dame un comando para ver archivos")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[bold red]Error:[/bold red] No está definida la variable de entorno GEMINI_API_KEY.")
        return

    prompt_usuario = " ".join(args.prompt)
    contexto = obtener_contexto_sistema()

    memoria = [] if args.no_memory else cargar_memoria()
    contents = memoria_a_contents(memoria)
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=prompt_usuario)])
    )

    client = genai.Client(api_key=api_key)

    system_instruction = f"""
[OBJETIVO Y ENTORNO]
Eres un asistente de terminal avanzado para un sistema Linux.
Entorno detectado: {contexto}

[USO DE HERRAMIENTAS]
Cuando una tarea requiera modificar archivos:
1. Primero usa la herramienta necesaria para obtener información.
2. Después usa write_file para guardar el resultado.
3. No declares una tarea terminada hasta que la operación de escritura haya sido ejecutada.

Ejemplo:
Usuario: guarda información del sistema en ~/archivo
Correcto:
system_info()
write_file("~/archivo", resultado)
Incorrecto:
system_info()
decir "hecho"

[PERSONALIDAD Y TONO]
- TONO PRINCIPAL: Confianza absoluta, seguridad, ironía y sarcasmo. Pero respeto ante todo.
- HUMOR: Humor negro y ácido. CERO chistes malos, bromas bobas o clichés.
- ACTITUD: Directo, mordaz y sin rodeos. Nada de formalidades, disculpas ni discursos vacíos.

[REGLAS DE COMANDOS Y REGIMEN DE BREVEDAD]
- COMPATIBILIDAD LINUX ESTRICTA: Todos los comandos, binarios y sintaxis deben ser 100% compatibles con la distribución, versión de kernel y arquitectura indicadas arriba (usa el gestor de paquetes correspondiente: apt, pacman, dnf, etc.).
- BREVEDAD POR DEFECTO: Respuesta ultra corta y al grano. Comando exacto + nota breve. Si la respuesta es código o comandos, puedes extenderte sin límite. No hables de temas ajenos a Linux salvo que se pida explícitamente.

[CONTROL DE EXPANSIÓN]
- Si la orden incluye '/etc': reactiva la brevedad estricta. Solo en ese modo puedes extenderte con explicaciones detalladas.
"""

    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
        tools=TOOLS,
        system_instruction=system_instruction,
    )

    # -----------------------------------------------------------------
    # Bucle de function-calling: repetimos hasta que ya no pida más tools
    # -----------------------------------------------------------------
    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            response = client.models.generate_content(
                model=MODEL, contents=contents, config=generate_content_config
            )
            candidate = response.candidates[0]

            tiene_tool_calls = any(
                getattr(p, "function_call", None) for p in candidate.content.parts
            )
            if not tiene_tool_calls:
                break

            resultados = ejecutar_function_calls(candidate)
            contents.append(candidate.content)
            contents.append(types.Content(role="user", parts=resultados))
        else:
            print("[red]Se alcanzó el máximo de iteraciones de herramientas.[/red]")
    except Exception as e:
        print(f"[bold red]Error consultando el modelo:[/bold red] {e}")
        return

    # -----------------------------------------------------------------
    # Respuesta final en streaming
    # -----------------------------------------------------------------
    texto_acumulado = ""
    try:
        with Live(Panel("", title="Respuesta"), refresh_per_second=15, auto_refresh=True) as live:
            response_stream = client.models.generate_content_stream(
                model=MODEL, contents=contents, config=generate_content_config
            )
            for chunk in response_stream:
                if chunk.text:
                    texto_acumulado += chunk.text
                    live.update(
                        Panel(
                            Markdown(texto_acumulado, style="#9fa5d9"),
                            title="[#858ab6]Response[/#858ab6]",
                            border_style="#858ab6",
                            style="on #0f0f14",
                        )
                    )
    except Exception as e:
        print(f"[bold red]Error en streaming:[/bold red] {e}")
        return

    # -----------------------------------------------------------------
    # Guardar memoria (usuario + respuesta final)
    # -----------------------------------------------------------------
    if not args.no_memory and texto_acumulado.strip():
        memoria.append({"role": "user", "content": prompt_usuario, "ts": datetime.now().isoformat()})
        memoria.append({"role": "model", "content": texto_acumulado, "ts": datetime.now().isoformat()})
        guardar_memoria(memoria)


if __name__ == "__main__":
    generate()
