"""
Formula evaluation utilities for insurance age calculations

Handles:
- Age string parsing ("만 15세" → 15)
- Formula evaluation with context ("min[세만기 - 년납, 70]" + context → 60)
- Period extraction ("80세 만기" → 80, "10년납" → 10)

All formula evaluation uses AST parsing for safety (no eval()).
"""

import re
import ast
from typing import Optional, Dict, Any, Union


class FormulaEvaluator:
    """Safe formula evaluator with context variables using AST parsing"""

    def __init__(self):
        # Whitelist of allowed functions
        self.allowed_functions = {
            'min': min,
            'max': max,
            'abs': abs,
            'round': round
        }

    def parse_age(self, age_str: str) -> Optional[int]:
        """
        Parse age string to numeric value

        Args:
            age_str: Age string like "만 15세", "보험연령 20세", "15세"

        Returns:
            Numeric age or None if it's a formula or unparseable

        Examples:
            >>> parse_age("만 15세")
            15
            >>> parse_age("만15세")
            15
            >>> parse_age("보험연령 20세")
            20
            >>> parse_age("min[세만기 - 년납, 70] 세")
            None  # Formula, not parseable
        """
        if not isinstance(age_str, str):
            return None

        # Remove extra whitespace
        age_str = age_str.strip()

        # Try to extract simple number with optional "만" or "보험연령" prefix
        # Patterns: "만 15세", "만15세", "보험연령 20세", "15세"
        match = re.search(r'(?:만|보험연령)?\s*(\d+)\s*세', age_str)
        if match:
            # Check if it contains formula characters (should not be parsed as simple age)
            if any(char in age_str for char in ['[', ']', 'min', 'max', '-', '+']):
                # Only return if the formula chars appear AFTER the number
                # "만 15세 - min[...]" → don't parse (formula)
                # "15세" → parse (simple age)
                num_pos = match.start()
                formula_chars_before = any(char in age_str[:num_pos] for char in ['[', ']', 'min', 'max'])
                if formula_chars_before:
                    return None

            return int(match.group(1))

        return None

    def evaluate_formula(self, formula_str: str, **context) -> Optional[int]:
        """
        Safely evaluate age formula with context

        Args:
            formula_str: Formula string like "min[세만기 - 년납, 90 - 년납, 70] 세"
            context: Context variables like 세만기=80, 년납=10

        Returns:
            Evaluated integer result or None on error

        Examples:
            >>> evaluate_formula("min[세만기 - 년납, 90 - 년납, 70] 세", 세만기=80, 년납=10)
            70  # min(80-10, 90-10, 70) = min(70, 80, 70) = 70

            >>> evaluate_formula("max[100 - 년만기, 80] 세", 년만기=20)
            80  # max(100-20, 80) = max(80, 80) = 80
        """
        try:
            # Remove extra whitespace
            formula = formula_str.strip()

            # Remove trailing " 세" or "세"
            formula = re.sub(r'\s*세\s*$', '', formula)

            # Convert bracket notation to parentheses
            # "min[...]" → "min(...)"
            formula = formula.replace('[', '(').replace(']', ')')

            # Replace Korean variable names with context values
            for key, value in context.items():
                if value is not None:
                    # Replace whole word only (avoid partial replacements)
                    formula = re.sub(r'\b' + re.escape(key) + r'\b', str(value), formula)

            # Parse and evaluate safely using AST
            tree = ast.parse(formula, mode='eval')
            result = self._safe_eval(tree.body, self.allowed_functions, context)

            # Round to nearest integer
            return int(round(result)) if result is not None else None

        except Exception as e:
            print(f"[WARN] Formula evaluation failed: {formula_str} - {e}")
            return None

    def _safe_eval(self, node: ast.AST, functions: Dict[str, Any], context: Dict[str, Any]) -> Union[int, float, None]:
        """
        Safely evaluate AST node

        Only allows:
        - Numbers (int, float)
        - Binary operations (+, -, *, /)
        - Function calls (from whitelist: min, max, abs, round)
        - Variable names (from context)

        Args:
            node: AST node to evaluate
            functions: Whitelist of allowed functions
            context: Variable context

        Returns:
            Evaluated numeric result or None
        """
        # Number literal
        if isinstance(node, (ast.Num, ast.Constant)):
            # ast.Num for Python < 3.8, ast.Constant for Python >= 3.8
            if isinstance(node, ast.Num):
                return node.n
            else:
                if isinstance(node.value, (int, float)):
                    return node.value
                else:
                    raise ValueError(f"Constant type {type(node.value)} not allowed")

        # Binary operation (+, -, *, /)
        elif isinstance(node, ast.BinOp):
            left = self._safe_eval(node.left, functions, context)
            right = self._safe_eval(node.right, functions, context)

            if left is None or right is None:
                return None

            if isinstance(node.op, ast.Add):
                return left + right
            elif isinstance(node.op, ast.Sub):
                return left - right
            elif isinstance(node.op, ast.Mult):
                return left * right
            elif isinstance(node.op, ast.Div):
                if right == 0:
                    print("[WARN] Division by zero in formula")
                    return None
                return left / right
            else:
                raise ValueError(f"Binary operation {type(node.op)} not allowed")

        # Unary operation (-, +)
        elif isinstance(node, ast.UnaryOp):
            operand = self._safe_eval(node.operand, functions, context)
            if operand is None:
                return None

            if isinstance(node.op, ast.USub):
                return -operand
            elif isinstance(node.op, ast.UAdd):
                return +operand
            else:
                raise ValueError(f"Unary operation {type(node.op)} not allowed")

        # Function call (min, max, abs, round only)
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only simple function calls allowed")

            func_name = node.func.id
            if func_name not in functions:
                raise ValueError(f"Function {func_name} not in whitelist")

            # Evaluate arguments
            args = []
            for arg in node.args:
                val = self._safe_eval(arg, functions, context)
                if val is None:
                    return None
                args.append(val)

            # Call whitelisted function
            return functions[func_name](*args)

        # Variable name (from context)
        elif isinstance(node, ast.Name):
            var_name = node.id
            if var_name in context:
                return context[var_name]
            else:
                # Variable not in context, might be already replaced
                raise ValueError(f"Variable {var_name} not in context")

        else:
            raise ValueError(f"AST node type {type(node)} not allowed")

    def parse_period(self, period_str: str) -> Optional[int]:
        """
        Extract numeric value from period string

        Args:
            period_str: Period string like "80세 만기", "10년납", "종신", "25년 만기"

        Returns:
            Numeric value or None if not parseable

        Examples:
            >>> parse_period("80세 만기")
            80
            >>> parse_period("10년납")
            10
            >>> parse_period("25년 만기")
            25
            >>> parse_period("종신")
            None
        """
        if not isinstance(period_str, str):
            return None

        # Extract first number found
        match = re.search(r'(\d+)', period_str)
        return int(match.group(1)) if match else None


# Global instance for convenience
evaluator = FormulaEvaluator()

# Convenience functions (module-level API)
def parse_age(age_str: str) -> Optional[int]:
    """Parse age string to numeric value. See FormulaEvaluator.parse_age for details."""
    return evaluator.parse_age(age_str)

def evaluate_formula(formula_str: str, **context) -> Optional[int]:
    """Safely evaluate formula with context. See FormulaEvaluator.evaluate_formula for details."""
    return evaluator.evaluate_formula(formula_str, **context)

def parse_period(period_str: str) -> Optional[int]:
    """Extract numeric value from period string. See FormulaEvaluator.parse_period for details."""
    return evaluator.parse_period(period_str)
