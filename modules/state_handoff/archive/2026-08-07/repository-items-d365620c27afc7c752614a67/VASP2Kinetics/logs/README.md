# Runtime logs

Log files are created only when the corresponding action runs. Their paths are
configured under `logging.file` and `logging.phase_files`:

- `parser.log`
- `simulation.log`
- `workflow.log`

Generated `.log` files are ignored by version control. Logs report execution
events and errors; they are not scientific result files.
