********************************************************************************
Installation
********************************************************************************

Stable
======

Stable releases are available on PyPI and can be installed with pip.

.. code-block:: bash

    pip install tekton_app


Latest
======

The latest version can be installed from local source.

.. code-block:: bash

    git clone https://github.com/gramaziokohler/tekton.git
    cd tekton
    pip install -e ./packages/compas_timber_fea -e ./packages/compas_dlubal -e ./packages/compas_saf -e ./packages/tekton_app


Development
===========

To install **Tekton** for development, install from local source with the "dev" requirements.

.. code-block:: bash

    git clone https://github.com/gramaziokohler/tekton.git
    cd tekton
    pip install -e ./packages/compas_timber_fea -e ./packages/compas_dlubal -e ./packages/compas_saf -e ./packages/tekton_app -r requirements-dev.txt
