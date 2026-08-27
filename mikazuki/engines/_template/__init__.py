"""Sample engine pack template.

Copy this whole directory to ``mikazuki/engines/<id>/`` when onboarding a new
engine, then follow ``mikazuki/engines/ADAPTATION_GUIDE.md`` step by step.
The registry skips directories starting with ``_``, so this template is never
mounted as a real engine.

Every stub file lists its 职责 (role), 输入输出 (I/O) and 完成判据 (done
criteria) in its module docstring. Delete what your engine does not need;
deviations are normal — the framework only fixes the mount points:

- ``manifest.py``  (required) — the pack's ID card, validated at scan time.
- ``run.py``       (required for training) — ``handle_run(config, ctx)``.
- ``routes.py``    (required for plugin engines) — status/preflight/install...
"""
