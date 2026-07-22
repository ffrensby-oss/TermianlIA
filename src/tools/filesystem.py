from pathlib import Path


def read_file(path: str) -> str:
    """
    Lee el contenido de un archivo de texto.
    """

    return Path(path).read_text(encoding="utf-8")


def write_file(path: str, text: str) -> str:
    """
    Escribe texto en un archivo.
    """

    Path(path).write_text(text, encoding="utf-8")

    return f"Archivo '{path}' escrito correctamente."


def list_directory(path: str = ".") -> str:
    """
    Lista el contenido de un directorio.
    """

    p = Path(path)

    if not p.exists():
        return f"Error: '{path}' no existe."

    if not p.is_dir():
        return f"Error: '{path}' no es un directorio."

    items = []

    for item in sorted(p.iterdir()):
        if item.is_dir():
            items.append(f"📁 {item.name}")
        else:
            items.append(f"📄 {item.name}")

    return "\n".join(items)