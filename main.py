# STEADY
#from src.backend.steady.steady_main import run_steady
#run_steady("steady_input_template.jsonc")


# UNSTEADY
from src.backend.unsteady.engine.phase_runner import run_unsteady
from src.backend.unsteady.analysis.unsteady_results import unsteady_results
# run_unsteady("unsteady_input_template.jsonc")

# see results of most recent sim (without running the simulation):
unsteady_results(
    display_graphs = True,
    save_to_pdf = False,
    save_to_png = False
)