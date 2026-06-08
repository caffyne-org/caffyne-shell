from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from snippets import Icon, Applet, AppletPage
from gi.repository import Gdk
import re

class CalculatorApplet(Applet):
    def __init__(self, parent, **kwargs):
        self.expression_label = Label(
            label="",
            v_expand=True,
            v_align="end",
            h_expand=True,
            h_align="end",
            style="font-size: 24px;"
        )
        self.preview_label = Label(
            label="",
            v_expand=True,
            v_align="start",
            h_expand=True,
            h_align="end",
            style="font-size: 14px; opacity: 0.6;"
        )
        self.display = Box(
            style_classes=["calculator-display"],
            orientation="v",
            children=[self.expression_label, self.preview_label]
        )
        self.expression = "0"
        self.showing_result = False

        buttons = [
            [
                ("C",  "C",  "arrows-counter-clockwise-duotone", "operator"),
                ("()", "()", "brackets-round",           "operator"),
                ("%",  "%",  "percent-duotone",          "operator"),
                ("÷",  "÷",  "divide",                   "operator"),
            ],
            [
                ("7", "7", None, "digit"), ("8", "8", None, "digit"),
                ("9", "9", None, "digit"), ("×", "×", "x", "operator"),
            ],
            [
                ("4", "4", None, "digit"), ("5", "5", None, "digit"),
                ("6", "6", None, "digit"), ("-", "-", "minus", "operator"),
            ],
            [
                ("1", "1", None, "digit"), ("2", "2", None, "digit"),
                ("3", "3", None, "digit"), ("+", "+", "plus", "operator"),
            ],
            [
                ("0", "0", None, "digit"),
                (".", ".", None, "operator"),
                ("⌫", "⌫", "backspace-duotone", "operator"),
                ("=", "=", "equals", "equals"),
            ],
        ]

        button_grid = Box(
            orientation="v",
            spacing=6,
            children=[
                Box(
                    spacing=6,
                    children=[
                        Button(
                            child=Label(label=display) if icon is None else Box(h_align="center", children=Icon(icon_name=icon, icon_size=16)),
                            style_classes=["calculator-button", css_class],
                            h_expand=True,
                            on_clicked=lambda _, v=value: self.on_button_click(v),
                        )
                        for display, value, icon, css_class in row
                    ],
                )
                for row in buttons
            ],
        )

        calculator = Box(
            style_classes=["calculator"],
            orientation="v",
            spacing=12,
            children=[self.display, button_grid],
        )

        super().__init__(
            main_menu=AppletPage(first=True, title="Calculator", child=calculator),
            **kwargs,
        )
        self.update_display()
        self.connect("realize", lambda _: parent.connect("key-press-event", self._on_key_press))

    def on_button_click(self, button: str):
        if button in "0123456789":   self.input_number(button)
        elif button == ".":          self.input_decimal(button)
        elif button in "+-×÷%":     self.input_operator(button)
        elif button == "=":          self.calculate()
        elif button == "C":          self.clear()
        elif button == "⌫":         self.backspace()
        elif button == "()":         self.input_bracket()

    def _on_key_press(self, _, event):
        key = Gdk.keyval_name(event.keyval)
        char = chr(event.keyval) if event.keyval < 128 else None
        if char:
            if char in "0123456789":
                self.on_button_click(char)
            elif char == ".":
                self.on_button_click(".")
            elif char == "+":
                self.on_button_click("+")
            elif char == "-":
                self.on_button_click("-")
            elif char == "*":
                self.on_button_click("×")
            elif char == "/":
                self.on_button_click("÷")
            elif char == "%":
                self.on_button_click("%")
            elif char == "=":
                self.on_button_click("=")
            elif char == "(":
                self.on_button_click("()")
            elif char == ")":
                self.on_button_click("()")
        else:
            if key == "BackSpace":
                self.on_button_click("⌫")
            elif key == "Delete":
                self.on_button_click("C")
            elif key == "Return":
                self.on_button_click("=")
                return True
            
    def input_number(self, num: str):
        if self.showing_result:
            self.expression = num
            self.showing_result = False
        elif self.expression == "0":
            self.expression = num
        else:
            self.expression += num
        self.update_display()

    def input_decimal(self, char: str):
        if self.showing_result:
            self.expression = "0."
            self.showing_result = False
        else:
            parts = self.expression.replace("+", " ").replace("-", " ").replace("×", " ").replace("÷", " ").replace("%", " ").replace("(", " ").replace(")", " ").split()
            current_num = parts[-1] if parts else "0"
            if "." not in current_num:
                self.expression += "."
        self.update_display()

    def input_operator(self, op: str):
        if self.showing_result:
            self.showing_result = False
        if self.expression and self.expression[-1] in "+-×÷%":
            self.expression = self.expression[:-1]
        self.expression += op
        self.update_display()

    def input_bracket(self):
        if self.showing_result:
            self.expression = "("
            self.showing_result = False
        else:
            open_count = self.expression.count("(")
            close_count = self.expression.count(")")
            if open_count > close_count and self.expression and (self.expression[-1].isdigit() or self.expression[-1] == ")"):
                self.expression += ")"
            else:
                self.expression += "("
        self.update_display()

    def calculate(self):
        result = self.evaluate_expression(self.expression)
        if result is not None:
            self.showing_result = True
            self.expression = result
            self.expression_label.set_label(result[:15])
            self.preview_label.set_label("")
    def evaluate_expression(self, expr: str) -> str | None:
        try:
            if not expr or expr == "0":
                return None
            
            open_count = expr.count("(")
            close_count = expr.count(")")
            expr_eval = expr + ")" * (open_count - close_count)
            
            expr_eval = expr_eval.replace("×", "*").replace("÷", "/")
            
            expr_eval = re.sub(r'(\d)(\()', r'\1*\2', expr_eval)
            expr_eval = re.sub(r'(\))(\()', r'\1*\2', expr_eval)
            expr_eval = re.sub(r'(\))(\d)', r'\1*\2', expr_eval)

            if re.search(r'[^0-9+\-*/.()%]', expr_eval):
                return None

            result = eval(expr_eval)
            if isinstance(result, (int, float)):
                if abs(result) > 1e15:
                    return f"{result:.6e}"
                return str(int(result)) if result == int(result) else str(round(result, 8))
            return str(result)
        except ZeroDivisionError:
            return "÷ 0"
        except (SyntaxError, ValueError):
            return None
        except Exception:
            return "Error"
    def clear(self):
        self.expression = "0"
        self.showing_result = False
        self.update_display()

    def backspace(self):
        if self.showing_result:
            self.expression = "0"
            self.showing_result = False
        elif len(self.expression) > 1:
            self.expression = self.expression[:-1]
        else:
            self.expression = "0"
        self.update_display()

    def update_display(self):
        if self.showing_result:
            return
        self.expression_label.set_label(self.expression[:15])
        preview = self.evaluate_expression(self.expression)
        self.preview_label.set_label(f"= {preview[:15]}" if preview and preview != self.expression else "")