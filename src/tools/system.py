import platform
import os

def system_info() -> str:
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
