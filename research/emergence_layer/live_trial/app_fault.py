"""Application-level response loss after a completed GitHub call.

This wraps the unchanged real GitHub client (`enforcing_dispatcher.GitHubAPI`).
It forwards every request to it, so the branch update really happens on GitHub.
For the one selected write it then discards the response the client returned and
raises the same unknown-outcome error the client raises on a transport failure,
before the dispatcher sees the response.

What this models: the server completed the operation and answered, but the
answer never reached the dispatcher. What it does NOT model: a transport
interruption (connection reset, timeout, truncated body) during the call
itself. Transport-level fault injection remains an open validation item; see
LIVE_TRIAL.md. The dispatcher code under test is unchanged; only this wrapper,
used by the trial runner, differs from production.
"""

UNKNOWN = 'provider_outcome_unknown'


class ResponseLostAfterCall:
    """Forward to the real client; drop the response of the first matching write.

    `match(method, path)` selects which call loses its response (default: the
    first PATCH, i.e. the branch ref update). `events` records what happened,
    with no request or response bodies.
    """

    def __init__(self, real_client, match=None):
        self._client = real_client
        self._match = match or (lambda method, path: method == 'PATCH')
        self._armed = True
        self.events = []

    def request(self, method, path, body=None):
        # The real network call. A genuine failure here raises before we record a loss.
        response = self._client.request(method, path, body)
        if self._armed and self._match(method, path):
            self._armed = False
            self.events.append({'method': method, 'path': path, 'response_discarded': True})
            # Same error type and message the real client raises on a failed call,
            # so the dispatcher cannot tell this from a genuine lost response.
            raise RuntimeError(UNKNOWN)
        self.events.append({'method': method, 'path': path, 'response_discarded': False})
        return response
