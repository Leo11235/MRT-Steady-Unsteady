#from src.backend.steady.steady_main import run_steady
from src.backend.unsteady.engine.phase_runner import run_unsteady

#run_steady("steady_input_template.jsonc")

run_unsteady("unsteady_input_template.jsonc")