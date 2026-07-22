import subprocess

def run_command(command: str) -> str:
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return result.stderr

    return result.stdout