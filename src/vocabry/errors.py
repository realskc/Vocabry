from __future__ import annotations


class VocabryError(Exception):
    code = "vocabry_error"
    status_code = 400

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(VocabryError):
    code = "not_found"
    status_code = 404


class RevisionConflictError(VocabryError):
    code = "revision_conflict"
    status_code = 409


class DuplicateJobError(VocabryError):
    code = "duplicate_job"
    status_code = 409


class IdempotencyConflictError(VocabryError):
    code = "idempotency_conflict"
    status_code = 409


class ValidationError(VocabryError):
    code = "validation_error"
    status_code = 422
