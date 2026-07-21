# Proyecto IA Terminal

![Banner del Proyecto](https://via.placeholder.com/800x400 "Tu imagen va aquí")

Este proyecto es algo sencillo que cualquiera puede hacer. La idea es realizar una pregunta rápida a la IA directamente desde la terminal y obtener una respuesta veloz *(¡seguimos trabajando en optimizar esos milisegundos!)*.

---

## Instalación y Configuración

Sigue estos pasos para dejar el script listo y accesible desde cualquier directorio:

1. **Configurar la API Key:**  
   Define tu clave de API exportando la variable de entorno `GEMINI_API_KEY` (puedes agregarlo a tu `~/.bashrc` o `~/.zshrc`):
   ```bash
   export GEMINI_API_KEY="tu_api_key_aqui"```


2. **Ajustar rutas:**
Abre el archivo `ia` y configura la ruta al entorno virtual de este repositorio junto con la ruta de ejecución del script principal.
3. **Mover al PATH:**
Otorga permisos de ejecución y mueve el archivo `ia` a `/usr/local/bin/`:
```bash
chmod +x ia
sudo mv ia /usr/local/bin/
```



> ⚠️ **Nota sobre modelos:** El script utiliza por defecto el modelo `gemma-4-26b-a4b-it`. Si quieres usar un modelo diferente o cambiar de proveedor, toca ensuciarse las manos y modificar el código... ¡que para algo es OpenSource!

---

## Comandos del Sistema

El script incluye comandos especiales para controlar el flujo y detalle de las respuestas al vuelo:

| Comando | Descripción |
| --- | --- |
| `/etc` | **Desactiva** la función de brevedad predeterminada para recibir respuestas extendidas y detalladas. |
| `/bla` | **Reactiva** la función de brevedad para volver a obtener respuestas cortas y directas al grano. |

---

## Personalización

Puedes ajustar la personalidad, el tono, el formato o las reglas del modelo modificando el parámetro `system_instruction` dentro del archivo `main.py`.

---

*Nota: Ojalá al que lea esto le salga un error inesperado en la distro... y que tenga que reinstalar el sistema.* 🐧🔥

```

```
