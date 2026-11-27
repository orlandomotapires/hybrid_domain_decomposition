# Installation

The project is used from a clone of the repository on Linux (built on Ubuntu 26.04). Python 3.10 or newer works; the instructions use 3.14.

## Install

```sh
git clone https://github.com/orlandomotapires/hybrid_domain_decomposition.git
cd hybrid_domain_decomposition

conda create -n hdd python=3.14 -y
conda activate hdd
pip install -e ".[gui]"
```

`pip install -e` is an editable install: Python runs the code straight from the repository, so pulling new commits updates the app without reinstalling. Run `pip install -e ".[gui]"` again only when the dependencies change.

| Command | Installs |
| --- | --- |
| `pip install -e ".[gui]"` | The pipeline and the desktop app (PySide6, pyqtgraph) |
| `pip install -e ".[gui,dev]"` | Also the test tools (pytest, pytest-qt) |
| `pip install -r requirements.txt` | The pipeline only, for command-line use |

A plain `python -m venv` environment works the same way as a conda env.

## Application-menu launcher

```sh
packaging/linux/install-launcher.sh            # add HDD Studio to the application menu
packaging/linux/install-launcher.sh --remove   # remove it
```

The application menu does not activate conda envs or venvs, so the launcher records the Python that has the app's dependencies when you install it. Run it from inside your environment, and run it again if you move to another environment. Only `~/.local/share` is touched.

## Which Python `run.sh` uses

`run.sh` tries these in order and uses the first that can import what the command needs (PySide6 and pyqtgraph for the app):

1. `HDD_PYTHON` (set by the menu launcher)
2. the active conda env, `base` included
3. the active venv
4. `.venv/` next to `run.sh`
5. `python3` on `PATH`

If none has the dependencies, it says so and how to install them. `./run.sh --which-python` prints the one it would pick for the app.

## Uninstall

```sh
packaging/linux/install-launcher.sh --remove
pip uninstall hybrid-domain-decomposition
```

This removes the menu entry and the install record. The repository, your matrices and your simulations stay where they are.

## Troubleshooting

**`ModuleNotFoundError: No module named 'PySide6'` (or `matplotlib`).** The dependencies are installed in a different environment from the one running the app. Activate the environment you installed into, or install into the active one with `pip install -e ".[gui]"`. `./run.sh --which-python` shows which Python is being used.

**The menu entry does nothing.** The launcher points at a Python that no longer has the dependencies (for example, an environment you deleted). Reinstall it from inside a working environment: `packaging/linux/install-launcher.sh`.

**The prompt shows two environments, like `(hdd) (base)`.** Only one is active. `(base)` comes from conda activating `base` in every new terminal; `(hdd)` was activated by another tool (often VS Code's Python extension), which leaves conda's label in place. `echo $CONDA_DEFAULT_ENV` shows the active one. To stop the double label, run `conda config --set auto_activate_base false`, or turn off VS Code's *Python › Terminal: Activate Environment* setting.

**A simulation fails with "Unable to coarsen graph into the requested node-count range".** Its coarsening limits cannot be reached on its matrix. The simulation's page in the app warns about this before you run it; change the limits on its **Coarsening** page. See [Simulations](simulations.md).
