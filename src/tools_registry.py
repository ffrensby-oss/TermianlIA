from tools.command import run_command
from google.genai import types
from tools.filesystem import (
    read_file,
    write_file,
    list_directory,
)
from tools.system import system_info


FUNCTIONS = {
    "run_command": run_command,
    "read_file": read_file,
    "write_file": write_file,
    "list_directory": list_directory,
    "system_info": system_info,
}

TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="run_command",
                description="Ejecuta un comando Linux y devuelve su salida.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "command": {
                            "type": "STRING",
                            "description": "Comando bash."
                        }
                    },
                    "required": ["command"]
                }
            ),

            types.FunctionDeclaration(
                name="system_info",
                description="Devuelve información del sistema.",
                parameters={
                    "type": "OBJECT",
                    "properties": {}
                }
            ),

            types.FunctionDeclaration(
                name="read_file",
                description="Lee un archivo.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "path": {
                            "type": "STRING"
                        }
                    },
                    "required": ["path"]
                }
            ),

            types.FunctionDeclaration(
                name="write_file",
                description="Escribe un archivo.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "path": {
                            "type": "STRING"
                        },
                        "text": {
                            "type": "STRING"
                        }
                    },
                    "required": ["path","text"]
                }
            ),

            types.FunctionDeclaration(
                name="list_directory",
                description="Lista el contenido de un directorio.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "path": {
                            "type": "STRING"
                        }
                    },
                    "required": ["path"]
                }
            )
        ]
    )
]