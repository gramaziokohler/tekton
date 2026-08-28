********************************************************************************
Installation
********************************************************************************

Tekton is not published on PyPI; it is installed from source. The repository is
a ``uv`` workspace, so a single command installs the pinned interpreter, all
four packages and their dependencies.

.. code-block:: bash

    git clone https://github.com/gramaziokohler/tekton.git
    cd tekton
    uv sync


Development
===========

Add the ``dev`` extra to get the test and lint tooling.

.. code-block:: bash

    uv sync --extra dev

Commands run through the workspace environment:

.. code-block:: bash

    uv run pytest
    uv run ruff check .
