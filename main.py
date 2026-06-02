from src.backend.unsteady.engine.phase_runner import run_unsteady
from src.backend.steady.steady_main import run_steady

run_steady("steady_input.jsonc")
run_unsteady("unsteady_input.jsonc")