"""Project-level exceptions for VASP2Kinetics."""


class VASP2KineticsError(Exception):
    """Base exception for expected VASP2Kinetics failures."""


class ConfigurationError(VASP2KineticsError):
    """Raised when the application configuration is missing or invalid."""


class ResultWriteError(VASP2KineticsError):
    """Raised when a standardized parser result cannot be written."""


class KineticDataError(VASP2KineticsError):
    """Raised when kinetic input data are missing or structurally invalid."""


class ReactionDefinitionError(KineticDataError):
    """Raised when a human-provided reaction definition is invalid."""


class RegistryError(KineticDataError):
    """Raised when the kinetic dataset registry cannot be read or written."""


class CatkinasGenerationError(VASP2KineticsError):
    """Raised when the static CATKINAS adapter package cannot be generated."""


class ZacrosGenerationError(VASP2KineticsError):
    """Raised when the static Zacros adapter package cannot be generated."""


class RunnerError(VASP2KineticsError):
    """Raised when execution metadata or raw output cannot be persisted."""


class AnalysisError(VASP2KineticsError):
    """Raised when parsed simulation results cannot be persisted."""


class WorkflowError(VASP2KineticsError):
    """Raised when workflow state or one scheduled step cannot proceed."""


class LoggingError(VASP2KineticsError):
    """Raised when a configured phase log cannot be opened."""
