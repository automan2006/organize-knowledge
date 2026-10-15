"""Estimate a conservative phone-friendly size for a LaTeX equation.

python fit_notion_equation.py --input equation.txt --width-px 220
Standard library only. This estimates glyph layout, not the user's live viewport.
It changes only explicit size commands; it never rewrites or truncates the math.
"""

import argparse
import json
from pathlib import Path
import re
import sys


SIZE_RE = re.compile(r"\\(?:Huge|huge|LARGE|Large|large|normalsize|small|footnotesize|scriptsize|tiny)\b\s*")
GREEK = set("alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega".split())
RELATIONS = set("le leq ge geq ne neq approx equiv sim simeq propto in notin subset supset to rightarrow leftarrow".split())
FONTS = set("mathrm mathit mathsf mathtt mathrm mathcal mathbb mathbf boldsymbol operatorname text textrm textsf".split())


def glyph_width(c):
    if c in "=<>≤≥≈≠": return 1.15
    if c in "+−-": return 1.0
    if c in "()[]|": return 0.4
    if c in ".,;:": return 0.28
    if c in "ilj1": return 0.36
    if c in "MW": return 0.92
    if c.isspace(): return 0.0
    if ord(c) > 0x2FFF: return 1.0
    return 0.58


class WidthEstimator:
    def __init__(self, source):
        self.source = source
        self.pos = 0
        self.unsupported = set()

    def skip_space(self):
        while self.pos < len(self.source) and self.source[self.pos].isspace(): self.pos += 1

    def atom(self):
        self.skip_space()
        if self.pos >= len(self.source): return 0.0
        c = self.source[self.pos]
        self.pos += 1
        if c == "{": return self.sequence(stop="}")
        if c != "\\": return glyph_width(c)
        match = re.match(r"[A-Za-z]+|.", self.source[self.pos:], re.S)
        if not match: return 0.0
        cmd = match.group(0)
        self.pos += len(cmd)
        if cmd in {"frac", "dfrac", "tfrac"}:
            return max(self.atom(), self.atom()) + 0.25
        if cmd == "sqrt":
            self.skip_space()
            if self.pos < len(self.source) and self.source[self.pos] == "[":
                end = self.source.find("]", self.pos)
                if end >= 0: self.pos = end + 1
            return self.atom() + 0.75
        if cmd in FONTS: return self.atom()
        if cmd == "boxed": return self.atom() + 0.9
        if cmd in {"displaystyle", "textstyle", "left", "right", "limits", "nolimits"}: return 0.0
        if cmd in {"begin", "end"}:
            self.atom()
            self.unsupported.add("environment")
            return 0.0
        if cmd in GREEK: return 0.68
        if cmd in RELATIONS: return 1.15
        if cmd in {"times", "cdot", "pm", "mp"}: return 1.0
        if cmd in {"sum", "prod", "int"}: return 1.1
        if cmd in {"sin", "cos", "tan", "log", "ln", "min", "max"}: return len(cmd) * 0.5 + 0.15
        if cmd in {",", ";", ":", " ", "quad", "qquad", "!"}:
            return {",": 0.17, ";": 0.28, ":": 0.22, " ": 0.33,
                    "quad": 1.0, "qquad": 2.0, "!": -0.17}[cmd]
        if cmd in {"{", "}", "%", "_", "#", "&"}: return glyph_width(cmd)
        self.unsupported.add(cmd)
        return max(1.0, len(cmd) * 0.4)

    def sequence(self, stop=None):
        width = 0.0
        while self.pos < len(self.source):
            self.skip_space()
            if self.pos >= len(self.source): break
            if stop and self.source[self.pos] == stop:
                self.pos += 1
                break
            # Subscript and superscript occupy a shared attachment column.
            if self.source[self.pos] in "_^":
                scripts = []
                while self.pos < len(self.source) and self.source[self.pos] in "_^":
                    self.pos += 1
                    scripts.append(0.72 * self.atom())
                    self.skip_space()
                width += max(scripts, default=0.0)
            elif self.source.startswith("\\\\", self.pos):
                self.unsupported.add("multiline")
                self.pos += 2
            else:
                width += self.atom()
        return width


def fit_equation(source, width_px=220.0, base_font_px=16.0):
    if not 100 <= width_px <= 2000 or not 12 <= base_font_px <= 30:
        raise ValueError("Use a realistic available width and base font size.")
    source = source.strip()
    if source.startswith("$$") and source.endswith("$$"):
        source = source[2:-2].strip()
    source = SIZE_RE.sub("", source).strip()
    if not source: raise ValueError("Equation is empty.")
    estimator = WidthEstimator(source)
    ems = estimator.sequence()
    # KaTeX's normal math is ~1.21 times surrounding text; leave 15% margin.
    normal_width = ems * base_font_px * 1.21
    budget = width_px * 0.85
    choices = [(r"\large", 1.2), (r"\normalsize", 1.0), (r"\small", 0.9)]
    # Multi-term formulas and fractions never inherit the previous blanket Large.
    selected, scale = choices[-1]
    for command, factor in choices:
        if normal_width * factor <= budget:
            selected, scale = command, factor
            break
    needs_split = normal_width * scale > budget or bool(estimator.unsupported)
    return {"latex": selected + " " + source,
            "size": selected, "estimated_width_px": round(normal_width * scale, 1),
            "available_width_px": width_px, "safe_budget_px": round(budget, 1),
            "needs_split_or_review": needs_split,
            "unsupported_constructs": sorted(estimator.unsupported),
            "measurement": "conservative_estimate_not_live_viewport"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="UTF-8 equation file, or '-' for stdin.")
    parser.add_argument("--width-px", type=float, default=220.0)
    parser.add_argument("--base-font-px", type=float, default=16.0)
    args = parser.parse_args()
    try:
        source = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8-sig")
        print(json.dumps(fit_equation(source, args.width_px, args.base_font_px), ensure_ascii=True))
        return 0
    except (OSError, ValueError, RecursionError):
        print(json.dumps({"error": "Unable to estimate safely; split into short editable equation blocks and review."}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
