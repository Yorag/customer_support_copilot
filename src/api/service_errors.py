from __future__ import annotations


class DuplicateRequestError(Exception):
    def __init__(self, key: str) -> None:
        super().__init__(f"Duplicate request for idempotency key `{key}`.")
        self.key = key


class TicketNotFoundError(Exception):
    def __init__(self, ticket_id: str) -> None:
        super().__init__(f"Ticket `{ticket_id}` does not exist.")
        self.ticket_id = ticket_id


class CustomerNotFoundError(Exception):
    def __init__(self, customer_id: str) -> None:
        super().__init__(f"Customer `{customer_id}` does not exist.")
        self.customer_id = customer_id


class RunNotFoundError(Exception):
    def __init__(self, *, ticket_id: str, run_id: str) -> None:
        super().__init__(f"Run `{run_id}` does not exist for ticket `{ticket_id}`.")
        self.ticket_id = ticket_id
        self.run_id = run_id


class RunExecutionFailedError(Exception):
    def __init__(self, *, ticket_id: str, run_id: str) -> None:
        super().__init__(f"Run `{run_id}` failed for ticket `{ticket_id}`.")
        self.ticket_id = ticket_id
        self.run_id = run_id
