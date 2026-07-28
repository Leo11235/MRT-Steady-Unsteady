"""Very small translation layer.

Design goals:
  - Zero runtime cost — one dict lookup at widget-build time.
  - Missing translations fall back gracefully to the English string,
    so a partial FR pass never crashes the UI.
  - Language choice persists in ui_settings.json under "language".

Scope:
  - We intentionally translate only high-visibility strings (page
    titles, button labels, section headers, status messages, error
    dialog text).  Individual physics-input labels ("Chamber pressure",
    "Fuel grain density") stay English — they're technical jargon that
    engineers use in both languages anyway, and translating them all
    would be a much bigger project.

Usage:
    from src.ui.app.services.i18n import t, set_language
    t("run_simulation")           # -> "Run simulation" or "Lancer la simulation"
    set_language("fr")            # persists to ui_settings.json
"""

from __future__ import annotations

from typing import Optional

from src.ui.app import settings as user_settings


LANGUAGES = ("en", "fr")
DEFAULT_LANGUAGE = "en"

LANGUAGE_DISPLAY = {
    "en": "English",
    "fr": "Français",
}


# ---------------------------------------------------------------------------
# Translation table
# key -> {language: string}
# Missing (key, lang) pairs fall back to the English entry, or to the
# key itself if there's no English entry either.
# ---------------------------------------------------------------------------
_STRINGS: dict[str, dict[str, str]] = {

    # ---- page titles ----
    "page.steady":            {"en": "Steady simulation",
                               "fr": "Simulation en régime permanent"},
    "page.unsteady":          {"en": "Unsteady simulation",
                               "fr": "Simulation en régime transitoire"},
    "page.steady_results":    {"en": "Steady simulation results",
                               "fr": "Résultats de simulation permanente"},
    "page.unsteady_results":  {"en": "Unsteady simulation results",
                               "fr": "Résultats de simulation transitoire"},
    "page.results_browser":   {"en": "Browse saved results",
                               "fr": "Résultats enregistrés"},
    # Shell uses "page.<page_key>" — the browser's key in shell.PAGES is
    # "results", so also register that alias.
    "page.results":           {"en": "Browse saved results",
                               "fr": "Résultats enregistrés"},
    "page.bug_report":        {"en": "Report a bug",
                               "fr": "Signaler un bogue"},
    "page.settings":          {"en": "Settings",
                               "fr": "Paramètres"},
    "page.loading":           {"en": "Running…",
                               "fr": "Exécution…"},

    # ---- main menu ----
    "menu.hero":              {"en": "Steady-Unsteady",
                               "fr": "Permanent-Transitoire"},
    "menu.subtitle":          {"en": "Hybrid Rocket Engine Simulator",
                               "fr": "Simulateur de moteur-fusée hybride"},
    "menu.steady":            {"en": "Steady",
                               "fr": "Permanent"},
    "menu.unsteady":          {"en": "Unsteady",
                               "fr": "Transitoire"},
    "menu.browse_results":    {"en": "Browse saved results…",
                               "fr": "Parcourir les résultats…"},
    "menu.report_bug":        {"en": "Report a bug",
                               "fr": "Signaler un bogue"},
    "menu.settings":          {"en": "Settings",
                               "fr": "Paramètres"},

    # ---- top-bar buttons ----
    "topbar.home":            {"en": "⌂  Home",
                               "fr": "⌂  Accueil"},
    "topbar.cancel":          {"en": "✕  Cancel",
                               "fr": "✕  Annuler"},
    "topbar.confirm_cancel":  {"en": "Confirm cancel",
                               "fr": "Confirmer l'annulation"},

    # ---- sidebar / actions ----
    "action.actions":         {"en": "Actions",
                               "fr": "Actions"},
    "action.graphs":          {"en": "Graphs",
                               "fr": "Graphiques"},
    "action.units":           {"en": "Units",
                               "fr": "Unités"},
    "help.units":             {"en": "SI: standard SI units (m, kg, Pa).  \n"
                                     "IMP: imperial units (ft, lbm, psi). \n"
                                     "MRT: McGill Rocket Team mix of SI and IMP, "
                                     "with inches for small lengths, ft for "
                                     "altitudes, and psi for pressures.",
                               "fr": "SI : unités SI standards (m, kg, Pa).  \n"
                                     "IMP : unités impériales (ft, lbm, psi).  \n"
                                     "MRT : mélange McGill Rocket Team. SI "
                                     "surtout, pouces pour petites longueurs, "
                                     "ft pour altitudes, psi pour pressions."},
    "action.run":             {"en": "Run simulation",
                               "fr": "Lancer la simulation"},
    "action.load_preset":     {"en": "Load preset…",
                               "fr": "Charger un préréglage…"},
    "action.save_preset":     {"en": "Save preset…",
                               "fr": "Enregistrer un préréglage…"},
    "action.recent_presets":  {"en": "Recent presets",
                               "fr": "Préréglages récents"},
    "action.more_presets":    {"en": "More presets…",
                               "fr": "Autres préréglages…"},
    "action.autosave":        {"en": "Auto-save inputs\nas new preset",
                               "fr": "Enregistrement auto\ncomme préréglage"},
    "action.copy":            {"en": "Copy to clipboard",
                               "fr": "Copier dans le presse-papiers"},
    "action.export_csv":      {"en": "Export to sheets (.csv)",
                               "fr": "Exporter en CSV"},
    "action.show_selected":   {"en": "Show select graphs",
                               "fr": "Afficher graphiques sélectionnés"},
    "action.show_all":        {"en": "Show all graphs",
                               "fr": "Afficher tous les graphiques"},

    # ---- filter / search ----
    "filter.placeholder":     {"en": "Filter rows…",
                               "fr": "Filtrer les lignes…"},

    # ---- graph picker ----
    "action.show_graphs":     {"en": "Show graphs…",
                               "fr": "Afficher les graphiques…"},
    "graphs.picker_title":    {"en": "Select graphs to display",
                               "fr": "Sélectionner les graphiques à afficher"},
    "graphs.picker_body":     {"en": "Tick the graphs you want. "
                                     "Each opens in its own matplotlib window.",
                               "fr": "Cochez les graphiques souhaités. "
                                     "Chacun s'ouvre dans sa propre fenêtre matplotlib."},
    "graphs.all":             {"en": "All",         "fr": "Tous"},
    "graphs.none":            {"en": "None",        "fr": "Aucun"},
    "graphs.cancel":          {"en": "Cancel",      "fr": "Annuler"},
    "graphs.show":            {"en": "Show",        "fr": "Afficher"},

    # Steady graph names (used in the picker)
    "graph.st.kinematics":    {"en": "Rocket kinematics (altitude, velocity, acceleration)",
                               "fr": "Cinématique (altitude, vitesse, accélération)"},
    "graph.st.thrust":        {"en": "Thrust curve",
                               "fr": "Courbe de poussée"},
    "graph.st.forces":        {"en": "Forces breakdown (thrust / drag / gravity)",
                               "fr": "Décomposition des forces (poussée / traînée / gravité)"},

    # Unsteady graph names — mirror the backend's toggle names.
    "graph.us.performance_panel":        {"en": "Performance panel (scorecard + tables)",
                                          "fr": "Panneau de performance"},
    "graph.us.events_warnings_panel":    {"en": "Events + warnings panel",
                                          "fr": "Événements et avertissements"},
    "graph.us.thrust_vs_time":           {"en": "Thrust vs. time",
                                          "fr": "Poussée vs. temps"},
    "graph.us.injector_mass_flow_vs_time":{"en": "Injector mass flow vs. time (burn only)",
                                          "fr": "Débit à l'injecteur vs. temps (combustion seulement)"},
    "graph.us.rocket_kinematics":        {"en": "Rocket kinematics",
                                          "fr": "Cinématique de la fusée"},
    "graph.us.of_ratio_vs_time":         {"en": "O/F ratio vs. time",
                                          "fr": "Rapport O/F vs. temps"},
    "graph.us.chamber_temperature_vs_time":{"en": "Chamber temperature vs. time",
                                          "fr": "Température chambre vs. temps"},
    "graph.us.tank_pressure_vs_time":    {"en": "Tank pressure vs. time",
                                          "fr": "Pression réservoir vs. temps"},
    "graph.us.tank_temperature_vs_time": {"en": "Tank temperature vs. time",
                                          "fr": "Température réservoir vs. temps"},
    "graph.us.chamber_pressure_vs_time": {"en": "Chamber pressure vs. time",
                                          "fr": "Pression chambre vs. temps"},
    "graph.us.oxidizer_inventory_vs_time":{"en": "Oxidizer inventory vs. time",
                                          "fr": "Inventaire oxydant vs. temps"},
    "graph.us.fuel_grain_state_vs_time": {"en": "Fuel grain state vs. time",
                                          "fr": "État du grain vs. temps"},
    "graph.us.injector_pressure_drop_vs_time":{"en": "Injector pressure drop vs. time",
                                          "fr": "Perte pression injecteur vs. temps"},
    "graph.us.nozzle_exit_conditions_vs_time":{"en": "Nozzle exit conditions vs. time",
                                          "fr": "Conditions à la sortie de tuyère vs. temps"},
    "graph.us.nozzle_flow_regime_vs_time":{"en": "Nozzle flow regime vs. time",
                                          "fr": "Régime d'écoulement tuyère vs. temps"},
    "graph.us.combustion_properties_vs_time":{"en": "Combustion properties vs. time",
                                          "fr": "Propriétés de combustion vs. temps"},
    "graph.us.ambient_atmosphere_vs_time":{"en": "Ambient atmosphere vs. time",
                                          "fr": "Atmosphère ambiante vs. temps"},
    "graph.us.isp_vs_time":              {"en": "Isp vs. time",
                                          "fr": "Isp vs. temps"},
    "graph.us.rocket_total_mass_vs_time":{"en": "Rocket total mass vs. time",
                                          "fr": "Masse totale vs. temps"},
    "graph.us.trajectory_map":           {"en": "Trajectory map (altitude vs. downrange)",
                                          "fr": "Carte de trajectoire"},
    "graph.us.of_vs_port_radius":        {"en": "O/F vs. port radius",
                                          "fr": "O/F vs. rayon du port"},
    "graph.us.thrust_vs_chamber_pressure":{"en": "Thrust vs. chamber pressure",
                                          "fr": "Poussée vs. pression chambre"},
    "graph.us.solver_step_size":         {"en": "Solver step size (diagnostic)",
                                          "fr": "Pas d'intégration (diagnostic)"},
    "graph.us.nan_map":                  {"en": "NaN map (diagnostic)",
                                          "fr": "Carte des NaN (diagnostic)"},
    "graph.us.mass_conservation_check":  {"en": "Mass conservation check",
                                          "fr": "Vérification conservation masse"},
    "graph.us.thrust_with_event_markers":{"en": "Thrust with event markers",
                                          "fr": "Poussée avec marqueurs d'événement"},
    "graph.us.rocket_cross_section":     {"en": "Rocket cross-section sketch",
                                          "fr": "Coupe de la fusée"},
    "graph.us.nozzle_profile":           {"en": "Nozzle profile sketch",
                                          "fr": "Profil de tuyère"},

    # ---- loading screen ----
    "loading.starting":       {"en": "Starting …",
                               "fr": "Démarrage…"},
    "loading.complete":       {"en": "Simulation complete.",
                               "fr": "Simulation terminée."},
    "loading.failed":         {"en": "Failed",
                               "fr": "Échec"},
    "loading.phase":          {"en": "Phase",
                               "fr": "Phase"},
    "loading.elapsed":        {"en": "elapsed",
                               "fr": "écoulés"},

    # ---- confirm dialogs ----
    "confirm.discard_title":  {"en": "Discard unsaved changes?",
                               "fr": "Annuler les modifications ?"},
    "confirm.discard_body":   {"en": "You have unsaved edits on this page. "
                                     "Return to Home anyway?",
                               "fr": "Cette page contient des modifications "
                                     "non enregistrées. Retourner à l'accueil "
                                     "quand même ?"},

    # ---- error popup ----
    "error.title":            {"en": "Error during simulation",
                               "fr": "Erreur pendant la simulation"},
    "error.body":             {"en": "Please verify all your inputs are "
                                     "correct, and run again.",
                               "fr": "Veuillez vérifier vos entrées et "
                                     "réessayer."},
    "error.back_steady":      {"en": "Back to Steady",
                               "fr": "Retour au régime permanent"},
    "error.back_unsteady":    {"en": "Back to Unsteady",
                               "fr": "Retour au régime transitoire"},
    "error.report_button":    {"en": "Report a bug",
                               "fr": "Signaler un bogue"},

    # ---- validation ----
    "validation.missing_title":   {"en": "Missing required fields",
                                   "fr": "Champs obligatoires manquants"},
    "validation.missing_body":    {"en": "Please fix the following before "
                                         "saving:",
                                   "fr": "Corrigez les points suivants avant "
                                         "d'enregistrer :"},
    "validation.cannot_run":      {"en": "Cannot run simulation",
                                   "fr": "Impossible de lancer la simulation"},
    "validation.cannot_run_body": {"en": "Please fix the following before "
                                         "running:",
                                   "fr": "Corrigez les points suivants avant "
                                         "de lancer :"},

    # ---- settings page ----
    "settings.title":              {"en": "User preferences",
                                    "fr": "Préférences utilisateur"},
    "settings.blurb":              {"en": "These settings persist between "
                                          "launches.\nThey live in "
                                          "user_data/ui_settings.json and are "
                                          "per-user (not committed to the repo).",
                                    "fr": "Ces réglages persistent entre les "
                                          "démarrages.\nIls sont stockés dans "
                                          "user_data/ui_settings.json (par "
                                          "utilisateur, non versionnés)."},
    "settings.default_units":      {"en": "Default output units",
                                    "fr": "Unités de sortie par défaut"},
    "settings.default_units_hint": {"en": "(this is what the Steady page's "
                                          "'Output units' dropdown starts on)",
                                    "fr": "(la valeur initiale du menu "
                                          "« Unités de sortie » de la page "
                                          "Permanent)"},
    "settings.language":           {"en": "Interface language",
                                    "fr": "Langue de l'interface"},
    "settings.shortcuts_header":   {"en": "Keyboard shortcuts",
                                    "fr": "Raccourcis clavier"},
    "settings.rebind":             {"en": "Rebind…",
                                    "fr": "Réassigner…"},
    "settings.press_key":          {"en": "Press the key combination …",
                                    "fr": "Appuyez sur la combinaison …"},
    "settings.save":               {"en": "Save",
                                    "fr": "Enregistrer"},
    "settings.reset":              {"en": "Reset all to defaults",
                                    "fr": "Réinitialiser aux valeurs par défaut"},
    "settings.cancel":             {"en": "Cancel",
                                    "fr": "Annuler"},
    "settings.saved":              {"en": "Saved to",
                                    "fr": "Enregistré dans"},

    # ---- shortcut action names (for the Settings rebind UI) ----
    "shortcut.run":                {"en": "Run simulation",
                                    "fr": "Lancer la simulation"},
    "shortcut.save":               {"en": "Save preset",
                                    "fr": "Enregistrer préréglage"},
    "shortcut.load":               {"en": "Load preset",
                                    "fr": "Charger préréglage"},
    "shortcut.cancel":             {"en": "Cancel run (double-press)",
                                    "fr": "Annuler l'exécution (double-appui)"},

    # ---- Settings — section headers ----
    "settings.section.language":   {"en": "Interface language",
                                    "fr": "Langue de l'interface"},
    "settings.section.units":      {"en": "Unit system",
                                    "fr": "Système d'unités"},
    "settings.section.keybinds":   {"en": "Keyboard shortcuts",
                                    "fr": "Raccourcis clavier"},

    # ---- Simulation tabs (steady + unsteady) ----
    "tab.sim_settings":            {"en": "Sim Settings",
                                    "fr": "Réglages"},
    "tab.oxidizer_fuel":           {"en": "Oxidizer & Fuel",
                                    "fr": "Oxydant et carburant"},
    "tab.rocket_body":             {"en": "Rocket Body",
                                    "fr": "Corps de la fusée"},
    "tab.tank":                    {"en": "Tank",       "fr": "Réservoir"},
    "tab.valve":                   {"en": "Valve",      "fr": "Vanne"},
    "tab.injector":                {"en": "Injector",   "fr": "Injecteur"},
    "tab.chamber":                 {"en": "Chamber",    "fr": "Chambre"},
    "tab.nozzle":                  {"en": "Nozzle",     "fr": "Tuyère"},

    # ---- Section headers inside sim pages ----
    "section.simulation":          {"en": "Simulation",
                                    "fr": "Simulation"},
    "section.combustion":          {"en": "Combustion",
                                    "fr": "Combustion"},
    "section.fuel_geometry":       {"en": "Fuel grain geometry",
                                    "fr": "Géométrie du grain"},
    "section.advanced":            {"en": "Advanced (propellant chemistry & regression law)",
                                    "fr": "Avancé (chimie propergol et régression)"},
    "section.rocket":              {"en": "Rocket",
                                    "fr": "Fusée"},
    "section.mission":             {"en": "Mission",
                                    "fr": "Mission"},
    "section.model":               {"en": "Model",
                                    "fr": "Modèle"},
    "section.inputs":              {"en": "Inputs",
                                    "fr": "Entrées"},
    "section.output":              {"en": "Output",
                                    "fr": "Sortie"},
    "section.parametric":          {"en": "Parametric Study Settings",
                                    "fr": "Réglages d'étude paramétrique"},

    # ---- Sim Settings labels ----
    "label.sim_name":              {"en": "Simulation name",
                                    "fr": "Nom de la simulation"},
    "label.sim_name_placeholder":  {"en": "(optional; used for the saved file name)",
                                    "fr": "(optionnel ; utilisé comme nom de fichier)"},
    "label.sim_type":              {"en": "Simulation type",
                                    "fr": "Type de simulation"},
    "label.output_units":          {"en": "Output units",
                                    "fr": "Unités de sortie"},
    "label.physics_model":         {"en": "Physics model",
                                    "fr": "Modèle physique"},
    "checkbox.save_data":          {"en": "Save simulation data to JSON",
                                    "fr": "Enregistrer les données en JSON"},
    "checkbox.warnings":           {"en": "Generate warnings report",
                                    "fr": "Générer un rapport d'avertissements"},
    "checkbox.save_pdf":           {"en": "Save graphs as PDF",
                                    "fr": "Enregistrer les graphiques en PDF"},
    "checkbox.save_png":           {"en": "Save graphs as PNG",
                                    "fr": "Enregistrer les graphiques en PNG"},
    "advanced.click_to_edit":      {"en": "click to edit",
                                    "fr": "cliquer pour modifier"},

    # ---- Simulation-type dropdown ----
    "simtype.hotfire":             {"en": "Hotfire",
                                    "fr": "Hotfire"},
    "simtype.convergence":         {"en": "Fuel mass convergence",
                                    "fr": "Convergence de masse de carburant"},
    "simtype.parametric":          {"en": "Parametric study",
                                    "fr": "Étude paramétrique"},

    # ---- Parametric-list ----
    "param.blurb":                 {"en": "Add one or more variables to sweep; each is given a "
                                          "low/high/step. Parametrized variables are hidden from "
                                          "the other tabs so you can't set them to a single value "
                                          "at the same time.",
                                    "fr": "Ajoutez une ou plusieurs variables à balayer ; "
                                          "chacune reçoit une valeur basse/haute/pas. Les "
                                          "variables paramétrées sont masquées dans les autres "
                                          "onglets pour éviter les doubles saisies."},
    "param.add":                   {"en": "➕  Add parameter",
                                    "fr": "➕  Ajouter une variable"},
    "param.none_left":             {"en": "(all variables already added)",
                                    "fr": "(toutes les variables ont été ajoutées)"},
    "param.low":                   {"en": "Low end",   "fr": "Valeur basse"},
    "param.high":                  {"en": "High end",  "fr": "Valeur haute"},
    "param.step":                  {"en": "Step size", "fr": "Pas"},

    # ---- Rocket Body tab placeholder for hotfire ----
    "rocket_body.not_used":        {"en": "Rocket Body inputs aren't used for a Hotfire simulation.",
                                    "fr": "Les entrées Corps de la fusée ne sont pas utilisées "
                                          "pour un Hotfire."},

    # ---- Bug-report page ----
    "bug.hero":                    {"en": "Tell us what went wrong.",
                                    "fr": "Dites-nous ce qui s'est mal passé."},
    "bug.blurb":                   {"en": "Reports go straight to the MRT Steady-Unsteady bug "
                                          "tracker. You don't have to do anything after "
                                          "clicking Send.",
                                    "fr": "Les rapports sont envoyés directement à l'équipe. "
                                          "Vous n'avez rien d'autre à faire après avoir cliqué "
                                          "sur Envoyer."},
    "bug.title_label":             {"en": "Title (optional)",
                                    "fr": "Titre (optionnel)"},
    "bug.title_placeholder":       {"en": "One-line summary",
                                    "fr": "Résumé en une ligne"},
    "bug.desc_label":              {"en": "Description of the issue",
                                    "fr": "Description du problème"},
    "bug.send":                    {"en": "Send report",
                                    "fr": "Envoyer le rapport"},
    "bug.sending":                 {"en": "Sending…",
                                    "fr": "Envoi…"},
    "bug.sent":                    {"en": "Sent ✓",
                                    "fr": "Envoyé ✓"},
    "bug.try_again":               {"en": "Try again",
                                    "fr": "Réessayer"},
    "bug.copy":                    {"en": "Copy report to clipboard",
                                    "fr": "Copier le rapport"},
    "bug.return_home":             {"en": "Return to home",
                                    "fr": "Retour à l'accueil"},
    "bug.status.empty":            {"en": "Please write a description of the issue.",
                                    "fr": "Veuillez rédiger une description."},
    "bug.status.copied":           {"en": "Copied. Paste into an email, chat, or GitHub issue.",
                                    "fr": "Copié. Collez dans un courriel, chat ou issue GitHub."},
    "bug.status.success":          {"en": "Report sent — thank you!",
                                    "fr": "Rapport envoyé — merci !"},
    "bug.status.error_send":       {"en": "Couldn't send the report. Copy it below and "
                                          "pass it on by hand.",
                                    "fr": "Impossible d'envoyer le rapport. Copiez-le et "
                                          "transmettez-le manuellement."},

    # ---- Results Browser ----
    "browser.list_header":         {"en": "Saved runs (newest first)",
                                    "fr": "Simulations enregistrées (plus récentes en premier)"},
    "browser.empty":               {"en": "No saved runs found in\nuser_data/simulation_results/",
                                    "fr": "Aucune simulation trouvée dans\nuser_data/simulation_results/"},
    "browser.no_selection":        {"en": "(no run selected)",
                                    "fr": "(aucune simulation sélectionnée)"},
    "browser.open":                {"en": "Open results",
                                    "fr": "Ouvrir les résultats"},
    "browser.size_kib":            {"en": "size",
                                    "fr": "taille"},
    "browser.section_steady":      {"en": "Steady runs",
                                    "fr": "Simulations permanentes"},
    "browser.section_unsteady":    {"en": "Unsteady runs",
                                    "fr": "Simulations transitoires"},
    "browser.section_empty":       {"en": "(none yet)",
                                    "fr": "(aucune pour l'instant)"},
    "browser.rename":              {"en": "Rename…",
                                    "fr": "Renommer…"},
    "browser.rename_title":        {"en": "Rename result file",
                                    "fr": "Renommer le fichier"},
    "browser.rename_prompt":       {"en": "New name (without extension):",
                                    "fr": "Nouveau nom (sans extension) :"},
    "browser.rename_invalid":      {"en": "Name can't be empty.",
                                    "fr": "Le nom ne peut pas être vide."},
    "browser.rename_exists":       {"en": "A file with that name already exists.",
                                    "fr": "Un fichier portant ce nom existe déjà."},
    "browser.renamed_to":          {"en": "Renamed to",
                                    "fr": "Renommé en"},
    "browser.delete":              {"en": "Delete",
                                    "fr": "Supprimer"},
    "browser.confirm_delete":      {"en": "Confirm delete",
                                    "fr": "Confirmer la suppression"},
    "browser.deleted":             {"en": "Deleted",
                                    "fr": "Supprimé"},

    # ---- Results-page section headers ----
    "results.rocket_inputs":       {"en": "Rocket inputs",
                                    "fr": "Entrées de la fusée"},
    "results.sim_settings":        {"en": "Simulation settings",
                                    "fr": "Réglages de simulation"},
    "results.sim_outputs":         {"en": "Simulation outputs (rocket_parameters)",
                                    "fr": "Sorties (rocket_parameters)"},
    "results.ascent_summary":      {"en": "Ascent summary",
                                    "fr": "Résumé de l'ascension"},
    "results.parametric_summary":  {"en": "Parametric study summary",
                                    "fr": "Résumé de l'étude paramétrique"},
    "results.metadata":            {"en": "Run metadata",
                                    "fr": "Métadonnées"},
    "results.rocket_metadata":     {"en": "Rocket-inputs metadata",
                                    "fr": "Métadonnées d'entrées"},
    "results.file":                {"en": "File",
                                    "fr": "Fichier"},
    "results.overall_perf":        {"en": "Overall performance",
                                    "fr": "Performance globale"},
    "results.no_overall":          {"en": "No overall-performance block in this file.",
                                    "fr": "Pas de bloc « performance globale » dans ce fichier."},
    "results.no_phase":            {"en": "No per-phase metrics in this file.",
                                    "fr": "Pas de métriques par phase dans ce fichier."},
    "results.per_phase":           {"en": "Per-phase metrics",
                                    "fr": "Métriques par phase"},
    "results.warnings_disabled":   {"en": "Warnings system was disabled for this run.",
                                    "fr": "Le système d'avertissements était désactivé."},
    "results.overall_level":       {"en": "Overall level",
                                    "fr": "Niveau global"},
    "results.no_warnings":         {"en": "No warnings triggered.",
                                    "fr": "Aucun avertissement déclenché."},
    "results.initial_conditions":  {"en": "Initial conditions",
                                    "fr": "Conditions initiales"},

    # CV pretty names for the Rocket-inputs tab
    "cv.tank":                     {"en": "Tank (CV1)",
                                    "fr": "Réservoir (CV1)"},
    "cv.valve":                    {"en": "Valve (CV2)",
                                    "fr": "Vanne (CV2)"},
    "cv.injector":                 {"en": "Injector (CV3)",
                                    "fr": "Injecteur (CV3)"},
    "cv.chamber":                  {"en": "Chamber (CV4)",
                                    "fr": "Chambre (CV4)"},
    "cv.nozzle":                   {"en": "Nozzle (CV5)",
                                    "fr": "Tuyère (CV5)"},
    "cv.trajectory":               {"en": "Trajectory (CV6)",
                                    "fr": "Trajectoire (CV6)"},
}


# ---------------------------------------------------------------------------
# Current language state
# ---------------------------------------------------------------------------

_current_lang: str = DEFAULT_LANGUAGE


def _init_from_settings() -> None:
    global _current_lang
    val = user_settings.get("language", DEFAULT_LANGUAGE)
    if isinstance(val, str) and val in LANGUAGES:
        _current_lang = val


def get_language() -> str:
    return _current_lang


def set_language(lang: str) -> None:
    """Change the current language and persist to ui_settings.json."""
    global _current_lang
    if lang not in LANGUAGES:
        raise ValueError(f"unknown language: {lang!r}")
    _current_lang = lang
    s = user_settings.load_settings()
    s["language"] = lang
    user_settings.save_settings(s)


def t(key: str, lang: Optional[str] = None) -> str:
    """Look up a string.  If the (key, lang) pair is missing, fall back
    to English; if English is missing too, fall back to the key itself
    so the developer notices."""
    L = lang or _current_lang
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(L) or entry.get("en") or key


# initialise on import
_init_from_settings()
