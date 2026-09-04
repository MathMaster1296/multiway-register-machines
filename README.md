# Multiway Register Machines

An open-source, Mathematica-free implementation of multiway register machine
evolution, with a browser explorer, exact analysis tools, and reproducible
figures. Companion code for my article
["State Evolution in Multiway Register Machines Featuring Applications to
Recursive Functions"](https://community.wolfram.com/groups/-/m/t/3499350) and the Wolfram
Function Repository resource
[MultiwayRegisterMachine](https://resources.wolframcloud.com/FunctionRepository/resources/MultiwayRegisterMachine/).

**Live explorer:**
[mathmaster1296.github.io/multiway-register-machines](https://mathmaster1296.github.io/multiway-register-machines/)

![The Fibonacci states graph revealing itself step by step](docs/figures/fibonacci-reveal.svg)

## What a multiway register machine is

A register machine holds non-negative integers in a few registers and runs a
program of increment and decrement instructions, where a decrement on an
empty register takes a separate fail branch. A multiway register machine
makes one change: an instruction may list several jump targets instead of
one. The machine no longer has a single next state, so evolution produces a
graph of every reachable configuration, where an ordinary machine would
produce one sequence.

Two views of that evolution matter. The tree keeps every computational path
separate, so it grows as fast as the paths multiply. The states graph merges
configurations that coincide, which can collapse an exponential tree into
something small while the number of distinct paths through it stays
exponential. The Fibonacci model below is the sharpest example: at k = 20
the states graph is a line of 20 nodes, and the number of paths through it
to the base cases is F(20) = 6765.

## Parity with the Wolfram original

The engine was ported from the published source of the WFR resource, and its
behavior is pinned by golden tests to the evaluated outputs recorded in the
resource's definition notebook and the research notebook: frontier lists to
depth 15, state graphs up to 71 nodes with identical node numbering and edge
order, complexity values to full double precision, the Collatz trajectory of
101, and the paper's Fibonacci and polynomial machines. Every place the
original left semantics implicit is written down in
[ASSUMPTIONS.md](ASSUMPTIONS.md), and
[docs/porting-notes.md](docs/porting-notes.md) maps each Wolfram function to
its Python equivalent.

## The models

Three models carry closed-form invariants that `mrm verify` checks against
the engine's own output:

* Grid paths walks from (0, 0) to (m, n) by unit steps right or up. The
  path count to the terminal must equal binomial(m + n, m), and the suite
  checks every m and n up to 8.
* Fibonacci recursion sends k to both k - 1 and k - 2, with base cases at
  1 and 2. The path count to the base cases must equal F(k), checked up to
  k = 20.
* Collatz comes in three flavors: the paper's multiway machine, which
  explores the 3n + 1 section and the halving section at every branch
  point; a deterministic variant whose parity test is written as modular
  guard rules; and a reverse machine that grows the Collatz tree upward
  from 1. The suite checks trajectories against the arithmetic map and the
  reverse tree against forward return.

The paper's own machines ship as presets too: the polynomial evaluator built
from `power`, `scalar`, and `add`, the Fibonacci adder, and the notebook's
halting, non-halting, and complete-graph examples.

## Install and use

```bash
pip install git+https://github.com/MathMaster1296/multiway-register-machines
```

```python
from mrm import Config, evolve, terminal_path_counts, absorption
from mrm.builders import grid_paths_machine

ev = evolve(grid_paths_machine(3, 3), Config(1, (0, 0)))
terminal_path_counts(ev)          # {16: 20}
absorption(ev).expected_steps     # Fraction(6, 1), exactly
```

The command line covers the common tasks:

```bash
mrm run fibonacci --analyze        # evolve a preset, with exact halting stats
mrm verify                         # all model invariants, nonzero exit on failure
mrm path collatz_forward --to "8|0,1" --max-steps 2000   # shortest rule path
mrm link grid_paths                # a URL that reopens this machine in the explorer
mrm ensemble --count 200 --out study   # random machines: complexity vs branching
mrm export ev.json --format dot    # DOT, GraphML, WL, or evolution JSON
mrm figure all --out figures       # regenerate every figure, byte-identical
```

The core package needs Python 3.10+ and nothing else: no NumPy, no graph
library, no Mathematica. The formal model, written for a referee, is in
[docs/semantics.md](docs/semantics.md).

## Beyond the original

Some analyses here go further than the WFR resource:

* `mrm.absorption` treats every applicable rule as equally probable, which
  turns the states graph into a Markov chain, then solves that chain in
  exact rational arithmetic: the probability of halting in each terminal,
  the probability of running forever, and the exact expected number of
  steps. The WFR probability plots are the transient face of the same
  chain, and `mrm.probability_table` reproduces those tables as exact
  fractions.
* Path counts respect rule multiplicity, and on cyclic graphs the affected
  nodes report an explicit infinite sentinel together with a concrete cycle
  witness, never a wrong number.
* `mrm.branchial_graph` connects same-layer states that share a parent, and
  `mrm.reconvergence` measures how often the two sides of a branch meet
  again, which is the property that decides whether state merging pays off.
* Figures come from a fixed-pass layered layout with no randomness, so the
  same evolution always renders to the same bytes.
* `mrm.causal_analysis` reads the data dependencies along a path: an event
  depends on the latest earlier event that wrote a register it reads. This
  separates the two reasons branches reconverge. Grid paths split into two
  independent chains, so merging happens because the updates commute;
  Fibonacci paths form one total chain, so merging is pure value collision.
* `mrm.absorption_time_distribution` gives the whole halting-time
  distribution exactly, step by step, and the explorer charts it. Its mean
  recovers the expected step count.
* `mrm link` prints a URL that reopens the explorer on exactly the machine
  and settings you name, using the same compressed encoding the site writes
  into its address bar. Links like these can sit in a paper.
* `mrm ensemble` samples seeded random machines and plots the paper's
  complexity measure against the branching their path trees actually
  realize.

## Files and formats

Machines serialize to a versioned JSON format
([docs/machine.schema.json](docs/machine.schema.json)); presets under
`src/mrm/presets/` are plain files in that format, so adding a model needs no
code. Evolutions serialize with their parameters, derived data, and a hash
of the machine that produced them
([docs/evolution.schema.json](docs/evolution.schema.json)).

## The explorer

The site under `web/` is static and framework-free. It does not reimplement
any mathematics in JavaScript: a Web Worker loads Pyodide, installs the same
`mrm` wheel that CI builds, and every run on the page goes through the exact
code in this repository, so the site and the paper cannot disagree. The
first visit downloads the Python runtime (a few megabytes, cached
afterwards); everything after that is local and works offline.

The page keeps the full machine and every evolution setting in the URL,
compressed, so any view can be cited by link and reproduced exactly. Step
playback reveals the evolution layer by layer, and selecting a state shows
its ancestors, its descendants, and the shortest path that reaches it. For
machines in instruction form the page also draws the program itself, the
same rule and circle diagrams the WFR resource plots. The current view
exports as SVG, PNG, or evolution JSON, and a copy-link button hands you
the reproduction URL. Graphs under 2000 nodes render as interactive SVG and
larger ones fall back to a canvas.

To work on it locally: `npm install && npm run build` inside `web/`, build a
wheel with `python -m build`, then `python scripts/build_site.py` and serve
`web/dist` with any static file server.

## License

MIT. See [LICENSE](LICENSE).
