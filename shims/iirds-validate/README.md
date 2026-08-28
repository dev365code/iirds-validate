# iirds-validate

The iiRDS checker now ships as [`iirds`](https://pypi.org/project/iirds/) —
install that. This name is kept so that `pip install iirds-validate` keeps
working: it installs nothing of its own and depends on `iirds`, which carries
the checker, the `iirds`, `iirds-validate` and `iirdsv` commands, and the
read/write library.

**Upgrading from 0.4.x:** uninstall first, then install the new name.

    pip uninstall -y iirds-validate
    pip install iirds

Two distributions used to own the `iirds_validate` package, and pip does not
track which files belong to which name: upgrading in place can leave the old
name's uninstall deleting files the new one had just written. If that has
already happened, `pip install --force-reinstall --no-deps iirds` restores
them.

Both names are held in stewardship for the iiRDS ecosystem and will be
transferred to the iiRDS Consortium on request.
