"""F1 capstone solution entry point (kept for template compat; real entry is app.py)."""

from src.solvers import answer_question
from src.playbook_engine import actions_for_scope


def main() -> None:
    print(answer_question("Where are we losing the most against target this quarter?")["answer"])
    print(actions_for_scope("West")[:1])


if __name__ == "__main__":
    main()
