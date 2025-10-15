# cogs/calculator.py
import ast
import operator
import math
from typing import Any

import discord
from discord import app_commands, Interaction
from discord.ext import commands

# Allowed binary/unary operations
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}

_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Allowed math functions - expose safe subset from math
_MATH_FUNCS = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "sqrt": math.sqrt,
    "log": math.log,        # natural log or log(x, base)
    "log10": math.log10,
    "exp": math.exp,
    "abs": abs,
    "fabs": math.fabs,
}

# Extra helpers
def _deg(x: float) -> float:
    """Convert degrees to radians for trig convenience."""
    return math.radians(x)

# Add deg to functions map
_MATH_FUNCS["deg"] = _deg

# Constants
_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}

# Allowed AST node types
_ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call,
                  ast.Name, ast.Load, ast.Constant, ast.Num)

class SafeEvaluator:
    """
    Evaluate a math expression AST safely using whitelisted operations and functions.
    """

    def eval(self, expression: str) -> Any:
        try:
            parsed = ast.parse(expression, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Syntax error: {e}")

        return self._eval_node(parsed.body)

    def _eval_node(self, node: ast.AST) -> Any:
        # Numbers (Constant for py3.8+)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            else:
                raise ValueError("Only numeric constants are allowed.")
        # For backwards compatibility (older pythons)
        if isinstance(node, ast.Num):
            return node.n

        # Binary operations
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_BINOPS:
                raise ValueError(f"Operator {op_type.__name__} not allowed.")
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            return _ALLOWED_BINOPS[op_type](left, right)

        # Unary operations
        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_UNARYOPS:
                raise ValueError(f"Unary operator {op_type.__name__} not allowed.")
            operand = self._eval_node(node.operand)
            return _ALLOWED_UNARYOPS[op_type](operand)

        # Names (constants)
        if isinstance(node, ast.Name):
            name = node.id
            if name in _CONSTANTS:
                return _CONSTANTS[name]
            raise ValueError(f"Unknown identifier: {name}")

        # Function calls
        if isinstance(node, ast.Call):
            # Only allow simple function names (no attribute access)
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only plain function calls allowed (e.g. sin(x)).")

            func_name = node.func.id
            if func_name not in _MATH_FUNCS:
                raise ValueError(f"Function '{func_name}' is not allowed.")

            func = _MATH_FUNCS[func_name]

            # Evaluate args
            args = [self._eval_node(arg) for arg in node.args]

            # Restrict keyword args for safety (disallow)
            if node.keywords:
                raise ValueError("Keyword arguments are not allowed in function calls.")

            # Support log(x, base) gracefully - math.log supports optional base
            try:
                return func(*args)
            except TypeError as e:
                raise ValueError(f"Invalid arguments for {func_name}: {e}")
            except ValueError as e:
                # math domain errors (e.g., log(-1))
                raise ValueError(str(e))

        raise ValueError(f"Unsupported expression element: {type(node).__name__}")

# Cog definition
class Calculator(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._evaluator = SafeEvaluator()

    @app_commands.command(name="calculate", description="Safely evaluate a mathematical expression.")
    @app_commands.describe(expression="The mathematical expression to evaluate (e.g. sin(pi/2) + sqrt(16))")
    async def calculate(self, interaction: Interaction, expression: str):
        await interaction.response.defer()

        try:
            result = self._evaluator.eval(expression)
        except Exception as e:
            return await interaction.followup.send(f"⚠️ Error: {e}", ephemeral=True)

        # Nicely format numeric results
        if isinstance(result, float):
            # Trim long floats sensibly
            out = f"{result:.12g}"
        else:
            out = str(result)

        await interaction.followup.send(f"🧮 **Expression:** `{expression}`\n**Result:** `{out}`")

async def setup(bot: commands.Bot):
    await bot.add_cog(Calculator(bot))
