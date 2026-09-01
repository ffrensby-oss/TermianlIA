import json
from pathlib import Path
import flet as ft


BLACK = "#000000"
WHITE = "#ffffff"


def border_all(color, width=1):
    """Crea un borde uniforme compatible con distintas versiones de flet."""
    side = ft.BorderSide(width, color)
    return ft.Border(left=side, top=side, right=side, bottom=side)


class ConfigEditor:
    def __init__(self):
        self.config_path = self.find_config_path()
        self.config_data = self.load_config()
        self.fields = {}
        self.page = None
        self.models_column = None  

    def find_config_path(self):
        candidates = [
            Path(__file__).resolve().parent / "config.json",
            Path(__file__).resolve().parent.parent / "config.json",
            Path.cwd() / "config.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return str(Path(__file__).resolve().parent / "config.json")

    def load_config(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as file:
                loaded = json.load(file)
                return loaded if isinstance(loaded, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as exc:
            print(f"Error: {exc}")
            return {}

    def build_ui(self, page: ft.Page):
        self.page = page
        page.title = "Editor de Configuración"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = BLACK
        page.vertical_alignment = ft.MainAxisAlignment.START
        page.height = 600
        page.width = 600
        page.resizeable = False 

        # Título
        title = ft.Text(
            "EDITOR DE CONFIGURACIÓN",
            size=15,
            weight="bold",
            color=WHITE,
        )

        # Contenedor de campos
        fields_column = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            spacing=10,
        )

        # Renderizar campos
        self.render_fields(fields_column, self.config_data)

        # Botones
        def save_config(e):
            try:
                updated = self.config_data.copy()

                # Actualizar campos de formulario
                for full_key, field_data in self.fields.items():
                    if isinstance(field_data, tuple):
                        field, orig_type = field_data
                        value = field.value.strip() if hasattr(field, 'value') else str(field)
                    else:
                        value = field_data
                        orig_type = type(field_data)

                    if orig_type == bool:
                        value = value.lower() in {"true", "1", "yes"}
                    elif orig_type == int:
                        value = int(value)
                    elif orig_type == float:
                        value = float(value)

                    updated[full_key.rstrip(".")] = value

                # Asegurar que chouse_models se guarde como array
                if "chouse_models" in updated and isinstance(updated["chouse_models"], list):
                    # Ya es un array, mantenerlo
                    pass

                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(updated, f, indent=2, ensure_ascii=False)
                    f.write("\n")

                snack = ft.SnackBar(
                    ft.Text("✓ CONFIGURACIÓN GUARDADA", color=WHITE),
                    bgcolor=BLACK,
                )
                page.overlay.append(snack)
                snack.open = True
                page.update()
                
            except Exception as exc:
                snack = ft.SnackBar(
                    ft.Text(f"✕ ERROR: {exc}", color=WHITE),
                    bgcolor=BLACK,
                )
                page.overlay.append(snack)
                snack.open = True
                page.update()

        def reload_config(e):
            self.config_data = self.load_config()
            self.fields.clear()
            fields_column.controls.clear()
            self.render_fields(fields_column, self.config_data)
            page.update()

        save_btn = ft.TextButton(
            content=ft.Text("GUARDAR", color=BLACK, weight="bold"),
            on_click=save_config,
            style=ft.ButtonStyle(
                bgcolor=WHITE,
                shape=ft.RoundedRectangleBorder(radius=4),
                side=ft.BorderSide(1, WHITE),
            ),
        )

        reload_btn = ft.TextButton(
            content=ft.Text("RECARGAR", color=WHITE, weight="bold"),
            on_click=reload_config,
            style=ft.ButtonStyle(
                bgcolor=BLACK,
                shape=ft.RoundedRectangleBorder(radius=4),
                side=ft.BorderSide(1, WHITE),
            ),
        )

        buttons_row = ft.Row(
            [reload_btn, save_btn],
            alignment=ft.MainAxisAlignment.END,
            spacing=10,
        )

        # Contenedor principal
        main_container = ft.Container(
            content=ft.Column(
                [
                    title,
                    ft.Divider(height=1, color=WHITE),
                    fields_column,
                    ft.Divider(height=1, color=WHITE),
                    buttons_row,
                ],
                spacing=15,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=20,
            expand=True,
            bgcolor=BLACK,
            border=border_all(WHITE),
            border_radius=6,
        
        )

        page.add(main_container)

    def render_fields(self, parent, data, prefix=""):
        for key, value in data.items():
            if isinstance(value, dict):
                self.render_fields(parent, value, f"{prefix}{key}.")
                continue

            # Saltar chouse_models - se maneja en el selector de modelos
            if key == "chouse_models":
                continue

            # Si es el campo "model" y existe "chouse_models", crear selector
            if key == "model" and "chouse_models" in data:
                self.render_model_selector(parent, data, key, value, prefix)
                continue

            full_key = f"{prefix}{key}"

            # Para campos de texto largo (system_instruction), usar multiline
            if key == "system_instruction" and isinstance(value, str) and len(value) > 200:
                self.render_system_instruction_editor(parent, data, key, value, prefix)
                continue

            # Para otros campos normales
            row = ft.Row(
                spacing=10,
                alignment=ft.MainAxisAlignment.START,
            )

            label = ft.Text(
                key,
                size=12,
                weight="bold",
                width=150,
                color=WHITE,
            )

            field = ft.TextField(
                value=str(value),
                width=300,
                bgcolor=BLACK,
                text_size=12,
                color=WHITE,
                border_color=WHITE,
                focused_border_color=WHITE,
                border_width=1,
            )

            row.controls.extend([label, field])
            parent.controls.append(row)

            self.fields[full_key] = (field, type(value))

    def render_system_instruction_editor(self, parent, data, key, value, prefix):
        """Renderiza un editor especial para system_instruction con área multiline"""
        full_key = f"{prefix}{key}"

        # Contenedor principal
        container = ft.Container(
            bgcolor=BLACK,
            border=border_all(WHITE),
            border_radius=6,
            padding=10,
            margin=5,
        )

        # Label
        label = ft.Text(
            key.upper(),
            size=12,
            weight="bold",
            color=WHITE,
        )

        # Texto explicativo
        info_text = ft.Text(
            "Instrucción del sistema (texto largo)",
            size=10,
            color="#CCCCCC",
            italic=True,
        )

        # Campo de texto multiline
        field = ft.TextField(
            value=str(value),
            multiline=True,
            min_lines=6,
            max_lines=10,
            width=370,
            bgcolor=BLACK,
            text_size=11,
            color=WHITE,
            border_color=WHITE,
            focused_border_color=WHITE,
            border_width=1,
        )

        # Contenedor con scroll si es necesario
        main_column = ft.Column([
            label,
            info_text,
            field,
        ], spacing=8)

        container.content = main_column
        parent.controls.append(container)

        # Guardar referencia del campo
        self.fields[full_key] = (field, type(value))

    def build_model_button(self, model, data, parent, current_model):
        """Crea un botón individual para un modelo dentro del acordeón"""
        selected = model == current_model
        return ft.Container(
            content=ft.Text(
                model,
                size=11,
                color=BLACK if selected else WHITE,
            ),
            bgcolor=WHITE if selected else BLACK,
            border=border_all(WHITE),
            border_radius=5,
            padding=8,
            on_click=lambda e, m=model, d=data: self.select_model(d, m, parent),
        )

    def render_model_selector(self, parent, data, key, current_model, prefix):
        """Crea un selector de modelos compacto con dropdown y acordeón expandible"""
        models = data.get("chouse_models", [])

        # Container principal (ancho fijo para no ocupar toda la pantalla)
        container = ft.Container(
            bgcolor=BLACK,
            border=border_all(WHITE),
            border_radius=8,
            padding=12,
            margin=5,
            width=380,
        )

        def on_model_change(e):
            """Cuando se selecciona un modelo en el dropdown"""
            if e.control.value:
                self.select_model(data, e.control.value, parent)

        # Dropdown para seleccionar modelos
        self.model_dropdown = ft.Dropdown(
            value=current_model,
            options=[ft.DropdownOption(model) for model in models],
            on_select=on_model_change,
            width=356,
            bgcolor=BLACK,
            color=WHITE,
            border_color=WHITE,
            focused_border_color=WHITE,
        )

        # Label del modelo actual
        self.model_label = ft.Text(
            f"MODELO SELECCIONADO: {current_model}",
            size=12,
            weight="bold",
            color=WHITE,
        )

        # Columna con altura limitada y scroll, para no crecer sin control
        models_column = ft.Column(spacing=5, scroll=ft.ScrollMode.AUTO, height=150)
        for model in models:
            models_column.controls.append(
                self.build_model_button(model, data, parent, current_model)
            )
        self.models_column = models_column

        # Campo + botón para agregar un modelo nuevo a chouse_models
        new_model_field = ft.TextField(
            hint_text="Nuevo modelo...",
            hint_style=ft.TextStyle(color=WHITE),
            width=270,
            height=38,
            content_padding=8,
            bgcolor=BLACK,
            text_size=11,
            color=WHITE,
            border_color=WHITE,
            focused_border_color=WHITE,
            border_width=1,
        )
        self.new_model_field = new_model_field

        def add_model(e):
            new_model = (new_model_field.value or "").strip()
            if not new_model or new_model in models:
                new_model_field.value = ""
                self.page.update()
                return

            # Muta la lista original (misma referencia que data["chouse_models"])
            models.append(new_model)

            models_column.controls.append(
                self.build_model_button(new_model, data, parent, data.get("model"))
            )
            self.model_dropdown.options = [ft.DropdownOption(m) for m in models]

            new_model_field.value = ""
            self.page.update()

        add_model_btn = ft.IconButton(
            icon=ft.Icons.ADD_CIRCLE_OUTLINE,
            icon_color=WHITE,
            tooltip="Agregar modelo",
            on_click=add_model,
        )

        add_model_row = ft.Row(
            [new_model_field, add_model_btn],
            spacing=5,
        )

        # Estados del acordeón (cerrado por defecto para ocupar menos espacio)
        accordion_expanded = [False]
        accordion_body = ft.Column(
            [models_column, add_model_row],
            spacing=8,
            visible=accordion_expanded[0],
        )

        def toggle_accordion(e):
            accordion_expanded[0] = not accordion_expanded[0]
            expand_btn_text.value = "▲" if accordion_expanded[0] else "▼"
            accordion_body.visible = accordion_expanded[0]
            self.page.update()

        # Botón para expandir/contraer
        expand_btn_text = ft.Text("▼", size=16, color=WHITE, weight="bold")

        accordion_header = ft.Row(
            [
                ft.Text("MODELOS DISPONIBLES", size=11, color=WHITE, weight="bold"),
                ft.Text("", expand=True),
                expand_btn_text,
            ],
            spacing=10,
        )

        accordion_btn = ft.Container(
            content=accordion_header,
            bgcolor=BLACK,
            border=border_all(WHITE),
            border_radius=5,
            padding=10,
            on_click=toggle_accordion,
        )

        main_column = ft.Column([
            self.model_label,
            ft.Divider(height=8, color="transparent"),
            ft.Text("SELECCIONA UN MODELO:", size=11, color=WHITE, weight="bold"),
            self.model_dropdown,
            ft.Divider(height=8, color="transparent"),
            accordion_btn,
            accordion_body,
        ])

        container.content = main_column
        parent.controls.append(container)

        # Guardar referencia al modelo seleccionado
        full_key = f"{prefix}{key}"
        self.fields[full_key] = current_model

    def select_model(self, data, model, parent):
        """Selecciona un modelo y actualiza el valor"""
        data["model"] = model
        self.fields["model"] = model

        # Actualizar el label del modelo seleccionado
        self.model_label.value = f"MODELO SELECCIONADO: {model}"

        # Actualizar el dropdown
        if hasattr(self, "model_dropdown"):
            self.model_dropdown.value = model

        # Recolorear todos los botones del acordeón (incluidos los agregados después)
        for btn in self.models_column.controls:
            if isinstance(btn, ft.Container) and isinstance(btn.content, ft.Text):
                is_selected = btn.content.value == model
                btn.bgcolor = WHITE if is_selected else BLACK
                btn.content.color = BLACK if is_selected else WHITE

        self.page.update()


def main(page: ft.Page):
    editor = ConfigEditor()
    editor.build_ui(page)


if __name__ == "__main__":
    ft.app(target=main)