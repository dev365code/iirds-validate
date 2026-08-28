# iirds-validate

The iiRDS checker now ships as [`iirds`](https://pypi.org/project/iirds/) —
install that. This name is kept so that `pip install iirds-validate` keeps
working: it installs nothing of its own and depends on `iirds`, which carries
the checker, the `iirds`, `iirds-validate` and `iirdsv` commands, and the
read/write library. Tools that install by executable, such as pipx and
`uv tool`, want the name that has one: `iirds`.

**Upgrading from 0.4.x:** uninstall first, then install the new name with
`-U` — without it, the `iirds` library already present satisfies the request
and nothing new is installed.

    pip uninstall -y iirds-validate
    pip install -U iirds

The order matters: pip records each distribution's files separately and does
not notice when two records claim one path, so installing the new name first
and uninstalling the old one afterwards deletes files the new one had just
written. If that has already happened, `pip install --force-reinstall
--no-deps iirds` restores them.

Both names are held in stewardship for the iiRDS ecosystem and will be
transferred to the iiRDS Consortium on request.
