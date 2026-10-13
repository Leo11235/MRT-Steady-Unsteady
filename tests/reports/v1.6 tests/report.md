# Backend test report

Generated 2026-10-13 16:15:16. 132 passed, 0 failed, 132 total.

## Environment

| | |
|---|---|
| generated | 2026-10-13T16:15:15 |
| python | 3.13.1 |
| platform | Windows-11-10.0.26200-SP0 |
| cwd | C:\Users\leoam\Documents\Mostly VS Code\Git Files\MRT-Steady-Unsteady |
| numpy | 2.4.6 |
| scipy | 1.17.1 |
| matplotlib | 3.10.9 |
| rocketcea | 1.2.3 |
| pypropep | installed |
| json5 | 0.14.0 |
| app_version | 1.6 |
| git_commit | db8fae9 |
| git_branch | dev-branch |
| git_dirty | yes |

## All tests

### Steady (58 configs)

| result | test | outcome | expected | time |
|---|---|---|---|---|
| PASS | 00_fuel_mass_convergence_baseline | success | success | 3.0s |
| PASS | 01_parametric_baseline | success | success | 30.0s |
| PASS | 02_hotfire_baseline | success | success | 0.2s |
| PASS | 03_hotfire_alt_diameter_only | success | success | 0.2s |
| PASS | 04_hotfire_high_chamber_pressure | success | success | 0.2s |
| PASS | 05_hotfire_low_chamber_pressure | success | success | 0.2s |
| PASS | 06_hotfire_high_ox_flow | success | success | 0.2s |
| PASS | 07_hotfire_low_ox_flow | success | success | 0.2s |
| PASS | 08_hotfire_short_grain | success | success | 0.2s |
| PASS | 09_hotfire_long_grain | success | success | 0.2s |
| PASS | 10_hotfire_fail_both_alt_filled | validation_error | validation_error | 0.0s |
| PASS | 11_hotfire_fail_missing_ox_type | validation_error | validation_error | 0.0s |
| PASS | 12_convergence_high_apogee | success | success | 2.1s |
| PASS | 13_convergence_low_apogee | success | success | 2.2s |
| PASS | 14_convergence_impossible_apogee | success | success | 0.5s |
| PASS | 15_convergence_off_vertical_launch | success | success | 2.1s |
| PASS | 16_convergence_high_drag | success | success | 1.9s |
| PASS | 17_convergence_heavy_dry_mass | success | success | 1.5s |
| PASS | 18_convergence_light_dry_mass | success | success | 2.2s |
| PASS | 19_convergence_fail_missing_kinematics | validation_error | validation_error | 0.0s |
| PASS | 20_parametric_sweep_fuel_length | success | success | 17.5s |
| PASS | 21_parametric_sweep_ox_flow | success | success | 15.1s |
| PASS | 22_parametric_sweep_chamber_pressure | success | success | 15.8s |
| PASS | 23_parametric_sweep_two_vars | success | success | 24.2s |
| PASS | 24_parametric_single_point | success | success | 3.1s |
| PASS | 25_parametric_fail_low_gt_high | validation_error | validation_error | 0.0s |
| PASS | 26_parametric_fail_missing_step_size | validation_error | validation_error | 0.0s |
| PASS | 27_parametric_fail_zero_step_size | validation_error | validation_error | 0.0s |
| PASS | 28_units_output_mrt_convergence | success | success | 2.6s |
| PASS | 29_units_output_mrt_hotfire | success | success | 0.2s |
| PASS | 30_units_output_mrt_parametric | success | success | 35.0s |
| PASS | 31_units_output_defaults_to_mrt | success | success | 2.5s |
| PASS | 32_units_output_imp_is_a_no_op | success | success | 2.3s |
| PASS | 33_units_input_imperial_equivalent | success | success | 2.5s |
| PASS | 34_units_input_metric_mixed_bag | success | success | 2.4s |
| PASS | 35_convergence_tight_tolerance | success | success | 3.2s |
| PASS | 36_convergence_loose_tolerance | success | success | 1.0s |
| PASS | 37_convergence_min_port_radius_binds | success | success | 0.6s |
| PASS | 38_convergence_vertical_launch | success | success | 2.5s |
| PASS | 39_convergence_steep_launch_angle | success | success | 2.1s |
| PASS | 40_convergence_very_low_apogee | success | success | 2.5s |
| PASS | 41_hotfire_high_regression_constant | success | success | 0.2s |
| PASS | 42_hotfire_low_regression_constant | success | success | 0.2s |
| PASS | 43_hotfire_dense_fuel | success | success | 0.2s |
| PASS | 44_hotfire_light_fuel | success | success | 0.2s |
| PASS | 45_hotfire_tight_initial_port | success | success | 0.2s |
| PASS | 46_hotfire_wide_initial_port | success | success | 0.2s |
| PASS | 47_parametric_three_variables | success | success | 26.4s |
| PASS | 48_parametric_sweep_kinematics_variable | success | success | 14.3s |
| PASS | 49_parametric_sweep_dry_mass | success | success | 9.0s |
| PASS | 50_parametric_non_integer_step_count | success | success | 5.5s |
| PASS | 51_parametric_mixed_units_sweep | success | success | 63.4s |
| PASS | 52_parametric_two_point_sweep | success | success | 6.4s |
| PASS | 53_fail_missing_regression_exponent | validation_error | validation_error | 0.0s |
| PASS | 54_fail_hotfire_neither_alt_filled | validation_error | validation_error | 0.0s |
| PASS | 55_fail_unknown_simulation_type | validation_error | validation_error | 0.0s |
| PASS | 56_fail_impossible_grain_geometry | validation_error | validation_error | 0.0s |
| PASS | 58_parametric_all_variables | success | success | 373.3s |

### Unsteady (74 configs)

| result | test | outcome | expected | time |
|---|---|---|---|---|
| PASS | 00_baseline | success | success | 3.2s |
| PASS | 01_no_warnings | success | success | 3.2s |
| PASS | 02_graphs | success | success | 18.5s |
| PASS | 03_stall_luminor_verbatim | engine_abort | engine_abort | 0.7s |
| PASS | 04_stress_high_regression_rate | engine_abort | engine_abort | 1.0s |
| PASS | 05_stress_small_throat | success | success | 3.2s |
| PASS | 06_stress_near_burnthrough_grain | success | success | 4.0s |
| PASS | 07_stress_low_feed_pressure_loss | success | success | 3.8s |
| PASS | 08_stress_high_injector_area | success | success | 3.4s |
| PASS | 09_stress_low_ullage | success | success | 3.6s |
| PASS | 10_stress_short_burn | success | success | 2.5s |
| PASS | 11_stress_long_burn | success | success | 5.2s |
| PASS | 12_stress_instant_valve | success | success | 3.2s |
| PASS | 13_fail_missing_cv3_injector | validation_error | validation_error | 0.1s |
| PASS | 14_fail_cv4_both_alt_filled | validation_error | validation_error | 0.1s |
| PASS | 15_fail_cv1_alt_neither | validation_error | validation_error | 0.1s |
| PASS | 16_fail_inner_gt_outer | validation_error | validation_error | 0.1s |
| PASS | 17_valve_linear | success | success | 3.7s |
| PASS | 18_phase4a_burnthrough_in_gas_blowdown | success | success | 4.1s |
| PASS | 19_tank_via_length_branch | success | success | 3.3s |
| PASS | 20_chamber_via_diameter_branch | success | success | 4.4s |
| PASS | 21_fuel_limited_burnout | engine_abort | engine_abort | 1.4s |
| PASS | 22_fast_ignition | success | success | 3.5s |
| PASS | 23_slow_ignition | success | success | 3.9s |
| PASS | 24_reaches_landing | success | success | 3.2s |
| PASS | 25_off_vertical_launch | success | success | 2.8s |
| PASS | 26_high_altitude_launch | success | success | 4.0s |
| PASS | 27_warn_short_fuel_grain | success | success | 1.9s |
| PASS | 28_phase4a_burnthrough_thinner_web | success | success | 3.8s |
| PASS | 32_phase4_large_chamber_volume | success | success | 3.0s |
| PASS | 33_nozzle_area_ratio_near_unity | success | success | 4.0s |
| PASS | 35_nozzle_very_high_area_ratio | success | success | 2.9s |
| PASS | 36_nozzle_large_throat_low_chamber_pressure | success | success | 4.0s |
| PASS | 37_nozzle_sea_level_launch | success | success | 3.2s |
| PASS | 38_nozzle_very_high_launch_site | success | success | 3.8s |
| PASS | 39_nozzle_tiny_throat_high_pressure | success | success | 3.2s |
| PASS | 40_injector_near_zero_feed_loss | success | success | 3.6s |
| PASS | 41_injector_huge_feed_loss | success | success | 2.7s |
| PASS | 42_injector_feed_loss_near_tank_pressure | engine_abort | engine_abort | 1.5s |
| PASS | 43_injector_very_low_discharge_coefficient | success | success | 4.0s |
| PASS | 44_injector_four_large_holes | success | success | 4.5s |
| PASS | 45_injector_many_tiny_holes | success | success | 3.9s |
| PASS | 46_thrust_floor_disabled | success | success | 3.0s |
| PASS | 47_thrust_floor_aggressive | success | success | 2.9s |
| PASS | 48_k_amb_raised | success | success | 3.1s |
| PASS | 51_cea_probe_low_of_ratio | engine_abort | engine_abort | 1.2s |
| PASS | 52_cea_probe_low_chamber_pressure | success | success | 3.7s |
| PASS | 53_cea_probe_extreme_pressure_tiny_throat | success | success | 3.7s |
| PASS | 54_n2o_cold_tank_start | engine_abort | engine_abort | 0.4s |
| PASS | 55_n2o_near_critical_tank | success | success | 3.3s |
| PASS | 56_n2o_floor_via_deep_blowdown | success | success | 2.7s |
| PASS | 57_terminal_phase_timeout | engine_abort | engine_abort | 0.7s |
| PASS | 58_terminal_quench_during_ignition | engine_abort | engine_abort | 1.2s |
| PASS | 59_terminal_apogee_abort_probe | engine_abort | engine_abort | 2.0s |
| PASS | 60_terminal_metadata_present_on_success | success | success | 3.1s |
| PASS | 61_units_imperial_equivalent | success | success | 3.2s |
| PASS | 62_units_metric_mixed_bag | success | success | 3.2s |
| PASS | 63_units_temperature_celsius_only | success | success | 3.0s |
| PASS | 64_units_fail_unknown_unit_string | config_error | config_error | 0.2s |
| PASS | 65_units_imperial_alternate_branches | success | success | 3.2s |
| PASS | 66_solver_tight_tolerances | success | success | 9.4s |
| PASS | 67_solver_loose_tolerances | success | success | 2.2s |
| PASS | 68_solver_bdf_method | success | success | 5.0s |
| PASS | 69_solver_large_max_step | success | success | 9.0s |
| PASS | 70_warn_tight_fuel_port | success | success | 6.2s |
| PASS | 71_warn_high_ullage | success | success | 3.5s |
| PASS | 72_warn_low_regression_exponent | success | success | 1.7s |
| PASS | 73_warn_high_regression_exponent | engine_abort | engine_abort | 1.4s |
| PASS | 74_warn_several_at_once | success | success | 2.0s |
| PASS | 75_trajectory_vertical_launch | success | success | 3.5s |
| PASS | 76_trajectory_steep_off_vertical | success | success | 3.1s |
| PASS | 77_trajectory_very_high_drag | success | success | 2.9s |
| PASS | 78_trajectory_low_drag_light_vehicle | success | success | 4.2s |
| PASS | 79_trajectory_tiny_drogue_fast_descent | success | success | 3.5s |

## Timing outliers

| test | elapsed | median for kind |
|---|---|---|
| 01_parametric_baseline | 30.0s | 1.9s |
| 20_parametric_sweep_fuel_length | 17.5s | 1.9s |
| 22_parametric_sweep_chamber_pressure | 15.8s | 1.9s |
| 23_parametric_sweep_two_vars | 24.2s | 1.9s |
| 30_units_output_mrt_parametric | 35.0s | 1.9s |
| 47_parametric_three_variables | 26.4s | 1.9s |
| 51_parametric_mixed_units_sweep | 63.4s | 1.9s |
| 58_parametric_all_variables | 373.3s | 1.9s |

