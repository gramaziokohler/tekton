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
    pip install -e ./compas_timber_fea -e ./compas_dlubal -e ./compas_saf -e ./tekton_app


Development
===========

To install **Tekton** for development, install from local source with the "dev" requirements.

.. code-block:: bash

    git clone https://github.com/gramaziokohler/tekton.git
    cd tekton
    pip install -e ./compas_timber_fea -e ./compas_dlubal -e ./compas_saf -e ./tekton_app -r requirements-dev.txt
