import os
import sys
import subprocess

from google import genai
from google.genai import types

from rich import print
from rich.panel import Panel
from rich.live import Live
from rich.markdown import Markdown

from tools_registry import TOOLS, FUNCTIONS


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
            executable="/bin/bash"
        ).strip()

    except Exception:
        return "Info del sistema no disponible"



def generate():

    if len(sys.argv) < 2:
        print("[bold red]Error:[/bold red] Debes ingresar un texto.")
        return


    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY")
    )


    prompt_usuario = " ".join(sys.argv[1:])


    model = "gemma-4-31b-it"


    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=prompt_usuario
                )
            ],
        )
    ]


    config = types.GenerateContentConfig(

        thinking_config=types.ThinkingConfig(
            thinking_level="MINIMAL"
        ),

        tools=TOOLS,

        system_instruction=f"""
[OBJETIVO Y ENTORNO]

Eres un asistente avanzado de terminal Linux.

Información del sistema:

{obtener_contexto_sistema()}


[PERSONALIDAD]

- Directo.
- Seguro.
- Sarcástico.
- Sin explicaciones innecesarias.


[HERRAMIENTAS]

Puedes usar herramientas cuando necesites información real del sistema.


[REGLAS]

- Usa comandos compatibles con Linux.
- No inventes resultados.
- Si necesitas datos del sistema usa las herramientas.


[BREVEDAD]

Respuestas cortas por defecto.

Si el usuario pide código o configuración puedes extenderte.
"""
    )


    # Primera llamada: detectar herramientas

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config
    )


    candidate = response.candidates[0]


    function_response_parts = []


    for part in candidate.content.parts:


        if part.function_call:

            function_name = part.function_call.name

            args = dict(part.function_call.args)


            print(
                f"[yellow]Ejecutando:[/yellow] "
                f"{function_name} {args}"
            )


            result = FUNCTIONS[function_name](**args)


            function_response_parts.append(

                types.Part.from_function_response(

                    name=function_name,

                    response={
                        "result": result
                    }
                )
            )


    # Si hubo herramientas, devolvemos el resultado al modelo

    if function_response_parts:


        contents.append(
            candidate.content
        )


        contents.append(

            types.Content(

                role="tool",

                parts=function_response_parts

            )
        )


    # Segunda llamada con STREAMING

    texto_acumulado = ""


    with Live(
        Panel(""),
        refresh_per_second=15,
        auto_refresh=True

    ) as live:


        response_stream = client.models.generate_content_stream(

            model=model,

            contents=contents,

            config=config

        )


        for chunk in response_stream:


            if chunk.text:

                texto_acumulado += chunk.text


                panel = Panel(

                    Markdown(
                        texto_acumulado,
                        style="#9fa5d9"
                    ),

                    title="[#858ab6]Response[/#858ab6]",

                    border_style="#858ab6",

                    style="on #0f0f14"

                )


                live.update(panel)



if __name__ == "__main__":
    generate()
