# MRT Steady-Unsteady User Manual

This guide is intended for those who want to use the MRT Steady-Unsteady program via the user interface. To run directly in the backend or make your own modifications to the program, see the [`Developer Manual`](https://github.com/Leo11235/MRT-Steady-Unsteady/blob/main/docs/developer_manual.md). 


## Contents

1. [Introduction](#1-Introduction)
2. [Installation](#2-Installation)
3. [Demonstration](#3-Demonstration)
4. [Steady](#4-Steady)
5. [Unsteady](#5-Unsteady)
6. [Unit systems](#6-Unit-systems)
7. [Warning system](#7-Warning-system)
8. [Program limitations](#8-Program-limitations)


---

## 1. Introduction

Every hot fire costs money and long days at the test site. Consequently, it is only possible to have a few per design cycle. The MRT Steady-Unsteady program is a custom, in-house tool that helps propulsion engineers iterate and compare engine designs. 

The program's inner workings are kept deliberately simple: quasi-steady thermodynamics, a one-dimensional fuel grain, a well-mixed chamber, a point-mass trajectory. Enough to compare and rank designs. The code assumes the engine is a hybrid powered by N<sub>2</sub>O and eicosane. 

As the name suggests, the program is split into its "Steady" and "Unsteady" components. Steady holds one operating point for the whole burn: constant flow, constant chamber pressure, constant thrust. These simulations are wildly optimistic, but are cheap enough to sweep hundreds of designs in minutes. Steady's `parametric study` simulation type does just that by taking in ranges of inputs such as chamber pressure and rate of N<sub>2</sub>O flow through the injector. 

Unsteady more accurately predicts the engine's burn parameters and final apogee, alebit at the cost of higher granularity and more inputs demanded to run the program. 

The recommended workflow is to first run a steady parametric study to decide rough fuel and nozzle geometry, then unsteady to see a better estimate of what that model actually does. Unsteady models typically have lower apogee for the same inputs. 

--- 

## 2. Installation

Download the latest [`MRT-Steady-Unsteady-Setup.exe`](https://github.com/Leo11235/MRT-Steady-Unsteady/releases) from the GitHub releases page and run it. It removes an older version first while preserving your past configs and runs. Files will be stored in `%APPDATA%\MRT-Steady-Unsteady\`.

---

## 3. Demonstration

1. Open the program and click **Steady** or **Unsteady**. This will take you to the inputs screen for either program.
2. Click **Load Preset** and open one of the files. Once you have opened one, it will appear in the **Recent Presets** dropdown. For Steady you should see `steady_example.jsonc` and `steady_parametric_example.jsonc`; for Unsteady you should see `unsteady_example.jsonc`. 
3. Click **Run Simulation** or press Ctrl+R. 
4. Explore the results page. You will have the option of generating graphs or saving output data. 
5. Go black to the inputs screen, select the same preset, and now change one of the inputs. Run the program again, and notice which outputs are different. 

---

## 4. Steady

<!---should include steady description--->

<details>
  <summary><h3>Steady inputs</h3></summary>
<table width="100%">
  <thead>
    <tr>
      <th>Input name</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
    <tr><th colspan="2" align="center">Simulation settings</th></tr>
    <tr>
      <td>Simulation name</td>
      <td>The name under which the config file (if "Auto-save inputs as new preset") and simulation file will be saved. If no name is given, the config and simulation file will instead be named <code>&lt;YYYY-MM-DD-HH-MM-SS&gt;.jsonc</code>.</td>
    </tr>
    <tr>
      <td>Simulation type</td>
      <td><b>Hotfire</b>: Only constant thrust and burntime are computed, with no rocket flight or apogee. <br /><b>Fuel mass convergence</b>: A constant thrust and burntime are computed, following which a rocket flight and final apogee are estimated. <br /><b>Parametric study</b>: Takes in ranges of inputs such as chamber pressure and rate of N<sub>2</sub>O flow through the injector. Chains together many fuel mass convergence simulations to visualize how a rocket will perform given the slight difference between each one. Useful to find a design point for unsteady.</td>
    </tr>
    <tr>
      <td>Description</td>
      <td>A description of the rocket config.</td>
    </tr>
    <tr><th colspan="2" align="center">Oxidizer &amp; Fuel</th></tr>
    <tr>
      <td>Oxidizer mass flow rate</td>
      <td>How much N<sub>2</sub>O passes from the tank through the feed system and into the combustion chamber each second. Typically 1-5 kg/s for MRT rockets.</td>
    </tr>
    <tr>
      <td>Chamber pressure</td>
      <td>Combustion chamber's stagnation pressure. Typically 400-800 psi.</td>
    </tr>
    <tr>
      <td>Fuel external diameter</td>
      <td>Outer diameter of the fuel grain, set by the inner bore of the chamber case. Typically 3-8 in.</td>
    </tr>
    <tr>
      <td>Fuel length</td>
      <td>Length of the fuel grain. Typically 20-30 in. Below 20 in the 1D regression model starts to lose accuracy and the program will warn you.</td>
    </tr>
    <tr>
      <td>Fuel grain density*</td>
      <td>Bulk density of the cast fuel. Paraffin is around 900 kg/m<sup>3</sup>.</td>
    </tr>
    <tr>
      <td>Regression coefficient (a)*</td>
      <td>The <code>a</code> in <code>r_dot = a·G_ox^n</code>. <br>While <code>a</code>'s true units are <code>L<sup>1+2n</sup>·M<sup>−n</sup>·T<sup>n−1</sup></code>, this <code>n</code>-dependence is clunky. (At the default <code>n = 0.555</code> that works out to m<sup>2.11</sup>·kg<sup>−0.555</sup>·s<sup>−0.445</sup>.) The convention is to leave <code>n</code> implicit and use a rate unit paired with a flux unit. The default of 0.132 in  <code>(mm/s)/(kg/m^2/s)^n </code> units is recommended. 
    </tr>
    <tr>
      <td>Regression exponent (n)*</td>
      <td>The <code>n</code> in <code>r_dot = a·G^n</code>. Around 0.555 for paraffin with N<sub>2</sub>O.</td>
    </tr>
    <tr>
      <td>Liquid oxidizer*</td>
      <td>Names the oxidizer species the program looks up in its PROPEP combustion tables. Currently, only <code>NITROUS OXIDE</code> is available.</td>
    </tr>
    <tr>
      <td>Solid fuel*</td>
      <td>Names the fuel species looked up in the same tables. Currently, only <code>EICOSANE (PARAFFIN)</code> is available. </td>
    </tr>
    <tr><th colspan="2" align="center">Hotfire only</th></tr>
    <tr>
      <td>Initial internal fuel diameter</td>
      <td>Diameter of the bore running down the centre of the fuel grain at t=0. Fill this <b>or</b> the fuel mass</td>
    </tr>
    <tr>
      <td>Fuel mass</td>
      <td>Total mass of solid fuel. Fill this <b>or</b> the initial port diameter.</td>
    </tr>
    <tr><th colspan="2" align="center">Rocket body (not used by hotfire)</th></tr>
    <tr>
      <td>Dry mass</td>
      <td>Mass of the rocket carrying no propellant: no oxidizer and no fuel grain. Typically 50-100 kg.</td>
    </tr>
    <tr>
      <td>Rocket external diameter</td>
      <td>Maximum airframe outer diameter, which sets the frontal area used for drag. Typically 6-8 in.</td>
    </tr>
    <tr>
      <td>Drag coefficient</td>
      <td>Rocket drag coefficient; constant for the entire flight. Usually around 0.5-0.7 for amateur rockets.</td>
    </tr>
    <tr>
      <td>Target apogee</td>
      <td>The altitude the fuel mass convergence solver iterates toward. IREC and Launch Canada entries usually aim for 10,000 - 30,000 ft.</td>
    </tr>
    <tr>
      <td>Launch site altitude</td>
      <td>Elevation of the pad above sea level, which sets the air density and nozzle backpressure the flight starts at. Usually 1,000 - 1,300 ft.</td>
    </tr>
    <tr>
      <td>Launch angle</td>
      <td>Rail angle measured from vertical (0° is straight up). Typically 5-10°.</td>
    </tr>
    <tr><th colspan="2" align="center">Parametric study</th></tr>
    <tr>
      <td>Low end</td>
      <td>First value in the swept range for the selected variable.</td>
    </tr>
    <tr>
      <td>High end</td>
      <td>Last value in the range. Must be above the low end.</td>
    </tr>
    <tr>
      <td>Step size</td>
      <td>Increment between runs. </br>Warning: the total number of simulations is every variable's step count multiplied together, so 3+ dimensional parametrizations tend to have long run times.</td>
    </tr>
  </tbody>
</table>

\* ≡ The preset value comes from research and does not depend on specific rocket configs. Unless you know what you're doing, don't touch it. 

</details>





---

## 5. Unsteady

<!---should include unsteady description--->

<details>
  <summary><h3>Unsteady inputs</h3></summary>
<table width="100%">
  <thead>
    <tr>
      <th>Input name</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
    <tr><th colspan="2" align="center">Simulation settings</th></tr>
    <tr>
      <td>Simulation name</td>
      <td>The name under which the config file (if "Auto-save inputs as new preset") and results folder will be saved. If no name is given, both are instead named <code>&lt;YYYY-MM-DD-HH-MM-SS&gt;</code>.</td>
    </tr>
    <tr>
      <td>Description</td>
      <td>A description of the rocket config.</td>
    </tr>
    <tr>
      <td>Collect warnings</td>
      <td>Whether the run records physics warnings about the inputs and about what happened during the burn. Turning it off may marginally improve performance, but will disable detection of potential physics problems during the run. </td>
    </tr>
    <tr>
      <td>Generate PDF report</td>
      <td>Writes <code>run_report.pdf</code> into the run folder, holding every input, every output, the warnings and all graphs. Adds an extra ~30s of runtime. Generating one from the results page is recommended. </td>
    </tr>
    <tr>
      <td>Save graphs as PNGs</td>
      <td>Writes every graph as a separate PNG into the run folder. Adds an extra ~30s of runtime (overlapping with PDF report generation). Generating from the results page is recommended. </td>
    </tr>
    <tr><th colspan="2" align="center">Tank</th></tr>
    <tr>
      <td>Physics model: Saturated equilibrium</td>
      <td>Treats the tank contents as liquid and vapour N<sub>2</sub>O in constant phase equilibrium. Tank pressure follows the saturation curve at the current temperature, so the tank self-pressurizes and cools as it drains. The switch from liquid to vapour-only blowdown is handled automatically.</td>
    </tr>
    <tr>
      <td>Internal diameter</td>
      <td>Inner diameter of the oxidizer tank.</td>
    </tr>
    <tr>
      <td>Initial temperature</td>
      <td>N<sub>2</sub>O temperature at ignition. This sets tank pressure through the saturation curve; a warm tank on a hot pad will behave significantly differently from a cold but otherwise identical one. Typically 15-30°C unless you're at the testsite in -20°C weather.</td>
    </tr>
    <tr>
      <td>Oxidizer mass</td>
      <td>Total N<sub>2</sub>O loaded into the tank. Typically 10-40 kg.</td>
    </tr>
    <tr>
      <td>Dip tube external diameter</td>
      <td>Outer diameter of the dip tube, which displaces tank volume.</td>
    </tr>
    <tr>
      <td>Dip tube internal diameter</td>
      <td>Flow diameter through the dip tube.</td>
    </tr>
    <tr>
      <td>Dip tube length</td>
      <td>Length of the dip tube, measured down from the top of the tank.</td>
    </tr>
    <tr>
      <td>Ullage fraction</td>
      <td>Fraction of tank volume that is vapour at t=0, from 0 to 1. Physics innacuracies may arise below 0.10. Fill this <b>or</b> the internal length</td>
    </tr>
    <tr>
      <td>Internal length</td>
      <td>Internal length of the tank including its end caps. Fill this <b>or</b> the ullage fraction.</td>
    </tr>
    <tr><th colspan="2" align="center">Valve</th></tr>
    <tr>
      <td>Physics model: Instant</td>
      <td>The valve is fully open at t=0, with no opening transient at all. </td>
    </tr>
    <tr>
      <td>Physics model: Linear</td>
      <td>The valve opens linearly from closed to fully open over the time constant.</td>
    </tr>
    <tr>
      <td>Physics model: Sigmoid</td>
      <td>The valve opens along a logistic curve centred on the half-time. Most realistic model, but a rocket's behavior will usually be very similar regardless of the valve model used.</td>
    </tr>
    <tr>
      <td>Time constant</td>
      <td>How long the linear valve takes to go from closed to fully open. Used by the linear model only.</td>
    </tr>
    <tr>
      <td>Sigmoid half time</td>
      <td>Time at which the sigmoid valve reaches 50% open.</td>
    </tr>
    <tr>
      <td>Sigmoid steepness</td>
      <td>How sharp the opening transition is. High values approach a step; low values stretch the ramp out.</td>
    </tr>
    <tr><th colspan="2" align="center">Injector</th></tr>
    <tr>
      <td>Physics model: SPI</td>
      <td>Single-phase incompressible; treats the upstream N<sub>2</sub>O as pure liquid across the injector, which holds while the tank still has liquid in it. Once the tank goes vapour-only the model falls back to a choked-flow relation.</td>
    </tr>
    <tr>
      <td>Discharge coefficient</td>
      <td>Injector plate discharge coefficient. Typically 0.6-0.85, but should be measured rather than assumed.</td>
    </tr>
    <tr>
      <td>Number of holes</td>
      <td>Total orifice count in the injector plate.</td>
    </tr>
    <tr>
      <td>Hole diameter</td>
      <td>Diameter of a single orifice. Typically 1-2 mm.</td>
    </tr>
    <tr>
      <td>Feed pressure loss</td>
      <td>Static pressure lost upstream of the injector, across the feed lines and the main valve. Typically 20-60 psi.</td>
    </tr>
    <tr><th colspan="2" align="center">Chamber</th></tr>
    <tr>
      <td>Physics model: 0D quasi-steady</td>
      <td>Treats the chamber as one well-mixed control volume at instantaneous chemical equilibrium. Combustion properties come from NASA CEA at the current pressure and O/F, and fuel regresses radially as <code>r_dot = a·G^n</code>. Pre- and post-chamber volumes add gas storage that damps pressure transients.</td>
    </tr>
    <tr>
      <td>Fuel length</td>
      <td>Length of the fuel grain. Typically 20-30 in. Below 20 in the 1D regression model starts to lose accuracy and the program will warn you.</td>
    </tr>
    <tr>
      <td>Fuel external diameter</td>
      <td>Outer diameter of the fuel grain. Typically 3-8 in.</td>
    </tr>
    <tr>
      <td>Pre-chamber diameter</td>
      <td>Diameter of the empty volume upstream of the fuel grain.</td>
    </tr>
    <tr>
      <td>Pre-chamber length</td>
      <td>Length of that same volume. Together with the diameter it sets the pre-chamber volume, which is gas storage that damps the ignition transient. A chamber with almost none of it is stiffer and harder to integrate.</td>
    </tr>
    <tr>
      <td>Post-chamber diameter</td>
      <td>Diameter of the empty volume between the end of the grain and the nozzle throat.</td>
    </tr>
    <tr>
      <td>Post-chamber length</td>
      <td>Length of that same volume. Serves a damping role, same as the pre-chamber.</td>
    </tr>
    <tr>
      <td>Fuel mass</td>
      <td>Total solid fuel loaded. Fill this <b>or</b> the fuel internal diameter.</td>
    </tr>
    <tr>
      <td>Fuel internal diameter</td>
      <td>Initial bore through the middle of the grain. Fill this <b>or</b> the fuel mass.</td>
    </tr>
    <tr>
      <td>Fuel density*</td>
      <td>Bulk density of the cast fuel. Paraffin is around 900 kg/m<sup>3</sup>.</td>
    </tr>
    <tr>
      <td>Regression coefficient (a)*</td>
      <td>The <code>a</code> in <code>r_dot = a·G_ox^n</code>. <br>While <code>a</code>'s true units are <code>L<sup>1+2n</sup>·M<sup>−n</sup>·T<sup>n−1</sup></code>, this <code>n</code>-dependence is clunky. (At the default <code>n = 0.555</code> that works out to m<sup>2.11</sup>·kg<sup>−0.555</sup>·s<sup>−0.445</sup>.) The convention is to leave <code>n</code> implicit and use a rate unit paired with a flux unit. The default of 0.132 in  <code>(mm/s)/(kg/m^2/s)^n </code> units is recommended. 
    </tr>
    <tr>
      <td>Regression exponent (n)*</td>
      <td>The <code>n</code> in <code>r_dot = a·G^n</code>. Around 0.555 for paraffin with N<sub>2</sub>O.</td>
    </tr>
    <tr>
      <td>C* efficiency</td>
      <td>Dimensionless fraction of the theoretical characteristic velocity the chamber actually delivers, from 0 to 1. Typically around 0.85-0.95.</td>
    </tr>
    <tr><th colspan="2" align="center">Nozzle</th></tr>
    <tr>
      <td>Physics model: 1D frozen</td>
      <td>One-dimensional isentropic expansion with frozen chemistry. The exhaust composition is fixed at the throat and does not recombine downstream. Detects under-expanded, ideal and over-expanded flow, including separation in heavily over-expanded cases.</td>
    </tr>
    <tr>
      <td>Throat diameter</td>
      <td>Sets the chamber pressure that a given mass flow produces. Most sensitive input in the program. Typically 1-1.5 in.</td>
    </tr>
    <tr>
      <td>Exit diameter</td>
      <td>Nozzle exit plane diameter. With the throat it fixes the expansion ratio, and in turn the altitude the nozzle is best matched to. Typically 4-8 times the throat diameter.</td>
    </tr>
    <tr><th colspan="2" align="center">Rocket body</th></tr>
    <tr>
      <td>Physics model: 2-DOF</td>
      <td>Two-degree-of-freedom point mass, vertical and downrange. Uses a fixed drag coefficient times frontal area, and altitude-dependent atmosphere density and gravity. Drogue deploys at apogee, main at the AGL altitude you specify.</td>
    </tr>
    <tr>
      <td>Dry mass</td>
      <td>Mass of the rocket carrying no propellant.</td>
    </tr>
    <tr>
      <td>Drag coefficient</td>
      <td>Rocket drag coefficient; constant for the entire flight. Usually around 0.5-0.7 for amateur rockets.</td>
    </tr>
    <tr>
      <td>Outer diameter</td>
      <td>Maximum airframe outer diameter. Typically 6-8 in.</td>
    </tr>
    <tr>
      <td>Launch angle</td>
      <td>Rail angle measured from vertical (0° is straight up). Typically 5-10°.</td>
    </tr>
    <tr>
      <td>Drogue parachute drag coefficient</td>
      <td>Drag coefficient of the drogue parachute. Around 1.2.</td>
    </tr>
    <tr>
      <td>Drogue parachute diameter</td>
      <td>The drogue deploys automatically at apogee.</td>
    </tr>
    <tr>
      <td>Main parachute deployment altitude AGL</td>
      <td>Height above the ground at which the main deploys. Typically 1000-1500 ft.</td>
    </tr>
    <tr>
      <td>Main parachute drag coefficient</td>
      <td>Drag coefficient of the main canopy. Around 1.5.</td>
    </tr>
    <tr>
      <td>Main parachute diameter</td>
      <td>Together with its drag coefficient, sets the landing speed.</td>
    </tr>
    <tr>
      <td>Launch site altitude ASL</td>
      <td>Elevation of the launch pad above sea level. Sets the air density and nozzle backpressure at t=0.</td>
    </tr>
  </tbody>
</table>

\* ≡ The preset value comes from research and does not depend on specific rocket configs. Unless you know what you're doing, don't touch it. 

</details>


### End of a run

Every unsteady run records a terminal state, visible in the results.

| Terminal state | What it means |
|---|---|
| Success, landed | Nominal outcome: burn, coast, drogue, main, touchdown all happened successfully. |
| Liquid quench | The solid grain ran out while liquid oxidizer was still flowing. The program stops rather than modelling it. Lengthen the grain or load less oxidizer. |
| Phase timeout | A flight phase ran past its time budget without transitioning. |
| Failed to launch | The rocket never gained altitude. Thrust-to-weight was never enough to lift it, so the apogee and recovery figures describe a rocket that did not fly. |
| Apogee abort | The trajectory reached apogee while the burn was still ongoing. |


---

## 6. Unit systems

The program supports three unit types: International system (SI), Imperial units (IMP), and McGill Rocket Team units (MRT). The latter is a mix of SI and IMP catered to the preference of Montreal's finest engineers. The table below shows key default units in each system. 

| System | Hardware | Altitudes | Pressure | Mass | Temperature |
|---|---|---|---|---|---|
| **SI** | cm | m | kPa | kg | K |
| **MRT** | in | ft | psi | kg | K |
| **IMP** | in | ft | psi | lb | °F |

Every numeric input has its own unit dropdown, allowing for mixing of units within a configuration. The results pages have a `Units` button in which all values, graphs, and reports are displayed. The settings page also allows setting a preffered default unit system to work in. 

---

## 7. Warning system

Both Steady and Unsteady have an initialization warning system which alert the user to problematic inputs. This system catches and rejects impossible inputs, such as a fuel cell larger than what the rocket's frame can physically hold. It also catches physically possible but dangerous or inefficient inputs, such as a tank with ullage under 10% (risks exploding) or over 30% (make the tank smaller).  

<!---sloppy, rewrite: --->
The Unsteady model expects certain variables to stay within pre-tested operating ranges to ensure simulation fidelity. It tracks these parameters during runtime and highlights any irregularities in the results. The table below shows what the range is for all such variables: 

| Quantity | Trustworthy range | What happens outside it |
|---|---|---|
| O/F ratio | 1 to 12, best between 5.5 and 8.5 | The CEA combustion table clamps O/F numbers to the nearest entry available. |
| Chamber pressure | 1 to 100 bar | Same |
| Tank temperature | Below 300 K | N<sub>2</sub>O's critical point is 309.5 K. Above roughly 300 K the saturated-equilibrium tank model degrades, and at the critical point it fails outright |
| Flight Mach number | Away from 0.8 to 1.2 | A fixed drag coefficient is least defensible through the transonic region |
| Fuel grain length | Above 20 in | The 1D regression model loses accuracy at low length-to-diameter ratios |

When reading the results, warnings can appear in one of three severity categories: 
* **Advisory** warnings are worth knowing about but either not a physics problem, or unavoidable due to Unsteady's physics formulation. High ullage fraction; an unusually low c* efficiency; a tank warm enough to be worth watching.
* **Caution** indicates the config is outside the range where the model is trustworthy, or is physically questionable. A short fuel grain; a very tight port; ullage under 10%. 
* **Critical** warnings mean the simulation will almost certainly fail or show nonsense values. Fuel cell wider than the airframe's outer diameter; c* efficiency above 100%. This will not prevent the simulation attempting to run but is nevertheless an indicator that the config should be revised. 

---

## 8. Program limitations

Steady is wildly innacurate when it comes to predicting the burn characteristics and flight path of a single rocket. Total impulse and apogee values are 10-25% higher than in real life. But it is useful for comparing different configurations and for finding a design point for more thorough testing in Unsteady. 

Unsteady aims for higher accuracy, so knowing its precise limitations is more valuable. Below is a non-comprehensive list: 
* **Not calibrated.** The program's default fuel density, regression constant, regression exponent, and C* efficiency are for a generic paraffin and N<sub>2</sub>O hybrid. Comparing between designs is reliable, but absolute numbers are no guarantee. 
* **Quasi-steady combustion.** Chemistry is assumed to reach equilibrium instantly at the current pressure and O/F. No consideration of chugging, acoustic instability, or hard starts.
* **Uniformly regressing fuel grain.** One circular port opening radially at the same rate along its whole length. Real grains develop non-uniform profiles, can slump, and paraffin in particular sheds liquid droplets that a 1D law only approximates.
* **Simple regression law.** The regression constant `a` and regression exponent `n` come from published paraffin and N<sub>2</sub>O data. They are the single largest source of error in the program.
* **Point mass trajectory.** Constant drag coefficient. No angle of attack, wind, fin effects, Mach drag rise, or stability considerations. 
* **No heat transfer through rocket body.** The rocket frame does not heat up, absorb energy, or deform. 
* **Parachutes deploy instantly and perfectly.** Drogue at apogee, main at the altitude you specify, both fully inflated the moment they appear. No deployment transient, no failure modes, no reefing.


