#!/usr/bin/env python3
import os
import sys
import json
import argparse
import subprocess
import time
import re
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


# =========================
# Configuración
# =========================

config_path = Path(__file__).parent / "config.json"
if not config_path.exists():
    print(f"[bold red]Error:[/bold red] No se encontró el archivo de configuración: {config_path}")
    sys.exit(1)

with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)

MEMORY_FILE = Path(
    os.environ.get(
        "ASSISTANT_MEMORY_FILE",
        Path.home() / ".terminal_assistant_memory.json",
    )
)

# Límite de conversaciones guardadas.
MAX_MEMORY_TURNS = 8

# Máximo de ciclos de llamadas a herramientas por petición.
# 8 es el máximo solicitado.
MAX_TOOL_ITERATIONS = 8

# Límite de caracteres de un resultado de herramienta que se muestra
# y se envía al modelo. Evita respuestas gigantescas.
MAX_TOOL_RESULT_CHARS = 12000

# Reintentos para errores temporales de la API.
MAX_API_RETRIES = 2

# Seguridad adicional: si el contexto crece demasiado, evitamos seguir
# acumulando resultados de herramientas.
MAX_CONTENT_ITEMS = 40


# =========================
# Utilidades de texto
# =========================

def texto_seguro(texto) -> str:
    """
    Convierte cualquier resultado a texto UTF-8 imprimible.

    Algunos nombres de archivos en Linux pueden contener bytes que Python
    representa mediante surrogate characters (por ejemplo \\udca6).
    Esos caracteres pueden provocar UnicodeEncodeError al escribirlos
    mediante Rich.
    """
    if texto is None:
        return ""

    if isinstance(texto, bytes):
        return texto.decode("utf-8", errors="backslashreplace")

    texto = str(texto)

    # Reemplaza/escapa surrogates para que Rich pueda escribir el resultado.
    try:
        texto.encode("utf-8")
        return texto
    except UnicodeEncodeError:
        return texto.encode("utf-8", errors="backslashreplace").decode("utf-8")


def limitar_texto(texto: str, limite: int = MAX_TOOL_RESULT_CHARS) -> str:
    """Limita resultados enormes para no inflar el contexto del modelo."""
    texto = texto_seguro(texto)

    if len(texto) <= limite:
        return texto

    return (
        texto[:limite]
        + "\n\n[Resultado truncado por TerminalIA: "
          f"{len(texto) - limite} caracteres omitidos.]"
    )


def imprimir_seguro(*objetos, **kwargs):
    """
    Intenta usar Rich y, si la salida contiene algo incompatible, utiliza
    stdout directamente con una representación segura.
    """
    objetos_seguros = [texto_seguro(obj) for obj in objetos]

    try:
        print(*objetos_seguros, **kwargs)
    except UnicodeEncodeError:
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        salida = sep.join(objetos_seguros) + end

        sys.stdout.write(
            salida.encode("utf-8", errors="backslashreplace").decode("utf-8")
        )
        sys.stdout.flush()


# =========================
# Contexto del sistema
# =========================

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
            cmd,
            shell=True,
            text=True,
            executable="/bin/bash",
            timeout=5,
            errors="replace",
        ).strip()
    except Exception as e:
        return f"Info del sistema no disponible ({texto_seguro(e)})"


# =========================
# Persistencia de memoria
# =========================

def cargar_memoria() -> list[dict]:
    if not MEMORY_FILE.exists():
        return []

    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))

        if isinstance(data, list):
            return data

        return []

    except (json.JSONDecodeError, OSError, UnicodeError):
        return []


def guardar_memoria(turnos: list[dict]) -> None:
    recortado = turnos[-MAX_MEMORY_TURNS * 2:]

    try:
        MEMORY_FILE.write_text(
            json.dumps(
                recortado,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    except (OSError, UnicodeError) as e:
        imprimir_seguro(
            f"[red]No se pudo guardar la memoria:[/red] {texto_seguro(e)}"
        )


def memoria_a_contents(turnos: list[dict]) -> list[types.Content]:
    contents = []

    for turno in turnos:
        rol = turno.get("role")
        texto = turno.get("content", "")

        if not texto or rol not in ("user", "model"):
            continue

        contents.append(
            types.Content(
                role=rol,
                parts=[
                    types.Part.from_text(
                        text=texto_seguro(texto)
                    )
                ],
            )
        )

    return contents


def limpiar_memoria():
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()

    imprimir_seguro("[green]Memoria borrada.[/green]")


# =========================
# Manejo de API / rate limit
# =========================

def obtener_retry_delay(error) -> float | None:
    """
    Intenta extraer el tiempo recomendado por Google desde un error 429.

    Ejemplos soportados:
      retry in 44.220506468s
      retryDelay: 44s
    """
    texto = texto_seguro(error)

    patrones = [
        r"retry in\s+([0-9]+(?:\.[0-9]+)?)s",
        r"retryDelay['\"]?\s*:\s*['\"]?([0-9]+(?:\.[0-9]+)?)s?",
    ]

    for patron in patrones:
        match = re.search(patron, texto, re.IGNORECASE)

        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

    return None


def es_error_rate_limit(error) -> bool:
    texto = texto_seguro(error).lower()

    return (
        "429" in texto
        or "resource_exhausted" in texto
        or "quota exceeded" in texto
        or "ratelimit" in texto
    )


def generar_con_reintento(client, model, contents, config_generacion):
    """
    Ejecuta generate_content respetando el retryDelay de Google cuando
    se produce un 429.
    """
    ultimo_error = None

    for intento in range(MAX_API_RETRIES + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config_generacion,
            )

        except Exception as e:
            ultimo_error = e

            if not es_error_rate_limit(e):
                raise

            if intento >= MAX_API_RETRIES:
                raise

            delay = obtener_retry_delay(e)

            if delay is None:
                delay = 30.0

            delay = min(max(delay, 1.0), 120.0)

            imprimir_seguro(
                f"[yellow]Límite de API alcanzado.[/yellow] "
                f"Reintentando en {delay:.1f}s "
                f"(intento {intento + 1}/{MAX_API_RETRIES})..."
            )

            time.sleep(delay)

    raise ultimo_error


def generar_stream_con_reintento(
    client,
    model,
    contents,
    config_generacion,
):
    """
    Streaming con manejo de 429.

    Importante: si el stream ya comenzó a entregar texto y falla a mitad,
    no se reinicia automáticamente para evitar duplicar la respuesta.
    """
    ultimo_error = None

    for intento in range(MAX_API_RETRIES + 1):
        try:
            return client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config_generacion,
            )

        except Exception as e:
            ultimo_error = e

            if not es_error_rate_limit(e):
                raise

            if intento >= MAX_API_RETRIES:
                raise

            delay = obtener_retry_delay(e)

            if delay is None:
                delay = 30.0

            delay = min(max(delay, 1.0), 120.0)

            imprimir_seguro(
                f"[yellow]Límite de API alcanzado durante streaming.[/yellow] "
                f"Reintentando en {delay:.1f}s "
                f"(intento {intento + 1}/{MAX_API_RETRIES})..."
            )

            time.sleep(delay)

    raise ultimo_error


# =========================
# Herramientas y function calls
# =========================

def ejecutar_function_calls(candidate) -> list[types.Part]:
    partes_respuesta = []

    for part in candidate.content.parts:
        function_call = getattr(part, "function_call", None)

        if not function_call:
            continue

        nombre = function_call.name
        args = dict(function_call.args or {})

        imprimir_seguro(
            f"[yellow]Ejecutando:[/yellow] "
            f"{nombre} {args}"
        )

        try:
            funcion = FUNCTIONS[nombre]
            resultado = funcion(**args)

        except KeyError:
            resultado = (
                f"Error: herramienta '{nombre}' no está registrada."
            )

        except Exception as e:
            resultado = (
                f"Error ejecutando '{nombre}': "
                f"{texto_seguro(e)}"
            )

        # Sanitizar antes de imprimir y antes de enviarlo al modelo.
        resultado = limitar_texto(resultado)

        imprimir_seguro(
            f"[green]Resultado:[/green]\n{resultado}"
        )

        partes_respuesta.append(
            types.Part.from_function_response(
                name=nombre,
                response={
                    "result": resultado
                },
            )
        )

    return partes_respuesta


# =========================
# Control de contexto
# =========================

def limitar_contents(contents: list[types.Content]) -> list[types.Content]:
    """
    Evita que una sesión de herramientas acumule indefinidamente elementos.

    Conserva siempre el comienzo de la conversación y los elementos más
    recientes, que son los más relevantes para continuar la tarea.
    """
    if len(contents) <= MAX_CONTENT_ITEMS:
        return contents

    # Mantener el primer mensaje del sistema conversacional/usuario y
    # conservar los mensajes recientes.
    recientes = contents[-(MAX_CONTENT_ITEMS - 2):]

    return contents[:2] + recientes


def estimar_caracteres_contexto(contents: list[types.Content]) -> int:
    """
    Estimación sencilla del tamaño del contexto.
    No pretende sustituir el contador oficial de tokens.
    """
    total = 0

    for content in contents:
        for part in getattr(content, "parts", []) or []:
            texto = getattr(part, "text", None)

            if texto:
                total += len(texto)

    return total


# =========================
# Argumentos
# =========================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Asistente de terminal con memoria persistente."
    )

    parser.add_argument(
        "prompt",
        nargs="*",
        help="Consulta para el asistente",
    )

    parser.add_argument(
        "--clear_memory",
        action="store_true",
        help="Borra la memoria guardada y sale",
    )

    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="Ignora la memoria en esta ejecución",
    )

    return parser.parse_args()


# =========================
# Main
# =========================

def generate():
    args = parse_args()

    if args.clear_memory:
        limpiar_memoria()
        return

    if not args.prompt:
        imprimir_seguro(
            "[bold red]Error:[/bold red] "
            "Debes ingresar un texto al ejecutar el script."
        )

        imprimir_seguro(
            "Ejemplo: python terminal_assistant.py "
            "dame un comando para ver archivos"
        )

        return

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        imprimir_seguro(
            "[bold red]Error:[/bold red] "
            "No está definida la variable de entorno GEMINI_API_KEY."
        )
        return

    prompt_usuario = " ".join(args.prompt)
    contexto = obtener_contexto_sistema()

    memoria = [] if args.no_memory else cargar_memoria()

    contents = memoria_a_contents(memoria)

    contents.append(
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=texto_seguro(prompt_usuario)
                )
            ],
        )
    )

    client = genai.Client(api_key=api_key)

    system_instruction = (
        f"{config['system_instruction']}\n\n"
        f"Contexto del sistema: {contexto}"
    )

    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_level="MINIMAL"
        ),
        tools=TOOLS,
        system_instruction=system_instruction,
    )

    # =========================
    # Iteraciones de herramientas
    # =========================

    try:
        for iteracion in range(MAX_TOOL_ITERATIONS):
            tamano_estimado = estimar_caracteres_contexto(contents)

            # Solo informativo; no modifica el comportamiento.
            imprimir_seguro(
                f"[dim]Contexto aproximado: "
                f"{tamano_estimado:,} caracteres | "
                f"iteración {iteracion + 1}/{MAX_TOOL_ITERATIONS}[/dim]"
            )

            response = generar_con_reintento(
                client,
                config["model"],
                limitar_contents(contents),
                generate_content_config,
            )

            if not response.candidates:
                raise RuntimeError(
                    "La API no devolvió ningún candidato."
                )

            candidate = response.candidates[0]

            tiene_tool_calls = any(
                getattr(p, "function_call", None)
                for p in candidate.content.parts
            )

            if not tiene_tool_calls:
                break

            resultados = ejecutar_function_calls(candidate)

            # Guardar la respuesta del modelo y los resultados de tools.
            contents.append(candidate.content)
            contents.append(
                types.Content(
                    role="user",
                    parts=resultados,
                )
            )

            contents = limitar_contents(contents)

        else:
            imprimir_seguro(
                "[red]Se alcanzó el máximo de "
                f"{MAX_TOOL_ITERATIONS} iteraciones de herramientas.[/red]"
            )

    except Exception as e:
        if es_error_rate_limit(e):
            delay = obtener_retry_delay(e)

            if delay:
                imprimir_seguro(
                    "[bold red]Cuota de API agotada.[/bold red] "
                    f"Google recomienda esperar aproximadamente "
                    f"{delay:.0f}s."
                )
            else:
                imprimir_seguro(
                    "[bold red]Cuota de API agotada.[/bold red] "
                    "Espera y vuelve a intentarlo."
                )
        else:
            imprimir_seguro(
                "[bold red]Error consultando el modelo:[/bold red] "
                f"{texto_seguro(e)}"
            )

        return

    # =========================
    # Streaming de respuesta final
    # =========================

    texto_acumulado = ""

    try:
        with Live(
            Panel(
                "",
                title="Respuesta",
            ),
            refresh_per_second=15,
            auto_refresh=True,
        ) as live:

            response_stream = generar_stream_con_reintento(
                client,
                config["model"],
                limitar_contents(contents),
                generate_content_config,
            )

            for chunk in response_stream:
                if chunk.text:
                    texto_acumulado += texto_seguro(chunk.text)

                    live.update(
                        Panel(
                            Markdown(
                                texto_acumulado,
                                style="#9fa5d9",
                            ),
                            title="[#858ab6]Response[/#858ab6]",
                            border_style="#858ab6",
                            style="on #0f0f14",
                        )
                    )

    except Exception as e:
        if es_error_rate_limit(e):
            delay = obtener_retry_delay(e)

            if delay:
                imprimir_seguro(
                    "[bold red]Error de cuota durante streaming.[/bold red] "
                    f"Espera aproximadamente {delay:.0f}s."
                )
            else:
                imprimir_seguro(
                    "[bold red]Error de cuota durante streaming.[/bold red]"
                )
        else:
            imprimir_seguro(
                "[bold red]Error en streaming:[/bold red] "
                f"{texto_seguro(e)}"
            )

        return

    # =========================
    # Guardar memoria
    # =========================

    if not args.no_memory and texto_acumulado.strip():
        memoria.append(
            {
                "role": "user",
                "content": texto_seguro(prompt_usuario),
                "ts": datetime.now().isoformat(),
            }
        )

        memoria.append(
            {
                "role": "model",
                "content": texto_seguro(texto_acumulado),
                "ts": datetime.now().isoformat(),
            }
        )

        guardar_memoria(memoria)


if __name__ == "__main__":
    generate()
